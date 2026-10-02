"""Operator study results from study/logs/*.csv (see study/protocol.md).

    python study/analyse.py [--logs study/logs]

Each row: guard, condition (W = video wall, R = Rakshak), set (A / B), event_id, event_start_s,
noticed_at_s (empty if not noticed). An event counts as noticed if noticed_at_s is within 60 s
of event_start_s.
"""
import argparse
import csv
import glob
import statistics
from collections import defaultdict
from pathlib import Path

WINDOW_S = 60
NAMES = {"W": "video wall", "R": "Rakshak queue"}


def load(folder):
    rows = []
    for path in sorted(glob.glob(str(Path(folder) / "*.csv"))):
        with open(path, newline="", encoding="utf-8") as f:
            rows += list(csv.DictReader(f))
    return rows


def analyse(rows):
    noticed = defaultdict(lambda: defaultdict(int))   # condition -> guard -> events noticed
    events = defaultdict(lambda: defaultdict(int))    # condition -> guard -> events shown
    delays = defaultdict(list)                         # condition -> seconds to acknowledge
    for r in rows:
        c, g = r["condition"].strip().upper(), r["guard"].strip()
        events[c][g] += 1
        if r["noticed_at_s"].strip():
            delay = float(r["noticed_at_s"]) - float(r["event_start_s"])
            if 0 <= delay <= WINDOW_S:
                noticed[c][g] += 1
                delays[c].append(delay)
    out = {}
    for c in sorted(events):
        per_guard = {g: noticed[c][g] for g in sorted(events[c])}
        d = sorted(delays[c])
        q = statistics.quantiles(d, n=4) if len(d) >= 2 else [None, None, None]
        out[c] = {"guards": len(per_guard), "events_per_guard": max(events[c].values()),
                  "median_noticed": statistics.median(per_guard.values()),
                  "range_noticed": [min(per_guard.values()), max(per_guard.values())],
                  "median_ack_s": round(statistics.median(d), 1) if d else None,
                  "iqr_ack_s": [round(q[0], 1), round(q[2], 1)] if d and len(d) >= 2 else None,
                  "per_guard": per_guard}
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--logs", default=str(Path(__file__).resolve().parent / "logs"))
    args = ap.parse_args()
    rows = load(args.logs)
    if not rows:
        raise SystemExit(f"No logs in {args.logs} yet (see study/protocol.md).")
    for c, r in analyse(rows).items():
        print(f"{NAMES.get(c, c)}: noticed median {r['median_noticed']} of {r['events_per_guard']} "
              f"(range {r['range_noticed'][0]}-{r['range_noticed'][1]}, {r['guards']} guards); "
              f"time to acknowledge median {r['median_ack_s']} s, IQR {r['iqr_ack_s']}")
        print("   per guard: " + ", ".join(f"{g} {n}" for g, n in r["per_guard"].items()))


if __name__ == "__main__":
    main()
