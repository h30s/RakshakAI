# Rakshak AI

**Alerts you can trust on an open border, from the cameras SSB already has.**

Rakshak AI is a software layer for existing CCTV cameras (Smart India Hackathon 2026, problem
statement 26187, AI video analytics for border surveillance). It detects and tracks people,
vehicles and weapons. It then **decides** which few movements an operator should look at: each one
is scored against what is normal for that post, that hour and that kind of day (haat, festival,
border seal), and only the most unusual reach the operator, at most a fixed number per shift.
Every alert is sealed in a signed, tamper-evident ledger.

```text
IP / USB / phone cameras ─► YOLOv8 detection ─► OSNet journey tracking ─► movements
    ─► per-post baseline score ─► alert budget + surge mode ─► ranked alert ─► signed ledger
```

## What is in this repository

| Capability | Status | Where |
| --- | --- | --- |
| Person, vehicle and object detection (YOLOv8n, CPU) | Working | `app/detector.py` |
| Weapon detection with two-pass confirmation | Working | `app/pipeline.py`, `app/threats/` |
| Cross-camera person re-identification (OSNet) | Working | `app/tracking/` |
| Camera inputs: recorded video, RTSP, USB, phone (QR) | Working | `app/sources/` |
| Night, thermal, fog and rain footage | Working | `app/modes/`, `/modes` |
| Operations console, camera health, incident reports + CSV | Working | `static/`, `/app`, `/reports` |
| Movements: path, speed, dwell, group, crawl, virtual-fence crossing, restricted zone | Working | `app/decision/events.py` |
| Per-post baseline (camera x hour x day type, haat / festival / seal days) | Working | `app/decision/baseline.py`, `calendar.py` |
| Alert budget (default 12 per 8-h shift), surge mode, Watch Orders, shift digest | Working | `app/decision/budget.py` |
| Learning period: 14 days of fence rules within the budget, or a borrowed baseline from a similar post | Working | `app/decision/engine.py` |
| Drift watch: weekly precision from operator taps, re-baseline prompt | Working | `app/decision/engine.py`, `/decision` |
| Tamper-evident ledger: SHA-256 hash chain, Ed25519 signatures, hourly Merkle anchors | Working | `app/decision/ledger.py` |
| Retention: unescalated alert clips deleted after 30 days (sealed in the ledger), logs 180 days | Working | `app/decision/engine.py` |
| Evidence packet: clip, sealed entry, chain, Merkle proof, s.63(4) Part A draft; offline check | Working | `/api/decision/alerts/{id}/packet`, `python -m app.decision.verify` |
| Store-and-forward to Sector HQ; HQ checks every signature, chain link and anchor | Working | `app/decision/sync.py`, `hq/` |
| Signed alert that fits one 160-character SMS (text only; no SMS gateway) | Working | `app/decision/ledger.py` |
| BSA s.63(4) Part A draft, pre-filled with the evidence hash | Working | `app/decision/ledger.py` |
| Ranked Alerts page: score terms, budget, surge, Watch Orders, ledger check, Hindi / English | Working (Hindi needs native review) | `/decision` |
| Benchmark: 4-stage ablation, by day type and night, blind review, calibration, tamper and timing | Working (no real data yet) | `python -m benchmark --all` |

Not in this repository yet: number-plate recognition (ANPR), face recognition, the YOLOX /
OpenVINO / Intel N100 edge build, sending SMS and voice calls through a GSM modem, camera network
isolation (Egress Guard), MQTT / ONVIF feeds and the satellite path. `CLAIMS.md` tracks every
claim of the SIH deck against this repository; `docs/PRD.md` is the build plan.

## How the decision layer works

1. **Movements.** When a tracked person leaves a camera's view, their pass becomes one movement:
   where they entered and left (a 4 x 3 grid), speed in body-heights per second, time in view,
   how many moved together, how long they were crawling, and whether they crossed a virtual fence.
2. **Score.** `s = -log P(path | camera, hour, day type) - log P(hour) - log P(speed) - log P(dwell)`
   plus crawl and group terms. Sparse cells back off to what the camera usually does, so a quiet
   festival hour is not treated as "everything is unusual". Each term is shown on the alert card.
3. **Budget.** The threshold is recalibrated every night so that on average 12 movements per shift
   pass it; once a shift has used its budget, the rest go to the digest.
4. **Never budgeted.** A fence breach into a restricted zone at night, any fence crossing while the
   border is sealed, and watchlist hits always alert.
5. **Surge mode.** If far more movements than usual pass the threshold within an hour, the budget
   lifts and the commander is told why. Officers can also force it on or off.
6. **Learning period.** For the first 14 days at a new post it scores against a baseline borrowed
   from a post with similar traffic (`borrow_baseline` in `post.json`), or, without one, alerts on
   fence crossings; either way within the shift budget. From day 15 it uses its own baseline,
   refit every night on the last 28 days.
7. **Drift watch.** Operator taps give a weekly precision; below 50% the console asks for a
   re-baseline.

**Stated limit:** someone who moves with the crowd, on the usual path, at the usual hour looks like
the background and will not be flagged. Watch Orders (raise sensitivity on chosen cameras for a set
window) and the shift digest cover that case.

## How to run

Requires Python 3.10+. Tested on a laptop CPU (no GPU needed).

```bash
python -m venv .venv
.venv\Scripts\activate            # Linux/macOS: source .venv/bin/activate
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
python scripts/fetch_assets.py    # demo videos and models (~1.4 GB)
copy config\post.example.json data\post.json   # Linux/macOS: cp config/post.example.json data/post.json
uvicorn app.server:app --port 8000
```

Open `http://localhost:8000/app` for the operations console and `http://localhost:8000/decision`
for ranked alerts. Edit `data/post.json` for your post: virtual fences, restricted zones, haat
days, festivals, seals and the alert budget.

## Benchmark and tests

```bash
python -m benchmark --all          # real results from benchmark/data/ (see benchmark/data/README.md)
python -m benchmark --review-sheet # blind sheet for the 3 reviewers (benchmark/rubric.md)
python -m benchmark --selftest     # synthetic data: checks the code runs; NOT results
python -m pytest -q                # or: python -m unittest discover tests
python -m app.decision.verify      # check this post's ledger and time the check
python scripts/decision_preview.py # the /decision page on synthetic data, no models needed
```

Before the first real run, fix the parameters in `benchmark/prereg.json` and commit it (see
`benchmark/PREREG.md`). Results record the prereg hash and the git commit.

The benchmark replays each day using only earlier days for training (walk-forward) and reports
alerts per shift for a line rule vs Rakshak, staged crossings alerted and logged, lawful crossers
flagged, a surge test and a 5-type tamper test. It writes `benchmark/results/latest.md` with the
SHA-256 of its input files, so every reported number can be traced to its data. It does not
measure detection accuracy, latency or power; those need the models and hardware.

## Sector HQ

```bash
python -m app.decision.verify --pubkey   # on the edge box: this post's public key
# at HQ: hq_data/posts.json = {"BOP07": "<that key>"}
uvicorn hq.server:app --port 9000
```

Set `"hq_url": "http://<hq>:9000"` in the post's `data/post.json`. The post forwards its ledger
whenever the link is up; HQ accepts only entries that extend the post's chain with a valid
signature, and recomputes every hourly Merkle anchor. `POST /api/hq/sms/verify` tells which
post signed an alert SMS.

## Tech stack and licences

Python, FastAPI, WebSockets, OpenCV, ONNX Runtime, SQLite, `cryptography` (Ed25519); vanilla HTML,
CSS and JavaScript. Models: Ultralytics YOLOv8 (AGPL-3.0; a closed deployment needs an Ultralytics
licence, or a switch to YOLOX, Apache-2.0, which is planned) and OSNet for re-identification. Demo
footage includes the MEVA dataset (CC BY 4.0). Every model, dataset and library and its licence is
listed in `THIRD_PARTY.md`.

## Data and privacy

`data/` (incidents, movements, evidence, ledger and the signing key) is never committed. Keep the
signing key on the edge box only; in the field, store it in the box's TPM or an encrypted volume.
