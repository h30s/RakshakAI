"""Appearance embeddings for person re-identification.

OSNet-x0.25 trained on MSMT17 (kaiyangzhou/osnet on Hugging Face), exported to ONNX and run
with ONNX Runtime, which is ~3x faster than PyTorch for this network on CPU.
"""
import cv2
import numpy as np

_MEAN = np.array([0.485, 0.456, 0.406], np.float32)
_STD = np.array([0.229, 0.224, 0.225], np.float32)


class ReID:
    def __init__(self, onnx_path):
        import onnxruntime as ort
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 2
        self.session = ort.InferenceSession(str(onnx_path), opts, providers=["CPUExecutionProvider"])

    def embed(self, frame, boxes):
        """L2-normalised appearance vector for each (x1, y1, x2, y2) box in a BGR frame."""
        if not boxes:
            return []
        h, w = frame.shape[:2]
        crops = []
        for x1, y1, x2, y2 in boxes:
            x1, y1 = min(w - 1, max(0, int(x1))), min(h - 1, max(0, int(y1)))
            x2, y2 = min(w, max(x1 + 1, int(x2))), min(h, max(y1 + 1, int(y2)))
            crop = cv2.resize(frame[y1:y2, x1:x2], (128, 256), interpolation=cv2.INTER_LINEAR)
            crops.append((crop[:, :, ::-1].astype(np.float32) / 255 - _MEAN) / _STD)
        x = np.ascontiguousarray(np.stack(crops).transpose(0, 3, 1, 2))
        feats = self.session.run(None, {"x": x})[0]
        return list(feats / np.maximum(np.linalg.norm(feats, axis=1, keepdims=True), 1e-6))


def export_onnx(weights, out_path):
    """Convert the torchreid OSNet-x0.25 checkpoint to ONNX (run once by fetch_assets.py)."""
    import torch
    from .osnet import OSBlock, OSNet

    model = OSNet(num_classes=1, blocks=[OSBlock] * 3, layers=[2, 2, 2], channels=[16, 64, 96, 128])
    state = torch.load(weights, map_location="cpu", weights_only=True)  # tensors only: no code runs on load
    state = {k.removeprefix("module."): v for k, v in state.get("state_dict", state).items()
             if "classifier" not in k}
    missing, _ = model.load_state_dict(state, strict=False)
    assert all("classifier" in k for k in missing), f"unexpected OSNet weights: {missing}"
    model.eval()
    torch.onnx.export(model, torch.randn(1, 3, 256, 128), str(out_path), input_names=["x"],
                      output_names=["y"], dynamic_axes={"x": {0: "n"}, "y": {0: "n"}},
                      opset_version=17, dynamo=False)
