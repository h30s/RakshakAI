"""On-demand feeds for the detection modes page."""
import itertools
import logging
import threading
import time

import cv2

from .. import config
from ..pipeline import Camera, ObjectLog, display_delay

log = logging.getLogger(__name__)


class ModeCamera(Camera):
    """A demo clip that only plays while someone is watching it.

    While nobody watches, it reads no frames and offers none to the detector, so it costs
    nothing and the dashboard feeds keep the whole detection budget. Each time someone starts
    watching, the clip restarts from the beginning with a clean detection history."""

    def __init__(self, index, cam_id, name, path):
        super().__init__(index, cam_id, name, path)
        self.viewers = 0
        self.session_start = 0  # frame index at which the current viewing session started
        self._viewers_lock = threading.Lock()

    def watch(self):
        with self._viewers_lock:
            self.viewers += 1

    def unwatch(self):
        with self._viewers_lock:
            self.viewers -= 1

    def run(self):
        cap = None
        period = 1.0 / config.FEED_FPS
        counter = itertools.count()  # frame indices keep increasing across sessions
        while True:
            if self.viewers <= 0:
                if cap is not None:
                    cap.release()
                    cap = None
                    self._reset()
                    log.info("Stopped mode clip %s", self.id)
                time.sleep(0.2)
                continue
            if cap is None:
                cap = cv2.VideoCapture(str(self.path))
                if not cap.isOpened():
                    log.error("Cannot open %s", self.path)
                    return
                idx = next(counter)
                self.session_start = idx
                next_t = time.monotonic()
                log.info("Started mode clip %s", self.id)
            else:
                idx = next(counter)
            ok, frame = cap.read()
            if not ok:  # loop the clip
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
                next_t = time.monotonic()

    def _reset(self):
        """Forget the finished session: frames, detections and listed objects."""
        with self.lock:
            self.latest = None
            self.frames.clear()
            self.det_idx.clear()
            self.det_lists.clear()
            self.packet, self.packet_idx, self.display_idx = None, -1, -1
        self.objects = ObjectLog()
        self.prev_threats, self.prev_idx, self.threat_pending = [], -10**9, False

    def add_detections(self, idx, frame, dets):
        if idx < self.session_start:  # a pass on a frame of an earlier session finished late
            return
        super().add_detections(idx, frame, dets)

    def _publish(self):
        # Show nothing until the clip has run for the display delay: the displayed frame lags
        # the newest one by that much, so earlier there is no frame with detections to show.
        if self.frames[-1][0] - self.session_start < display_delay.seconds * config.FEED_FPS:
            return
        super()._publish()
