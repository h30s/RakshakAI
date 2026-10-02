# Rakshak AI

**Alerts you can trust on an open border, from the cameras SSB already has.**

Rakshak AI is a software layer for existing CCTV cameras (Smart India Hackathon 2026, problem
statement 26187, AI video analytics for border surveillance). It detects and tracks people,
vehicles and weapons. It then **decides** which few movements an operator should look at: each one
is scored against what is normal for that post, that hour and that kind of day (haat, festival,
border seal), and only the most unusual reach the operator, at most a fixed number per shift.
Every alert is sealed in a signed, tamper-evident ledger that Sector HQ can check.

```text
IP / USB / phone cameras ─► YOLOX detection ─► OSNet journey tracking ─► movements (decided while in view)
    ─► per-post baseline score ─► alert budget + surge mode ─► ranked alert ─► signed ledger
    ─► console (live push) · signed SMS / call / siren · Sector HQ (store-and-forward) · C2 feeds
```

**Every claim of the SIH deck and the evidence behind it: [`CLAIMS.md`](CLAIMS.md).** Build plan:
[`docs/PRD.md`](docs/PRD.md).

## What is in this repository

| Capability | Status | Where |
| --- | --- | --- |
| Person, vehicle and object detection: YOLOX (Apache-2.0), ONNX Runtime or OpenVINO, CPU only | Working | `app/detector.py` |
| Weapon detection with two-pass confirmation | Working | `app/pipeline.py`, `app/threats/` |
| Motion gating: quiet cameras analysed once a second, busy ones every pass | Working | `app/pipeline.py` |
| Cross-camera person re-identification (OSNet) | Working | `app/tracking/` |
| Camera inputs: recorded video, RTSP, USB, phone (QR) | Working | `app/sources/` |
| Movements: path, speed, dwell, group, crawl, fence crossing, restricted zone, loitering | Working | `app/decision/events.py` |
| Live decisions: a crossing or a loiterer alerts while still in view | Working | `app/decision/engine.py` |
| Per-post baseline (camera × hour × day type: haat, festival, seal) | Working | `app/decision/baseline.py`, `calendar.py` |
| Alert budget (12 per 8-h shift), surge mode, Watch Orders, shift digest | Working | `app/decision/budget.py`, `/decision` |
| Learning period (14 days, borrowed baseline), drift watch | Working | `app/decision/engine.py` |
| Tamper-evident ledger: SHA-256 chain, Ed25519 signatures, hourly Merkle anchors | Working | `app/decision/ledger.py` |
| Restart recovery: alerts, statuses and the shift budget restored from the ledger | Working | `app/decision/engine.py` |
| Retention: unescalated clips deleted after 30 days (sealed), logs kept 180 days | Working | `app/decision/engine.py` |
| Evidence packet + BSA s.63(4) Part A draft, checked offline | Working | `/api/decision/alerts/{id}/packet`, `python -m app.decision.verify` |
| Sector HQ: store-and-forward; HQ checks every signature, chain link and anchor | Working | `app/decision/sync.py`, `hq/` |
| Signed 160-character SMS; checked on the phone offline (`/verify`) and at HQ | Working | `app/decision/ledger.py`, `static/verify.html` |
| GSM modem SMS + voice call, siren relay, retry until sent | Built, **untested on hardware** | `app/decision/comms.py` |
| C2 feeds: REST, WebSocket (`/ws/c2`, signed entries), MQTT | Built (MQTT untested with a broker) | `app/decision/c2.py`, `api.py` |
| FRS / ANPR hits from existing systems join the queue (token-protected) | Working | `POST /api/decision/external-hits` |
| Alert latency per channel (sealed, console, SMS, acknowledged) | Working | `data/latency.csv`, `/decision` |
| Border Pulse: new paths, peak shifts, night activity, repeat crossers | Working | `/pulse` |
| Printable shift report with signature lines | Working | `/shift-report` |
| Hindi / English operator screens | Working (Hindi needs native review) | `static/i18n.js` |
| Egress Guard: cameras isolated, call-home logged and blocked | Built, **untested on the N100** | `deploy/egress-guard/`, `scripts/egress_summary.py` |
| Benchmark: 4-stage ablation, by day type and night, blind review, calibration, tamper, latency | Working (**no real data yet**) | `python -m benchmark --all` |
| Throughput measurement | Working | `scripts/measure_perf.py` |

**Not built yet:** number-plate recognition (ANPR), face detection and matching at gates,
tractor / e-rickshaw classes, ONVIF Profile M metadata, operator login, signed updates.

## Measured so far (and only this)

All on an **Intel i3-1115G4** laptop (4 threads, no GPU), 13 demo feeds, motion gating on. Files in
[`benchmark/results/`](benchmark/results/).

| What | ONNX Runtime + YOLOX-tiny | OpenVINO + YOLOX-tiny INT8 | OpenVINO + YOLOX-nano |
|---|---|---|---|
| Frames analysed per feed per second (all / busy feeds) | 0.37 / 0.40 | 0.52–0.63 / 0.56–0.69 | 0.78 / 0.89 |
| Detection cycle (all 13 feeds) | 2.4 s | 1.5–1.6 s | 1.2 s |
| Triggering frame → alert sealed, live run (n is small) | median 3.0 s, max 3.1 s (n=6) | — | median 1.5 s, max 2.0 s (n=7) |

The SIH deck's throughput (2.1 fps per feed) and its accuracy, alert-volume, reviewer and operator
study numbers are **not reproduced yet**; see `CLAIMS.md`. Decision numbers need our own footage:
`benchmark/data/README.md`.

## How the decision layer works

1. **Movements.** Each tracked person's pass through a camera: where they entered and left (a 4 x 3
   grid), speed in body-heights per second, time in view, group size, time crawling, time inside a
   restricted zone, and whether they crossed a virtual fence. Tracks still in view are evaluated
   every quarter second, so an alert does not wait for the person to leave.
2. **Score.** `s = -log P(path | camera, hour, day type) - log P(hour) - log P(speed) - log P(dwell)`
   plus crawl, group and loitering terms. Sparse cells back off to what the camera usually does.
   Each term is shown on the alert card.
3. **Budget.** The threshold is recalibrated every night so that on average 12 movements per shift
   pass it; once a shift has used its budget, the rest go to the digest.
4. **Never budgeted.** A fence breach into a restricted zone at night, any fence crossing while the
   border is sealed, watchlist hits and FRS / ANPR hits always alert.
5. **Surge mode.** If far more movements than usual pass the threshold within an hour, the budget
   lifts and the commander is told why. Officers can also force it on or off.
6. **Learning period.** For the first 14 days a new post scores against a baseline borrowed from a
   post with similar traffic (`borrow_baseline`), or alerts on fence crossings; either way within
   the budget. From day 15 it uses its own baseline, refit nightly on the last 28 days.
7. **Drift watch.** Operator taps give a weekly precision; below 50% the console asks for a re-baseline.

**Stated limit:** someone who moves with the crowd, on the usual path, at the usual hour looks like
the background and will not be flagged. Watch Orders and the shift digest cover that case.

## How to run

Requires Python 3.10+. No GPU.

```bash
python -m venv .venv
.venv\Scripts\activate                        # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt               # run time: no PyTorch, no Ultralytics
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements-export.txt        # one-time model preparation only
python scripts/fetch_assets.py                # demo videos and models (--models-only for models)
copy config\post.example.json data\post.json   # Linux/macOS: cp config/post.example.json data/post.json
uvicorn app.server:app --port 8000
```

Pages: `/app` operations console · `/decision` ranked alerts · `/pulse` Border Pulse ·
`/shift-report` · `/verify` (duty phone) · `/demo`. Edit `data/post.json` for your post: fences,
restricted zones, haat days, festivals, seals, the alert budget, and optionally `comms` (GSM modem),
`mqtt`, `hq_url` and `integration_token` (see `config/post.example.json` and
`app/decision/comms.py`).

Faster on Intel CPUs (N100): `pip install openvino nncf`, `python scripts/quantize_openvino.py`,
then run with `DETECTOR_BACKEND=openvino` (and `GENERAL_MODEL=yolox_nano.onnx` for the most speed).

## Benchmark, measurements and tests

```bash
python -m benchmark --all          # real results from benchmark/data/ (see benchmark/data/README.md)
python -m benchmark --review-sheet # blind sheet for the 3 reviewers (benchmark/rubric.md)
python -m benchmark --selftest     # synthetic data: checks the code runs; NOT results
python scripts/measure_perf.py     # throughput on this machine (names the CPU in the result)
python -m pytest -q
python -m app.decision.verify      # check this post's ledger and time the check
python scripts/decision_preview.py # decision pages on synthetic data, no models needed
```

**The real footage is not public** (residents' privacy). `python -m benchmark --all` therefore runs
only on the team's machines; judges can get the full-data run offline on request. Before the first
real run, fix the parameters in `benchmark/prereg.json` and commit it (`benchmark/PREREG.md`).

## Sector HQ

```bash
python -m app.decision.verify --pubkey   # on the edge box: this post's public key
# at HQ: hq_data/posts.json = {"BOP07": "<that key>"}
uvicorn hq.server:app --port 9000
```

Set `"hq_url": "http://<hq>:9000"` in the post's `data/post.json`. The post forwards its ledger
whenever the link is up; HQ accepts only entries that extend the post's chain with a valid
signature, and recomputes every hourly Merkle anchor.

## Documents

[Threat model](docs/threat-model.md) · [Security scan](docs/security-scan/README.md) ·
[DPDP privacy assessment](docs/dpia.md) · [Parts list](docs/bom.md) (estimates; quotes pending) ·
[Hindi operator card](docs/operator-card-hi.md) · [Pilot acceptance tests](docs/pilot-oat.md) ·
[Operator study](study/protocol.md) · [Red-team test](docs/red-team.md) ·
[Demo video shot list](docs/demo-video.md) · [Third-party licences](THIRD_PARTY.md)

## Data and privacy

`data/` (incidents, movements, evidence, ledger, latency log and the signing key) is never
committed. Keep the signing key on the edge box only; in the field, store it in the box's TPM or an
encrypted volume. See `docs/dpia.md`.
