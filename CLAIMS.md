# Claims ledger

Every claim in the submitted SIH deck, its status in this repository, and the evidence behind it.
IDs match `docs/PRD.md` §5. Update every Sunday.

**Status:** `TODO` → `PARTIAL` → `BUILT` (code + tests) → `MEASURED` (number produced by a script
or a logged study, result committed). A measured value that differs from the deck is recorded as
it is: **we present the measured value, not the deck value.**

Last updated: 2026-10-02 · Tests: 44 (`python -m pytest`)

## ⚠ Read this first

- **No deck number about alerts, accuracy, reviewers or operators has been measured on real footage
  yet.** `benchmark/data/` holds no real logs.
- **The synthetic self-test prints "line rule 96.8 → Rakshak 11.3".** That is fake data made only to
  check the code runs, and it looks almost exactly like the deck's "normal day 96 → 11". If the deck
  number came from the self-test, it is **not a result**. Don't repeat it until the benchmark
  has run on real footage.
- **Throughput differs from the deck.** Deck: 2.1 fps per feed on an i5-6200U. Measured on an
  i3-1115G4: 0.37–0.78 fps per feed depending on the backend (below). The website says i7-6600U.
  The team must state which laptop the deck's numbers came from.

## PS capabilities and vision

| ID | Claim (deck) | Deck value | Measured | Status | Evidence / note |
|---|---|---|---|---|---|
| V1 | Human detection & tracking recall | 0.91 day / 0.84 night | — | PARTIAL | YOLOX-tiny (Apache-2.0) in `app/detector.py`. Agreement with the old YOLOv8n on 65 demo frames: 163 of 174 YOLOv8n people boxes also found, 54 extra. No labelled recall set yet |
| V2 | Vehicle classes incl. tractor, e-rickshaw | 7 classes | — | TODO | COCO classes only; needs labelled data and fine-tuning |
| V3 | Face detection at gates, recall ≤ 6 m | 0.93 | — | TODO | |
| V4 | ANPR full-plate accuracy | 87% | — | TODO | External ANPR hits can already join the queue (A9) |
| V5 | Virtual fence, always alerts at night | — | — | BUILT | Fence lines + restricted zones; restricted-zone breach at night is never budgeted. Seen live: fence-crossing alerts on the entrance feed |
| V6 | Loiter, crawl, run, group, off-path | — | — | BUILT | `baseline.py`: off-path, speed (run), dwell, crawl, group, loiter in restricted zone; tests |
| V7 | Night: IR and thermal, tested on LLVIP | — | — | PARTIAL | `/modes` showcase; no LLVIP evaluation |
| V8 | Alert latency p95 | 2.4 s console / 3.1 s SMS | to sealed: p50 1.5 s, max 2.0 s (n=7, OpenVINO + nano); p50 3.0 s, max 3.1 s (n=6, ONNX Runtime + tiny), i3-1115G4 | PARTIAL | Logged per channel (`data/latency.csv`); console and SMS latency not measured yet; samples far too small. `benchmark/results/latency_i3-1115g4_live.json` |
| V9 | Tracking across cameras | — | — | PARTIAL | OSNet re-ID; no IDF1 measured |
| V10 | Watchlist hit | — | — | PARTIAL | Watchlist by tracker ID; FRS hits from SSB systems via `/api/decision/external-hits`; no face matching of our own |
| V11 | Confirmed weapon | — | — | PARTIAL | Two-pass confirmation; model now runs on ONNX Runtime without Ultralytics, output identical to Ultralytics on the test frames; weights' licence still open (THIRD_PARTY.md) |

## Decision engine

| ID | Claim (deck) | Deck value | Measured | Status | Evidence / note |
|---|---|---|---|---|---|
| D1 | Score = −log P(…) + behaviour terms | — | — | BUILT | `baseline.py`, tests |
| D2 | Day types normal / haat / festival / seal | — | — | BUILT | `calendar.py`, tests |
| D3 | ≤ 12 routine alerts/shift; critical bypass; surge mode | — | — | BUILT | `budget.py`, tests; budget survives restarts |
| D4 | Days 1–14 zone rules + borrowed baseline; refit nightly | — | — | BUILT | `engine.py`, tests |
| D5 | Drift watch < 50% → re-baseline | — | — | BUILT | `engine.drift()`, console banner, tests |
| D6 | Score calibrated | ECE 0.06 | — | BUILT (not measured) | Benchmark ECE needs reviewer ratings |
| D7 | Ablation, haat-day shift | 231 → 88 → 31 → 12 | — | BUILT (not measured) | 4 labelled stages, `benchmark/PREREG.md` |
| D8 | Normal day / night | 96 → 11 / 34 → 9 | — | BUILT (not measured) | ⚠ see note above |
| D9 | Actionable, 3 blind reviewers | 58% vs 4% | — | BUILT (not measured) | `--review-sheet`, `benchmark/rubric.md`, Fleiss κ |
| D10 | Staged movements detected | 19 / 20 | — | BUILT (not measured) | `staged.csv` matching |
| D11 | Watch Orders | — | — | BUILT | |
| D12 | Shift digest | — | — | BUILT | Top of this shift's digest on `/decision`; full list in `movements.csv` |
| D13 | Alert card shows every score term | — | — | BUILT | `/decision` |

## Evidence and security

| ID | Claim (deck) | Deck value | Measured | Status | Evidence / note |
|---|---|---|---|---|---|
| S1 | Egress Guard | — | — | BUILT, untested on hardware | `deploy/egress-guard/` (nftables, dnsmasq, chrony, installer), `scripts/egress_summary.py` + tests |
| S2 | 24-h capture, ₹2,400 camera | 1,146 → 3 hosts, 100% blocked | — | TODO | Needs the camera and the box; procedure in `deploy/egress-guard/install.sh` |
| S3 | Signed chain; edit caught | 0.3 s | 0.04 s for a 6-entry live ledger; 0.49 s for 1,000 entries + 100 × 100 KB clips (synthetic), i3-1115G4 | MEASURED (state the ledger size) | `python -m app.decision.verify`; benchmark tamper/timing |
| S4 | Hourly Merkle anchor at HQ | — | — | BUILT | `ledger.anchor()`, `hq/`, tests |
| S5 | Signed SMS checked on phone and HQ | — | — | BUILT | `/verify` (WebCrypto, TweetNaCl fallback, replay-age warning), `/api/hq/sms/verify`, tests |
| S6 | Evidence packet, §63(4) Part A | 2 h → 3 min | — | BUILT (not measured) | One click; manual baseline not timed |
| S7 | Clips 30 days, logs 180 days | — | — | BUILT | `engine.apply_retention()`, tests |
| S8 | Threat model, security scan, DPDP assessment | — | — | BUILT | `docs/threat-model.md`, `docs/security-scan/` (bandit 0 high; pip-audit 0 known vulnerabilities), `docs/dpia.md` (draft for legal review) |

## Alerts, comms, UI, integration

| ID | Claim (deck) | Deck value | Measured | Status | Evidence / note |
|---|---|---|---|---|---|
| A1 | Console offline; Hindi and English | — | — | BUILT | Hindi on `/decision`, `/pulse`, `/shift-report`, `/verify`, navigation; older pages English only; translations need native review |
| A2 | One tap: acknowledge / escalate / dismiss | — | — | BUILT | Sealed in the ledger; time to acknowledge logged |
| A3 | Signed SMS on 2G, Hindi voice call, siren relay | — | — | BUILT, untested on hardware | `app/decision/comms.py` (AT commands, retry, siren); voice clip playback is modem-specific |
| A4 | Store-and-forward to HQ | — | — | BUILT | `sync.py`, tests with a link outage |
| A5 | Satellite phone SMS | — | — | TODO | Format fits 160 characters; never tested on a satellite phone; say so |
| A6 | Shift report, one signature | — | — | BUILT | `/shift-report` (printable) |
| A7 | Border Pulse | — | — | BUILT | `/pulse`, `app/decision/pulse.py`, tests |
| A8 | C2: REST, WebSocket, MQTT, ONVIF Profile M; Frigate tested | — | — | PARTIAL | REST, `/ws/decision`, `/ws/c2` (signed entries), MQTT built; ONVIF Profile M and the Frigate test not done |
| A9 | External FRS/ANPR hits join the queue | — | — | BUILT | `/api/decision/external-hits` with `integration_token`, tests |

## Edge, performance, deployment

| ID | Claim (deck) | Deck value | Measured | Status | Evidence / note |
|---|---|---|---|---|---|
| E1 | RTSP/ONVIF, USB, phone feeds | — | — | PARTIAL | RTSP, USB, phone; no ONVIF discovery |
| E2 | Laptop, 13 feeds | i5-6200U: 2.1 fps/feed avg, 6 on active | i3-1115G4: 0.37 (busy 0.40) ONNX Runtime + tiny; 0.52–0.63 OpenVINO INT8 tiny; 0.78 (busy 0.89) OpenVINO nano | MEASURED (differs) | `scripts/measure_perf.py`, `benchmark/results/perf_*.json`. Different CPU from the deck; the deck number is not reproduced |
| E3 | N100, OpenVINO INT8: 10 feeds | 1 / 8 fps, 11.6 W | — | PARTIAL | OpenVINO backend + INT8 quantization built and measured on the i3 (INT8 keeps 98% of the detector's boxes; weapon model kept in FP32 because INT8 lost 26% of its candidates). No N100, no power measurement |
| E4 | One-hour install | — | — | PARTIAL | Egress Guard installer; full box installer TODO |
| E5 | Cost per post | ₹32,500 + ₹4,000/yr | estimates ₹22,000–36,500 + ₹3,600–6,000/yr | PARTIAL | `docs/bom.md`; dated quotes pending |

## Studies and artifacts

| ID | Claim (deck) | Deck value | Measured | Status | Evidence / note |
|---|---|---|---|---|---|
| X1 | 72 h benchmark, `python -m benchmark --all` | — | — | PARTIAL | Command works; no real data yet |
| X2 | Operator study | 13 → 23 of 24; 71 s → 19 s | — | PARTIAL | `study/protocol.md`, `study/analyse.py`; not run |
| X3 | Red-team | 7 / 10 | — | PARTIAL | `docs/red-team.md`; not run |
| X4 | Automated tests | 146 | 44 | PARTIAL | `pytest`; CI on GitHub |
| X5 | Hindi operator card, 2-h training | — | — | PARTIAL | `docs/operator-card-hi.md`; training slides TODO |
| X6 | 90-second demo video | — | — | PARTIAL | `/demo` live with a walkthrough of real screens; video to record (`docs/demo-video.md`) |
| X7 | OAT-1…7 pilot protocol | — | — | BUILT | `docs/pilot-oat.md` |
| X8 | Comparison table | — | — | TODO | Replace "Varies" with named products in future materials |
