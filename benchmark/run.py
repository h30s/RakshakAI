"""Rakshak AI benchmark: every decision-layer number, recomputed from raw logs.

    python -m benchmark --all                 # evaluate benchmark/data/
    python -m benchmark --all --data PATH     # another folder
    python -m benchmark --review-sheet        # blind review sheet for the reviewers (see below)
    python -m benchmark --selftest            # synthetic data: checks the code runs, NOT results

Inputs (benchmark/data/, see README.md there):
    movements.csv  every movement the system logged on your footage (DATA_DIR/movements.csv)
    staged.csv     ground truth: the crossings your team staged (camera, start, end, staged_id)
    post.json      optional: the post's calendar and alert budget (same format as data/post.json)
    ratings.csv    optional: blind reviewer ratings of the review sheet (item, reviewer, actionable)

Parameters come from benchmark/prereg.json, committed BEFORE the evaluation run (pre-registration);
its hash and the git commit are written into the results.

Protocol (walk-forward, no peeking): for each day after the first `train_days`, the baseline and
the alert threshold are learned only from earlier days, then that day is replayed in time order.
Four stages are compared on the same movements (the ablation):

    1 line rule         every virtual-fence crossing alerts (a classic tripwire)
    2 + zone rules      a crossing alerts only if it enters a restricted zone or shows a behaviour
                        flag (crawl, group, running); always-alert rules apply
    3 + baseline        the movement is unusual for this camera, hour and day type (score above the
                        calibrated threshold); always-alert rules apply; no per-shift cap
    4 + budget          the full system: stage 3 plus the per-shift cap and surge mode

Results go to benchmark/results/latest.json and .md with the SHA-256 of every input file.
"""
import argparse
import csv
import datetime as dt
import hashlib
import json
import random
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))

from app.decision.baseline import Baseline  # noqa: E402
from app.decision.budget import ALERT, AlertBudget, shift_of  # noqa: E402
from app.decision.calendar import SEAL, PostCalendar  # noqa: E402
from app.decision.engine import load_movements  # noqa: E402
from app.decision.events import Movement  # noqa: E402
from app.decision.ledger import Ledger, sms_alert, verify_sms  # noqa: E402

SHIFTS_PER_DAY = 3
STAGES = ["line", "zones", "baseline", "full"]
STAGE_NAMES = {"line": "1 line rule", "zones": "2 + zone rules", "baseline": "3 + baseline", "full": "4 + budget"}
DEFAULTS = {"train_days": 7, "per_shift": None, "crawl_low": 0.5, "group_min": 3, "run_speed": 1.6,
            "review_line_sample": 60, "seed": 7}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest() if Path(path).exists() else None


def git_commit():
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT.parent, capture_output=True, text=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT.parent, capture_output=True, text=True).stdout
        return {"commit": head or None, "uncommitted_changes": bool(dirty.strip())}
    except OSError:
        return {"commit": None, "uncommitted_changes": None}


def _ts(value):
    try:
        return float(value)
    except ValueError:
        return dt.datetime.fromisoformat(value).timestamp()


def load_staged(path):
    if not Path(path).exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return [{"camera": r["camera"], "start": _ts(r["start"]), "end": _ts(r["end"]), "id": r["staged_id"]}
                for r in csv.DictReader(f)]


def label_staged(movements, staged):
    """Mark movements that overlap a staged crossing on the same camera."""
    for m in movements:
        for s in staged:
            if m.camera == s["camera"] and m.t_start <= s["end"] and m.t_end >= s["start"]:
                m.staged, m.staged_id = True, s["id"]
                break


def shift_start(day, index, shift_hours=8, first_shift_hour=6):
    return dt.datetime.combine(day, dt.time(first_shift_hour)) + dt.timedelta(hours=index * shift_hours)


# ---------------------------------------------------------------- walk-forward replay
def replay(movements, calendar, per_shift, train_days, params, surge=True):
    """One record per movement on evaluated days, with the decision of every ablation stage."""
    by_day = defaultdict(list)  # keyed by shift day (06:00 to 06:00), so a night shift is one budget
    for m in sorted(movements, key=lambda m: m.t_start):
        by_day[shift_of(m.t_start)[0]].append(m)
    days = sorted(by_day)
    out, eval_days, surges = [], [], 0
    for i, day in enumerate(days):
        if i < train_days:
            continue
        past = [m for d in days[:i] for m in by_day[d]]
        base = Baseline()
        base.add_all(past, calendar.day_type)
        budget = AlertBudget(per_shift=per_shift)
        budget.calibrate([(m.t_start, base.score(m, calendar.day_type(m.t_start))[0]) for m in past])
        if not surge:
            budget.surge.manual = False
        was_active = False
        for m in by_day[day]:
            dtype = calendar.day_type(m.t_start)
            sealed = dtype == SEAL
            score, _ = base.score(m, dtype)
            critical = budget.always_alert(m, sealed) is not None
            flagged = m.low >= params["crawl_low"] or m.group >= params["group_min"] or m.speed >= params["run_speed"]
            decision, reason = budget.decide(m, score, sealed=sealed)
            if budget.surge.active and not was_active:
                surges += 1
            was_active = budget.surge.active
            out.append({"m": m, "score": score, "day_type": dtype, "shift": shift_of(m.t_start), "reason": reason,
                        "line": m.crossed,
                        "zones": critical or (m.crossed and (m.restricted or flagged)),
                        "baseline": critical or score >= budget.threshold,
                        "full": decision == ALERT})
        eval_days.append(day)
    return out, eval_days, surges


def evaluate(movements, staged, calendar, per_shift, train_days, params):
    label_staged(movements, staged)
    results, days, surges = replay(movements, calendar, per_shift, train_days, params)
    if not days:
        raise SystemExit(f"Need more than {train_days} days of movements to evaluate (found "
                         f"{len({shift_of(m.t_start)[0] for m in movements})}).")
    shifts = len(days) * SHIFTS_PER_DAY
    eval_set = set(days)
    staged_eval = [s for s in staged if shift_of(s["start"])[0] in eval_set]
    logged_ids = {r["m"].staged_id for r in results if r["m"].staged}

    ablation = {}
    for stage in STAGES:
        alerts = [r for r in results if r[stage]]
        ablation[stage] = {
            "alerts_per_shift": round(len(alerts) / shifts, 1),
            "staged_alerted": len({r["m"].staged_id for r in alerts if r["m"].staged}),
            "lawful_flagged_per_shift": round(sum(1 for r in alerts if not r["m"].staged) / shifts, 1),
        }

    # Alerts per shift by kind of shift: the day type at mid-shift, and the night shift (22-06).
    groups = defaultdict(list)
    for day in days:
        for idx in range(SHIFTS_PER_DAY):
            mid = shift_start(day, idx) + dt.timedelta(hours=4)
            groups[calendar.day_type(mid.timestamp())].append((day, idx))
            if idx == SHIFTS_PER_DAY - 1:
                groups["night shift"].append((day, idx))
    by_shift = defaultdict(lambda: defaultdict(int))
    for r in results:
        for stage in STAGES:
            by_shift[r["shift"]][stage] += r[stage]
    breakdown = {g: {"shifts": len(keys), **{s: round(sum(by_shift[k][s] for k in keys) / len(keys), 1) for s in STAGES}}
                 for g, keys in sorted(groups.items())}

    return {
        "evaluated_days": len(days), "shifts": shifts, "movements": len(results),
        "first_day": str(days[0]), "last_day": str(days[-1]),
        "ablation": ablation, "by_shift_type": breakdown,
        "line_rule_alerts_per_shift": ablation["line"]["alerts_per_shift"],
        "rakshak_alerts_per_shift": ablation["full"]["alerts_per_shift"],
        "staged_total": len(staged_eval),
        "staged_logged": len(logged_ids),
        "staged_alerted": ablation["full"]["staged_alerted"],
        "staged_missed_by_detection": sorted(s["id"] for s in staged_eval if s["id"] not in logged_ids),
        "lawful_flagged_by_line_rule_per_shift": ablation["line"]["lawful_flagged_per_shift"],
        "lawful_flagged_by_rakshak_per_shift": ablation["full"]["lawful_flagged_per_shift"],
        "surge_activations_without_injection": surges,
    }, results


def surge_test(movements, calendar, per_shift, train_days, params, n=15, seed=7):
    """Inject n unusual crossings into one night (40 minutes from 02:00) of the last evaluated day
    and compare how many are alerted with surge mode on and off."""
    rng = random.Random(seed)
    days = sorted({shift_of(m.t_start)[0] for m in movements})
    if len(days) <= train_days:
        return None
    night = dt.datetime.combine(days[-1] + dt.timedelta(days=1), dt.time(2, 0)).timestamp()  # its night shift
    cams = sorted({m.camera for m in movements})
    injected = [Movement(camera=rng.choice(cams), t_start=night + k * 160, t_end=night + k * 160 + 30,
                         entry="r0c0", exit="r2c3", speed=1.2, dwell=30, group=3, low=0.6, crossed=True,
                         staged=True, staged_id=f"surge-{k}") for k in range(n)]
    out = {}
    for label, surge in (("surge_on", True), ("surge_off", False)):
        results, _, _ = replay(movements + injected, calendar, per_shift, train_days, params, surge=surge)
        out[label] = sum(1 for r in results if r["m"].staged_id.startswith("surge-") and r["full"])
    return {"injected": n, "alerted_with_surge": out["surge_on"], "alerted_without_surge": out["surge_off"]}


# ---------------------------------------------------------------- ledger
def ledger_test(entries=1000, clips=100, clip_kb=100):
    """Seal 10 clips, then try 5 kinds of tampering; each must be caught by verify(). Then time
    verify() on a larger ledger (default: 1,000 entries, 100 clips of 100 KB) after a one-byte edit."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    caught = {}
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        def fresh():
            for p in tmp.glob("*"):
                p.unlink()
            key = Ed25519PrivateKey.generate()
            led = Ledger(tmp / "ledger.jsonl", key, clip_dir=tmp)
            for i in range(10):
                clip = tmp / f"clip{i}.bin"
                clip.write_bytes(bytes(random.Random(i).randbytes(2048)))
                led.append("alert", {"n": i}, clip=clip, t=1_700_000_000 + i)
            assert not led.verify(), "fresh ledger must verify"
            return led, key

        led, key = fresh()
        p = tmp / "clip3.bin"
        p.write_bytes(p.read_bytes()[:-1] + b"\x00")
        caught["edited clip"] = bool(led.verify())
        led, key = fresh()
        (tmp / "clip5.bin").unlink()
        caught["deleted clip"] = bool(led.verify())
        led, key = fresh()
        entries_copy = [dict(e) for e in led.entries]
        entries_copy[4]["data"] = {"n": 99}
        caught["edited entry"] = bool(led.verify(entries=entries_copy))
        led, key = fresh()
        caught["deleted entry"] = bool(led.verify(entries=led.entries[:6] + led.entries[7:]))
        led, key = fresh()
        other = Ledger(tmp / "forged.jsonl", Ed25519PrivateKey.generate(), clip_dir=tmp)
        forged = [other.append(e["kind"], e["data"], t=e["t"]) for e in led.entries[:3]]
        caught["entries signed by another key"] = bool(led.verify(public_key=key.public_key(), entries=forged))
        msg = sms_alert(key, "BOP07", "cam-03", 1_700_000_000, "OFFPATH", led.head)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        big = Ledger(tmp / "ledger.jsonl", Ed25519PrivateKey.generate(), clip_dir=tmp)
        rng = random.Random(1)
        every = max(1, entries // clips)
        for i in range(entries):
            clip = None
            if i % every == 0:
                clip = tmp / f"c{i}.jpg"
                clip.write_bytes(rng.randbytes(clip_kb * 1024))
            big.append("alert", {"n": i}, clip=clip, t=1_700_000_000 + i)
        victim = tmp / f"c{every * (clips // 2)}.jpg"
        data = bytearray(victim.read_bytes())
        data[len(data) // 2] ^= 1
        victim.write_bytes(bytes(data))
        t0 = time.perf_counter()
        found = big.verify()
        seconds = time.perf_counter() - t0
    return {"caught": sum(caught.values()), "types": len(caught), "detail": caught,
            "sms_chars": len(msg), "sms_verifies": verify_sms(msg, key.public_key()), "sms_example": msg,
            "timing": {"entries": entries, "clips": clips, "clip_kb": clip_kb, "edit_found": bool(found),
                       "verify_seconds": round(seconds, 3)}}


# ---------------------------------------------------------------- blind review (actionable %)
def review_sheet(results, out_dir, n_line, seed):
    """Every alert of the full system plus a random sample of line-rule alerts, shuffled, with no
    hint of which system raised them. Reviewers get sheet.csv only; key.csv stays with the team."""
    rng = random.Random(seed)
    full = [r for r in results if r["full"]]
    line = [r for r in results if r["line"]]
    sample = rng.sample(line, min(n_line, len(line)))
    items = {id(r): r for r in full + sample}
    order = list(items.values())
    rng.shuffle(order)
    sample_ids = {id(r) for r in sample}
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "sheet.csv", "w", newline="", encoding="utf-8") as fs, \
            open(out_dir / "key.csv", "w", newline="", encoding="utf-8") as fk:
        sheet = csv.writer(fs)
        key = csv.writer(fk)
        sheet.writerow(["item", "camera", "start", "end", "actionable (1/0)", "notes"])
        key.writerow(["item", "rakshak_alert", "line_sample", "score", "day", "staged"])
        for n, r in enumerate(order, start=1):
            m = r["m"]
            item = f"R{n:03d}"
            sheet.writerow([item, m.camera, dt.datetime.fromtimestamp(m.t_start).isoformat(timespec="seconds"),
                            dt.datetime.fromtimestamp(m.t_end).isoformat(timespec="seconds"), "", ""])
            key.writerow([item, int(r["full"]), int(id(r) in sample_ids), r["score"], str(r["shift"][0]), int(m.staged)])
    return len(order), len(full), len(sample)


def fleiss_kappa(ratings):
    """Fleiss' kappa for yes/no ratings: {item: [0/1, ...]} with the same number of raters per item."""
    rows = [r for r in ratings.values() if len(r) >= 2]
    if not rows:
        return None
    n = len(rows[0])
    rows = [r for r in rows if len(r) == n]
    p_yes = sum(sum(r) for r in rows) / (len(rows) * n)
    p_items = [(sum(r) ** 2 + (n - sum(r)) ** 2 - n) / (n * (n - 1)) for r in rows]
    p_bar, p_e = sum(p_items) / len(rows), p_yes ** 2 + (1 - p_yes) ** 2
    return round((p_bar - p_e) / (1 - p_e), 2) if p_e < 1 else 1.0


def isotonic(xs, ys):
    """Pool-adjacent-violators fit: returns a function score -> probability, non-decreasing."""
    pts = sorted(zip(xs, ys))
    blocks = []  # [sum y, count, max x]
    for x, y in pts:
        blocks.append([y, 1, x])
        while len(blocks) > 1 and blocks[-2][0] / blocks[-2][1] > blocks[-1][0] / blocks[-1][1]:
            s, c, mx = blocks.pop()
            blocks[-1][0] += s
            blocks[-1][1] += c
            blocks[-1][2] = mx
    steps = [(b[2], b[0] / b[1]) for b in blocks]

    def f(x):
        for mx, p in steps:
            if x <= mx:
                return p
        return steps[-1][1]
    return f


def ece(probs, labels, bins=10):
    total, err = len(probs), 0.0
    for b in range(bins):
        idx = [i for i, p in enumerate(probs) if b / bins <= p < (b + 1) / bins or (b == bins - 1 and p == 1.0)]
        if idx:
            err += len(idx) / total * abs(sum(probs[i] for i in idx) / len(idx) - sum(labels[i] for i in idx) / len(idx))
    return round(err, 3)


def rate(ratings_path, key_path):
    """Actionable % per system (majority of reviewers), reviewer agreement, and score calibration."""
    with open(key_path, newline="", encoding="utf-8") as f:
        key = {r["item"]: r for r in csv.DictReader(f)}
    votes, reviewers = defaultdict(list), set()
    with open(ratings_path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["item"] in key and r["actionable"].strip() in ("0", "1"):
                votes[r["item"]].append(int(r["actionable"]))
                reviewers.add(r["reviewer"])
    label = {i: int(sum(v) * 2 > len(v)) for i, v in votes.items()}

    def share(flag):
        rated = [i for i in label if key[i][flag] == "1"]
        return {"rated": len(rated), "actionable_pct": round(100 * sum(label[i] for i in rated) / len(rated)) if rated else None}

    out = {"reviewers": len(reviewers), "items_rated": len(label), "rakshak": share("rakshak_alert"), "line_rule": share("line_sample"),
           "fleiss_kappa": fleiss_kappa(votes)}
    # Calibration: fit score -> P(actionable) on one half of the days, measure on the other half, and swap.
    items = sorted(label, key=lambda i: key[i]["day"])
    days = sorted({key[i]["day"] for i in items})
    if len(items) >= 20 and len(days) >= 2:
        half = set(days[: len(days) // 2])
        folds = [[i for i in items if key[i]["day"] in half], [i for i in items if key[i]["day"] not in half]]
        probs, labels = [], []
        for fit, test in ((folds[0], folds[1]), (folds[1], folds[0])):
            f = isotonic([float(key[i]["score"]) for i in fit], [label[i] for i in fit])
            probs += [f(float(key[i]["score"])) for i in test]
            labels += [label[i] for i in test]
        out["calibration"] = {"items": len(probs), "ece": ece(probs, labels),
                              "note": "on reviewed items only (alerts and the line-rule sample), 2-fold by day"}
    else:
        out["calibration"] = None
    return out


# ---------------------------------------------------------------- synthetic data (self-test only)
def synthetic(folder, days=12, seed=1):
    """Plausible-looking fake logs, ONLY to check that the benchmark runs end to end."""
    rng = random.Random(seed)
    start = dt.datetime(2026, 8, 3)
    rows, staged = [], []
    usual = ["r2c0>r2c3", "r2c3>r2c0", "r1c0>r1c3", "r2c1>r2c2"]
    for d in range(days):
        for cam in ("cam-1", "cam-2", "cam-3"):
            for h in range(24):
                n = rng.randint(4, 9) if 6 <= h <= 19 else rng.randint(0, 1)
                for _ in range(n):
                    t = (start + dt.timedelta(days=d, hours=h, minutes=rng.randint(0, 59))).timestamp()
                    e, x = rng.choice(usual).split(">")
                    rows.append(Movement(cam, t, t + 20, e, x, speed=round(rng.uniform(0.3, 0.7), 2),
                                         dwell=round(rng.uniform(8, 30), 1), group=rng.choice([1, 1, 1, 2]),
                                         crossed=True))
        if d >= 7:
            for k in range(5):
                t = (start + dt.timedelta(days=d, hours=rng.choice([1, 2, 3, 23]), minutes=rng.randint(0, 50))).timestamp()
                cam = rng.choice(("cam-1", "cam-2", "cam-3"))
                rows.append(Movement(cam, t, t + 40, "r0c1", "r2c3", speed=0.1, dwell=45, low=0.7, group=2, crossed=True))
                staged.append({"camera": cam, "start": t - 5, "end": t + 45, "staged_id": f"S{d}-{k}"})
    mfile, sfile = Path(folder) / "movements.csv", Path(folder) / "staged.csv"
    with open(mfile, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].row().keys()))
        w.writeheader()
        for m in rows:
            w.writerow(m.row())
    with open(sfile, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["camera", "start", "end", "staged_id"])
        w.writeheader()
        w.writerows(staged)
    return mfile, sfile


def synthetic_ratings(folder, key_path, seed=3):
    """Fake reviewer ratings for the self-test: 3 reviewers who mostly agree that staged movements
    and high scores are actionable."""
    rng = random.Random(seed)
    with open(key_path, newline="", encoding="utf-8") as f:
        key = list(csv.DictReader(f))
    path = Path(folder) / "ratings.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["item", "reviewer", "actionable"])
        for r in key:
            truth = r["staged"] == "1" or float(r["score"]) > 20
            for reviewer in ("rev-a", "rev-b", "rev-c"):
                w.writerow([r["item"], reviewer, int(truth if rng.random() > 0.1 else not truth)])
    return path


# ---------------------------------------------------------------- report
def report(res, synthetic_run):
    lines = []
    add = lines.append
    if synthetic_run:
        add("SYNTHETIC SELF-TEST - fake data, checks that the code runs. These are NOT results; do not quote them.")
        add("")
    if not res["prereg"]["sha256"] and not synthetic_run:
        add("WARNING: no benchmark/prereg.json - these parameters were not fixed in advance.")
        add("")
    e = res["evaluation"]
    add(f"Evaluated {e['evaluated_days']} days ({e['first_day']} to {e['last_day']}), {e['shifts']} shifts, "
        f"{e['movements']} movements; walk-forward after {res['params']['train_days']} training days; "
        f"budget {res['per_shift']}/shift")
    add("")
    add("Ablation (same movements, same cameras)   alerts/shift   staged alerted   lawful flagged/shift")
    for stage in STAGES:
        a = e["ablation"][stage]
        add(f"  {STAGE_NAMES[stage]:<40}{a['alerts_per_shift']:>10}   {a['staged_alerted']:>6}/{e['staged_total']:<8}"
            f"{a['lawful_flagged_per_shift']:>12}")
    add("")
    add("Alerts per shift by kind of shift         shifts   " + "   ".join(f"{s:>8}" for s in STAGES))
    for g, b in e["by_shift_type"].items():
        add(f"  {g:<40}{b['shifts']:>6}   " + "   ".join(f"{b[s]:>8}" for s in STAGES))
    add("")
    add(f"Staged crossings         {e['staged_alerted']}/{e['staged_total']} alerted, "
        f"{e['staged_logged']}/{e['staged_total']} logged (alert or digest)")
    if e["staged_missed_by_detection"]:
        add(f"                         not detected at all: {', '.join(e['staged_missed_by_detection'])}")
    s = res.get("surge")
    if s:
        add(f"Surge test               {s['alerted_with_surge']}/{s['injected']} injected crossings alerted with surge mode, "
            f"{s['alerted_without_surge']}/{s['injected']} without; "
            f"{e['surge_activations_without_injection']} surge(s) on normal days")
    r = res.get("review")
    if r:
        add(f"Blind review             actionable: Rakshak {r['rakshak']['actionable_pct']}% of {r['rakshak']['rated']} alerts, "
            f"line rule {r['line_rule']['actionable_pct']}% of {r['line_rule']['rated']} sampled; "
            f"{r['reviewers']} reviewers, Fleiss kappa {r['fleiss_kappa']}")
        c = r.get("calibration")
        add(f"Calibration              ECE {c['ece']} on {c['items']} items ({c['note']})" if c
            else "Calibration              not enough rated items (need >= 20 over >= 2 days)")
    else:
        add("Blind review             no ratings.csv yet (python -m benchmark --review-sheet)")
    lt = res["ledger"]
    tm = lt["timing"]
    add(f"Tamper test              {lt['caught']}/{lt['types']} tamper types caught ({', '.join(k for k, v in lt['detail'].items() if v)})")
    add(f"Verify time              {tm['verify_seconds']} s for {tm['entries']} entries with {tm['clips']} x {tm['clip_kb']} KB clips "
        f"(one-byte edit found: {tm['edit_found']}; this machine)")
    add(f"Signed SMS               {lt['sms_chars']} characters, verifies: {lt['sms_verifies']}")
    names = {"server": "sealed", "console": "on console", "sms": "SMS accepted", "ack": "acknowledged"}
    if res.get("latency"):
        add("Latency from the triggering frame (live logs): " + "; ".join(
            f"{names.get(k, k)} p50 {v['p50']} s / p95 {v['p95']} s (n={v['n']})" for k, v in res["latency"].items()))
    else:
        add("Latency                  no latency.csv in the data folder (copy DATA_DIR/latency.csv from a live run)")
    add("")
    add("Not measured here: detection/face/ANPR accuracy and power; throughput: scripts/measure_perf.py.")
    add("Inputs: " + ", ".join(f"{k} sha256 {v[:12] if v else 'missing'}" for k, v in res["inputs"].items()))
    g = res["git"]
    add(f"Code: commit {(g['commit'] or 'unknown')[:10]}{' + uncommitted changes' if g['uncommitted_changes'] else ''}")
    return "\n".join(lines)


def latency_stats(path):
    """p50 / p95 per channel from a latency.csv written by the live system (DATA_DIR/latency.csv)."""
    if not Path(path).exists():
        return None
    by_kind = defaultdict(list)
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            by_kind[r["kind"]].append(float(r["seconds"]))
    out = {}
    for kind, v in sorted(by_kind.items()):
        v.sort()
        out[kind] = {"n": len(v), "p50": round(v[len(v) // 2], 2), "p95": round(v[min(len(v) - 1, int(0.95 * len(v)))], 2)}
    return out


def load_params(path):
    params = dict(DEFAULTS)
    if Path(path).exists():
        params.update(json.loads(Path(path).read_text(encoding="utf-8")))
    return params


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true", help="run every test on the real logs")
    ap.add_argument("--selftest", action="store_true", help="run on synthetic data (checks the code only)")
    ap.add_argument("--review-sheet", action="store_true", help="write the blind review sheet from the real logs")
    ap.add_argument("--data", default=str(ROOT / "data"), help="folder with movements.csv, staged.csv, post.json")
    ap.add_argument("--prereg", default=str(ROOT / "prereg.json"), help="pre-registered parameters")
    args = ap.parse_args()
    if not (args.all or args.selftest or args.review_sheet):
        ap.print_help()
        return

    params = load_params(args.prereg)
    if args.selftest:
        folder = Path(tempfile.mkdtemp())
        mfile, sfile = synthetic(folder)
    else:
        folder = Path(args.data)
        mfile, sfile = folder / "movements.csv", folder / "staged.csv"
        if not mfile.exists():
            raise SystemExit(f"No {mfile}. Run the system on your footage (it writes data/movements.csv), copy that "
                             f"file and your staged.csv here - see benchmark/data/README.md. "
                             f"To check the code only: python -m benchmark --selftest")
    post = json.loads((folder / "post.json").read_text(encoding="utf-8")) if (folder / "post.json").exists() else {}
    calendar = PostCalendar.from_dict(post.get("calendar", {}))
    per_shift = params["per_shift"] or post.get("alerts_per_shift", 12)
    train_days = params["train_days"]
    movements, staged = load_movements(mfile), load_staged(sfile)

    t0 = time.time()
    evaluation, results = evaluate(movements, staged, calendar, per_shift, train_days, params)
    review_dir = (folder if args.selftest else ROOT) / "review"
    if args.review_sheet or args.selftest:
        n, n_full, n_line = review_sheet(results, review_dir, params["review_line_sample"], params["seed"])
        print(f"Review sheet: {n} items ({n_full} Rakshak alerts + {n_line} sampled line-rule alerts) -> "
              f"{review_dir / 'sheet.csv'}\nGive reviewers sheet.csv only; keep key.csv with the team.\n")
        if args.review_sheet:
            return
    ratings = synthetic_ratings(folder, review_dir / "key.csv") if args.selftest else folder / "ratings.csv"
    res = {
        "synthetic": bool(args.selftest), "run_at": dt.datetime.now().isoformat(timespec="seconds"),
        "params": params, "per_shift": per_shift,
        "prereg": {"path": str(args.prereg), "sha256": None if args.selftest else sha256(args.prereg)},
        "git": git_commit(),
        "evaluation": evaluation,
        "surge": surge_test(load_movements(mfile), calendar, per_shift, train_days, params),
        "review": rate(ratings, review_dir / "key.csv") if ratings.exists() and (review_dir / "key.csv").exists() else None,
        "ledger": ledger_test(),
        "latency": latency_stats(folder / "latency.csv"),
    }
    res["seconds"] = round(time.time() - t0, 1)
    res["inputs"] = {"movements.csv": sha256(mfile), "staged.csv": sha256(sfile), "post.json": sha256(folder / "post.json"),
                     "ratings.csv": sha256(ratings)}
    text = report(res, args.selftest)
    print(text)
    if not args.selftest:  # never overwrite real results with synthetic ones
        out = ROOT / "results"
        out.mkdir(exist_ok=True)
        (out / "latest.json").write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
        (out / "latest.md").write_text("```\n" + text + "\n```\n", encoding="utf-8")
        print(f"\nSaved {out / 'latest.json'} and latest.md")
