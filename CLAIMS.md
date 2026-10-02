# Claims ledger

Every claim in the submitted SIH deck, its status in this repository, and the evidence behind it.
IDs match `docs/PRD.md` §5. Update every Sunday.

**Status:** `TODO` → `PARTIAL` → `BUILT` (code + tests) → `MEASURED` (number produced by
`python -m benchmark` or a logged study, result committed). A measured value that differs from
the deck is recorded as it is: **we present the measured value, not the deck value.**

Last updated: 2026-09-30

## ⚠ Read this first

- **No deck number has been measured on real footage yet.** `benchmark/data/` holds no real
  logs, and `benchmark/results/` does not exist.
- **The synthetic self-test prints "line rule 96.8 → Rakshak 11.3".** That is fake data made
  only to check the code runs, and it looks almost exactly like the deck's "normal day 96 → 11".
  If the deck number came from the self-test, it is **not a result**. Do not repeat it anywhere
  until the benchmark has been run on real footage.
- **The detector is still Ultralytics YOLOv8 (AGPL-3.0).** The deck says YOLOX (Apache-2.0). See
  THIRD_PARTY.md.

## PS capabilities and vision

| ID | Claim (deck) | Deck value | Measured | Status | Evidence / note |
|---|---|---|---|---|---|
| V1 | Human detection & tracking recall | 0.91 day / 0.84 night | — | PARTIAL | Detection runs (YOLOv8n); no labelled recall set yet |
| V2 | Vehicle classes incl. tractor, e-rickshaw | 7 classes | — | TODO | COCO classes only; needs fine-tuning |
| V3 | Face detection at gates, recall ≤ 6 m | 0.93 | — | TODO | |
| V4 | ANPR full-plate accuracy | 87% | — | TODO | |
| V5 | Virtual fence, always alerts at night | — | — | BUILT | `app/decision/events.py`, `budget.py`; fences are lines + restricted rectangles (not yet polygons, no zone editor UI) |
| V6 | Loiter, crawl, run, group, off-path | — | — | PARTIAL | crawl, group, off-path, dwell, speed terms in `baseline.py`; no explicit loiter rule |
| V7 | Night: IR and thermal, tested on LLVIP | — | — | PARTIAL | `/modes` showcase; no LLVIP evaluation |
| V8 | Alert latency p95 | 2.4 s console / 3.1 s SMS | — | TODO | No latency instrumentation; no SMS gateway |
| V9 | Tracking across cameras | — | — | PARTIAL | OSNet re-ID in `app/tracking/`; no IDF1 measured |
| V10 | Watchlist hit | — | — | PARTIAL | Watchlist by tracker ID in `budget.py`; no face matching |
| V11 | Confirmed weapon | — | — | PARTIAL | Two-pass weapon confirmation in `app/pipeline.py`; YOLOv8 model (licence issue) |

## Decision engine

| ID | Claim (deck) | Deck value | Measured | Status | Evidence / note |
|---|---|---|---|---|---|
| D1 | Score = −log P(…) + behaviour terms | — | — | BUILT | `app/decision/baseline.py`, tests |
| D2 | Day types normal / haat / festival / seal | — | — | BUILT | `app/decision/calendar.py`, tests |
| D3 | ≤ 12 routine alerts/shift; critical bypass; surge mode | — | — | BUILT | `app/decision/budget.py`, tests |
| D4 | Days 1–14 zone rules + borrowed baseline; own baseline after, refit nightly | — | — | BUILT | `engine.py` (learning_days 14, borrow_baseline, 28-day refit), tests |
| D5 | Drift watch: weekly precision < 50% → re-baseline | — | — | BUILT | `engine.drift()`, console banner, `/api/decision/rebaseline`, tests |
| D6 | Score calibrated | ECE 0.06 | — | BUILT (not measured) | `benchmark/run.py` isotonic 2-fold ECE; needs reviewer ratings |
| D7 | Ablation, haat-day shift | 231 → 88 → 31 → 12 | — | BUILT (not measured) | 4 labelled stages in `benchmark/run.py`; see `benchmark/PREREG.md` |
| D8 | Normal day / night | 96 → 11 / 34 → 9 | — | BUILT (not measured) | By-shift-type breakdown in benchmark. ⚠ see note above |
| D9 | Actionable, 3 blind reviewers | 58% vs 4% | — | BUILT (not measured) | `--review-sheet`, `benchmark/rubric.md`, Fleiss κ |
| D10 | Staged movements detected | 19 / 20 | — | BUILT (not measured) | `staged.csv` matching in benchmark |
| D11 | Watch Orders | — | — | BUILT | `budget.py`, console form |
| D12 | Shift digest | — | — | PARTIAL | Digest count + movements.csv; no digest review page |
| D13 | Alert card shows every score term | — | — | BUILT | `/decision` |

## Evidence and security

| ID | Claim (deck) | Deck value | Measured | Status | Evidence / note |
|---|---|---|---|---|---|
| S1 | Egress Guard | — | — | TODO | Linux nftables/dnsmasq setup not written |
| S2 | 24-h capture on ₹2,400 camera | 1,146 → 3 hosts, 100% blocked | — | TODO | Needs the camera |
| S3 | Signed hash chain; edit caught in 0.3 s | 0.3 s | — | BUILT (timed on synthetic ledger) | `ledger.py`, `python -m app.decision.verify`; benchmark times 1,000 entries + 100 × 100 KB clips (≈0.5 s on the dev laptop). State the ledger size whenever you quote a time |
| S4 | Hourly Merkle anchor per post at Sector HQ | — | — | BUILT | `ledger.anchor()` (fixed: anchors by position so late alerts are covered), `hq/`, tests |
| S5 | Ed25519-signed SMS verified on phone and at HQ | — | — | PARTIAL | Format + HQ check (`/api/hq/sms/verify`) built; no phone verifier app, no modem |
| S6 | Evidence packet, §63(4) Part A | 2 h → 3 min | — | BUILT (not measured) | `/api/decision/alerts/{id}/packet`, `verify --packet`; manual baseline not timed |
| S7 | Clips 30 days, logs 180 days | — | — | BUILT | `engine.apply_retention()`; deletions sealed in the ledger; tests |
| S8 | Threat model, security scan, DPIA in repo | — | — | TODO | |

## Alerts, comms, UI, integration

| ID | Claim (deck) | Deck value | Measured | Status | Evidence / note |
|---|---|---|---|---|---|
| A1 | Console offline; Hindi and English | — | — | PARTIAL | `/decision` has a Hindi toggle (`static/i18n.js`); translations need native-speaker review; other pages English only |
| A2 | One tap: acknowledge / escalate / dismiss | — | — | BUILT | `/decision`, sealed as ledger actions |
| A3 | Signed SMS on 2G, Hindi voice call, siren relay | — | — | TODO | No GSM modem code |
| A4 | Store-and-forward to HQ | — | — | BUILT | `app/decision/sync.py` (ledger as outbox), tests with link outage |
| A5 | Satellite phone SMS | — | — | TODO | Format fits 160 characters; never field-tested — say so |
| A6 | Shift report, one signature | — | — | TODO | |
| A7 | Border Pulse | — | — | TODO | |
| A8 | C2 feed: REST, WebSocket, MQTT, ONVIF Profile M; Frigate tested | — | — | PARTIAL | REST only |
| A9 | External FRS/ANPR hits join the queue | — | — | TODO | |

## Edge, performance, deployment

| ID | Claim (deck) | Deck value | Measured | Status | Evidence / note |
|---|---|---|---|---|---|
| E1 | RTSP/ONVIF, USB, phone feeds | — | — | PARTIAL | RTSP, USB, phone in `app/sources/`; no ONVIF discovery |
| E2 | i5-6200U: 13 feeds | 2.1 fps avg, 6 active | — | TODO | Not measured |
| E3 | N100 OpenVINO INT8: 10 feeds | 1 / 8 fps, 11.6 W | — | TODO | No OpenVINO build; no N100 |
| E4 | One-hour install | — | — | TODO | |
| E5 | Cost per post | ₹32,500 + ₹4,000/yr | — | TODO | Needs dated quotes in `docs/bom.md` |

## Studies and artifacts

| ID | Claim (deck) | Deck value | Measured | Status | Evidence / note |
|---|---|---|---|---|---|
| X1 | 72 h benchmark, `python -m benchmark --all` | — | — | PARTIAL | Command works; no real data yet |
| X2 | Operator study | 13 → 23 of 24; 71 s → 19 s | — | TODO | No `/study` |
| X3 | Red-team | 7 / 10 | — | TODO | |
| X4 | Automated tests | 146 | 28 | PARTIAL | `pytest` (28 on 2026-09-30) |
| X5 | Hindi operator card, 2-h training | — | — | TODO | |
| X6 | 90-second demo video | — | — | TODO | |
| X7 | OAT-1…7 pilot protocol | — | — | TODO | |
| X8 | Comparison table | — | — | TODO | Replace "Varies" with named products |
