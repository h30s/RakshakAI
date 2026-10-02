# Third-party models, data and libraries

Everything Rakshak AI uses that we did not write, with its licence. Check the licence **before**
adding anything, and add it here in the same change. "Verify" means the licence below is taken
from the project page and must be re-checked by the compliance officer.

## ⚠ Open issues

| Item | Issue | Action |
|---|---|---|
| Ultralytics YOLOv8 (`ultralytics`, `yolov8n.pt`) | **AGPL-3.0.** A closed or government deployment needs an Ultralytics licence. The deck names YOLOX (Apache-2.0) | Replace with YOLOX (PRD A-1) |
| Threat-Detection-YOLOv8n (weapon model) | Card says MIT, but the weights are a fine-tuned YOLOv8 trained with Ultralytics; the training data licence is not stated | Check the dataset licence; retrain on YOLOX with data of known licence |
| OSNet-x0.25 weights (MSMT17) | Code is MIT, but MSMT17 is for **non-commercial research use** | Fine for the hackathon; retrain for deployment |
| Repository licence | No `LICENSE` file yet | Team to choose (Apache-2.0 suggested) |

## Models

| Model | Used for | Licence | Source |
|---|---|---|---|
| YOLOv8n | General detection (people, vehicles) | AGPL-3.0 | ultralytics |
| Threat-Detection-YOLOv8n | Weapon detection | MIT (verify; see above) | huggingface.co/Subh775/Threat-Detection-YOLOv8n |
| OSNet-x0.25, MSMT17 | Person re-identification | MIT code / research-only data | huggingface.co/kaiyangzhou/osnet |

## Data

| Data | Used for | Licence |
|---|---|---|
| MEVA | Demo footage; benchmark (planned) | CC BY 4.0; attribute wherever frames appear |
| Pexels clips | Demo footage | Pexels License |
| LLVIP (planned) | Night / thermal evaluation | Verify before use |
| Indian LP dataset, arXiv 2111.06054 (planned) | ANPR evaluation | Verify before use |

## Libraries (`requirements.txt`)

| Library | Licence |
|---|---|
| ultralytics | AGPL-3.0 (see above) |
| opencv-python-headless | Apache-2.0 (OpenCV) / MIT (wheel packaging) |
| fastapi | MIT |
| uvicorn | BSD-3-Clause |
| huggingface_hub | Apache-2.0 |
| onnxruntime | MIT |
| onnx | Apache-2.0 |
| onnxslim | MIT (verify) |
| segno | BSD-3-Clause |
| cryptography | Apache-2.0 or BSD-3-Clause |
| numpy | BSD-3-Clause |
| pytest (dev) | MIT |
