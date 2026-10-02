"""Synchronised playback for cameras that recorded the same moment from different places."""
import logging
import time

import cv2

from .. import config
from ..pipeline import Camera

log = logging.getLogger(__name__)


class SyncedCamera(Camera):
    """A camera whose frame index is derived from a clock shared with the other cameras of its
    site. A slow thread skips frames instead of drifting, so a person walking from one camera's
    view into the next appears in the right order at the right time. All recordings of a site
    loop at the same length: the shortest recording of the site (`loop_frames`)."""

    def __init__(self, index, cam_id, name, path, clock, loop_frames):
        super().__init__(index, cam_id, name, path)
        self.clock = clock  # shared time.monotonic() start of the site's playback
        self.loop_frames = loop_frames

    def run(self):
        cap = cv2.VideoCapture(str(self.path))
        if not cap.isOpened():
            log.error("Cannot open %s", self.path)
            return
        n = self.loop_frames
        last = -1  # last frame index pushed; the file is positioned just after it
        while True:
            target = int((time.monotonic() - self.clock) * config.FEED_FPS)
            if target <= last:
                time.sleep(max(0.0, self.clock + (last + 1) / config.FEED_FPS - time.monotonic()))
                continue
            if target - last > config.FEED_FPS or target // n != last // n:
                # far behind, or a new loop starts: jump straight to the right frame
                cap.set(cv2.CAP_PROP_POS_FRAMES, target % n)
            else:
                for _ in range(target - last - 1):
                    cap.grab()
            ok, frame = cap.read()
            if not ok:
                log.error("Cannot read %s at frame %d", self.path, target % n)
                return
            self._push(target, frame)
            last = target
