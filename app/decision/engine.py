"""DecisionEngine: runs the decision layer live next to the detection pipeline.

Wiring (see app/server.py): after the journey tracker has labelled people in a detection pass,
the server calls engine.observe(t, group). A background thread (engine.run) closes finished
movements every second, scores them against this post's baseline, applies the alert budget,
seals alerts in the ledger and appends every movement to DATA_DIR/movements.csv - the same file
`python -m benchmark` reads, so live results and benchmark results use one format.

Post settings live in DATA_DIR/post.json (copy config/post.example.json).

* Days 1-14 (`learning_days`): if post.json names a similar post's movements file
  (`borrow_baseline`), the engine scores against that post's pooled baseline ("borrowed" mode);
  otherwise it alerts on fence crossings ("learning" mode). Either way the shift budget applies.
* From then on: this post's own baseline, refit every night on the last `baseline_days` (28).
* Drift watch: operator taps (acknowledge / escalate = actionable, dismiss = not) give a weekly
  precision; below 50% the console asks for a re-baseline.
* Retention: evidence clips of alerts that were not escalated are deleted after 30 days (the
  deletion is sealed in the ledger); movement logs are kept 180 days.
"""
import csv
import datetime as dt
import itertools
import json
import logging
import threading
import time
from pathlib import Path

from .baseline import Baseline
from .budget import ALERT, AlertBudget, WatchOrder, shift_of
from .calendar import SEAL, PostCalendar
from .events import Movement, TrackAccumulator
from .ledger import Ledger, certificate_part_a, evidence_packet, load_or_create_key, sms_alert
from .sync import Forwarder, http_transport

log = logging.getLogger(__name__)

CSV_FIELDS = ["camera", "t_start", "t_end", "entry", "exit", "speed", "dwell", "group", "low", "crossed",
              "restricted", "person", "day_type", "score", "decision", "reason"]
REASON_CODES = {"off usual path": "OFFPATH", "unusual hour": "HOUR", "unusual speed": "SPEED",
                "unusual dwell": "DWELL", "low posture / crawl": "CRAWL", "group": "GROUP"}


def load_movements(path):
    """Movements (and their day types) from a movements CSV."""
    out = []
    path = Path(path)
    if not path.exists():
        return out
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out.append(Movement(
                camera=r["camera"], t_start=float(r["t_start"]), t_end=float(r["t_end"]), entry=r["entry"],
                exit=r["exit"], speed=float(r["speed"]), dwell=float(r["dwell"]), group=int(float(r["group"])),
                low=float(r["low"]), crossed=r["crossed"] in ("1", "True", "true"),
                restricted=r["restricted"] in ("1", "True", "true"), person=r.get("person", "")))
    return out


class DecisionEngine(threading.Thread):
    def __init__(self, data_dir, camera_names, snapshot=None, min_days=None):
        super().__init__(daemon=True, name="decision")
        self.data_dir = Path(data_dir)
        self.names = camera_names
        self.snapshot = snapshot  # snapshot(camera id) -> JPEG bytes or None
        cfg_path = self.data_dir / "post.json"
        self.cfg = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
        self.min_days = min_days if min_days is not None else self.cfg.get("learning_days", 14)
        self.baseline_days = self.cfg.get("baseline_days", 28)
        retention = self.cfg.get("retention", {})
        self.clip_days, self.log_days = retention.get("clip_days", 30), retention.get("log_days", 180)
        self.post = self.cfg.get("post_id", "BOP")
        self.calendar = PostCalendar.from_dict(self.cfg.get("calendar", {}))
        self.acc = TrackAccumulator(
            fences={c: [tuple(l) for l in v] for c, v in self.cfg.get("fences", {}).items()},
            restricted={c: [tuple(r) for r in v] for c, v in self.cfg.get("restricted_zones", {}).items()})
        self.budget = AlertBudget(per_shift=self.cfg.get("alerts_per_shift", 12))
        self.budget.watchlist = set(self.cfg.get("watchlist", []))
        self.movements_csv = self.data_dir / "movements.csv"
        self.ledger = Ledger(self.data_dir / "ledger" / "ledger.jsonl",
                             load_or_create_key(self.data_dir / "keys" / "ledger_ed25519.pem"),
                             clip_dir=self.data_dir / "evidence")
        self.forwarder = (Forwarder(self.ledger, self.post, http_transport(self.cfg["hq_url"]))
                          if self.cfg.get("hq_url") else None)
        self.baseline = Baseline()
        self.borrowed, self.days_learned = False, 0
        self.alerts, self.digest_count = [], 0
        self._ids = itertools.count(1)
        self._day = None
        self._anchored_until = None
        self.lock = threading.Lock()
        self.relearn()

    # ------------------------------------------------------------- learning
    def relearn(self, now=None):
        """Rebuild the baseline from the last `baseline_days` of movements and recalibrate the
        budget (run nightly, and on request after a drift warning)."""
        now = time.time() if now is None else now
        history = [m for m in load_movements(self.movements_csv) if m.t_start >= now - self.baseline_days * 86400]
        own = Baseline()
        own.add_all(history, self.calendar.day_type)
        self.days_learned = own.days_seen
        self.budget.threshold, self.borrowed = None, False
        self.baseline = own
        if own.days_seen >= self.min_days:
            self._calibrate(own, history)
        elif self.cfg.get("borrow_baseline"):
            borrowed_path = self.data_dir / self.cfg["borrow_baseline"]
            other = load_movements(borrowed_path)
            if other:
                pooled = Baseline(pooled=True)
                pooled.add_all(other, self.calendar.day_type)
                self.baseline, self.borrowed = pooled, True
                self._calibrate(pooled, other)
            else:
                log.warning("borrow_baseline %s has no movements; staying in learning mode", borrowed_path)
        log.info("Decision layer: %s mode, %d movements over %d days learned; threshold %s",
                 self.mode, len(history), own.days_seen, self.budget.threshold)

    def _calibrate(self, baseline, history):
        scored = [(m.t_start, baseline.score(m, self.calendar.day_type(m.t_start))[0]) for m in history]
        self.budget.calibrate(scored)

    @property
    def mode(self):
        if self.budget.threshold is None:
            return "learning"
        return "borrowed" if self.borrowed else "ranked"

    # ------------------------------------------------------------- live loop
    def observe(self, t, group):
        self.acc.observe(t, group)

    def run(self):
        if self.forwarder:
            self.forwarder.start()
        while True:
            try:
                self.tick(time.time())
            except Exception:
                log.exception("Decision layer failed")
            time.sleep(1.0)

    def tick(self, now):
        today = dt.date.fromtimestamp(now)
        if self._day and today != self._day:
            self.relearn(now)
            self.apply_retention(now)
        self._day = today
        self.acc.flush(now)
        for m in self.acc.pop_finished():
            self.process(m)
        hour_start = now - now % 3600
        if self._anchored_until is None:
            self._anchored_until = hour_start
        elif hour_start > self._anchored_until:
            self.ledger.anchor(self._anchored_until, hour_start)
            self._anchored_until = hour_start

    def process(self, m):
        day_type = self.calendar.day_type(m.t_start)
        if self.budget.threshold is not None:
            score, terms = self.baseline.score(m, day_type)
        else:
            score, terms = 0.0, {}
        decision, reason = self.budget.decide(m, score, sealed=day_type == SEAL)
        with self.lock:
            if decision == ALERT:
                self._alert(m, score, terms, reason, day_type)
            else:
                self.digest_count += 1
        self._log(m, day_type, score, decision, reason)

    def _alert(self, m, score, terms, reason, day_type):
        alert_id = f"A-{next(self._ids):04d}"
        clip = None
        if self.snapshot:
            jpeg = self.snapshot(m.camera)
            if jpeg:
                clip = self.data_dir / "evidence" / f"{alert_id}.jpg"
                clip.parent.mkdir(parents=True, exist_ok=True)
                clip.write_bytes(jpeg)
        top = sorted(terms.items(), key=lambda kv: -kv[1])
        data = {"alert": alert_id, "camera": m.camera, "person": m.person, "path": m.path, "score": score,
                "reason": reason, "terms": terms, "day_type": day_type, "group": m.group}
        entry = self.ledger.append("alert", data, clip=clip, t=m.t_start)
        code = REASON_CODES.get(top[0][0], "ALERT") if top and top[0][1] > 0 else "FENCE"
        self.alerts.append({
            "id": alert_id, "t": m.t_start, "camera": m.camera, "camera_name": self.names.get(m.camera, m.camera),
            "person": m.person, "score": score, "reason": reason, "day_type": day_type,
            "terms": [{"term": k, "value": v} for k, v in top if v > 0],
            "ledger_seq": entry["seq"], "clip_sha256": entry["clip_sha256"],
            "sms": sms_alert(self.ledger.key, self.post[:8], m.camera[:10], m.t_start, code, entry["hash"]),
            "status": "new",
        })
        self.alerts = self.alerts[-500:]

    def _log(self, m, day_type, score, decision, reason):
        new = not self.movements_csv.exists()
        self.movements_csv.parent.mkdir(parents=True, exist_ok=True)
        with open(self.movements_csv, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
            if new:
                w.writeheader()
            w.writerow({**m.row(), "day_type": day_type, "score": score, "decision": decision, "reason": reason})

    # ------------------------------------------------------------- operator actions
    def set_status(self, alert_id, status):
        with self.lock:
            a = next((a for a in self.alerts if a["id"] == alert_id), None)
            if a is None:
                return None
            a["status"] = status
        self.ledger.append("action", {"alert": alert_id, "status": status})
        return a

    def drift(self, now=None, days=7, min_taps=10):
        """Precision over the last `days` from operator taps, read back from the sealed ledger."""
        now = time.time() if now is None else now
        latest = {}  # alert -> last status an operator set
        for e in self.ledger.entries:
            if e["kind"] == "action" and e["t"] >= now - days * 86400:
                latest[e["data"]["alert"]] = e["data"]["status"]
        taps = len(latest)
        useful = sum(1 for s in latest.values() if s in ("acknowledged", "escalated"))
        precision = useful / taps if taps else None
        return {"days": days, "taps": taps, "precision": None if precision is None else round(precision, 2),
                "rebaseline": precision is not None and taps >= min_taps and precision < 0.5}

    def apply_retention(self, now=None):
        """Delete clips of alerts that were not escalated after `clip_days`; prune movement logs
        older than `log_days`. Returns (clips deleted, movement rows pruned)."""
        now = time.time() if now is None else now
        escalated = {e["data"]["alert"] for e in self.ledger.entries
                     if e["kind"] == "action" and e["data"].get("status") == "escalated"}
        retired = {e["data"]["entry"] for e in self.ledger.entries if e["kind"] == "retention"}
        clips = 0
        for e in list(self.ledger.entries):
            if (e["kind"] == "alert" and e.get("clip") and e["seq"] not in retired
                    and e["data"].get("alert") not in escalated and e["t"] < now - self.clip_days * 86400):
                self.ledger.retire_clip(e["seq"], f"{self.clip_days}-day retention; alert not escalated")
                clips += 1
        rows = 0
        if self.movements_csv.exists():
            with open(self.movements_csv, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                fields, all_rows = reader.fieldnames, list(reader)
            keep = [r for r in all_rows if float(r["t_start"]) >= now - self.log_days * 86400]
            rows = len(all_rows) - len(keep)
            if rows:
                with open(self.movements_csv, "w", newline="", encoding="utf-8") as f:
                    w = csv.DictWriter(f, fieldnames=fields)
                    w.writeheader()
                    w.writerows(keep)
        if clips or rows:
            log.info("Retention: %d clips deleted, %d movement rows pruned", clips, rows)
        return clips, rows

    def watch_order(self, camera, minutes, reason=""):
        order = WatchOrder(camera, time.time() + minutes * 60, reason=reason)
        self.budget.add_watch_order(order)
        self.ledger.append("watch_order", {"camera": camera, "minutes": minutes, "reason": reason})
        return order

    def set_surge(self, mode):
        self.budget.surge.manual = {"on": True, "off": False}.get(mode)
        self.ledger.append("surge_mode", {"mode": mode})

    def certificate(self, alert_id):
        a = next((a for a in self.alerts if a["id"] == alert_id), None)
        if a is None:
            return None
        return certificate_part_a(self.ledger.entries[a["ledger_seq"]], self.post, "Rakshak AI edge box")

    def packet(self, alert_id):
        """Evidence packet (ZIP bytes) for an alert: clip, sealed entry, chain, anchor proof, Part A."""
        a = next((a for a in self.alerts if a["id"] == alert_id), None)
        if a is None:
            return None
        return evidence_packet(self.ledger, a["ledger_seq"], self.certificate(alert_id))

    def overview(self):
        now = time.time()
        shift = shift_of(now)
        with self.lock:
            alerts = list(reversed(self.alerts[-50:]))
        return {
            "mode": self.mode, "days_learned": self.days_learned, "min_days": self.min_days,
            "drift": self.drift(now),
            "threshold": self.budget.threshold, "per_shift": self.budget.per_shift,
            "used_this_shift": self.budget.used.get(shift, 0),
            "surge": {"active": self.budget.surge.active, "manual": self.budget.surge.manual,
                      "reason": self.budget.surge.reason(now) if self.budget.surge.active else None},
            "watch_orders": [{"camera": w.camera, "until": w.until, "reason": w.reason}
                             for w in self.budget.watch_orders if w.until > now],
            "day_type": self.calendar.day_type(now), "digest_count": self.digest_count,
            "ledger": {"entries": len(self.ledger.entries), "head": self.ledger.head},
            "hq": self.forwarder.status if self.forwarder else None,
            "alerts": alerts,
        }
