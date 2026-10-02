"""Tests for the ONNX detector. The model checks run only when the models are downloaded
(python scripts/fetch_assets.py --models-only); CI has no models and skips them."""
import unittest

import numpy as np

from app import config
from app.detector import coverage, iou, nms, onnx_path

HAVE_MODELS = (config.MODEL_DIR / config.GENERAL_MODEL).exists() and onnx_path(config.THREAT_MODEL, config.THREAT_IMGSZ).exists()


class GeometryTest(unittest.TestCase):
    def test_nms_is_per_class(self):
        boxes = np.array([[0, 0, 10, 10], [1, 1, 11, 11], [0, 0, 10, 10], [50, 50, 60, 60]], np.float32)
        scores = np.array([0.9, 0.8, 0.7, 0.2], np.float32)
        classes = np.array([0, 0, 1, 0])
        self.assertEqual(sorted(nms(boxes, scores, classes, conf=0.3)), [0, 2])  # overlap removed within class 0 only
        self.assertEqual(nms(boxes, scores, classes, conf=0.95), [])

    def test_iou_and_coverage(self):
        self.assertAlmostEqual(iou((0, 0, 10, 10), (5, 0, 15, 10)), 1 / 3)
        self.assertEqual(coverage((2, 2, 4, 4), (0, 0, 10, 10)), 1.0)


@unittest.skipUnless(HAVE_MODELS, "models not downloaded")
class ModelTest(unittest.TestCase):
    def test_finds_people_on_a_demo_frame(self):
        import cv2
        from app.detector import Detector
        path = config.VIDEO_DIR / "ground_floor_1.mp4"
        if not path.exists():
            self.skipTest("demo video not downloaded")
        cap = cv2.VideoCapture(str(path))
        cap.set(cv2.CAP_PROP_POS_FRAMES, 50)
        ok, frame = cap.read()
        cap.release()
        dets = Detector().detect([frame])[0]
        people = [d for d in dets if d["label"] == "person"]
        self.assertGreaterEqual(len(people), 3)
        for d in people:
            x1, y1, x2, y2 = d["box"]
            self.assertTrue(0 <= x1 < x2 <= frame.shape[1] and 0 <= y1 < y2 <= frame.shape[0])


if __name__ == "__main__":
    unittest.main()
