"""Movements: one person's pass through one camera, summarised in a few numbers.

The tracker labels every person detection with an ID (d["pid"]). TrackAccumulator collects the
boxes of each (camera, person) and, once the person has left the view for `gap_s` seconds, turns
them into a Movement. Everything is measured in the image, normalised so it does not depend on
resolution or on how far away the person is:

* entry / exit  - which cell of a GRID_COLS x GRID_ROWS grid the path started and ended in
* speed         - median speed in body-heights per second (a person 3x further away moves
                  3x fewer pixels, but also looks 3x smaller, so this stays comparable)
* dwell         - seconds the person was visible
* group         - how many people moved together (this person included)
* low           - fraction of the time the box was wider than tall (crawling / lying)
* crossed       - whether the path crossed a virtual fence line configured for this camera
* restricted    - whether the path entered a restricted zone configured for this camera
"""
import math
import statistics
import threading
from dataclasses import asdict, dataclass, field

GRID_COLS, GRID_ROWS = 4, 3


@dataclass
class Movement:
    camera: str
    t_start: float
    t_end: float
    entry: str
    exit: str
    speed: float = 0.0
    dwell: float = 0.0
    group: int = 1
    low: float = 0.0
    crossed: bool = False
    restricted: bool = False
    person: str = ""
    # Filled in by the benchmark from ground truth; never used for scoring.
    staged: bool = False
    staged_id: str = ""

    @property
    def path(self):
        return f"{self.entry}>{self.exit}"

    def row(self):
        return asdict(self)


def cell(x, y):
    """Grid cell of a normalised point (0..1, 0..1): 'r0c0' is top-left."""
    c = min(GRID_COLS - 1, max(0, int(x * GRID_COLS)))
    r = min(GRID_ROWS - 1, max(0, int(y * GRID_ROWS)))
    return f"r{r}c{c}"


def _segments_cross(p1, p2, q1, q2):
    """True if segment p1-p2 crosses segment q1-q2 (proper intersection)."""
    def orient(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    d1, d2 = orient(q1, q2, p1), orient(q1, q2, p2)
    d3, d4 = orient(p1, p2, q1), orient(p1, p2, q2)
    return d1 * d2 < 0 and d3 * d4 < 0


def _inside(pt, rect):
    x1, y1, x2, y2 = rect
    return x1 <= pt[0] <= x2 and y1 <= pt[1] <= y2


def summarise(camera, samples, fences=(), restricted=(), person=""):
    """samples: [(t, (x1, y1, x2, y2) normalised 0..1, neighbours)] for one person, oldest first.
    fences: [(x1, y1, x2, y2)] lines; restricted: [(x1, y1, x2, y2)] rectangles; all normalised."""
    feet = [((b[0] + b[2]) / 2, b[3]) for _, b, _ in samples]  # bottom-centre = where they stand
    heights = [max(1e-3, b[3] - b[1]) for _, b, _ in samples]
    speeds = []
    for (t0, _, _), (t1, _, _), f0, f1, h0, h1 in zip(samples, samples[1:], feet, feet[1:], heights, heights[1:]):
        dt = t1 - t0
        if dt > 0:
            speeds.append(math.dist(f0, f1) / ((h0 + h1) / 2) / dt)
    low = sum(1 for _, b, _ in samples if (b[2] - b[0]) > (b[3] - b[1])) / len(samples)
    crossed = any(_segments_cross(a, b, (f[0], f[1]), (f[2], f[3])) for a, b in zip(feet, feet[1:]) for f in fences)
    entered = any(_inside(p, r) for p in feet for r in restricted)
    return Movement(
        camera=camera, t_start=samples[0][0], t_end=samples[-1][0],
        entry=cell(*feet[0]), exit=cell(*feet[-1]),
        speed=round(statistics.median(speeds), 3) if speeds else 0.0,
        dwell=round(samples[-1][0] - samples[0][0], 2),
        group=1 + round(statistics.median(n for *_, n in samples)),
        low=round(low, 2), crossed=crossed, restricted=entered, person=person,
    )


@dataclass
class _Open:
    samples: list = field(default_factory=list)
    last: float = 0.0


class TrackAccumulator:
    """Feed it every detection pass; collect finished Movements with pop_finished()."""

    def __init__(self, fences=None, restricted=None, gap_s=6.0, min_samples=3, group_radius=1.5):
        self.fences = fences or {}          # camera id -> [(x1, y1, x2, y2)]
        self.restricted = restricted or {}  # camera id -> [(x1, y1, x2, y2)]
        self.gap_s, self.min_samples, self.group_radius = gap_s, min_samples, group_radius
        self.open = {}
        self.finished = []
        self.lock = threading.Lock()

    def observe(self, t, group):
        """group: [(camera id, frame, detections)] from one pass, after the tracker added d['pid']."""
        with self.lock:
            for cam, frame, dets in group:
                h, w = frame.shape[:2]
                people = [d for d in dets if d.get("label") == "person" and d.get("pid")]
                boxes = [(d["pid"], (d["box"][0] / w, d["box"][1] / h, d["box"][2] / w, d["box"][3] / h))
                         for d in people]
                for pid, box in boxes:
                    bh = max(1e-3, box[3] - box[1])
                    fx, fy = (box[0] + box[2]) / 2, box[3]
                    near = sum(1 for other, ob in boxes if other != pid and
                               math.dist((fx, fy), ((ob[0] + ob[2]) / 2, ob[3])) < self.group_radius * bh)
                    tr = self.open.setdefault((cam, pid), _Open())
                    tr.samples.append((t, box, near))
                    tr.last = t
            self._close(t)

    def _close(self, now):
        for key in [k for k, tr in self.open.items() if now - tr.last > self.gap_s]:
            tr = self.open.pop(key)
            if len(tr.samples) >= self.min_samples:
                cam, pid = key
                self.finished.append(summarise(cam, tr.samples, self.fences.get(cam, ()),
                                               self.restricted.get(cam, ()), person=pid))

    def flush(self, now):
        with self.lock:
            self._close(now)

    def pop_finished(self):
        with self.lock:
            out, self.finished = self.finished, []
            return out
