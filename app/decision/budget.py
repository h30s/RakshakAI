"""Alert budget: a fixed amount of operator attention per shift, spent on the most unusual movements.

* Threshold. Calibrated from past days so that, on average, `per_shift` movements per shift score
  above it (default 12 per 8-hour shift). Re-run calibrate() nightly.
* Cap. Once a shift has used its budget, further movements go to the shift digest instead,
  unless an always-alert rule or surge mode applies.
* Always alert (never budgeted): a virtual-fence crossing into a restricted zone at night,
  any fence crossing while the border is sealed, and a person on the watchlist.
* Surge mode. If far more movements than usual cross the threshold within an hour (seal nights,
  festivals, a coordinated crossing), the cap is lifted and the commander is told why.
* Watch Orders. An officer with a tip-off lowers the threshold on chosen cameras for a set window.
* Digest. Everything not alerted is kept, so nothing is lost - only not interrupted for.
* Learning mode (no threshold yet). Fence crossings alert, but within the same per-shift budget;
  the always-alert rules still bypass it.
"""
import datetime as dt
from collections import defaultdict, deque
from dataclasses import dataclass

ALERT, DIGEST = "alert", "digest"


def shift_of(t, shift_hours=8, first_shift_hour=6):
    """(date, shift number) of a timestamp; shifts start at first_shift_hour (06-14, 14-22, 22-06)."""
    when = dt.datetime.fromtimestamp(t) - dt.timedelta(hours=first_shift_hour)
    return when.date(), when.hour // shift_hours


def is_night(t, start=22, end=5):
    h = dt.datetime.fromtimestamp(t).hour
    return h >= start or h < end


@dataclass
class WatchOrder:
    camera: str
    until: float
    factor: float = 0.6  # threshold multiplier while active (lower = more sensitive)
    reason: str = ""


class SurgeDetector:
    """Surge = above-threshold movements in the last `window_s` exceed `k` x (usual rate for that hour + 1)."""

    def __init__(self, window_s=3600, k=3.0, min_events=6):
        self.window_s, self.k, self.min_events = window_s, k, min_events
        self.usual = defaultdict(float)  # hour -> mean above-threshold movements per hour
        self.recent = deque()
        self.active_since = None
        self.last_over = None
        self.manual = None  # True/False when a commander forces it, None = automatic

    def calibrate(self, above_times, n_days):
        counts = defaultdict(int)
        for t in above_times:
            counts[dt.datetime.fromtimestamp(t).hour] += 1
        self.usual = defaultdict(float, {h: c / max(1, n_days) for h, c in counts.items()})

    def limit(self, t):
        return max(self.min_events, self.k * (self.usual[dt.datetime.fromtimestamp(t).hour] + 1))

    def observe(self, t, above):
        if above:
            self.recent.append(t)
        while self.recent and t - self.recent[0] > self.window_s:
            self.recent.popleft()
        if self.manual is not None:
            self.active_since = (self.active_since or t) if self.manual else None
            return self.active
        if len(self.recent) >= self.limit(t):
            self.active_since, self.last_over = self.active_since or t, t
        elif self.active_since and t - self.last_over > self.window_s:  # an hour back under the limit
            self.active_since = None
        return self.active

    @property
    def active(self):
        return self.active_since is not None

    def reason(self, t):
        return (f"Surge: {len(self.recent)} unusual movements in the last {self.window_s // 60} min; "
                f"usual is about {self.usual[dt.datetime.fromtimestamp(t).hour]:.1f}")


class AlertBudget:
    def __init__(self, per_shift=12, shift_hours=8, night=(22, 5)):
        self.per_shift, self.shift_hours, self.night = per_shift, shift_hours, night
        self.threshold = None          # None = not calibrated yet (learning mode: fence rules)
        self.used = defaultdict(int)   # shift -> alerts sent
        self.watch_orders = []
        self.watchlist = set()
        self.surge = SurgeDetector()

    # ------------------------------------------------------------- calibration
    def calibrate(self, history):
        """history: [(t, score)] from past days. Sets the threshold so that on average `per_shift`
        movements per shift score above it, and the usual above-threshold rate for surge mode."""
        if not history:
            return None
        shifts = {shift_of(t, self.shift_hours) for t, _ in history}
        want = self.per_shift * len(shifts)
        scores = sorted((s for _, s in history), reverse=True)
        self.threshold = scores[min(want, len(scores)) - 1] if want < len(scores) else min(scores)
        days = {dt.datetime.fromtimestamp(t).date() for t, _ in history}
        self.surge.calibrate([t for t, s in history if s >= self.threshold], len(days))
        return self.threshold

    # ------------------------------------------------------------- decisions
    def add_watch_order(self, order):
        self.watch_orders.append(order)

    def _threshold_for(self, camera, t):
        factor = min((w.factor for w in self.watch_orders if w.camera == camera and w.until > t), default=1.0)
        return self.threshold * factor

    def always_alert(self, m, sealed=False):
        """Reason an always-alert rule applies (never budgeted, never suppressed), else None."""
        if m.person and m.person in self.watchlist:
            return "Watchlist person"
        if sealed and m.crossed:
            return "Fence crossing while the border is sealed"
        if m.restricted and m.crossed and is_night(m.t_start, *self.night):
            return "Virtual-fence breach into a restricted zone at night"
        return None

    def decide(self, m, score, sealed=False):
        """(ALERT or DIGEST, reason) for a scored movement, in time order."""
        t = m.t_start
        shift = shift_of(t, self.shift_hours)
        self.watch_orders = [w for w in self.watch_orders if w.until > t]
        critical = self.always_alert(m, sealed)
        if critical:
            return self._send(shift, critical)
        if self.threshold is None:  # cold start: zone rules (fence crossings) within the same budget
            if not m.crossed:
                return DIGEST, "Learning this post's normal"
            if self.used[shift] >= self.per_shift:
                return DIGEST, "Shift budget used; fence crossing in the digest"
            return self._send(shift, "Fence crossing (learning mode)")
        above = score >= self._threshold_for(m.camera, t)
        surge = self.surge.observe(t, above)
        if not above:
            return DIGEST, "Usual for this post and hour"
        if surge:
            return self._send(shift, self.surge.reason(t))
        if self.used[shift] >= self.per_shift:
            return DIGEST, "Shift budget used; ranked in the digest"
        return self._send(shift, "Unusual for this post, hour and day")

    def _send(self, shift, reason):
        self.used[shift] += 1
        return ALERT, reason

