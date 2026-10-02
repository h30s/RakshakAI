"""Border Pulse: what changed at this post this week, compared with the four weeks before.

Built only from movements.csv (grid cells, times, pseudonymous tracker IDs; no images), per camera:

* new paths      - walked at least `min_new` times this week, never in the previous 4 weeks
* rising paths   - at least `rise` x their usual weekly count (and at least `min_new` times)
* peak shifted   - the busiest hour moved by 2 hours or more, and that hour now carries
                   at least 1.5x its usual share of the week (so chance wobbles are ignored)
* night activity - movements between 22:00 and 05:00, this week vs the usual week
* repeat crossers- the same tracker ID crossing a fence `repeat` or more times in one day; tracker
                   IDs are pseudonymous and reset when the system restarts, so these are leads for
                   review, never an identification
"""
import datetime as dt
import math
from collections import Counter, defaultdict

WEEK = 7 * 86400


def _hour(t):
    return dt.datetime.fromtimestamp(t).hour


def _night(t):
    h = _hour(t)
    return h >= 22 or h < 5


def pulse(movements, now, weeks_before=4, min_new=3, rise=3.0, repeat=3, peak_gain=1.5):
    this = [m for m in movements if now - WEEK <= m.t_start < now]
    before = [m for m in movements if now - (weeks_before + 1) * WEEK <= m.t_start < now - WEEK]
    earliest = min((m.t_start for m in before), default=now - WEEK)
    weeks = max(1, min(weeks_before, math.ceil((now - WEEK - earliest) / WEEK)))  # weeks of history we have
    cameras = sorted({m.camera for m in this} | {m.camera for m in before})
    out = []
    for cam in cameras:
        now_paths = Counter(m.path for m in this if m.camera == cam)
        old_paths = Counter(m.path for m in before if m.camera == cam)
        usual = {p: c / weeks for p, c in old_paths.items()}
        new = [{"path": p, "count": c} for p, c in now_paths.most_common() if c >= min_new and p not in old_paths]
        rising = [{"path": p, "count": c, "usual": round(usual[p], 1)} for p, c in now_paths.most_common()
                  if p in usual and c >= min_new and c >= rise * usual[p]]
        hours_now = Counter(_hour(m.t_start) for m in this if m.camera == cam)
        hours_old = Counter(_hour(m.t_start) for m in before if m.camera == cam)
        peak_now = hours_now.most_common(1)[0][0] if hours_now else None
        peak_old = hours_old.most_common(1)[0][0] if hours_old else None
        # With flat daytime traffic the busiest hour moves by chance; call it a shift only if the new
        # peak hour also carries a clearly larger share of the week than it usually does.
        share_now = hours_now[peak_now] / max(1, sum(hours_now.values())) if peak_now is not None else 0
        share_old = hours_old[peak_now] / max(1, sum(hours_old.values())) if peak_now is not None else 0
        shifted = (peak_now is not None and peak_old is not None
                   and min(abs(peak_now - peak_old), 24 - abs(peak_now - peak_old)) >= 2
                   and share_now >= peak_gain * share_old + 0.02)
        night_now = sum(1 for m in this if m.camera == cam and _night(m.t_start))
        night_usual = sum(1 for m in before if m.camera == cam and _night(m.t_start)) / weeks
        crossings = defaultdict(int)
        for m in this:
            if m.camera == cam and m.crossed and m.person:
                crossings[(m.person, dt.date.fromtimestamp(m.t_start))] += 1
        repeats = [{"person": p, "day": str(d), "crossings": n} for (p, d), n in sorted(crossings.items()) if n >= repeat]
        out.append({
            "camera": cam, "movements": sum(now_paths.values()), "usual_movements": round(sum(usual.values()), 1),
            "paths": [{"path": p, "count": c, "usual": round(usual.get(p, 0), 1)} for p, c in now_paths.most_common(12)],
            "usual_paths": [{"path": p, "usual": round(u, 1)} for p, u in sorted(usual.items(), key=lambda kv: -kv[1])[:12]],
            "new_paths": new, "rising_paths": rising,
            "peak_hour": peak_now, "usual_peak_hour": peak_old, "peak_shifted": shifted,
            "night": night_now, "usual_night": round(night_usual, 1), "repeat_crossers": repeats,
        })
    return {"week_ending": dt.datetime.fromtimestamp(now).isoformat(timespec="minutes"),
            "compared_with_weeks": weeks, "cameras": out}
