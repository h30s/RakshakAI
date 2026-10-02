# Rakshak AI: Build Plan & PRD

**SIH 2026 · PS 26187 · Team RAKSHAKAI TEAM (ID 172311)**
Version 1.0 · 30 Sep 2026 · Status: Active
Owner: _(team lead)_ · Compliance officer: _(Member F)_

> **Why this document exists.** The submitted PPT describes a system with specific features and specific measured numbers. Our goal is to build exactly that system, measure it honestly, and walk into the finale able to prove every line on every slide. **The rule:** a claim is not done until someone can click a link and see the code, the test, or the raw result behind it.

---

## Table of contents

1. [How to use this document](#1-how-to-use-this-document)
2. [Where we stand today](#2-where-we-stand-today-30-sep-2026)
3. [Non-negotiables (disqualification-proofing)](#3-non-negotiables-disqualification-proofing)
4. [Scope and priorities](#4-scope-and-priorities)
5. [Claims ledger: every PPT claim, traced](#5-claims-ledger-every-ppt-claim-traced)
6. [Architecture and tech choices](#6-architecture-and-tech-choices)
7. [Functional requirements by workstream](#7-functional-requirements-by-workstream)
8. [Measurement plan (how every number gets produced)](#8-measurement-plan)
9. [Team, ownership and rituals](#9-team-ownership-and-rituals)
10. [Timeline: 10 weeks](#10-timeline-10-weeks)
11. [Risks and fallbacks](#11-risks-and-fallbacks)
12. [Finale readiness](#12-finale-readiness)
13. [Appendix](#13-appendix)

---

## 1. How to use this document

- This file lives in the repo at `docs/PRD.md`. The live status of each claim lives in `CLAIMS.md` (a copy of §5 with the Status and Evidence columns filled in).
- Every claim from the PPT has an **ID** (e.g. `D3`, `S4`). Use the ID in branch names, commits and PR titles: `feat(D3): alert budget pacing`.
- **Status values:** `TODO` → `PARTIAL` → `BUILT` (code merged + tests) → `MEASURED` (number produced by a script, result file committed).
- If a measured number differs from the PPT, the status is `MEASURED (differs)` and we record the real value. See §3, rule 2.
- Weekly on Sunday: the compliance officer updates `CLAIMS.md` and posts the diff in the team group.

---

## 2. Where we stand today (30 Sep 2026)

This is based on the public repo `github.com/h30s/RakshakAI` (last push 27 Sep). **If anyone has unpushed work, push it this week and update this table.**

| Area | What exists | Gap vs PPT |
|---|---|---|
| Detection | `app/detector.py`: YOLOv8n via `ultralytics` | PPT says YOLOX (Apache-2.0). `ultralytics` is **AGPL-3.0**. Must migrate (see §3, rule 4) |
| Tracking / Re-ID | `app/tracking/`: tracker + OSNet-x0.25 ONNX re-ID | ByteTrack not confirmed; cross-camera needs a metric |
| Sources | `app/sources/`: feeds, phone camera over HTTPS/QR | RTSP/ONVIF discovery and USB need verifying |
| Threats | `app/threats/`: monitor/store, weapon alerts | No scoring, budget, day types, Watch Orders |
| Modes | Night / thermal / fog / rain showcase | Needs LLVIP evaluation numbers |
| UI | Dashboard, reports, phone page, detection modes | No Hindi, no one-tap ack/escalate flow, no score-term card |
| **Not present** | — | Benchmark module, tests, `/study`, hash chain, Ed25519, Merkle, SMS/voice/siren, Egress Guard, ANPR, face, §63 draft, HQ service, C2 APIs, docs (threat model, DPIA, BOM, Hindi card), LICENSE file |

The site `rakshakai.live` currently lists the decision and evidence core as **"Next · Oct–Nov 2026"**. That is honest, so keep the site's roadmap in sync with reality as items land.

---

## 3. Non-negotiables (disqualification-proofing)

These override deadlines. If a task conflicts with a rule, the rule wins.

1. **Build what we submitted.** The finale solution must be the solution in the PPT: same problem, same architecture, same capabilities. No pivots. New ideas go in a `LATER.md` file until every P0 is `BUILT`.

2. **No number without a script, and report the real number.**
   - Every number we show anywhere (finale slides, demo, video, README, website) must come from `python -m benchmark …` or a logged study, saved under `results/` with the git commit hash.
   - If our measured value differs from the submitted PPT, **we present the measured value and say so plainly**: "At submission we reported early results; here is the reproducible number, and here is the script."
   - Never tune on the test set, never edit result files by hand, never cherry-pick footage after seeing results, and never present recorded footage as live. Misrepresentation is a far bigger risk than a number moving.

3. **Pre-register every evaluation.** Before any test-set run, commit `benchmark/PREREG.md` (metric definitions, thresholds, weights, model versions, data manifest hashes) and tag it (`prereg-v1`). This is the same "fixed in advance" principle our OAT slide sells, so we follow it ourselves.

4. **Licences are clean and declared.**
   - Replace `ultralytics` (AGPL-3.0) with **YOLOX (Apache-2.0)**, as the PPT states. Remove it from `requirements.txt` and from any weights we ship.
   - Add a `LICENSE` to the repo (suggest Apache-2.0; team decides in W1).
   - Keep `THIRD_PARTY.md` listing every model, dataset and library with its licence and URL. Check dataset terms (LLVIP, Indian LP dataset, any weapon dataset) before use; if a dataset is research-only, say so in the table.
   - Attribute MEVA (CC BY 4.0) wherever its frames appear.

5. **Filming, data and privacy.**
   - **Never** film BOPs, border fencing, military, paramilitary or police installations, or security personnel on duty. These can be prohibited places, and filming them creates legal risk (Official Secrets Act, 1923). All our footage comes from campus and a local weekly haat.
   - Get written permission before recording (campus administration for the gate; the market committee or local authority for the haat). Display notices while recording. Keep the letters in a private `permissions/` folder (not in the public repo).
   - The public repo never contains raw footage of the public. Publish annotations, clip hashes and manifests only. Blur faces and plates in any published frame, video or slide.
   - Follow our own stated retention policy on our own data: lawful-crossing clips are deleted after 30 days, logs are kept 180 days.

6. **Consent.** Operator-study participants and the 3 reviewers sign consent forms. The watchlist and face demo uses **only team members' faces**, with written consent.

7. **Originality and attribution.** All code is written by the team or clearly attributed. Each member commits from their own GitHub account (git history is evidence of team work). No code from other SIH teams, and no paid or closed code. Cite every paper we use.

8. **No implied endorsement.** Don't imply SSB or MHA endorsement. Don't use SSB/MHA logos beyond the SIH template. Use only public sources, never real or leaked SSB data.

9. **Eligibility and admin.** One person (compliance officer) reads the official SIH 2026 guidelines end to end in W1 and turns them into a checklist in `docs/sih-rules-checklist.md`: team composition (past editions required 6 members including at least 1 female; verify for 2026), student IDs, institute nomination, mentor, finale attendance, member-change rules, and submission deadlines. Re-check whenever SIH publishes an update.

10. **Security hygiene.** No secrets in the repo (keys, tokens, SIM numbers, phone numbers). Device signing keys are generated on the device at install. Run `gitleaks` in CI.

---

## 4. Scope and priorities

| Priority | Meaning | Rule |
|---|---|---|
| **P0** | Shown as working or measured in the PPT. Must work live at the finale with evidence | Nothing else starts until all P0s are at least `BUILT` |
| **P1** | Mentioned as a capability; must exist in a demonstrable basic form | Build after P0 core, before polish |
| **P2** | PPT roadmap items (months 2–12, "subject to approval") | Design notes only. **Do not present as done** |

---

## 5. Claims ledger: every PPT claim, traced

Slide numbers refer to the submitted deck. "WS" is the owning workstream (§9).

### 5.1 PS capabilities and vision (slides 1, 3, 4)

| ID | Claim | Slide | Pri | WS | Evidence required | Status |
|---|---|---|---|---|---|---|
| V1 | Human detection & tracking: recall **0.91 day / 0.84 night** | 4 | P0 | A | `results/detect_recall.json` on labelled sampled frames | PARTIAL |
| V2 | Vehicle detection, **7 classes incl. tractor, e-rickshaw** | 4 | P0 | A | Class list + per-class AP on test split | TODO |
| V3 | Face detection at gates only (IEC 62676-4), **0.93 recall ≤ 6 m** | 4 | P0 | A | Staged gate test at marked distances | TODO |
| V4 | ANPR **87% full-plate** (Indian plates) | 4 | P0 | A | Full-plate accuracy on test set | TODO |
| V4b | Nepali and Bhutanese plates ("next") | 4 | P2 | A | Design note + dataset search | TODO |
| V5 | Virtual fence: polygon per camera, always alerts at night | 4 | P0 | B | Zone editor + test | TODO |
| V6 | Suspicious activity: loiter, crawl, run, group, off-path | 4 | P0 | B | Per-behaviour unit tests + staged clips | TODO |
| V7 | Night movement: IR and thermal, **tested on LLVIP** | 4 | P0 | A | LLVIP recall result | PARTIAL |
| V8 | Real-time alerts, **p95 2.4 s console / 3.1 s SMS**, every event sealed | 2,4 | P0 | D | Latency log ≥ 500 events | TODO |
| V9 | Track within and **across** cameras | 3 | P0 | A | Cross-camera ID-switch/IDF1 on multi-cam clips | PARTIAL |
| V10 | **Watchlist hit** (always-alert class) | 3 | P1 | A | Face match on consenting team members | TODO |
| V11 | **Confirmed weapon** (always-alert class) | 3 | P1 | A | Multi-frame + operator confirmation flow; licence of weapon model checked | PARTIAL |

### 5.2 Decision engine (slides 1–3)

| ID | Claim | Slide | Pri | WS | Evidence required | Status |
|---|---|---|---|---|---|---|
| D1 | Score `s = −log P(path, speed, dwell \| camera, zone, hour, day type) + loiter + crawl + run + group` | 3 | P0 | B | Implementation + tests + doc of weights | TODO |
| D2 | Day types: normal, haat, festival, seal | 2 | P0 | B | Calendar config + UI switch | TODO |
| D3 | **≤ 12 routine alerts per 8 h shift**; critical bypass; **surge mode** lifts cap | 1–5 | P0 | B | Pacing algorithm + tests + OAT-1 result | TODO |
| D4 | Cold start: days 1–14 zone rules + borrowed baseline; day 15+ per-post baseline (camera × zone × hour × day type), refit nightly | 3 | P0 | B | Refit job + test with simulated days | TODO |
| D5 | Drift watch: weekly precision per post from operator taps; re-baseline if < 50% | 3 | P1 | B | Job + dashboard tile | TODO |
| D6 | Score is calibrated, **ECE 0.06** | 2 | P0 | B | Reliability diagram + ECE from benchmark | TODO |
| D7 | Ablation **231 → 88 → 31 → 12** alerts per haat-day shift | 1,2,5 | P0 | F | Benchmark ablation output (bars must be **labelled**, see §8.4) | TODO |
| D8 | Normal day **96 → 11**, night **34 → 9** | 2 | P0 | F | Benchmark output | TODO |
| D9 | **58% vs 4%** alerts actionable (3 independent reviewers) | 2 | P0 | F | Blind rating sheet + kappa | TODO |
| D10 | **19 / 20** staged movements detected | 1 | P0 | F | Staged-event log + benchmark output | TODO |
| D11 | Watch Orders (commander-issued temporary rules) | 4,5 | P1 | B | UI + tests | TODO |
| D12 | Shift digest: all non-alerted detections stay logged and reviewable | 2 | P0 | D | Digest page + test | TODO |
| D13 | Ranked alert card shows every score term | 2 | P0 | D | UI screenshot + test | TODO |

### 5.3 Evidence and security (slides 3, 4, 6)

| ID | Claim | Slide | Pri | WS | Evidence required | Status |
|---|---|---|---|---|---|---|
| S1 | **Egress Guard**: cameras on isolated port; vendor call-home blocked and logged | 3,4 | P0 | C | nftables/dnsmasq config + install script + test | TODO |
| S2 | 24-h lab capture on a **₹2,400** camera: **1,146 attempts → 3 hosts, 100% blocked, 0 reached** | 4 | P0 | C | Raw log + summary script output (report real values) | TODO |
| S3 | Seal: signed hash chain; edits caught in **0.3 s** | 3 | P0 | C | `rakshak verify` + timing result | TODO |
| S4 | **Hourly Merkle anchor** per post at Sector HQ | 3,4 | P0 | C | HQ service stores roots; verification test | TODO |
| S5 | **Ed25519-signed SMS**; signature checked on the phone and again at HQ | 3 | P0 | C+D | Verifier app + HQ verify endpoint | TODO |
| S6 | Evidence packet: clip + hash + drafted **BSA §63(4) Part A**; **2 h → 3 min** | 4,5 | P0 | C | Packet generator + timed manual baseline | TODO |
| S7 | Retention: lawful-crossing clips deleted after 30 days; logs 180 days | 4 | P0 | C | Retention job + test | TODO |
| S8 | Repo docs: **threat model, security scan report, DPDP privacy assessment** | 6 | P0 | C | `docs/threat-model.md`, `docs/security-scan/`, `docs/dpia.md` | TODO |

### 5.4 Alerts, comms, UI, integration (slides 2, 3, 5)

| ID | Claim | Slide | Pri | WS | Evidence required | Status |
|---|---|---|---|---|---|---|
| A1 | Duty console on post LAN, **no internet needed**; **Hindi and English** | 2,3 | P0 | D | Offline test (cable pulled) + i18n | PARTIAL |
| A2 | **One tap**: acknowledge / escalate / dismiss (console + phone) | 2,3 | P0 | D | UI + audit log entries | TODO |
| A3 | Duty phone: signed SMS on **2G**, **Hindi voice call**, **post siren relay** | 3 | P0 | D | GSM modem integration + relay demo | TODO |
| A4 | **Store-and-forward** when the link to HQ returns | 3 | P0 | D | Link-down/link-up test | TODO |
| A5 | Same SMS over **satellite phones** SSB already holds | 3,4 | P1 | D | Format fits 160-char SMS limit; field test **not possible**, must be stated as untested | TODO |
| A6 | Shift report drafted; **one signature at handover** | 5 | P1 | D | PDF shift report | TODO |
| A7 | **Border Pulse**: new path, repeat crosser (re-ID), peak shifted | 5 | P1 | B | Weekly view on benchmark footage | TODO |
| A8 | C2 feed over **REST, WebSocket, MQTT, ONVIF Profile M**; tested with **Frigate VMS** | 3 | P0 | D | API docs + Frigate MQTT test log; Profile M metadata stream (do not claim formal conformance) | TODO |
| A9 | SSB's existing **FRS/ANPR hits join the ranked queue** | 3 | P1 | D | Ingest API + mock external hit test | TODO |

### 5.5 Edge, performance, deployment (slides 3, 4)

| ID | Claim | Slide | Pri | WS | Evidence required | Status |
|---|---|---|---|---|---|---|
| E1 | Ingest IP (RTSP/ONVIF), USB and phone feeds; no camera replacement | 3 | P0 | E | Test with each source type | PARTIAL |
| E2 | 2016 laptop i5-6200U, no GPU: **13 feeds, 2.1 fps/feed avg, 6 fps on active** | 3 | P0 | E | `results/perf_i5.json` | TODO |
| E3 | N100 + OpenVINO INT8: **10 feeds, 1 fps idle / 8 fps on motion, 11.6 W** | 3 | P0 | E | `results/perf_n100.json` + power meter photo | TODO |
| E4 | **One-hour install**; works offline | 4 | P0 | E | `install.sh` + timed install video | TODO |
| E5 | **₹32,500 per post + ≈ ₹4,000/yr**; parts list with quotes | 4,6 | P0 | E | `docs/bom.md` with dated vendor quotes | TODO |
| E6 | Signed OTA updates | 5 | P2 | E | Design note only | TODO |

### 5.6 Studies and artifacts (slides 2, 5, 6)

| ID | Claim | Slide | Pri | WS | Evidence required | Status |
|---|---|---|---|---|---|---|
| X1 | Benchmark **72 h = 41 h MEVA + 19 h campus gate + 12 h haat**; `python -m benchmark --all` reproduces slides 2–5 | 2,6 | P0 | F | Working command + manifests + results | TODO |
| X2 | Operator study: events noticed **13 → 23 of 24**; median ack **71 s → 19 s**; protocol + raw logs in `/study` | 5 | P0 | F | `/study/protocol.md`, anonymised logs, analysis script | TODO |
| X3 | Red-team: **7 / 10 caught**, 3 crowd-blending misses | 4 | P0 | F | Red-team log + clips (blurred) | TODO |
| X4 | **146 automated tests** | 3 | P0 | all | CI badge + test count | TODO |
| X5 | 2-hour operator training in Hindi; **Hindi operator card** | 4,6 | P0 | D | `docs/operator-card-hi.pdf` + training deck | TODO |
| X6 | **90-second demo video** at `rakshakai.live/demo` | 6 | P0 | F | Video live | TODO |
| X7 | OAT-1…7 pilot protocol (fixed in advance) | 4 | P1 | F | `docs/pilot-oat.md` (pilot itself is P2) | TODO |
| X8 | Comparison table vs tripwire VMS / typical AI prototype | 6 | P1 | F | Replace "Varies" with named products and honest ✓/✗ in future materials | TODO |

---

## 6. Architecture and tech choices

### 6.1 Per-post system (one edge box per BOP)

```
 Cameras (RTSP/ONVIF, USB, phone)
        │   isolated NIC / VLAN
        ▼
 ┌──────────────── Egress Guard (nftables + dnsmasq + chrony) ────────────────┐
 │  camera subnet → WAN: DROP + LOG      cameras get local NTP/DNS only       │
 └────────────────────────────────────────────────────────────────────────────┘
        ▼
 1 DETECT ── YOLOX (OpenVINO INT8) · YuNet faces · plate detector + OCR
        ▼       motion gate: 1 fps idle → 8 fps on motion
 2 TRACK ─── ByteTrack per camera · OSNet re-ID across cameras
        ▼
 3 SCORE ─── baseline model (camera × zone × hour × day type) + behaviour terms
        ▼       calibrated → P(actionable)
 4 BUDGET ── pacing to ≤12 routine / 8 h · always-alert bypass · surge mode
        ▼
 5 SEAL ──── SHA-256 hash chain · Ed25519-signed records · clip hashes
        │
        ├──► Duty console (FastAPI + WebSocket, LAN only, Hindi/English)
        ├──► Duty phone (GSM modem: signed SMS · Hindi voice call) · siren relay
        ├──► Outbox (store-and-forward) ──► Sector HQ service
        └──► C2 feeds: REST · WebSocket · MQTT · ONVIF Profile M metadata

 Sector HQ service: receives hourly Merkle roots + events · verifies signatures ·
 audit UI · Border Pulse · accepts external FRS/ANPR hits into the queue
```

### 6.2 Tech choices and licences

Verify each licence when adding it to `THIRD_PARTY.md`.

| Purpose | Choice | Licence |
|---|---|---|
| Object detection | YOLOX-Nano/Tiny/S → ONNX → OpenVINO INT8 (NNCF) | Apache-2.0 |
| Tracking | ByteTrack | MIT |
| Re-ID | OSNet (deep-person-reid), already in repo | MIT |
| Face detection | YuNet (OpenCV Zoo) | check (MIT expected) |
| Face match (watchlist) | SFace (OpenCV Zoo) | check (Apache-2.0 expected) |
| Plate OCR | PaddleOCR, or a small CRNN we train | Apache-2.0 |
| Backend | Python, FastAPI, SQLite, OpenCV, ONNX Runtime | MIT / PD / Apache-2.0 / MIT |
| Crypto | `cryptography` or PyNaCl, Ed25519 (RFC 8032) | Apache/BSD |
| MQTT | Mosquitto + paho-mqtt | EPL-2.0 / EDL-1.0 |
| GSM | USB modem (SIM7600 / SIM800 class) via `pyserial` AT commands | BSD |
| Network guard | nftables, dnsmasq, chrony on Debian/Ubuntu | GPL (system tools, not linked) |
| RTSP test server | MediaMTX (replays recorded footage as cameras) | MIT |
| Labelling | CVAT | MIT |
| Quality | pytest, GitHub Actions, bandit, pip-audit, gitleaks, trivy | various OSS |

### 6.3 Repo layout (target)

```
rakshak/                 # was app/ — migrate incrementally
  ingest/  detect/  track/  anpr/  face/
  score/   budget/  watch/  seal/  alerts/
  comms/   c2/      egress/ console/ hq/  pulse/
benchmark/               # python -m benchmark --all
  __main__.py  manifests/  PREREG.md
results/                 # generated, committed with commit hash
study/                   # operator study protocol, anonymised logs, analysis
docs/                    # PRD, threat model, DPIA, BOM, operator card, security scan
tests/
install.sh  LICENSE  THIRD_PARTY.md  CLAIMS.md
```

---

## 7. Functional requirements by workstream

Each requirement lists **acceptance criteria (AC)**. A requirement is `BUILT` only when all of its ACs pass in CI or have a documented manual test.

### WS-A · Vision (V1–V4, V7, V9–V11)

**A-1 Detector migration (YOLOX).** Replace `ultralytics` with YOLOX exported to ONNX, running under ONNX Runtime (laptop) and OpenVINO INT8 (N100).
- AC: `ultralytics` absent from `requirements.txt` and from the code; the same detection API is used by the pipeline; the mAP drop vs FP32 after INT8 is ≤ 2 points on our dev set.

**A-2 Vehicle classes (V2).** Freeze the 7 classes in W1 (proposal: car, motorcycle, bicycle, bus, truck, tractor, e-rickshaw/auto).
- Collect and label ≥ 300 instances each of tractor and e-rickshaw (campus road, haat approach). Fine-tune YOLOX.
- AC: per-class AP reported on a held-out split; the class list matches the slide.

**A-3 Face detection (V3).** YuNet at the gate camera only. Mark distances of 1–6 m on the ground; team members walk through.
- AC: recall at ≤ 6 m reported; pixel density at 6 m computed and compared with IEC 62676-4 tiers (the "identify" tier is 250 px/m). Placement guidance goes in `docs/camera-placement.md`.

**A-4 ANPR (V4).** Plate detector (YOLOX fine-tuned) + OCR + Indian format validator (state code, RTO, series, number).
- AC: full-plate accuracy (all characters correct) on the Indian LP test set and on our own gate footage, reported separately. Plates are blurred in anything published.

**A-5 Night / thermal (V7).** Evaluate on LLVIP (visible and IR pairs) plus our own night IR footage.
- AC: person recall at IoU ≥ 0.5 for LLVIP IR and our night set.

**A-6 Cross-camera tracking (V9).** ByteTrack per camera; OSNet embeddings for handoff between cameras.
- AC: IDF1 reported on a 2-camera staged clip set.

**A-7 Watchlist (V10).** SFace matching against an enrolled list (consenting team members only). A match raises an always-alert.
- AC: TPR at a fixed FPR on staged clips; the enrolment UI requires a "consent recorded" checkbox and logs who enrolled whom.

**A-8 Weapon confirmation (V11).** A weapon counts only after N of M frames agree, then the operator confirms. Check and record the weapon model's licence and training-data licence.
- AC: the confirmation flow is tested; the false-alarm rate on normal footage is reported.

### WS-B · Decision engine (V5, V6, D1–D7, D11, A7)

**B-1 Zones (V5).** Per-camera polygon editor in the console (fence, path, road, field). The fence zone at night is an always-alert.
- AC: zones saved per camera; a crossing test clip triggers exactly one alert per crossing track.

**B-2 Behaviour terms (V6).** loiter (dwell > T in a sensitive zone), crawl (low bounding-box height ratio + slow speed), run (speed z-score > k), group (≥ N co-moving tracks), off-path (low path probability).
- AC: one unit test per behaviour on synthetic tracks and one staged clip per behaviour.

**B-3 Baseline model (D1, D4).**
- Discretise each camera view into a grid. For each (camera, zone, hour bucket, day type) keep smoothed histograms: a path cell-transition model, speed, and dwell.
- `−log P` = sum over path transitions + speed + dwell (independence assumption, documented).
- Cold start (days 1–14): zone rules + budget + baseline borrowed from the most similar post profile.
- Nightly refit at 02:00 on the last 28 days.
- AC: the refit job is idempotent and tested; the model file is versioned; the score for a novel path is higher than for a common path (tested).

**B-4 Weights and calibration (D1, D6).** Behaviour weights are set on the **dev** split only and frozen in `PREREG.md`. Isotonic regression maps the raw score to P(actionable). Display score is 1–5.
- AC: reliability diagram + ECE (10 bins) computed on the **test** split by the benchmark.

**B-5 Budget pacing (D3).** Routine target of ≤ 12 per 8-h shift.
- Threshold τ is initialised from the score distribution of the same day type so that the expected count equals 12. It is adjusted online: raised if we are ahead of pace, lowered if behind. Items below τ go to the digest.
- Always-alert classes (night fence breach, crossing during a seal, watchlist hit, confirmed weapon) bypass the budget.
- **Surge mode:** if high-score events in the last 30 min exceed X × the baseline rate, the cap is lifted and the commander is notified. This is logged.
- AC: simulation tests covering a normal day, a haat day, a surge night and all-critical cases; routine count ≤ 12 in non-surge simulations.

**B-6 Day types and Watch Orders (D2, D11).** Day type comes from a calendar (weekly haat day, festival list, seal dates) and can be overridden by the commander. Watch Orders are time-bound rules (camera/zone, object type, attributes such as vehicle class or plate prefix, a priority boost or always-alert, and an expiry).
- AC: an expired order has no effect; every order change is written to the sealed log.

**B-7 Drift watch (D5).** Weekly precision per post comes from operator taps (acknowledged-actionable vs dismissed).
- AC: a re-baseline flag is raised when precision < 50% (tested with synthetic taps).

**B-8 Border Pulse (A7, P1).** A weekly heat map of paths vs the previous 4 weeks, showing new paths, repeat crossers (re-ID) and peak-hour shifts.
- AC: renders on benchmark footage; re-ID data follows the retention rules.

### WS-C · Evidence and security (S1–S8)

**C-1 Egress Guard (S1, S2).** Cameras sit on a dedicated NIC/VLAN. nftables drops and logs all camera → WAN traffic. dnsmasq answers camera DNS queries locally and logs the names. chrony serves NTP locally so cameras don't need the internet.
- AC: `install.sh` sets it up; a test camera cannot reach the internet (verified with packet capture); the log summary script outputs attempts, distinct hosts and blocked counts.
- **24-h capture:** buy a ₹2,400-class IP camera, factory reset it, capture for 24 h, and publish the summary. **Our numbers will depend on the camera; publish what we see.**

**C-2 Hash chain + signatures (S3).** Each record is `h_i = SHA-256(h_{i−1} ‖ canonical_json(record_i))` and signed with the device's Ed25519 key. Records include the clip's SHA-256.
- AC: `rakshak verify` detects any single-byte edit in a record or clip; the time to verify one full shift is measured and reported.

**C-3 Merkle anchor (S4).** Every hour the device computes a Merkle root over that hour's record hashes, signs it and sends it to HQ. If the data link is down, the 32-byte root goes by SMS (it fits); it also goes in the outbox.
- AC: HQ verifies the roots; a tampered past record fails against the anchored root (tested).

**C-4 Evidence packet + §63(4) Part A (S6).** One click produces a ZIP with the clip, hashes, chain proof and a pre-filled BSA 2023 §63(4) certificate Part A (PDF). Part B is left for the expert.
- AC: packet generation time is measured; the manual baseline (export clip from a VMS, hash it, fill the form by hand) is timed with a team member, and both are reported honestly.

**C-5 Retention (S7).** A daily job deletes clips of lawful crossings (non-alerted, not flagged) older than 30 days and logs older than 180 days. **Sealed evidence attached to an incident is exempt.**
- AC: the job is tested with fake timestamps; deletions are themselves logged.

**C-6 Docs (S8).**
- Threat model using STRIDE per component, including box theft, clip edits, camera compromise, SMS spoofing and insider misuse.
- Security scan: bandit + pip-audit + trivy output, with fixes.
- DPIA under the DPDP Act, 2023 (purpose, data minimisation, retention, access, re-ID risks).
- AC: all three are in `docs/` and linked from the README.

### WS-D · Alerts, console, comms, integration (V8, D12, D13, A1–A6, A8, A9)

**D-1 Console (A1, A2, D12, D13).** Runs on the post LAN with no internet. Hindi/English toggle. The alert queue is ranked; each card shows the clip, track, and every score term with its contribution. One-tap acknowledge / escalate / dismiss, each written to the sealed log. Shift digest page.
- AC: works with the WAN cable unplugged; all strings are externalised (i18n); a native Hindi speaker reviews the text.

**D-2 SMS (A3, S5).** Format ≤ 160 GSM-7 characters, for example:
  `RKSHK-07|A0417|C3Z2|0214|FENCE-NIGHT|<86-char base64url Ed25519 sig>`
  (a 64-byte signature is 86 characters in base64url, leaving 74 for the payload).
- A verifier Android app (offline) reads the SMS, checks it against the post public key provisioned by QR at install, and shows ✓/✗ plus Acknowledge / Escalate buttons (which reply by SMS).
- AC: tested on a 2G-only network setting; forged or modified SMS is rejected.

**D-3 Voice call and siren (A3).** Hindi voice call built from pre-recorded Hindi audio prompts (alert type, camera, zone) played through the modem. Siren via a USB/GPIO relay.
- **Spike in W2.** If modem audio playback proves infeasible, fall back to a call with a distinctive ring pattern plus SMS content, and **state the limitation honestly**.

**D-4 Store-and-forward (A4).** Outbox table; exponential retry; HQ acknowledges by hash.
- AC: 30 min link-down test: nothing lost, nothing duplicated.

**D-5 C2 integration (A8, A9).**
- REST: events, clips, verify. WebSocket: live alerts. MQTT: Frigate-compatible topics.
- ONVIF Profile M-style metadata stream. Say "Profile M metadata", not "Profile M conformant"; formal conformance is an ONVIF process.
- Ingest endpoint for external FRS/ANPR hits, which enter the ranked queue.
- AC: API documented (OpenAPI); a Frigate instance consumes our MQTT events (test log saved); a mock external hit appears in the queue.

**D-6 Latency (V8).** Timestamp at frame capture → alert rendered in the browser (the browser reports back) and → modem `+CMGS` OK.
- AC: p50/p95 over ≥ 500 events, reported per device.

**D-7 Shift report + Hindi operator card (A6, X5).** PDF shift report with one signature line; an A5 laminated-style Hindi quick card; 2-hour training slides in Hindi.

### WS-E · Edge, performance, install (E1–E5)

**E-1 Ingest (E1).** RTSP with ONVIF discovery, USB (V4L2 / DirectShow) and phone (existing).
- AC: one test per source type; reconnect after a camera reboot.

**E-2 Performance (E2, E3).** Motion gating (frame differencing) so idle feeds run at 1 fps and active feeds at up to 8 fps; batched inference.
- A harness replays recorded footage as N RTSP cameras through MediaMTX.
- AC: `results/perf_*.json` records per-feed fps, CPU and RAM; power is measured with a wall meter (photo kept). Report what we measure on both machines.

**E-3 Install (E4).** `install.sh` on a fresh Debian/Ubuntu N100: dependencies, services, Egress Guard, key generation, console URL.
- AC: a timed run from a blank disk is recorded on video.

**E-4 BOM (E5).** `docs/bom.md` with line items, dated vendor quotes (screenshots or PDFs), per-post total and annual running cost (SIM, power, maintenance).
- If the real total differs from ₹32,500, **update it and say why**.

### WS-F · Benchmark, studies, compliance (D7–D10, X1–X3, X6–X8)

See §8. Member F also owns `CLAIMS.md`, the SIH rules checklist, permissions and consent paperwork.

---

## 8. Measurement plan

### 8.1 Data collection (critical path, **start in Week 1**)

| Set | Target | Notes |
|---|---|---|
| MEVA | 41 h of outdoor clips | CC BY 4.0. Clip IDs go in `benchmark/manifests/meva.csv`; a download script fetches them. Anyone can reproduce this part |
| Campus gate | 19 h **eval** + ≥ 2 weeks of **training** footage | The baseline needs history. Record continuously for ≥ 3 weeks with permission; hold out the eval days |
| Weekly haat | 12 h **eval** + ≥ 3 earlier haat days for training | A local haat, not near the border. Weekly means only ~4 haat days in a month, so **begin now** |
| Staged movements | 20 events (crawl, run, loiter at "fence", off-path, night crossing, group split, vehicle off-route) | Scripted by team members, timestamps logged, spread across eval footage (campus + haat with permission) |
| LLVIP | Night detection eval | Check licence terms first |
| Indian LP dataset (arXiv 2111.06054) + own gate plates | ANPR eval | Check licence; blur in any publication |
| Face gate set | Team members at marked 1–6 m distances | Consent forms |

**Splits:** by **day**, never by frame. The test split is hashed and frozen in `PREREG.md` before first use.

**Public reproducibility:** campus and haat footage cannot be public. `python -m benchmark --all` runs everything on the team's machines. The public version runs the MEVA portion plus our published annotations and hashes. The README says this plainly, and judges can get the full-data results offline on request.

### 8.2 Labelling

- CVAT. Detection recall uses sampled frames (e.g. 1 frame per 10 s, ~1,500 day + 1,000 night frames), not every frame.
- Events: label start/end, type, and "actionable yes/no" (per the rubric) only for alerts and staged events.
- Two labellers on 10% of the data for an agreement check.

### 8.3 Metric definitions (these go into PREREG.md)

| Metric | Definition |
|---|---|
| Detection recall | TP / (TP + FN) at IoU ≥ 0.5, conf ≥ fixed threshold, day and night separately |
| Full-plate accuracy | Plate string exactly correct / plates with readable ground truth |
| Alerts per shift | Routine alerts in an 8-h window on eval footage (critical counted separately) |
| Line-rule baseline | One alert per track crossing the fence polygon (a classic tripwire) |
| Actionable % | Share of alerts rated actionable by the majority of 3 blind reviewers (rubric in `benchmark/rubric.md`); report Fleiss' κ |
| Staged detection | Staged event produced an alert within 30 s (also report "alert or digest", which is OAT-4) |
| ECE | 10 equal-width bins, test split |
| Latency | Capture → console render; capture → modem OK; p50/p95, ≥ 500 events |
| Edit detection time | Wall time for `rakshak verify` over one shift's chain after a single-byte edit |

### 8.4 The ablation (D7): label the bars this time

The submitted chart's x-axis read 1.0–4.0 with no names. Define the bars in PREREG. Proposal (adjust if the original intent differed, but write it down before running):

1. **Line rule:** tripwire on the fence polygon
2. **+ Zones & behaviours:** zone rules + loiter/crawl/run/group
3. **+ Learned baseline:** −log P for camera × zone × hour × day type
4. **+ Budget:** pacing to ≤ 12 routine; critical bypass

All four run on the same haat-day eval footage and cameras.

### 8.5 Reviewer rating (D9)

- 3 reviewers **outside the team** (faculty, NCC officers, ex-servicemen, campus security supervisors).
- They see mixed, shuffled alert clips from both systems and **don't know which system produced each one**. They rate with the rubric.

### 8.6 Operator study (X2)

- **Participants:** 6 campus security guards, consented and compensated. Get your faculty mentor's sign-off, and institute ethics approval if your institute requires it.
- **Design:** within-subjects. Two matched night-footage sets (A and B) of 2 h each with 24 staged events each. Conditions: 16-feed video wall vs Rakshak queue, on different days, counterbalanced (condition × set).
- **Training:** 2 h in Hindi.
- **Measures:** events noticed (acknowledged within 60 s of onset) and time to acknowledge. Report medians and ranges per condition.
- Commit the protocol **before** running (`study/protocol.md`). Anonymised raw logs and the analysis script go in `/study`.

### 8.7 Red-team (X3)

- 10 attempts by members **not** involved in tuning: crawl, split group, blend into the haat crowd, very slow walk, off-hours crossing.
- Log caught/missed with clips. Publish the misses too.

### 8.8 Tests (X4)

- pytest runs in CI on every PR, with a badge in the README.
- The target is ≥ 146 **meaningful** tests (not padding). Priority areas: scoring, budget, seal/verify, SMS format, retention, zones, APIs.

---

## 9. Team, ownership and rituals

| Member | Workstream | Also owns |
|---|---|---|
| A | WS-A Vision | Model licences in THIRD_PARTY.md |
| B | WS-B Decision engine | PREREG weights and thresholds |
| C | WS-C Evidence & security | Threat model, DPIA, security scan |
| D | WS-D Console, comms, integration | Hindi UI, operator card, Android verifier |
| E | WS-E Edge & performance | Hardware purchase, BOM, install script |
| F | WS-F Benchmark & studies | **Compliance officer**: CLAIMS.md, SIH rules, permissions, consent |

Pick one **integration lead** (usually the team lead), who owns `main`, releases and the demo kit.

**Rituals**
- **Mon, 20 min:** plan the week using claim IDs.
- **Thu:** 30-min internal demo; must run on the N100, not a dev laptop.
- **Sun:** update CLAIMS.md; the compliance officer flags anything at risk.
- **PRs:** one reviewer minimum; CI green; claim ID in the title.

---

## 10. Timeline: 10 weeks

Assumes a finale in early–mid December. **Re-plan as soon as SIH publishes official dates.** Diwali (~8 Nov) week is planned light.

| Week | Dates | Goals | Exit check |
|---|---|---|---|
| **W1** | 1–7 Oct | Read SIH rules → checklist · LICENSE, THIRD_PARTY, CI, pytest skeleton, CLAIMS.md · **permission letters (campus, haat)** · **order hardware** (§12.2) · freeze 7 vehicle classes and ablation bar definitions · YOLOX spike | Permissions requested; hardware ordered; CI green |
| **W2** | 8–14 Oct | **Start campus recording** · YOLOX + ByteTrack in pipeline (`ultralytics` removed) · RTSP/ONVIF/USB ingest · hash-chain + Ed25519 library · GSM modem SMS + **voice spike** · zone editor | Detector swapped; first signed record verifies |
| **W3** | 15–21 Oct | Haat recording #1 · scoring v0 · budget v0 · alert card with score terms · one-tap actions · Egress Guard on N100 · SMS verifier app v0 · **staged movements session 1** | End-to-end: detection → alert → signed SMS on phone |
| **W4** | 22–28 Oct | Haat #2 · ANPR · YuNet faces · vehicle fine-tune · baseline fit + nightly refit · day types · Watch Orders · Hindi UI · staged session 2 | All 8 PS capabilities run (unmeasured) |
| **W5** | 29 Oct–4 Nov | Haat #3 · OpenVINO INT8 + motion gating · store-and-forward · HQ service + Merkle anchor · §63 Part A packet · shift digest · REST/WS/MQTT · **Egress 24-h capture** | Link-down test passes; Egress summary produced |
| **W6** | 5–11 Nov (Diwali) | Calibration · surge mode · drift watch · voice/siren finalised · Frigate test · retention job · labelling sprint | All P0 features `BUILT` |
| **W7** | 12–18 Nov | Haat #4 (eval) · **commit PREREG + tag** · run benchmark · perf + power + latency measurements | `results/` populated; CLAIMS.md shows real numbers |
| **W8** | 19–25 Nov | **Reviewer rating · operator study · red-team** · SFace watchlist · weapon confirmation | Studies done; raw logs committed |
| **W9** | 26 Nov–2 Dec | Docs: threat model, DPIA, security scan, BOM with quotes, Hindi card, training deck · Border Pulse · shift report · **90-s demo video** · update README and site with **measured** numbers | Every P0 claim `MEASURED` or honestly marked |
| **W10** | 3–9 Dec | Code freeze · demo kit packed · 3 full rehearsals (one with no internet, one with a hostile Q&A panel) · backup video | Finale-ready checklist (§12.1) all ticked |

**Critical path:** haat footage (weekly), permissions, and hardware delivery. If any of them slips by more than 1 week, the team lead re-plans that same day.

---

## 11. Risks and fallbacks

| Risk | Impact | Fallback |
|---|---|---|
| Haat permission refused or delayed | No haat-day data → D7, D9 at risk | Use a high-traffic campus event day as the "haat" day type and **label it as such**; keep asking for haat permission |
| Measured numbers worse than the PPT | Credibility | Report the real numbers with the script (§3, rule 2). Explain what we learned and what we changed. Judges respect reproducibility |
| YOLOX accuracy below YOLOv8 | V1/V2 numbers drop | Try YOLOX-S or RT-DETR (Apache-2.0 implementations); never ship AGPL weights |
| Tractor / e-rickshaw data scarce | V2 incomplete | Collect on the haat approach road; augment; report per-class AP even if low |
| Modem voice audio infeasible | A3 "Hindi voice call" | Ring pattern + SMS; state the limitation honestly |
| N100 can't hold 10 feeds at the targets | E3 | Smaller model, stricter motion gating, fewer feeds; report the real count |
| Satellite SMS can't be field-tested | A5 | Show format compatibility; say "untested on satellite" |
| Exams / mid-sems overlap | Velocity | Plan exam weeks at 50% capacity; pair members across workstreams |
| Hardware delivery delays | E2–E4, S2 | Order in W1 from 2 vendors; use a laptop as a stand-in N100 until it arrives |
| Scope creep | P0 slips | New ideas go in LATER.md; the team lead says no |

---

## 12. Finale readiness

### 12.1 Checklist

- [ ] Every P0 in CLAIMS.md is `MEASURED`, or `BUILT` with an honest note
- [ ] `python -m benchmark --all` runs cleanly on the demo laptop (with the full data offline)
- [ ] The public repo has LICENSE, THIRD_PARTY.md, README with reproducibility notes, CI badge, docs/, study/, results/
- [ ] No AGPL components; no secrets; no raw public footage in the repo
- [ ] Permissions and consent forms filed (private)
- [ ] The website and demo video show measured numbers only
- [ ] Demo works with **no internet** (the finale venue network will be unreliable, and that suits our pitch)
- [ ] Backup: demo video on 2 USB drives + phone
- [ ] SIH rules checklist re-verified in the final week

### 12.2 Demo kit (buy in W1; approximate prices, confirm with quotes)

| Item | Qty | Approx. |
|---|---|---|
| Intel N100 mini PC, 16 GB RAM | 1 | ₹15–20k |
| ₹2,400-class IP camera (also used for the Egress Guard capture) | 2 | ₹5k |
| USB GSM modem (voice-capable) + 2G/4G SIM | 1 | ₹2–4k |
| USB/GPIO relay + buzzer/siren | 1 | ₹0.5–1k |
| USB Ethernet adapter (isolated camera port) or small managed switch | 1 | ₹1–3k |
| Plug-in power meter | 1 | ₹0.8k |
| Android phone (verifier app) | 1 | existing |

### 12.3 Demo script (~7 minutes)

1. **Plug in a camera** → Egress Guard log shows vendor call-home attempts blocked live.
2. **Live crossing** of a virtual fence by a team member → an always-alert fires.
3. **Replay haat-day footage** (clearly labelled "recorded") → the line rule floods the screen; Rakshak's queue stays calm; open the ablation chart with labelled bars.
4. **Open an alert card** → every score term visible → one-tap Escalate → the phone receives a signed SMS → verifier shows ✓ → siren sounds.
5. **Pull the network cable** → the console keeps working → events queue → plug back in → HQ syncs and verifies the Merkle root.
6. **Tamper test:** edit one byte of a clip → `rakshak verify` fails, with the measured time shown.
7. **Evidence packet** → ZIP with clip, hashes and the §63(4) Part A draft.
8. **Close** on `results/` and CLAIMS.md: "Every number you saw has a script."

### 12.4 Questions to rehearse

1. "Run the benchmark now." → Have it ready, and know how long it takes.
2. "Your submitted slide said X; you now show Y. Why?" → Answer honestly: early estimate vs reproducible result, and what changed.
3. "Where does a watchlist hit come from?" → SFace on the gate camera; enrolled with consent; external SSB FRS hits via the ingest API.
4. "Six campus guards: why does that transfer to SSB?" → Acknowledge the limit; that is why the pilot OAT exists.
5. "How are the behaviour weights set?" → Dev split, frozen in PREREG, tag link.
6. "A new post with no similar post?" → Zone rules + budget until 14 days of history exist; the drift watch catches problems.
7. "Nepali plates?" → Roadmap (V4b); explain the plan and data sourcing.
8. "What if the box is stolen?" → Keys on the device, hourly roots already at HQ, so tampering is detectable; disk encryption option.
9. "Why not a real blockchain?" → Posts are offline; a signed hash chain + Merkle anchoring gives tamper evidence without needing connectivity.
10. "What happens to villagers' data?" → DPIA, 30-day deletion, no face storage outside gates, re-ID retention limits.

---

## 13. Appendix

### 13.1 Definition of done (per claim)

- [ ] Code merged to `main` with tests; CI green
- [ ] Docs updated (README or `docs/`)
- [ ] If a metric: produced by a script, result in `results/` with commit hash, PREREG respected
- [ ] CLAIMS.md row updated with a status and an evidence link
- [ ] Demo step exists (if user-visible)

### 13.2 Commit and branch conventions

- Branch: `feat/D3-budget-pacing`, `fix/S3-verify-timing`
- Commit: `feat(D3): pace threshold to shift budget`
- Results commit: `results(D7): ablation on haat eval, prereg-v1`

### 13.3 CLAIMS.md row template

```
| ID | Claim | PPT value | Measured value | Status | Evidence | Owner | Updated |
|----|-------|-----------|----------------|--------|----------|-------|---------|
| D7 | Haat-day alerts, line rule → Rakshak | 231 → 12 | _ → _ | TODO | results/ablation.json | B | 2026-10-__ |
```

### 13.4 References to keep in the README

MEVA (CC BY 4.0) · LLVIP (ICCV-W 2021) · YOLOX (2021) · ByteTrack (ECCV 2022) · OSNet (ICCV 2019) · YuNet / SFace (OpenCV Zoo) · Indian LP dataset (arXiv 2111.06054) · BSA 2023 §63(4) · DPDP Act 2023 · IEC 62676-4 · ONVIF Profile M · RFC 8032 · CERT-In Directions 2022 · MeitY CCTV Essential Requirements (Apr 2025).
