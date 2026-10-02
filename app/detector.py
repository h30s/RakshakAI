"""Object detection: a general COCO model plus a dedicated weapon model, merged per frame."""
import logging

import numpy as np
from ultralytics import YOLO

from . import config

log = logging.getLogger(__name__)


def iou(a, b):
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def coverage(inner, outer):
    """Fraction of box `inner` that lies inside box `outer`."""
    w = max(0.0, min(inner[2], outer[2]) - max(inner[0], outer[0]))
    h = max(0.0, min(inner[3], outer[3]) - max(inner[1], outer[1]))
    area = (inner[2] - inner[0]) * (inner[3] - inner[1])
    return w * h / area if area > 0 else 0.0


def onnx_path(pt_path, imgsz):
    return pt_path.with_name(f"{pt_path.stem}_{imgsz}.onnx")


def load_yolo(pt_path, imgsz):
    """Prefer the ONNX export of a model (same detections, ~1.5x faster on CPU with ONNX
    Runtime); fall back to the PyTorch weights. scripts/fetch_assets.py creates the exports."""
    onnx = onnx_path(pt_path, imgsz)
    if onnx.exists():
        return YOLO(str(onnx), task="detect")
    log.info("No ONNX export at %s — using the slower PyTorch model", onnx)
    return YOLO(str(pt_path))


class Detector:
    def __init__(self):
        log.info("Loading models ...")
        self.general = load_yolo(config.MODEL_DIR / config.GENERAL_MODEL, config.GENERAL_IMGSZ)
        self.threat = (load_yolo(config.THREAT_MODEL, config.THREAT_IMGSZ)
                       if config.THREAT_MODEL.exists() else None)
        if self.threat is None:
            log.warning("Weapon model not found at %s — only COCO classes will be detected. "
                        "Run scripts/fetch_assets.py.", config.THREAT_MODEL)

    @staticmethod
    def _parse(result, conf_min):
        names = result.names
        boxes = result.boxes
        out = []
        for (x1, y1, x2, y2), conf, cls in zip(boxes.xyxy.tolist(), boxes.conf.tolist(), boxes.cls.tolist()):
            if conf < conf_min:
                continue
            label = names[int(cls)].lower()
            out.append({"label": label, "conf": conf, "box": (x1, y1, x2, y2),
                        "threat": label in config.THREAT_CLASSES})
        return out

    def detect(self, frames: list[np.ndarray]) -> list[list[dict]]:
        """Run both models on a batch of BGR frames; returns one detection list per frame.

        Weapon detections are returned down to THREAT_CANDIDATE_CONF; the caller confirms them
        over time (see pipeline.Camera.add_detections).
        """
        general = self.general.predict(frames, imgsz=config.GENERAL_IMGSZ, conf=config.GENERAL_CONF,
                                       verbose=False)
        threat = (self.threat.predict(frames, imgsz=config.THREAT_IMGSZ, conf=config.THREAT_CANDIDATE_CONF,
                                      verbose=False) if self.threat else [None] * len(frames))
        merged = []
        for g, t in zip(general, threat):
            dets = self._parse(t, config.THREAT_CANDIDATE_CONF) if t is not None else []
            for d in self._parse(g, config.GENERAL_CONF):
                # Both models know "knife": keep a single box when they agree.
                if any(o["label"] == d["label"] and o["conf"] >= d["conf"] and iou(o["box"], d["box"]) > 0.5
                       for o in dets):
                    continue
                dets.append(d)
            merged.append(dets)
        return merged
