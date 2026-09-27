"""Person journey tracking.

Two levels of identity:

* Track  - one person inside one camera. Detections are linked pass-to-pass by predicted
           position (constant velocity) and, where available, appearance.
* Person - a site-wide identity (P-001, ...). A new track is linked to an existing person when
           its appearance embedding matches that person's gallery and the person was last seen
           recently in a camera of the same site (cameras people can walk between). Otherwise
           the track gets a new Person ID once it has been seen on two detection passes.

A person's journey is the sequence of cameras (locations) they were seen in. A move to a new
camera is only recorded once the person has been seen there on two passes and is no longer
visible in the previous camera, so overlapping views do not make the journey flicker.
"""
import base64
import itertools
import logging
import math
import threading
from collections import deque
from dataclasses import dataclass, field

import cv2
import numpy as np

from .. import config
from ..detector import iou
from .reid import ReID

log = logging.getLogger(__name__)


@dataclass
class Track:
    tid: int
    cam: str
    box: tuple
    t: float
    vel: tuple = (0.0, 0.0)  # box-centre velocity, px/s
    hits: int = 1
    pid: str | None = None
    embs: deque = field(default_factory=lambda: deque(maxlen=8))
    emb_t: float = -1e9

    def predicted_centre(self, t):
        dt = min(t - self.t, 3.0)
        cx, cy = (self.box[0] + self.box[2]) / 2, (self.box[1] + self.box[3]) / 2
        return cx + self.vel[0] * dt, cy + self.vel[1] * dt

    def appearance(self):
        if not self.embs:
            return None
        m = np.mean(self.embs, axis=0)
        return m / max(np.linalg.norm(m), 1e-6)


@dataclass
class Step:
    cam: str
    start: float
    end: float


@dataclass
class Person:
    pid: str
    site: str
    first_seen: float
    last_seen: float
    steps: list = field(default_factory=list)
    gallery: deque = field(default_factory=lambda: deque(maxlen=40))
    last_cam: str = ""
    pending: list | None = None  # [cam, first_t, passes] for a possible move to another camera
    thumb: str | None = None
    thumb_score: float = 0.0
    thumb_t: float = -1e9

    def similarity(self, emb):
        """Mean of the 3 best cosine similarities between emb and this person's gallery."""
        if not self.gallery:
            return 0.0
        sims = np.asarray(self.gallery) @ emb
        return float(np.mean(np.sort(sims)[-3:]))


class JourneyTracker:
    def __init__(self, cameras):
        """cameras: {cam_id: display name}."""
        self.names = cameras
        self.site_of = {cam: cam for cam in cameras}  # a camera not in any site is its own site
        for site, cams in config.TRACKING_SITES.items():
            for cam in cams:
                self.site_of[cam] = site
        self.overlap = {frozenset(pair) for pair in config.TRACKING_OVERLAPS}
        self.reid = ReID(config.REID_MODEL) if config.REID_MODEL.exists() else None
        if self.reid is None:
            log.warning("ReID model not found at %s — people are tracked within each camera only. "
                        "Run scripts/fetch_assets.py.", config.REID_MODEL)
        self.tracks = {cam: [] for cam in cameras}
        self.persons = {}
        self.aliases = {}  # merged person ID -> the ID it was folded into
        self._tids = itertools.count(1)
        self._pids = itertools.count(1)
        self.lock = threading.Lock()

    # ------------------------------------------------------------------ update
    def update(self, t, batch):
        """batch: [(cam_id, frame, dets)] from one detection pass. Adds d["pid"] to person dets."""
        with self.lock:
            work = []
            for cam, frame, dets in batch:
                people = [d for d in dets if d["label"] == "person"]
                self.tracks[cam] = [tr for tr in self.tracks[cam] if t - tr.t <= config.TRACK_LOST_S]
                work.append((cam, frame, people, [None] * len(people)))

            # Multi-camera sites: embed every usable person so association can use appearance.
            self._embed(work, lambda cam, i, matched: self.site_of[cam] != cam)
            matches = [self._associate(cam, people, embs, t) for cam, _, people, embs in work]
            # Everywhere else: embed only people that motion alone could not place.
            self._embed(work, lambda cam, i, matched: i not in matched, matches)

            for (cam, frame, people, embs), matched in zip(work, matches):
                self._recover_lost(cam, people, embs, matched, t)
                self._apply(cam, frame, people, embs, matched, t)
            self._prune(t)

    def _usable(self, people, i):
        d = people[i]
        return d["box"][3] - d["box"][1] >= config.REID_MIN_HEIGHT

    def _embed(self, work, wanted, matches=None):
        if self.reid is None:
            return
        budget = config.REID_BUDGET - sum(e is not None for *_, embs in work for e in embs)
        for k, (cam, frame, people, embs) in enumerate(work):
            matched = matches[k] if matches else {}
            idx = [i for i in range(len(people))
                   if embs[i] is None and self._usable(people, i) and wanted(cam, i, matched)]
            idx = sorted(idx, key=lambda i: people[i]["box"][1] - people[i]["box"][3])[:max(0, budget)]
            if not idx:
                continue
            budget -= len(idx)
            for i, e in zip(idx, self.reid.embed(frame, [people[i]["box"] for i in idx])):
                embs[i] = e

    def _associate(self, cam, people, embs, t):
        """Greedy lowest-cost matching of detections to this camera's live tracks.

        Returns {det index: track}."""
        live = [tr for tr in self.tracks[cam] if t - tr.t <= config.TRACK_MOTION_S]
        pairs = []
        for i, d in enumerate(people):
            x1, y1, x2, y2 = d["box"]
            cx, cy, h = (x1 + x2) / 2, (y1 + y2) / 2, y2 - y1
            for tr in live:
                th = tr.box[3] - tr.box[1]
                if max(h, th) / max(1.0, min(h, th)) > 1.7:
                    continue
                px, py = tr.predicted_centre(t)
                gate = 0.4 + 0.6 * min(t - tr.t, 3.0)  # in person heights
                dist = math.hypot(cx - px, cy - py) / max(h, th) / gate
                if dist > 1:
                    continue
                cost = dist
                app = tr.appearance()
                if embs[i] is not None and app is not None:
                    sim = float(app @ embs[i])
                    if sim < config.TRACK_MIN_SIM:
                        continue
                    cost = 0.5 * dist + 0.5 * (1 - sim)
                pairs.append((cost, i, tr))
        matched, used = {}, set()
        for cost, i, tr in sorted(pairs, key=lambda p: p[0]):
            if i not in matched and tr.tid not in used:
                matched[i] = tr
                used.add(tr.tid)
        return matched

    def _recover_lost(self, cam, people, embs, matched, t):
        """Re-attach unmatched detections to this camera's recently lost tracks by appearance."""
        taken = {tr.tid for tr in matched.values()}
        for i, e in enumerate(embs):
            if i in matched or e is None:
                continue
            best, best_sim = None, config.TRACK_RECOVER_SIM
            for tr in self.tracks[cam]:
                app = tr.appearance()
                if tr.tid in taken or app is None:
                    continue
                sim = float(app @ e)
                if sim > best_sim:
                    best, best_sim = tr, sim
            if best is not None:
                matched[i] = best
                taken.add(best.tid)

    def _apply(self, cam, frame, people, embs, matched, t):
        site = self.site_of[cam]
        det_tracks = []
        for i, d in enumerate(people):
            tr = matched.get(i)
            if tr is None:
                tr = Track(next(self._tids), cam, d["box"], t)
                self.tracks[cam].append(tr)
            else:
                dt = t - tr.t
                if dt > 0:
                    ocx, ocy = (tr.box[0] + tr.box[2]) / 2, (tr.box[1] + tr.box[3]) / 2
                    ncx, ncy = (d["box"][0] + d["box"][2]) / 2, (d["box"][1] + d["box"][3]) / 2
                    v = ((ncx - ocx) / dt, (ncy - ocy) / dt)
                    tr.vel = (0.5 * tr.vel[0] + 0.5 * v[0], 0.5 * tr.vel[1] + 0.5 * v[1])
                tr.box, tr.t, tr.hits = d["box"], t, tr.hits + 1
            if embs[i] is not None:
                tr.embs.append(embs[i])
                tr.emb_t = t
            det_tracks.append(tr)

        # Identities: continue, re-identify, or create.
        held = {tr.pid for tr in det_tracks if tr.pid}
        for tr in det_tracks:
            if tr.pid is None:
                app = tr.appearance()
                if app is not None:
                    tr.pid = self._reidentify(cam, app, t, exclude=held)
                if tr.pid is None and tr.hits >= 2:
                    tr.pid = self._new_person(site, t)
                if tr.pid:
                    held.add(tr.pid)
            elif t - self.persons[tr.pid].first_seen <= config.PROVISIONAL_S and len(tr.embs) >= 2:
                # A new ID is provisional: once more (and usually closer) views of the person
                # have been collected, it may turn out to be someone seen earlier.
                p = self.persons[tr.pid]
                earlier = self._reidentify(cam, tr.appearance(), t, exclude=held, merge_from=p)
                if earlier:
                    held.discard(p.pid)
                    held.add(earlier)
                    self._merge(p, self.persons[earlier])

        occluded = {id(a) for a in people for b in people if a is not b and iou(a["box"], b["box"]) > 0.3}
        for i, (d, tr) in enumerate(zip(people, det_tracks)):
            if not tr.pid:
                continue
            d["pid"] = tr.pid
            self._observe(self.persons[tr.pid], cam, frame, d, embs[i], id(d) in occluded, t)

    def _can_see_both(self, a, b):
        return a == b or frozenset((a, b)) in self.overlap

    def _reidentify(self, cam, emb, t, exclude, merge_from=None):
        """ID of the person that `emb`, seen in `cam` at time t, most likely belongs to, or None.

        Candidates are people of the same site seen within REID_WINDOW_S. Someone who was just
        seen in a camera that does not overlap `cam` cannot be here as well, so is ruled out.
        With merge_from (a provisional person), only earlier people whose journey never
        overlaps in time with merge_from's journey in another camera qualify, and the bar is higher.
        """
        site = self.site_of[cam]
        threshold = config.REID_MERGE_THRESHOLD if merge_from else config.REID_THRESHOLD
        best, best_sim, second = None, 0.0, 0.0
        for p in self.persons.values():
            if p.site != site or p.pid in exclude or t - p.last_seen > config.REID_WINDOW_S:
                continue
            if t - p.last_seen < config.CO_OCCUR_S and not self._can_see_both(p.last_cam, cam):
                continue
            if merge_from and (p is merge_from or p.first_seen >= merge_from.first_seen
                               or self._coexist(p, merge_from)):
                continue
            sim = p.similarity(emb)
            if sim > best_sim:
                best, best_sim, second = p, sim, best_sim
            elif sim > second:
                second = sim
        if best and best_sim >= threshold and best_sim - second >= config.REID_MARGIN:
            return best.pid
        return None

    def _coexist(self, a, b):
        """True if a and b were seen at the same time in cameras that do not overlap."""
        for sa in a.steps:
            for sb in b.steps:
                if (not self._can_see_both(sa.cam, sb.cam)
                        and min(sa.end, sb.end) - max(sa.start, sb.start) > -config.CO_OCCUR_S):
                    return True
        return False

    def _merge(self, src, dst):
        """Fold person `src` into `dst` (same individual): combine journeys and appearance."""
        steps = sorted(dst.steps + src.steps, key=lambda s: s.start)
        merged = []
        for st in steps:
            if merged and merged[-1].cam == st.cam:
                merged[-1].end = max(merged[-1].end, st.end)
            else:
                merged.append(Step(st.cam, st.start, st.end))
        dst.steps = merged[-config.MAX_JOURNEY_STEPS:]
        dst.gallery.extend(src.gallery)
        dst.first_seen, dst.last_seen = min(dst.first_seen, src.first_seen), max(dst.last_seen, src.last_seen)
        dst.pending = None
        if src.thumb_score > dst.thumb_score:
            dst.thumb, dst.thumb_score, dst.thumb_t = src.thumb, src.thumb_score, src.thumb_t
        for tracks in self.tracks.values():
            for tr in tracks:
                if tr.pid == src.pid:
                    tr.pid = dst.pid
        self.aliases[src.pid] = dst.pid
        del self.persons[src.pid]

    def _new_person(self, site, t):
        pid = f"P-{next(self._pids):03d}"
        self.persons[pid] = Person(pid, site, t, t)
        return pid

    def _observe(self, p, cam, frame, d, emb, occluded, t):
        p.last_seen, p.last_cam = t, cam
        if emb is not None and not occluded:
            p.gallery.append(emb)
        if not p.steps:
            p.steps.append(Step(cam, t, t))
        cur = p.steps[-1]
        if cam == cur.cam:
            cur.end, p.pending = t, None
        else:
            if p.pending and p.pending[0] == cam:
                p.pending[2] += 1
            else:
                p.pending = [cam, t, 1]
            if p.pending[2] >= 2 and t - cur.end >= config.MOVE_CONFIRM_S:
                p.steps.append(Step(cam, p.pending[1], t))
                p.pending = None
                del p.steps[:-config.MAX_JOURNEY_STEPS]
        # Keep the clearest crop as the person's photo (refreshed at most every 2 s).
        h = d["box"][3] - d["box"][1]
        score = d["conf"] * min(h, 200) / 200 * (0.5 if occluded else 1.0)
        if score > p.thumb_score * 1.1 and t - p.thumb_t > 2:
            p.thumb, p.thumb_score, p.thumb_t = _crop_jpeg(frame, d["box"]), score, t

    def _prune(self, t):
        for pid in [pid for pid, p in self.persons.items() if t - p.last_seen > config.PERSON_RETENTION_S]:
            del self.persons[pid]

    # ------------------------------------------------------------------ queries
    def _view(self, p, now):
        """A person's state as the viewer sees it: the video runs behind real time, so events
        after `now` (the displayed moment) are hidden."""
        steps = [s for s in p.steps if s.start <= now]
        if not steps:
            return None
        last_seen = min(p.last_seen, now)
        cur = steps[-1]
        return {
            "id": p.pid,
            "site": p.site if p.site in config.TRACKING_SITES else None,
            "active": now - last_seen <= config.PERSON_ACTIVE_S,
            "first_seen": p.first_seen,
            "last_seen": last_seen,
            "location": self._location(cur.cam),
            "camera_id": cur.cam,
            "camera": self.names[cur.cam],
            "thumbnail": p.thumb,
            "journey": [{"location": self._location(s.cam), "camera_id": s.cam, "camera": self.names[s.cam],
                         "start": s.start, "end": min(s.end, now)} for s in steps],
        }

    def _location(self, cam):
        return self.names[cam].split(" — ")[0]

    def persons_list(self, now):
        with self.lock:
            views = [v for p in self.persons.values() if (v := self._view(p, now))]
        for v in views:
            v["steps"] = len(v.pop("journey"))
        # Active people in ID order (a stable list), then everyone else, most recently seen first.
        views.sort(key=lambda v: (0, int(v["id"][2:])) if v["active"] else (1, -v["last_seen"]))
        return views

    def counts(self, now):
        """(active, total) people as of `now`, without building their full views."""
        with self.lock:
            shown = [p for p in self.persons.values() if p.steps and p.steps[0].start <= now]
            active = sum(now - min(p.last_seen, now) <= config.PERSON_ACTIVE_S for p in shown)
            return active, len(shown)

    def person(self, pid, now):
        with self.lock:
            while pid in self.aliases:
                pid = self.aliases[pid]
            p = self.persons.get(pid)
            return self._view(p, now) if p else None


def _crop_jpeg(frame, box, size=160):
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = box
    pad = (x2 - x1) * 0.1
    x1, x2 = int(max(0, x1 - pad)), int(min(w, x2 + pad))
    y1, y2 = int(max(0, y1)), int(min(h, y2))
    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        return None
    scale = size / max(crop.shape[:2])
    crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
    ok, buf = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return "data:image/jpeg;base64," + base64.b64encode(buf).decode() if ok else None
