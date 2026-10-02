# Operator study protocol

**Status: protocol only. The study has not been run.** Commit this file (and any change to it)
**before** the first session; the git history is the proof it was fixed in advance.

Deck claim to test (slide 5): with the same night footage, operators notice more staged events
and acknowledge them faster with the Rakshak queue than with a 16-feed video wall. Deck values:
events noticed 13 → 23 of 24; median time to acknowledge 71 s → 19 s. **We report whatever we
measure.**

## Participants

- 6 campus security guards (or more), each paid for their time.
- Written consent (template below). Participants are told they can stop at any time.
- Faculty mentor signs off; ask whether your institute needs ethics-committee approval.
- Results use codes (`G1`…`G6`), never names.

## Material

- Two matched sets of night footage, **A** and **B**, 2 hours each, from the same cameras, each
  with **24 staged events** (crossing the fence line, crawling, a group splitting, loitering,
  off-path at night). Scripted and timed in advance; the event list lives in `study/events_A.csv`
  and `study/events_B.csv` and is never shown to participants.
- **Condition W (video wall):** 16 feeds in a grid; the guard presses the event key when they
  notice something.
- **Condition R (Rakshak):** the `/decision` queue on the same footage; the guard acknowledges
  alerts and may also press the event key for things they notice on their own.

## Design

- Within-subjects: every guard does both conditions on different days.
- Counterbalanced: G1–G3 do W on set A then R on set B; G4–G6 do R on set A then W on set B.
- 2 hours of training in Hindi first (`docs/operator-card-hi.md`), on footage not used in the test.

## Measures (fixed now)

- **Noticed:** a staged event counts as noticed if the guard pressed the event key or acknowledged
  an alert for that camera within 60 s of the event's start.
- **Time to acknowledge:** from the event's start to that key press or acknowledgement.
- Report per condition: median events noticed (of 24) with the range, and median time to
  acknowledge with the interquartile range. Also report every guard's numbers.

## Logs

One CSV per session in `study/logs/` (anonymised): `guard,condition,set,event_id,event_start_s,noticed_at_s`
(`noticed_at_s` empty if not noticed). `python study/analyse.py` prints the results.

## Consent (template, Hindi and English copies to be signed)

> I agree to take part in a study of a surveillance-console prototype by <team>, <institute>. I
> will watch recorded video for about 2 hours on each of two days and press a key or button when
> I notice certain events. I am paid ₹____ for my time. I can stop at any time without giving a
> reason. My name will not appear in any result. Name / signature / date.
