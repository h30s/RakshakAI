"""DecisionEngine: runs the decision layer live next to the detection pipeline.

Wiring (see app/server.py): after the journey tracker has labelled people in a detection pass,
the server calls engine.observe(t, group). A background thread (engine.run) evaluates tracks
still in view every quarter second (so a fence crossing or a loiterer alerts while it happens),
closes finished movements, scores them against this post's baseline, applies the alert budget,
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
* Latency: for every alert, capture-of-the-triggering-frame -> alert sealed (server), -> shown on
  the console (console), -> SMS accepted by the modem (sms), -> first operator tap (ack, OAT-3),
  appended to DATA_DIR/latency.csv.
* After a restart, alerts, operator statuses and this shift's budget are restored from the ledger.
"""
import csv
import datetime as dt
import json
import logging
import threading
import time
from collections import deque
from pathlib import Path

from .baseline import Baseline
from .budget import ALERT, DIGEST, AlertBudget, WatchOrder, shift_of
from .calendar import SEAL, PostCalendar
from .events import Movement, TrackAccumulator
from .ledger import Ledger, certificate_part_a, evidence_packet, load_or_create_key, sms_alert
from .sync import Forwarder, http_transport

log = logging.getLogger(__name__)

CSV_FIELDS = ["camera", "t_start", "t_end", "entry", "exit", "speed", "dwell", "group", "low", "crossed",
              "restricted", "zone_dwell", "person", "day_type", "score", "decision", "reason"]
REASON_CODES = {"off usual path": "OFFPATH", "unusual hour": "HOUR", "unusual speed": "SPEED",
                "unusual dwell": "DWELL", "low posture / crawl": "CRAWL", "group": "GROUP",
                "loiter in restricted zone": "LOITER"}
EXTERNAL_CODES = {"watchlist": "WATCH", "anpr": "ANPR", "frs": "FRS"}
TICK_S = 0.25


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
                restricted=r["restricted"] in ("1", "True", "true"),
                zone_dwell=float(r.get("zone_dwell") or 0), person=r.get("person", "")))
    return out


def percentiles(values):
    v = sorted(values)
    if not v:
        return {"n": 0, "p50": None, "p95": None}
    return {"n": len(v), "p50": round(v[len(v) // 2], 2), "p95": round(v[min(len(v) - 1, int(0.95 * len(v)))], 2)}


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
        self.latency_csv = self.data_dir / "latency.csv"
        self.ledger = Ledger(self.data_dir / "ledger" / "ledger.jsonl",
                             load_or_create_key(self.data_dir / "keys" / "ledger_ed25519.pem"),
                             clip_dir=self.data_dir / "evidence")
        self.forwarder = (Forwarder(self.ledger, self.post, http_transport(self.cfg["hq_url"]))
                          if self.cfg.get("hq_url") else None)
        self.notifiers = []  # callables(alert dict) - SMS / voice / siren dispatch (app/decision/comms.py)
        self.baseline = Baseline()
        self.borrowed, self.days_learned = False, 0
        self.alerts, self.digest_count = [], 0
        self.digest = deque(maxlen=300)  # recent movements that went to the digest, for review
        self.latency = {k: deque(maxlen=5000) for k in ("server", "console", "sms", "ack")}
        self.version = 0  # bumps on every change the console shows (pushed over /ws/decision)
        self._next_id = 1
        self._day = None
        self._anchored_until = None
        self.lock = threading.Lock()
        self._restore()
        self.relearn()

    # ------------------------------------------------------------- restart
    def _restore(self):
        """Rebuild alerts, operator statuses and the budget used per shift from the sealed ledger,
        so a restart neither forgets alerts, nor reuses alert ids, nor resets the shift budget."""
        status = {}
        for e in self.ledger.entries:
            if e["kind"] == "action":
                status[e["data"]["alert"]] = e["data"]["status"]
        for e in self.ledger.entries:
            if e["kind"] != "alert":
                continue
            d = e["data"]
            self._next_id = max(self._next_id, int(d["alert"].split("-")[1]) + 1)
            self.budget.used[shift_of(e["t"])] += 1
            acted = d["alert"] in status  # an acknowledgement before the restart is not timed again
            self.alerts.append(self._card(e, d, status.get(d["alert"], "new"), latency={"ack": None} if acted else None))
        self.alerts = self.alerts[-500:]

    def _card(self, entry, d, status="new", latency=None):
        terms = sorted(d.get("terms", {}).items(), key=lambda kv: -kv[1])
        code = d.get("code") or (REASON_CODES.get(terms[0][0], "ALERT") if terms and terms[0][1] > 0 else "FENCE")
        return {
            "id": d["alert"], "t": entry["t"], "t_event": d.get("t_event", entry["t"]),
            "camera": d["camera"], "camera_name": self.names.get(d["camera"], d["camera"]),
            "person": d.get("person", ""), "score": d.get("score", 0.0), "reason": d["reason"],
            "day_type": d.get("day_type", ""), "source": d.get("source", "rakshak"),
            "terms": [{"term": k, "value": v} for k, v in terms if v > 0],
            "ledger_seq": entry["seq"], "clip_sha256": entry["clip_sha256"],
            "sms": sms_alert(self.ledger.key, self.post[:8], d["camera"][:10], entry["t"], code, entry["hash"]),
            "status": status, "latency": latency or {},
        }

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
        self.version += 1
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

    def start_feeds(self):
        """Start what post.json configures: SMS / voice / siren ("comms") and MQTT ("mqtt").
        A missing device is logged, never fatal: the console and the ledger keep working."""
        comms = self.cfg.get("comms") or {}
        if comms.get("modem") and comms.get("duty_phones"):
            from .comms import Dispatcher
            try:
                self.dispatcher = Dispatcher.from_config(self, comms)
                self.notifiers.append(self.dispatcher.notify)
                self.dispatcher.start()
            except Exception:
                log.exception("GSM modem %s not available; alerts will not be sent by SMS", comms["modem"])
        mqtt = self.cfg.get("mqtt") or {}
        if mqtt.get("host"):
            from .c2 import MqttFeed
            try:
                self.ledger.listeners.append(MqttFeed.connect(self.post, mqtt))
            except Exception:
                log.exception("MQTT broker %s not available", mqtt["host"])

    def run(self):
        self.start_feeds()
        if self.forwarder:
            self.forwarder.start()
        while True:
            try:
                self.tick(time.time())
            except Exception:
                log.exception("Decision layer failed")
            time.sleep(TICK_S)

    def tick(self, now):
        today = dt.date.fromtimestamp(now)
        if self._day and today != self._day:
            self.relearn(now)
            self.apply_retention(now)
        self._day = today
        for key, m in self.acc.partials(now):
            self.consider_live(key, m, now)
        self.acc.flush(now)
        for m in self.acc.pop_finished():
            self.process(m, now)
        hour_start = now - now % 3600
        if self._anchored_until is None:
            self._anchored_until = hour_start
        elif hour_start > self._anchored_until:
            self.ledger.anchor(self._anchored_until, hour_start)
            self._anchored_until = hour_start

    def _score(self, m, day_type):
        return self.baseline.score(m, day_type) if self.budget.threshold is not None else (0.0, {})

    def consider_live(self, key, m, now):
        """A track still in view: decide it now if it already meets an alert condition."""
        day_type = self.calendar.day_type(m.t_start)
        sealed = day_type == SEAL
        score, terms = self._score(m, day_type)
        if self.budget.threshold is None:
            trigger = m.crossed or self.budget.always_alert(m, sealed)
        else:
            trigger = self.budget.always_alert(m, sealed) or score >= self.budget._threshold_for(m.camera, m.t_start)
        if not trigger:
            return None
        decision, reason = self.budget.decide(m, score, sealed=sealed)
        alert_id = None
        if decision == ALERT:
            alert_id = self._alert(m, score, terms, reason, day_type, t_event=m.t_end, now=now)
        self.acc.mark(key, (decision, reason, alert_id))
        return decision

    def process(self, m, now=None):
        """A finished movement: log it; decide it unless it was already decided while in view."""
        now = time.time() if now is None else now
        day_type = self.calendar.day_type(m.t_start)
        score, terms = self._score(m, day_type)
        decided = getattr(m, "decided", None)
        if decided:
            decision, reason, _ = decided
        else:
            decision, reason = self.budget.decide(m, score, sealed=day_type == SEAL)
            if decision == ALERT:
                self._alert(m, score, terms, reason, day_type, t_event=m.t_end, now=now)
        if decision == DIGEST:
            with self.lock:
                self.digest_count += 1
                self.digest.append({"t": m.t_start, "camera": m.camera, "camera_name": self.names.get(m.camera, m.camera),
                                    "path": m.path, "score": score, "reason": reason, "crossed": m.crossed,
                                    "shift": list(map(str, shift_of(m.t_start)))})
                self.version += 1
        self._log(m, day_type, score, decision, reason)
        return decision

    def _alert(self, m, score, terms, reason, day_type, t_event, now, source="rakshak", code=None, extra=None):
        tick_started = time.time()
        with self.lock:
            alert_id = f"A-{self._next_id:04d}"
            self._next_id += 1
        clip = None
        if self.snapshot:
            jpeg = self.snapshot(m.camera)
            if jpeg:
                clip = self.data_dir / "evidence" / f"{alert_id}.jpg"
                clip.parent.mkdir(parents=True, exist_ok=True)
                clip.write_bytes(jpeg)
        data = {"alert": alert_id, "camera": m.camera, "person": m.person, "path": m.path, "score": score,
                "reason": reason, "terms": terms, "day_type": day_type, "group": m.group,
                "t_event": round(t_event, 3), "source": source, **({"code": code} if code else {}), **(extra or {})}
        entry = self.ledger.append("alert", data, clip=clip, t=m.t_start)
        # `now` is the wall clock when this tick started; add the time spent since (scoring, clip,
        # sealing), so live this is exactly sealed-time minus capture-time of the triggering frame.
        server_latency = max(0.0, now - t_event) + max(0.0, time.time() - tick_started)
        card = self._card(entry, data, latency={"server": round(server_latency, 3)})
        with self.lock:
            self.alerts.append(card)
            self.alerts = self.alerts[-500:]
            self.version += 1
        self._record_latency("server", alert_id, server_latency)
        for notify in self.notifiers:
            try:
                notify(card)
            except Exception:
                log.exception("Alert notifier failed")
        return alert_id

    def _log(self, m, day_type, score, decision, reason):
        new = not self.movements_csv.exists()
        self.movements_csv.parent.mkdir(parents=True, exist_ok=True)
        with open(self.movements_csv, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
            if new:
                w.writeheader()
            w.writerow({**m.row(), "day_type": day_type, "score": score, "decision": decision, "reason": reason})

    # ------------------------------------------------------------- latency
    def _record_latency(self, kind, alert_id, seconds):
        self.latency[kind].append(seconds)
        new = not self.latency_csv.exists()
        self.latency_csv.parent.mkdir(parents=True, exist_ok=True)
        with open(self.latency_csv, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["kind", "alert", "seconds", "at"])
            w.writerow([kind, alert_id, round(seconds, 3), round(time.time(), 3)])

    def delivered(self, alert_id, kind, now=None):
        """Record that an alert reached the console or was accepted by the SMS modem (first time only)."""
        now = time.time() if now is None else now
        with self.lock:
            a = next((a for a in self.alerts if a["id"] == alert_id), None)
            if a is None or kind in a["latency"]:
                return a
            a["latency"][kind] = round(max(0.0, now - a["t_event"]), 3)
        self._record_latency(kind, alert_id, a["latency"][kind])
        return a

    def latency_stats(self):
        return {kind: percentiles(v) for kind, v in self.latency.items()}

    # ------------------------------------------------------------- operator actions
    def set_status(self, alert_id, status):
        with self.lock:
            a = next((a for a in self.alerts if a["id"] == alert_id), None)
            if a is None:
                return None
            a["status"] = status
            self.version += 1
        self.ledger.append("action", {"alert": alert_id, "status": status})
        self.delivered(alert_id, "ack")  # first tap only: time to acknowledge (OAT-3)
        return a

    def external_hit(self, source, camera, label, confidence=None, t=None):
        """A hit from SSB's existing FRS / ANPR (or another system) joins the ranked queue as an
        always-alert: sealed, numbered and sent like any other alert."""
        now = time.time()
        t = now if t is None else t
        m = Movement(camera=camera, t_start=t, t_end=t, entry="ext", exit="ext", person=label)
        reason = f"{source.upper()} hit: {label}" + (f" ({confidence:.0%})" if confidence is not None else "")
        shift = shift_of(t)
        self.budget.used[shift] += 1  # counted, never capped
        alert_id = self._alert(m, 0.0, {}, reason, self.calendar.day_type(t), t_event=t, now=now,
                               source=source, code=EXTERNAL_CODES.get(source.lower(), "EXT"),
                               extra={"label": label, "confidence": confidence})
        return next(a for a in self.alerts if a["id"] == alert_id)

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
        self.version += 1
        return order

    def set_surge(self, mode):
        self.budget.surge.manual = {"on": True, "off": False}.get(mode)
        self.ledger.append("surge_mode", {"mode": mode})
        self.version += 1

    def _find(self, alert_id):
        return next((a for a in self.alerts if a["id"] == alert_id), None)

    def certificate(self, alert_id):
        a = self._find(alert_id)
        if a is None:
            return None
        return certificate_part_a(self.ledger.entries[a["ledger_seq"]], self.post, "Rakshak AI edge box")

    def packet(self, alert_id):
        """Evidence packet (ZIP bytes) for an alert: clip, sealed entry, chain, anchor proof, Part A."""
        a = self._find(alert_id)
        if a is None:
            return None
        return evidence_packet(self.ledger, a["ledger_seq"], self.certificate(alert_id))

    # ------------------------------------------------------------- shift report
    def shift_report(self, when=None):
        """Everything the post commander signs at handover, for the shift containing `when`."""
        when = time.time() if when is None else when
        shift = shift_of(when)
        start = dt.datetime.combine(shift[0], dt.time(6)) + dt.timedelta(hours=8 * shift[1])
        with self.lock:
            alerts = [a for a in self.alerts if shift_of(a["t"]) == shift]
            digest = [d for d in self.digest if d["shift"] == list(map(str, shift))]
        actions = [e for e in self.ledger.entries if e["kind"] in ("action", "watch_order", "surge_mode")
                   and shift_of(e["t"]) == shift]
        return {"post": self.post, "shift": {"date": str(shift[0]), "number": shift[1] + 1,
                                             "from": start.isoformat(timespec="minutes"),
                                             "to": (start + dt.timedelta(hours=8)).isoformat(timespec="minutes")},
                "day_type": self.calendar.day_type(start.timestamp() + 4 * 3600), "mode": self.mode,
                "per_shift": self.budget.per_shift, "alerts": alerts, "digest": digest,
                "digest_count": len(digest), "actions": actions,
                "ledger": {"entries": len(self.ledger.entries), "head": self.ledger.head,
                           "intact": not self.ledger.verify()},
                "latency": self.latency_stats()}

    def overview(self):
        now = time.time()
        shift = shift_of(now)
        with self.lock:
            alerts = list(reversed(self.alerts[-50:]))
            digest = sorted((d for d in self.digest if d["shift"] == list(map(str, shift))),
                            key=lambda d: -d["score"])[:20]
        return {
            "version": self.version, "post": self.post,
            "mode": self.mode, "days_learned": self.days_learned, "min_days": self.min_days,
            "drift": self.drift(now),
            "threshold": self.budget.threshold, "per_shift": self.budget.per_shift,
            "used_this_shift": self.budget.used.get(shift, 0),
            "surge": {"active": self.budget.surge.active, "manual": self.budget.surge.manual,
                      "reason": self.budget.surge.reason(now) if self.budget.surge.active else None},
            "watch_orders": [{"camera": w.camera, "until": w.until, "reason": w.reason}
                             for w in self.budget.watch_orders if w.until > now],
            "day_type": self.calendar.day_type(now), "digest_count": self.digest_count, "digest": digest,
            "ledger": {"entries": len(self.ledger.entries), "head": self.ledger.head},
            "hq": self.forwarder.status if self.forwarder else None,
            "latency": self.latency_stats(),
            "alerts": alerts,
        }
