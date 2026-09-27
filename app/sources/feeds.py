"""Live camera sources: frames sent in by a browser (webcam, USB camera, phone)."""
import itertools
import logging
import threading
import time

import cv2
import numpy as np

from .. import config
from ..pipeline import Camera, ObjectLog, display_delay

log = logging.getLogger(__name__)


class LiveCamera(Camera):
    """A dashboard camera whose frames come from a connected device instead of a file.

    The device sends JPEG frames at its own pace; this thread plays the newest one at the feed
    frame rate, so the rest of the pipeline (display delay, box interpolation, weapon re-check)
    sees an ordinary camera. One device at a time: a new one takes the source over, which is
    how the user switches cameras without restarting anything. With no device (or no frame for
    LIVE_STALE_S) the source is idle and costs nothing."""

    def __init__(self, index, cam_id, name):
        super().__init__(index, cam_id, name, None)
        self.publisher = None      # the connected device's session (any object), or None
        self.device = None         # its label, e.g. "Integrated Webcam" or "Phone (back camera)"
        self.connected_at = None
        self.disconnected_at = None  # when the last device left (None: never connected yet)
        self.incoming = None       # newest decoded frame from the device
        self.received_at = 0.0
        self.session_start = 0     # frame index at which the current connection started
        self._pub_lock = threading.Lock()

    # --- called from the WebSocket handlers ---
    def connect(self, device):
        """Register a new device; returns (session, replaced session or None)."""
        session = object()
        with self._pub_lock:
            old, self.publisher = self.publisher, session
            self.device, self.connected_at = device, time.time()
            self.incoming = None
        log.info("%s connected: %s", self.name, device)
        return session, old

    def receive(self, session, jpeg):
        if session is not self.publisher:
            return False
        frame = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
        if frame is not None:
            self.incoming, self.received_at = frame, time.monotonic()
        return True

    def disconnect(self, session):
        with self._pub_lock:
            if session is self.publisher:
                self.publisher, self.device, self.connected_at = None, None, None
                self.disconnected_at = time.time()
                log.info("%s disconnected", self.name)

    @property
    def streaming(self):
        return (self.publisher is not None and self.incoming is not None
                and time.monotonic() - self.received_at < config.LIVE_STALE_S)

    # --- playback thread ---
    def run(self):
        period = 1.0 / config.FEED_FPS
        counter = itertools.count()  # frame indices keep increasing across connections
        active = False
        while True:
            frame = self.incoming
            if frame is None or not self.streaming:
                if active:
                    active = False
                    self._reset()
                time.sleep(0.1)
                continue
            idx = next(counter)
            if not active:
                active = True
                self.session_start = idx
                next_t = time.monotonic()
            self._push(idx, frame)
            next_t += period
            delay = next_t - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            else:
                next_t = time.monotonic()

    def _reset(self):
        """Forget the finished connection: frames, detections and listed objects."""
        with self.lock:
            self.latest = None
            self.frames.clear()
            self.det_idx.clear()
            self.det_lists.clear()
            self.packet, self.packet_idx, self.display_idx = None, -1, -1
        self.objects = ObjectLog()
        self.prev_threats, self.prev_idx, self.threat_pending = [], -10**9, False

    def add_detections(self, idx, frame, dets):
        if idx < self.session_start:  # a pass on a frame of an earlier connection finished late
            return
        super().add_detections(idx, frame, dets)

    def _publish(self):
        # Like every feed, the shown frame lags the newest one by the display delay; show
        # nothing until the connection has run that long.
        if self.frames[-1][0] - self.session_start < display_delay.seconds * config.FEED_FPS:
            return
        super()._publish()
