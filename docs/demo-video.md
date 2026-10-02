# 90-second demo video: shot list

Record the **real running system** (screen capture + phone camera). Label replayed footage as
"recorded footage". Save as `static/site/demo.mp4` (H.264, 1280×720, under 20 MB); `/demo` shows it
automatically. Captions in English, voice-over in Hindi or English.

| Time | Shot | What to show | Caption |
|---|---|---|---|
| 0–8 s | Title | Rakshak AI · existing cameras · no GPU | "Alerts you can trust on an open border" |
| 8–20 s | Overview, Cameras | 13 feeds on one laptop CPU; detections | "Existing cameras, one laptop CPU" |
| 20–35 s | `/decision` | A movement off the usual path alerts; open the card; point at the score terms | "Unusual for this post, hour and day" |
| 35–45 s | `/decision` | Budget counter "3 / 12"; the digest below | "At most 12 routine alerts a shift; nothing deleted" |
| 45–55 s | Phone | Signed SMS arrives; paste into `/verify` → Genuine; edit one letter → NOT genuine | "Signed alert, checked on the phone, no internet" |
| 55–65 s | `/decision` | Unplug the network cable; alerts continue; "HQ link down · held"; plug back | "Works with the link down" |
| 65–78 s | Terminal | Edit one byte of a clip; `python -m app.decision.verify` → FAILED; evidence packet ZIP | "Any edit is caught" |
| 78–90 s | `/pulse`, GitHub | Border Pulse new path; CLAIMS.md | "Every claim, with its evidence" |

Don't show any number the repository can't reproduce. Show measured throughput only with its
CPU named (see `benchmark/results/perf_*.json`).
