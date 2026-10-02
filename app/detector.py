"""Object detection: a general COCO model plus a dedicated weapon model, merged per frame.

Both models run as plain ONNX graphs, with no Ultralytics package at run time:

* General model: YOLOX (Megvii, Apache-2.0), the official ONNX release (yolox_tiny.onnx by
  default; yolox_nano / yolox_s also work). Pre- and post-processing follow the YOLOX ONNX
  Runtime demo: top-left letterbox padded with 114, BGR, 0-255, grid decoding, then NMS.
* Weapon model: Subh775/Threat-Detection-YOLOv8n exported once to ONNX by
  scripts/fetch_assets.py. The weights were trained with Ultralytics; see THIRD_PARTY.md.

Backends: ONNX Runtime (default) or OpenVINO (DETECTOR_BACKEND=openvino; uses an INT8 IR from
scripts/quantize_openvino.py when it exists, else the ONNX file).
"""
import ast
import logging
from pathlib import Path

import cv2
import numpy as np

from . import config

log = logging.getLogger(__name__)

COCO = ["person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat", "traffic light",
        "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow",
        "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee",
        "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove", "skateboard", "surfboard",
        "tennis racket", "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple",
        "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch",
        "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote", "keyboard",
        "cell phone", "microwave", "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase", "scissors",
        "teddy bear", "hair drier", "toothbrush"]


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


# ---------------------------------------------------------------- runtimes
class OrtRunner:
    def __init__(self, path):
        import onnxruntime as ort
        opts = ort.SessionOptions()
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(str(path), opts, providers=["CPUExecutionProvider"])
        self.input = self.session.get_inputs()[0]
        self.shape = self.input.shape  # [batch, 3, h, w]; batch may be symbolic
        self.meta = self.session.get_modelmeta().custom_metadata_map

    def __call__(self, blob):
        return self.session.run(None, {self.input.name: blob})[0]


class OvRunner:
    """OpenVINO on the CPU. Uses <model>_int8.xml next to the ONNX file when allowed and present."""

    def __init__(self, path, int8=True):
        import openvino as ov
        core = ov.Core()
        int8 = Path(path).with_name(Path(path).stem + "_int8.xml") if int8 else None
        source = int8 if int8 and int8.exists() else path
        model = core.read_model(str(source))
        self.compiled = core.compile_model(model, "CPU", {"PERFORMANCE_HINT": "LATENCY"})  # one request at a time
        self.shape = list(model.inputs[0].get_partial_shape().to_string().strip("[]").split(","))
        self.shape = [int(s) if s.strip().isdigit() else s.strip() for s in self.shape]
        self.meta = {}
        try:
            names = model.get_rt_info(["framework", "names"]).astype(str)
            self.meta = {"names": names}
        except Exception:
            pass
        if source == int8:
            log.info("OpenVINO INT8 model %s", int8.name)

    def __call__(self, blob):
        return self.compiled(blob)[0]


def make_runner(path, int8=True):
    if config.DETECTOR_BACKEND == "openvino":
        return OvRunner(path, int8)
    return OrtRunner(path)


def nms(boxes, scores, classes, conf, iou_thr=0.45):
    """Class-wise NMS. boxes: (n, 4) xyxy. Returns kept indices."""
    keep = scores >= conf
    idx = np.nonzero(keep)[0]
    if not len(idx):
        return []
    b = boxes[idx]
    xywh = np.column_stack([b[:, 0], b[:, 1], b[:, 2] - b[:, 0], b[:, 3] - b[:, 1]])
    kept = cv2.dnn.NMSBoxesBatched(xywh.tolist(), scores[idx].tolist(), classes[idx].tolist(), conf, iou_thr)
    return [int(idx[k]) for k in np.array(kept).reshape(-1)]


# ---------------------------------------------------------------- models
class Yolox:
    """YOLOX ONNX (official release): input (1, 3, H, W) BGR 0-255, top-left letterbox."""

    def __init__(self, path, names=COCO):
        self.run = make_runner(path)
        self.h, self.w = int(self.run.shape[2]), int(self.run.shape[3])
        self.names = names
        grids, strides = [], []
        for s in (8, 16, 32):
            xv, yv = np.meshgrid(np.arange(self.w // s), np.arange(self.h // s))
            grids.append(np.stack((xv, yv), 2).reshape(-1, 2))
            strides.append(np.full((grids[-1].shape[0], 1), s))
        self.grid, self.stride = np.concatenate(grids).astype(np.float32), np.concatenate(strides).astype(np.float32)

    def blob(self, frame):
        """(model input, scale) for a BGR frame: top-left letterbox, padded with 114."""
        r = min(self.h / frame.shape[0], self.w / frame.shape[1])
        resized = cv2.resize(frame, (int(frame.shape[1] * r), int(frame.shape[0] * r)), interpolation=cv2.INTER_LINEAR)
        canvas = np.full((self.h, self.w, 3), 114, np.uint8)
        canvas[:resized.shape[0], :resized.shape[1]] = resized
        return canvas.transpose(2, 0, 1)[None].astype(np.float32), r

    def predict(self, frame, conf):
        blob, r = self.blob(frame)
        out = self.run(blob)[0]
        xy = (out[:, :2] + self.grid) * self.stride
        wh = np.exp(out[:, 2:4]) * self.stride
        scores_all = out[:, 4:5] * out[:, 5:]
        classes = scores_all.argmax(1)
        scores = scores_all[np.arange(len(classes)), classes]
        boxes = np.column_stack([xy - wh / 2, xy + wh / 2]) / r
        return [(boxes[i], float(scores[i]), self.names[classes[i]]) for i in nms(boxes, scores, classes, conf)]


class YoloV8:
    """Ultralytics-format ONNX export: input (n, 3, S, S) RGB 0-1, centred letterbox; output
    (n, 4 + classes, anchors) with cx, cy, w, h in input pixels. Class names from the metadata."""

    def __init__(self, path):
        # INT8 lost a quarter of the weapon candidates in our check (scripts/quantize_openvino.py),
        # so the weapon model stays in full precision unless OPENVINO_INT8_WEAPON=1.
        self.run = make_runner(path, int8=config.OPENVINO_INT8_WEAPON)
        self.dynamic = not str(self.run.shape[2]).isdigit()
        self.size = config.THREAT_IMGSZ if self.dynamic else int(self.run.shape[2])
        names = self.run.meta.get("names")
        self.names = ([v for _, v in sorted(ast.literal_eval(names).items())] if names
                      else ["Gun", "Explosion", "Grenade", "Knife"])

    def _scaled(self, frame):
        r = min(self.size / frame.shape[0], self.size / frame.shape[1])
        return r, int(round(frame.shape[1] * r)), int(round(frame.shape[0] * r))

    def _blob(self, frame, H, W):
        """Centred letterbox into H x W, rounded the way Ultralytics does it."""
        r, nw, nh = self._scaled(frame)
        dx, dy = round((W - nw) / 2 - 0.1), round((H - nh) / 2 - 0.1)
        canvas = np.full((H, W, 3), 114, np.uint8)
        canvas[dy:dy + nh, dx:dx + nw] = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_LINEAR)
        return canvas[:, :, ::-1].transpose(2, 0, 1), r, dx, dy

    def predict_batch(self, frames, conf):
        if self.dynamic:  # smallest stride-32 rectangle, as Ultralytics feeds a dynamic export
            sizes = [self._scaled(f) for f in frames]
            H = max(-(-nh // 32) * 32 for _, _, nh in sizes)
            W = max(-(-nw // 32) * 32 for _, nw, _ in sizes)
        else:
            H = W = self.size
        prepared = [self._blob(f, H, W) for f in frames]
        blob = np.stack([p[0] for p in prepared]).astype(np.float32) / 255.0
        batch = int(self.run.shape[0]) if str(self.run.shape[0]).isdigit() else None
        outs = (np.concatenate([self.run(blob[i:i + 1]) for i in range(len(blob))]) if batch == 1
                else self.run(blob))
        results = []
        for out, (_, r, dx, dy) in zip(outs, prepared):
            out = out.T  # (anchors, 4 + classes)
            classes = out[:, 4:].argmax(1)
            scores = out[np.arange(len(out)), 4 + classes]
            cx, cy, w, h = out[:, 0], out[:, 1], out[:, 2], out[:, 3]
            boxes = np.column_stack([(cx - w / 2 - dx) / r, (cy - h / 2 - dy) / r, (cx + w / 2 - dx) / r, (cy + h / 2 - dy) / r])
            # IoU 0.7: the Ultralytics default, so detections match what this model produced before.
            results.append([(boxes[i], float(scores[i]), self.names[classes[i]])
                            for i in nms(boxes, scores, classes, conf, iou_thr=0.7)])
        return results


class Detector:
    def __init__(self):
        log.info("Loading models (%s) ...", config.DETECTOR_BACKEND)
        general = config.MODEL_DIR / config.GENERAL_MODEL
        if not general.exists():
            raise FileNotFoundError(f"{general} not found. Run: python scripts/fetch_assets.py")
        self.general = Yolox(general)
        threat_onnx = onnx_path(config.THREAT_MODEL, config.THREAT_IMGSZ)
        self.threat = YoloV8(threat_onnx) if threat_onnx.exists() else None
        if self.threat is None:
            log.warning("Weapon model not found at %s — only COCO classes will be detected. "
                        "Run scripts/fetch_assets.py.", threat_onnx)

    @staticmethod
    def _dets(found, h, w):
        out = []
        for box, conf, name in found:
            label = name.lower()
            x1, y1, x2, y2 = (float(np.clip(box[0], 0, w)), float(np.clip(box[1], 0, h)),
                              float(np.clip(box[2], 0, w)), float(np.clip(box[3], 0, h)))
            out.append({"label": label, "conf": conf, "box": (x1, y1, x2, y2), "threat": label in config.THREAT_CLASSES})
        return out

    def detect(self, frames: list[np.ndarray]) -> list[list[dict]]:
        """Run both models on a batch of BGR frames; returns one detection list per frame.

        Weapon detections are returned down to THREAT_CANDIDATE_CONF; the caller confirms them
        over time (see pipeline.Camera.add_detections).
        """
        threat = self.threat.predict_batch(frames, config.THREAT_CANDIDATE_CONF) if self.threat else [[]] * len(frames)
        merged = []
        for frame, t in zip(frames, threat):
            h, w = frame.shape[:2]
            dets = self._dets(t, h, w)
            for d in self._dets(self.general.predict(frame, config.GENERAL_CONF), h, w):
                # Both models know "knife": keep a single box when they agree.
                if any(o["label"] == d["label"] and o["conf"] >= d["conf"] and iou(o["box"], d["box"]) > 0.5
                       for o in dets):
                    continue
                dets.append(d)
            merged.append(dets)
        return merged
