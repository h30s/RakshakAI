# Pre-registration: fix the rules before looking at the results

Every number we show must come from `python -m benchmark --all`, and the parameters it uses must be
committed **before** it is run on the evaluation days. This is the same "fixed in advance"
principle as the pilot pass criteria (OAT-1…7), applied to ourselves.

## Steps

1. **Split by day.** Decide which recorded days are training and which are evaluation, and write
   the evaluation dates below. Never split by frame.
2. **Fill in `prereg.json`.** Copy `prereg.example.json` and set the parameters. Behaviour
   thresholds (`crawl_low`, `group_min`, `run_speed`) and the baseline weights in
   `app/decision/baseline.py` may be tuned on **training days only**.
3. **Commit and tag.** Commit `prereg.json` and this file, then run `git tag prereg-v1`.
4. **Run once:** `python -m benchmark --all`. The results record the prereg hash and the git commit.
5. **If anything changes afterwards** (a bug fix, new footage), make a new tag (`prereg-v2`) and
   report both runs. Never overwrite a result we didn't like.

## Filled in by the team (before the run)

| Item | Value |
|---|---|
| Training days | _e.g. 2026-10-08 … 2026-10-28_ |
| Evaluation days | _e.g. 2026-10-29 … 2026-11-18 (incl. 3 haat days)_ |
| Footage sources and hours | _MEVA clip list · campus gate · haat_ |
| Staged movements (count, who staged, how logged) | _20; logged in staged.csv at the time_ |
| Reviewers (3, outside the team, blind) | _names kept private; roles only_ |
| Actionable rubric | `benchmark/rubric.md` |
| Commit / tag | _prereg-v1 @ <hash>_ |

## Ablation stages (what each bar on the chart means)

1. **Line rule:** every virtual-fence crossing alerts.
2. **+ Zone rules:** a crossing alerts only if it enters a restricted zone or shows a behaviour flag
   (crawl: `low ≥ crawl_low`, group: `group ≥ group_min`, running: `speed ≥ run_speed`). The
   always-alert rules apply.
3. **+ Baseline:** the movement's score is above the calibrated threshold for this camera, hour and
   day type. The always-alert rules apply; there is no per-shift cap.
4. **+ Budget:** the full system, i.e. stage 3 plus the per-shift cap and surge mode.

Stage 2 can raise **fewer** alerts than stage 4 on some footage (it ignores everything that
doesn't cross a fence). If that happens, report it as it is.
