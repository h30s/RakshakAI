# Reviewer rubric: is this alert actionable?

For each row of `sheet.csv`, watch the camera between `start` and `end` (plus 30 s on either
side) and mark **1** or **0** in `actionable`. You are not told which system raised the alert.
Rate every row on its own.

**1 = actionable.** A post commander would reasonably want a sentry to look at it now, for
example:
- crossing the fence line or entering a restricted area, especially at night
- crawling, running away, or a group splitting up near the fence
- loitering at the fence, or moving off the usual path at an unusual hour
- carrying something that looks like a weapon or contraband load

**0 = not actionable.** Ordinary movement a commander would not send anyone for, for example:
- villagers, traders or students walking the usual path at a usual time
- a crowd on a haat day moving normally
- a detection error (no person, a shadow, an animal)

If you are unsure, choose 0 and write why in `notes`.

Return your sheet as `ratings.csv` rows: `item,reviewer,actionable`. Use your reviewer code
(`rev-a`, `rev-b`, `rev-c`), not your name.
