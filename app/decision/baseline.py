"""Per-post baseline: how unusual is this movement for THIS camera, at THIS hour, on THIS kind of day?

Score (higher = more unusual), every term shown to the operator:

    s = -log P(path  | camera, hour, day type)      "off usual path"
        -log P(hour  | camera, day type)            "unusual hour" (activity level)
        -log P(speed | camera, day type)            "unusual speed"
        -log P(dwell | camera, day type)            "unusual dwell"
        + behavioural terms: crawl/low posture, group size, loitering in a restricted zone

Counts are sparse (camera x hour x day type is hundreds of cells and a festival may have been seen
once), so each probability is smoothed towards its parent level (hierarchical back-off):

    path | cam, hour, day  ->  path | cam, day  ->  path | cam  ->  uniform over paths
    P = (count + a * P_parent) / (total + a)

A cell with no data therefore falls back to what the camera usually does, instead of treating
everything as unusual. The weights of the behavioural terms are defaults to tune per post.

A pooled baseline ignores the camera id. A new post borrows one, learned from a post with similar
traffic, for its first days: the other post's cameras are different, but "most people walk the
usual path at a walking pace in daytime" carries over.
"""
import datetime as dt
import math
from collections import defaultdict

SPEED_BINS = [0.05, 0.15, 0.3, 0.6, 1.0, 1.6, 2.5]    # body-heights per second
DWELL_BINS = [2, 5, 10, 20, 40, 80, 160, 320]          # seconds
N_PATHS = 12 * 12                                      # grid cells squared: prior for unseen paths
CRAWL_WEIGHT, GROUP_WEIGHT = 2.0, 0.5
LOITER_S, LOITER_WEIGHT, LOITER_MAX = 30.0, 2.0, 8.0   # loiter term starts after 30 s in a restricted zone


def _bin(value, edges):
    return sum(1 for e in edges if value >= e)


def hour_of(t):
    return dt.datetime.fromtimestamp(t).hour


class Baseline:
    def __init__(self, alpha=4.0, pooled=False):
        self.alpha = alpha
        self.pooled = pooled
        self.c = defaultdict(lambda: defaultdict(float))  # context key -> {value: count}
        self.days = set()

    # ------------------------------------------------------------- learning
    def add(self, m, day_type):
        h = hour_of(m.t_start)
        cam = self._cam(m)
        for key, value in (
            (("path", cam), m.path), (("path", cam, day_type), m.path), (("path", cam, h, day_type), m.path),
            (("hour", cam), h), (("hour", cam, day_type), h),
            (("speed", cam), _bin(m.speed, SPEED_BINS)), (("speed", cam, day_type), _bin(m.speed, SPEED_BINS)),
            (("dwell", cam), _bin(m.dwell, DWELL_BINS)), (("dwell", cam, day_type), _bin(m.dwell, DWELL_BINS)),
        ):
            self.c[key][value] += 1
        self.days.add(dt.datetime.fromtimestamp(m.t_start).date())

    def add_all(self, movements, day_type_of):
        for m in movements:
            self.add(m, day_type_of(m.t_start))

    def _cam(self, m):
        return "*" if self.pooled else m.camera

    @property
    def days_seen(self):
        return len(self.days)

    # ------------------------------------------------------------- scoring
    def _p(self, chain, value, prior):
        """P(value) smoothed down a chain of context keys, most general first."""
        p = prior
        for key in chain:
            counts = self.c.get(key)
            if counts:
                total = sum(counts.values())
                p = (counts.get(value, 0.0) + self.alpha * p) / (total + self.alpha)
        return p

    def score(self, m, day_type):
        """(total score, {term: contribution}) for a movement."""
        h, cam = hour_of(m.t_start), self._cam(m)
        terms = {
            "off usual path": -math.log(self._p([("path", cam), ("path", cam, day_type), ("path", cam, h, day_type)],
                                                m.path, 1 / N_PATHS)),
            "unusual hour": max(0.0, -math.log(24 * self._p([("hour", cam), ("hour", cam, day_type)], h, 1 / 24))),
            "unusual speed": -math.log(self._p([("speed", cam), ("speed", cam, day_type)],
                                               _bin(m.speed, SPEED_BINS), 1 / (len(SPEED_BINS) + 1))),
            "unusual dwell": -math.log(self._p([("dwell", cam), ("dwell", cam, day_type)],
                                               _bin(m.dwell, DWELL_BINS), 1 / (len(DWELL_BINS) + 1))),
            "low posture / crawl": CRAWL_WEIGHT * m.low,
            "group": GROUP_WEIGHT * max(0, m.group - 2),
            "loiter in restricted zone": (min(LOITER_MAX, LOITER_WEIGHT * m.zone_dwell / LOITER_S)
                                          if m.zone_dwell >= LOITER_S else 0.0),
        }
        terms = {k: round(v, 3) for k, v in terms.items()}
        return round(sum(terms.values()), 3), terms
