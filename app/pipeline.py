"""Camera feeds and the detection loop.

Each Camera thread plays its video file in real time (looping, like a live feed) and keeps a
short frame buffer. A single detection thread repeatedly takes the newest frame of every
camera and runs the models on all of them in one batch. The frame shown to viewers is
a few seconds behind the newest one (see DisplayDelay), so it can be paired with detections computed on
(nearly) the same frame.
"""
import base64
import bisect
import itertools
import json
import logging
import struct
import threading
import time
from collections import deque

import cv2
import numpy as np

from . import config
from .detector import Detector, coverage, iou

log = logging.getLogger(__name__)


class DisplayDelay:
    """How far (seconds) the displayed video runs behind the newest frame.

    Each displayed frame needs the detection pass after it to be finished, so the delay follows
    the measured detection cycle time (DELAY_PER_CYCLE x cycle), between DISPLAY_DELAY and
    MAX_DISPLAY_DELAY. It changes a little per cycle, so playback only speeds up or slows down
    slightly while it adjusts."""

    def __init__(self):
        self.seconds = config.DISPLAY_DELAY

    def adapt(self, cycle_time):
        target = min(config.MAX_DISPLAY_DELAY, max(config.DISPLAY_DELAY, config.DELAY_PER_CYCLE * cycle_time))
        step = 0.25 if target > self.seconds else 0.05  # grow quickly, shrink slowly
        self.seconds += max(-step, min(step, target - self.seconds))


display_delay = DisplayDelay()


class ObjectLog:
    """Groups repeated detections of the same object into one entry for the info panel."""

    KEEP_SECONDS = 5  # an ordinary object disappears from the panel after this long unseen
    KEEP_THREAT_SECONDS = 30  # weapons stay listed longer

    def __init__(self):
        self._entries = []
        self._ids = itertools.count(1)
        self._lock = threading.Lock()

    def update(self, idx, frame, dets):
        with self._lock:
            unmatched = list(self._entries)
            for d in sorted(dets, key=lambda d: -d["conf"]):
                match = max((e for e in unmatched if e["label"] == d["label"]),
                            key=lambda e: iou(e["box"], d["box"]), default=None)
                if match is not None and iou(match["box"], d["box"]) > 0.2:
                    unmatched.remove(match)
                    match["box"], match["last_idx"] = d["box"], idx
                    if d["conf"] > match["conf"]:
                        match["conf"], match["thumb"] = d["conf"], _thumbnail(frame, d["box"])
                else:
                    self._entries.append({
                        "id": next(self._ids), "label": d["label"], "conf": d["conf"],
                        "threat": d["threat"], "box": d["box"], "first_idx": idx, "last_idx": idx,
                        "thumb": _thumbnail(frame, d["box"]),
                    })
            # Drop entries long gone (relative to the newest processed frame).
            self._entries = [e for e in self._entries if idx - e["last_idx"] <= self._keep_frames(e)]

    def _keep_frames(self, e):
        return (self.KEEP_THREAT_SECONDS if e["threat"] else self.KEEP_SECONDS) * config.FEED_FPS

    def snapshot(self, display_idx):
        """Entries visible at the currently displayed frame, weapons first."""
        with self._lock:
            items = [e for e in self._entries
                     if e["first_idx"] <= display_idx and display_idx - e["last_idx"] <= self._keep_frames(e)]
            items.sort(key=lambda e: (not e["threat"], -e["conf"]))
            return [{
                "id": e["id"],
                "label": e["label"].title(),
                "confidence": round(e["conf"] * 100),
                "threat": e["threat"],
                "in_view": display_idx - e["last_idx"] <= 2 * config.FEED_FPS,
                "seconds_ago": max(0, round((display_idx - e["last_idx"]) / config.FEED_FPS)),
                "details": config.DESCRIPTIONS.get(e["label"], f"{e['label'].title()} detected in the camera feed."),
                "thumbnail": e["thumb"],
            } for e in items]


def _area(box):
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def _held_by(weapon, person):
    """Could this weapon box be held by this person: mostly on them, and much smaller?"""
    return (coverage(weapon, person) >= config.HELD_MIN_OVERLAP
            and _area(weapon) <= config.HELD_MAX_AREA_RATIO * _area(person))


def interpolate(before, after, idx):
    """Move each box linearly from its position in `before` to its match in `after`.

    Detection only runs on some frames, so without this boxes would jump every pass and
    trail behind moving people in between.
    """
    (ia, da), (ib, db) = before, after
    t = (idx - ia) / (ib - ia)
    remaining = list(db)
    out = []
    for a in da:
        b = max((d for d in remaining if d["label"] == a["label"]),
                key=lambda d: iou(a["box"], d["box"]), default=None)
        if b is not None and iou(a["box"], b["box"]) > 0.1:
            remaining.remove(b)
            out.append({**a, "conf": a["conf"] + (b["conf"] - a["conf"]) * t,
                        "box": tuple(pa + (pb - pa) * t for pa, pb in zip(a["box"], b["box"]))})
        elif t < 0.5:  # object leaves before the next pass: keep it for the first half
            out.append(a)
    if t >= 0.5:  # new objects appear for the second half
        out.extend(remaining)
    return out


def _thumbnail(frame, box, size=160):
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = box
    pad_x, pad_y = (x2 - x1) * 0.15, (y2 - y1) * 0.15
    x1, y1 = int(max(0, x1 - pad_x)), int(max(0, y1 - pad_y))
    x2, y2 = int(min(w, x2 + pad_x)), int(min(h, y2 + pad_y))
    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        return None
    scale = size / max(crop.shape[:2])
    if scale < 1:
        crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return "data:image/jpeg;base64," + base64.b64encode(buf).decode() if ok else None


class Camera(threading.Thread):
    def __init__(self, index, cam_id, name, path):
        super().__init__(daemon=True, name=f"cam-{cam_id}")
        self.index, self.id, self.name, self.path = index, cam_id, name, path
        # (idx, jpeg) of recent frames: what viewers are shown, a few seconds behind
        self.frames = deque(maxlen=int(config.MAX_DISPLAY_DELAY * config.FEED_FPS) + 2)
        self.latest = None  # (idx, raw frame) for the detector
        self.det_idx, self.det_lists = [], []  # detection results, sorted by frame idx
        self.objects = ObjectLog()
        self.prev_threats = []  # weapon candidates from the previous detection pass
        self.prev_idx = -10**9  # frame index of that pass
        self.threat_pending = False  # last pass had a weapon candidate awaiting confirmation
        self.packet, self.packet_idx, self.display_idx = None, -1, -1
        self.lock = threading.Lock()

    # --- called from the detector thread ---
    def add_detections(self, idx, frame, dets):
        # Weapon false-positive filter: a hand-held weapon must sit on a person, and it must
        # also have been a candidate at the same spot on the previous pass, at most
        # THREAT_CONFIRM_GAP_S earlier - or already be a confirmed weapon (see config).
        persons = [d["box"] for d in dets if d["label"] == "person"]
        candidates = [d for d in dets if d["threat"] and (
            d["label"] not in config.HELD_CLASSES or any(_held_by(d["box"], p) for p in persons))]
        recent = (idx - self.prev_idx) / config.FEED_FPS <= config.THREAT_CONFIRM_GAP_S
        confirmed = []
        for d in candidates:
            d["confirmed"] = d["conf"] >= config.THREAT_CONF and any(
                p["label"] == d["label"] and iou(p["box"], d["box"]) > 0.2 and (recent or p["confirmed"])
                for p in self.prev_threats)
            if d["confirmed"]:
                confirmed.append(d)
        dets = [d for d in dets if not d["threat"]] + confirmed
        self.threat_pending = any(d["conf"] >= config.THREAT_CONF and not d["confirmed"] for d in candidates)
        self.prev_threats, self.prev_idx = candidates, idx
        with self.lock:
            self.det_idx.append(idx)
            self.det_lists.append(dets)
            if len(self.det_idx) > 200:
                del self.det_idx[:100], self.det_lists[:100]
        self.objects.update(idx, frame, dets)

    def buffered_frame(self, idx):
        """(idx, frame) of the first buffered frame at or after idx, or None."""
        for i, jpeg in list(self.frames):
            if i >= idx:
                return i, cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
        return None

    def _detections_for(self, idx):
        """Detections for frame idx, interpolated between the processed frames around it."""
        max_gap = config.FEED_FPS * 5  # ignore passes further than this from the frame
        with self.lock:
            i = bisect.bisect_right(self.det_idx, idx)
            before = (self.det_idx[i - 1], self.det_lists[i - 1]) if i > 0 else None
            after = (self.det_idx[i], self.det_lists[i]) if i < len(self.det_idx) else None
        if before and idx - before[0] > max_gap:
            before = None
        if after and after[0] - idx > max_gap:
            after = None
        if not before or not after:
            return (before or after or (0, []))[1]
        return interpolate(before, after, idx)

    def run(self):
        cap = cv2.VideoCapture(str(self.path))
        if not cap.isOpened():
            log.error("Cannot open %s", self.path)
            return
        period = 1.0 / config.FEED_FPS
        next_t = time.monotonic()
        for idx in itertools.count():
            ok, frame = cap.read()
            if not ok:  # loop the recording so it behaves like a continuous feed
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ok, frame = cap.read()
                if not ok:
                    log.error("Cannot read %s", self.path)
                    return
            self._push(idx, frame)

            next_t += period
            delay = next_t - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            else:
                next_t = time.monotonic()  # fell behind; don't try to catch up in a burst

    def _push(self, idx, frame):
        """Make a newly read frame available to the detector and the viewers."""
        if frame.shape[1] != config.FRAME_W or frame.shape[0] != config.FRAME_H:
            frame = cv2.resize(frame, (config.FRAME_W, config.FRAME_H), interpolation=cv2.INTER_AREA)
        _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, config.JPEG_QUALITY])
        self.frames.append((idx, jpeg.tobytes()))
        self.latest = (idx, frame)
        self._publish()

    def _publish(self):
        """Build the binary message for the frame that is currently on display."""
        frames = self.frames
        newest = frames[-1][0]
        target = newest - int(display_delay.seconds * config.FEED_FPS)
        pos = max(0, len(frames) - 1 - (newest - target))
        while pos > 0 and frames[pos - 1][0] >= target:
            pos -= 1
        while pos < len(frames) - 1 and frames[pos][0] < target:
            pos += 1
        idx, jpeg = frames[pos]
        dets = self._detections_for(idx)
        meta = json.dumps({
            "idx": idx,
            "time": time.time() - (newest - idx) / config.FEED_FPS,
            "dets": [[round(d["box"][0] / config.FRAME_W, 4), round(d["box"][1] / config.FRAME_H, 4),
                      round(d["box"][2] / config.FRAME_W, 4), round(d["box"][3] / config.FRAME_H, 4),
                      d["label"].title(), round(d["conf"] * 100), int(d["threat"]), d.get("pid", "")]
                     for d in dets],
        }, separators=(",", ":")).encode()
        # [uint8 camera index][uint16 meta length][meta json][jpeg]
        self.packet = struct.pack(">BH", self.index, len(meta)) + meta + jpeg
        self.packet_idx = self.display_idx = idx


class DetectionLoop(threading.Thread):
    def __init__(self, cameras, on_results=None):
        """on_results(t, [(camera id, frame, detections)]) is called after every pass, with t the
        frames' capture time; it may annotate the detections (the tracker adds person IDs)."""
        super().__init__(daemon=True, name="detector")
        self.cameras = cameras
        self.on_results = on_results
        self.detector = Detector()
        self.cycle_time = 0.0
        self.post_time = 0.0

    def run(self):
        done = {}
        last_log = time.monotonic()
        while True:
            batch = [(cam, *cam.latest) for cam in self.cameras
                     if cam.latest is not None and done.get(cam.id) != cam.latest[0]]
            if not batch:
                time.sleep(0.01)
                continue
            t0 = time.monotonic()
            captured = time.time()
            if not self._process(batch, {cam.id: captured for cam, _, _ in batch}):
                time.sleep(1)
                continue
            for cam, idx, _ in batch:
                done[cam.id] = idx
            self._recheck_weapons(batch, captured)
            dt = time.monotonic() - t0
            self.cycle_time = dt if not self.cycle_time else 0.8 * self.cycle_time + 0.2 * dt
            display_delay.adapt(self.cycle_time)
            if time.monotonic() - last_log > 30:
                last_log = time.monotonic()
                slow = self.cycle_time * config.DELAY_PER_CYCLE > config.MAX_DISPLAY_DELAY
                log.log(logging.WARNING if slow else logging.INFO,
                        "Detection cycle %.2fs for %d feeds, of which %.2fs post-processing; display delay %.1fs",
                        self.cycle_time, len(batch), self.post_time, display_delay.seconds)

    def _process(self, items, captured):
        """Detect on [(camera, frame idx, frame)] and hand the results on. captured: {camera id:
        wall-clock capture time of its frame}. Returns False if detection failed."""
        try:
            results = self.detector.detect([frame for _, _, frame in items])
        except Exception:
            log.exception("Detection failed")
            return False
        t1 = time.monotonic()
        if self.on_results:
            try:
                by_time = {}
                for (cam, _, frame), dets in zip(items, results):
                    by_time.setdefault(captured[cam.id], []).append((cam.id, frame, dets))
                for t, group in sorted(by_time.items()):
                    self.on_results(t, group)
            except Exception:
                log.exception("Detection post-processing failed")
        self.post_time = 0.8 * self.post_time + 0.2 * (time.monotonic() - t1)
        for (cam, idx, frame), dets in zip(items, results):
            cam.add_detections(idx, frame, dets)
        return True

    def _recheck_weapons(self, batch, captured):
        """A weapon is only shown once seen on two passes. With many feeds a full cycle takes
        a while, so a briefly visible weapon could be missed; instead, re-check the frame
        THREAT_RECHECK_S later, which is still in the camera's display buffer."""
        step = round(config.THREAT_RECHECK_S * config.FEED_FPS)
        items, times = [], {}
        for cam, idx, _ in batch:
            if cam.threat_pending and (later := cam.buffered_frame(idx + step)):
                items.append((cam, *later))
                times[cam.id] = captured + (later[0] - idx) / config.FEED_FPS
        if items:
            self._process(items, times)
