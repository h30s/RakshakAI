# Red-team test: can a crosser get past without an alert?

**Status: protocol only, not run yet.** Deck claim (slide 4): 7 of 10 caught, 3 crowd-blending
misses. Report what you measure, including every miss.

## Rules (fixed before the test)

- **Attackers:** team members who did **not** tune the baseline or the thresholds, briefed only on
  what a villager would know: where the cameras are, not how the score works.
- **Where:** campus, on cameras with at least 14 days of learned baseline. Haat-crowd attempts
  only with the haat permission and on a haat day.
- **10 attempts**, each logged in `benchmark/data/staged.csv` (`staged_id` `RT01`…`RT10`) at the time:
  1–2. crawl across the fence line at night
  3–4. split a group of three: one crosses, two walk the usual path
  5–6. walk with the haat crowd, then step off the path
  7. very slow walk along the fence
  8. cross at the busiest hour, on the usual path
  9. run across a gap in coverage between two cameras
  10. cross during a Watch Order on that camera (should alert)
- **Caught** = an alert within 60 s of the attempt starting. Also report "in the digest only".

## Result table (fill in)

| ID | Tactic | Alerted | In digest | Seconds to alert | Why missed (if missed) |
|---|---|---|---|---|---|
| RT01 | crawl, night | | | | |
| … | | | | | |

`python -m benchmark --all` counts staged events alerted and logged; the "why" column is the team's
judgement from the alert card's score terms. Misses go into the stated limit on the deck and the
README, unedited.
