# 30-day pilot: operational acceptance tests (OAT-1…7)

Fixed **before** the pilot starts, as on the SIH deck (slide 4). The post commander's unit
scores them; the team only supplies the tools. A test that fails is reported as failed.

**Pilot:** 2–3 BOPs, including one haat-crossing post, 30 days, subject to approval.
**Before day 1:** Egress Guard installed; operator login (threat model T8); `post.json` with
fences, restricted zones, haat days, festival and seal dates; duty phones registered; HQ key
registered; 2-hour operator training in Hindi (`docs/operator-card-hi.md`).

| Test | Pass if | Measured with | Where it comes from |
|---|---|---|---|
| OAT-1 Alert volume | ≤ 12 routine alerts per 8-h shift (critical alerts and surge excluded) | Shift reports | `/shift-report`; ledger alert entries by shift |
| OAT-2 Precision | ≥ 50% of alerts judged actionable by the post commander | Commander's daily review of the shift report | Operator taps give an early signal (drift watch); the commander's rating is the test |
| OAT-3 Response time | Median time to acknowledge ≤ 30 s | First operator tap after the alert's triggering frame ("ack" in `data/latency.csv`) | Console latency card; `python -m benchmark --all` with `latency.csv` in the data folder |
| OAT-4 Missed events | Every known event (staged by the unit, or reported later) appears as an alert or in the digest | Unit's own list of events vs `movements.csv` and the ledger | `benchmark/data/staged.csv` format |
| OAT-5 Evidence | Every seal and the whole chain verify, every day; HQ holds every hourly anchor | `python -m app.decision.verify`; HQ `/api/hq/posts` | Ledger, HQ store |
| OAT-6 Availability | ≥ 95% of camera-hours processed; every gap logged | Camera health log | `app/threats/monitor.py` stalls |
| OAT-7 Adoption | Still switched on, unprompted, on day 30 | The unit says so | — |

## Daily routine (5 minutes, post commander)

1. Print the shift reports. Mark each alert actionable / not actionable (OAT-2).
2. Check "Ledger intact" on each report (OAT-5).
3. Note any event the system missed (OAT-4).

## End of pilot

The team compiles OAT-1…7 from the shift reports, the ledger and the unit's notes, with every
number traceable to a file. The unit decides pass or fail.
