"""Quantize the detectors to INT8 for OpenVINO (Intel CPUs such as the N100), and check the result.

    pip install openvino nncf
    python scripts/quantize_openvino.py            # writes models/<model>_int8.xml / .bin
    DETECTOR_BACKEND=openvino python scripts/measure_perf.py

Calibration uses frames sampled from videos/ (use footage from the post's own cameras when you
have it). Afterwards the INT8 and FP32 models are run on different frames and their detections
compared, so a quantization that hurts detection shows up before it is deployed.
"""
import argparse
import glob
import sys
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import config  # noqa: E402
from app.detector import Yolox, YoloV8, iou, onnx_path  # noqa: E402


def sample_frames(n, offset):
    """n frames spread over every video; `offset` shifts the positions (calibration vs check)."""
    paths = sorted(glob.glob(str(config.VIDEO_DIR / "*.mp4")))
    per = max(1, n // max(1, len(paths)))
    frames = []
    for p in paths:
        cap = cv2.VideoCapture(p)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        for k in range(per):
            cap.set(cv2.CAP_PROP_POS_FRAMES, int((k + offset) * total / (per + 1)) % max(1, total))
            ok, f = cap.read()
            if ok:
                frames.append(f)
        cap.release()
    return frames


def agreement(a, b):
    """Share of boxes in a matched in b (same label, IoU > 0.5), and the reverse."""
    def matched(x, y):
        return sum(1 for bx, _, lx in x if any(lx == ly and iou(bx, by) > 0.5 for by, _, ly in y))
    na, nb = sum(map(len, a)), sum(map(len, b))
    return (sum(matched(x, y) for x, y in zip(a, b)) / na if na else 1.0,
            sum(matched(y, x) for x, y in zip(a, b)) / nb if nb else 1.0)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--frames", type=int, default=300, help="calibration frames")
    args = ap.parse_args()
    import nncf
    import openvino as ov

    core = ov.Core()
    calib, check = sample_frames(args.frames, 0.37), sample_frames(60, 0.81)
    general = config.MODEL_DIR / config.GENERAL_MODEL
    weapon = onnx_path(config.THREAT_MODEL, config.THREAT_IMGSZ)
    yolox, yolov8 = Yolox(general), YoloV8(weapon)
    # The weapon model takes a dynamic shape; calibrate it with the one the pipeline uses.
    H = -(-yolov8._scaled(calib[0])[2] // 32) * 32
    W = -(-yolov8._scaled(calib[0])[1] // 32) * 32
    jobs = [(general, lambda f: yolox.blob(f)[0]),
            (weapon, lambda f: (yolov8._blob(f, H, W)[0][None].astype(np.float32) / 255.0))]
    for path, transform in jobs:
        out = path.with_name(path.stem + "_int8.xml")
        t0 = time.time()
        quantized = nncf.quantize(core.read_model(str(path)), nncf.Dataset(calib, transform),
                                  preset=nncf.QuantizationPreset.MIXED, subset_size=len(calib))
        ov.save_model(quantized, str(out))
        print(f"{out.name}: quantized on {len(calib)} frames in {time.time() - t0:.0f} s")

    # FP32 (ONNX Runtime) vs INT8 (OpenVINO) on frames not used for calibration.
    config.DETECTOR_BACKEND = "openvino"
    yolox8, yolov88 = Yolox(general), YoloV8(weapon)
    fp = [yolox.predict(f, config.GENERAL_CONF) for f in check]
    q = [yolox8.predict(f, config.GENERAL_CONF) for f in check]
    a, b = agreement(fp, q)
    print(f"{config.GENERAL_MODEL}: {a:.0%} of FP32 boxes kept by INT8, {b:.0%} of INT8 boxes also in FP32 "
          f"({sum(map(len, fp))} vs {sum(map(len, q))} boxes on {len(check)} frames)")
    fp = yolov8.predict_batch(check, config.THREAT_CANDIDATE_CONF)
    q = yolov88.predict_batch(check, config.THREAT_CANDIDATE_CONF)
    a, b = agreement(fp, q)
    print(f"weapon model: {a:.0%} / {b:.0%} ({sum(map(len, fp))} vs {sum(map(len, q))} candidate boxes)")


if __name__ == "__main__":
    main()
