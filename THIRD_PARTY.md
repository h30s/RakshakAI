# Third-party models, data and libraries

Everything Rakshak AI uses that we did not write, with its licence. Check the licence **before**
adding anything, and add it here in the same change. "Verify" means the licence below is taken
from the project page and must be re-checked by the compliance officer.

## ⚠ Open issues

| Item | Issue | Action |
|---|---|---|
| Threat-Detection-YOLOv8n (weapon model) | Card says MIT, but the weights are a fine-tuned YOLOv8 trained with Ultralytics (whose licence is AGPL-3.0), and the training data's licence is not stated | Run without the Ultralytics package (done). For deployment: retrain a weapon detector on YOLOX with data of known licence |
| OSNet-x0.25 weights (MSMT17) | Code is MIT, but MSMT17 is for **non-commercial research use** | Fine for the hackathon; retrain for deployment |
| Repository licence | No `LICENSE` file yet | Team to choose (Apache-2.0 suggested) |

**Resolved 2026-10-02:** the general detector is now **YOLOX (Apache-2.0)**, as the SIH deck states.
The running system no longer needs the `ultralytics` package; it is used only once, by
`scripts/fetch_assets.py` (`requirements-export.txt`), to convert the weapon weights to ONNX.

## Models

| Model | Used for | Licence | Source |
|---|---|---|---|
| YOLOX-tiny (default) / -nano / -s, ONNX | General detection (people, vehicles, COCO) | Apache-2.0 | github.com/Megvii-BaseDetection/YOLOX, release 0.1.1rc0; SHA-256 pinned in `scripts/fetch_assets.py` |
| Threat-Detection-YOLOv8n | Weapon detection | MIT card (see above) | huggingface.co/Subh775/Threat-Detection-YOLOv8n @ c6d6fa4 |
| OSNet-x0.25, MSMT17 | Person re-identification | MIT code / research-only data | huggingface.co/kaiyangzhou/osnet @ a5c5cc0 |

## Data

| Data | Used for | Licence |
|---|---|---|
| MEVA | Demo footage; benchmark (planned) | CC BY 4.0; attribute wherever frames appear |
| Pexels clips | Demo footage | Pexels License |
| LLVIP (planned) | Night / thermal evaluation | Verify before use |
| Indian LP dataset, arXiv 2111.06054 (planned) | ANPR evaluation | Verify before use |

## Libraries

**Runtime (`requirements.txt`)**

| Library | Licence |
|---|---|
| opencv-python-headless | Apache-2.0 (OpenCV) / MIT (wheel packaging) |
| fastapi | MIT |
| uvicorn | BSD-3-Clause |
| onnxruntime | MIT |
| numpy | BSD-3-Clause |
| segno | BSD-3-Clause |
| cryptography | Apache-2.0 or BSD-3-Clause |
| pyserial (optional, GSM modem / siren) | BSD-3-Clause |
| paho-mqtt (optional, MQTT feed) | EPL-2.0 / EDL-1.0 |
| openvino (optional, Intel CPUs) | Apache-2.0 |
| TweetNaCl-js 1.0.3 (`static/vendor/nacl-fast.min.js`, SMS check on older phones) | Unlicense (public domain); identical to the npm release (SHA-256 3ec535c0…) |

**One-time model preparation (`requirements-export.txt`)**

| Library | Licence |
|---|---|
| torch (CPU) | BSD-3-Clause |
| huggingface_hub | Apache-2.0 |
| onnx | Apache-2.0 |
| ultralytics | AGPL-3.0, conversion tool only, not shipped |
| onnxslim | MIT (verify) |
| nncf (optional, INT8 quantization) | Apache-2.0 |

**Development (`requirements-dev.txt`)**: pytest (MIT), bandit (Apache-2.0), pip-audit (Apache-2.0).
