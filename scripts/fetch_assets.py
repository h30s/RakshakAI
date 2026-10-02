"""Download the demo footage and model weights.

Footage: free stock clips from Pexels (Pexels License — free to use, no attribution required).
Each clip is center-cropped to 16:9, scaled to 640x360, resampled to the feed frame rate and
trimmed, so the server only has to loop small files.

Journey-tracking footage: five cameras of the MEVA dataset (https://mevadata.org, CC BY 4.0)
inside and around one school building, recorded at the same moment. The same 3-minute window is
cut from each so the feeds can be played in lockstep.

Detection-modes footage (the /modes page): Pexels clips recorded at night, in fog, rain and
snow, plus two real thermal surveillance cameras of the MEVA dataset (CC BY 4.0).

General detector: YOLOX (Megvii, Apache-2.0), official ONNX release (GENERAL_MODEL, default yolox_tiny.onnx).
Weapon model: Subh775/Threat-Detection-YOLOv8n on Hugging Face (MIT card; trained with Ultralytics,
see THIRD_PARTY.md), exported once to ONNX.
Person re-identification model: OSNet-x0.25 trained on MSMT17, kaiyangzhou/osnet on Hugging Face
(MIT; the MSMT17 training data is for non-commercial research use), converted to ONNX.

Usage:  python scripts/fetch_assets.py [--force] [--models-only]
"""
import hashlib
import shutil
import sys
import tempfile
import urllib.request
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config  # noqa: E402
from app.detector import onnx_path  # noqa: E402

# output file -> Pexels video id (https://www.pexels.com/video/<id>/)
FOOTAGE = {
    "ground_floor_1.mp4": 5762612,   # shopping-centre ground floor, people walking
    "ground_floor_2.mp4": 4750042,   # shopping aisle with trolleys
    "first_floor_1.mp4": 854665,     # upper-level walkway
    "first_floor_2.mp4": 4750049,    # escalator up to the first floor
    "parking_1.mp4": 34765009,       # car park at night, high angle
    "parking_2.mp4": 6092110,        # man holding a rifle (gun detection test)
    "entrance_1.mp4": 30243320,      # plaza in front of a building entrance
    "entrance_2.mp4": 8094256,       # person holding a knife (knife detection test)
}
MAX_SECONDS = 30

# output file -> (MEVA recording, start second within it, crop box as fractions or None)
MEVA_URL = "https://mevadata-public-01.s3.amazonaws.com/drops-123-r13/2018-03-09/10/"
SITE_FOOTAGE = {
    # recordings starting at 10:10:01 are cut one second earlier to line up with the 10:10:00 ones
    "school_plaza.mp4": ("2018-03-09.10-10-01.10-15-01.school.G638.r13.avi", 119, (0.15, 0.25, 0.85, 0.955)),
    "school_lobby.mp4": ("2018-03-09.10-10-01.10-15-01.school.G420.r13.avi", 119, None),
    "school_stairwell.mp4": ("2018-03-09.10-10-00.10-15-00.school.G419.r13.avi", 120, None),
    "school_cafeteria.mp4": ("2018-03-09.10-10-00.10-15-00.school.G421.r13.avi", 120, None),
    "school_hallway.mp4": ("2018-03-09.10-10-00.10-15-00.school.G423.r13.avi", 120, (0.2, 0.08, 0.8, 0.685)),
}
SITE_SECONDS = 180

# Detection-modes footage: output file -> (source URL, start second, seconds, crop box or None).
# Pexels clips are taken at 960x540 (their CDN renditions); links are on https://www.pexels.com/video/<id>/.
PEXELS_CDN = "https://videos.pexels.com/video-files/"
MEVA_ROOT = "https://mevadata-public-01.s3.amazonaws.com/drops-123-r13/"
MODE_FOOTAGE = {
    # Normal: pexels 27700659 (crossing, high angle), 14365420 (Toronto street corner)
    "mode_day_crossing.mp4": (PEXELS_CDN + "27700659/12208357_960_540_60fps.mp4", 0, 30, None),
    "mode_day_street.mp4": (PEXELS_CDN + "14365420/14365420-sd_960_540_30fps.mp4", 0, 30, None),
    # Night: pexels 4122942 (night market; starts out of focus), 11839819 (dark street)
    "mode_night_market.mp4": (PEXELS_CDN + "4122942/4122942-sd_960_540_24fps.mp4", 6, 30, None),
    "mode_night_street.mp4": (PEXELS_CDN + "11839819/11839819-sd_960_540_25fps.mp4", 0, 30, None),
    # Thermal: MEVA camera G476 (thermal IR, 352x240), cropped to where people walk
    "mode_thermal_1.mp4": (MEVA_ROOT + "2018-03-07/11/2018-03-07.11-05-00.11-10-00.hospital.G476.r13.avi",
                           0, 60, (0.0, 0.22, 0.72, 0.81)),
    "mode_thermal_2.mp4": (MEVA_ROOT + "2018-03-07/11/2018-03-07.11-10-00.11-15-00.hospital.G476.r13.avi",
                           130, 60, (0.28, 0.22, 1.0, 0.81)),
    # Fog: pexels 11786068 (foggy square at night), 29725266 (misty park)
    "mode_fog_square.mp4": (PEXELS_CDN + "11786068/11786068-sd_960_540_25fps.mp4", 0, 30, None),
    "mode_fog_park.mp4": (PEXELS_CDN + "29725266/12779330_960_540_50fps.mp4", 0, 30, None),
    # Rain & snow: pexels 5743580 (rainy night, London), 30379876 (snowfall, Toronto)
    "mode_rain_street.mp4": (PEXELS_CDN + "5743580/5743580-sd_960_540_30fps.mp4", 0, 30, None),
    "mode_snow_street.mp4": (PEXELS_CDN + "30379876/13019692_960_540_60fps.mp4", 0, 30, None),
}

YOLOX_URL = "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/"
# Pinned: a changed file on the server is refused instead of silently run (supply-chain check).
YOLOX_SHA256 = {
    "yolox_nano.onnx": "c789161ed43c8269fcd4e67c67eeeb4e80c622da2eb296a20bc6007bd18a0b7d",
    "yolox_tiny.onnx": "427cc366d34e27ff7a03e2899b5e3671425c262ea2291f88bb942bc1cc70b0f7",
    "yolox_s.onnx": "c5c2d13e59ae883e6af3b45daea64af4833a4951c92d116ec270d9ddbe998063",
}
REID_REVISION = "a5c5cc037c24235cda3b21085b93ad77c9616224"
THREAT_REPO, THREAT_REVISION = "Subh775/Threat-Detection-YOLOv8n", "c6d6fa4e6c9bfd4c4fccb46478db23609e5468fb"
REID_REPO = "kaiyangzhou/osnet"
REID_FILE = ("osnet_x0_25_msmt17_combineall_256x128_amsgrad_ep150_stp60_lr0.0015_b64_fb10_softmax_"
             "labelsmooth_flip_jitter.pth")


def download(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)


def transcode(src, dest, start=0, seconds=MAX_SECONDS, crop=None):
    """crop: (x0, y0, x1, y1) as fractions of the frame (should be 16:9); default center 16:9."""
    cap = cv2.VideoCapture(str(src))
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30
    w, h = cap.get(cv2.CAP_PROP_FRAME_WIDTH), cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
    if crop:
        x0, y0 = int(crop[0] * w), int(crop[1] * h)
        cw, ch = int((crop[2] - crop[0]) * w), int((crop[3] - crop[1]) * h)
    else:  # center crop to 16:9
        if w / h > 16 / 9:
            cw, ch = int(h * 16 / 9), int(h)
        else:
            cw, ch = int(w), int(w * 9 / 16)
        x0, y0 = int((w - cw) // 2), int((h - ch) // 2)
    if start:
        cap.set(cv2.CAP_PROP_POS_FRAMES, round(start * src_fps))

    out = cv2.VideoWriter(str(dest), cv2.VideoWriter_fourcc(*"mp4v"), config.FEED_FPS,
                          (config.FRAME_W, config.FRAME_H))
    written, i = 0, 0
    while written < seconds * config.FEED_FPS:
        ok, frame = cap.read()
        if not ok:
            break
        # keep the source frames that fall on the output frame-rate grid
        if i >= round(written * src_fps / config.FEED_FPS):
            frame = cv2.resize(frame[y0:y0 + ch, x0:x0 + cw], (config.FRAME_W, config.FRAME_H),
                               interpolation=cv2.INTER_AREA)
            out.write(frame)
            written += 1
        i += 1
    out.release()
    return written


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # the Windows console can't print ↓ ⚙ ✓ otherwise
    force = "--force" in sys.argv
    config.VIDEO_DIR.mkdir(exist_ok=True)
    config.MODEL_DIR.mkdir(exist_ok=True)
    if "--models-only" not in sys.argv:
        fetch_footage(force)
    fetch_models(force)
    print("Done.")


def fetch_footage(force):
    with tempfile.TemporaryDirectory() as tmp:
        for name, pexels_id in FOOTAGE.items():
            dest = config.VIDEO_DIR / name
            if dest.exists() and not force:
                print(f"✓ {name} (exists)")
                continue
            raw = Path(tmp) / f"{pexels_id}.mp4"
            print(f"↓ {name}  ← pexels {pexels_id}")
            download(f"https://www.pexels.com/download/video/{pexels_id}/", raw)
            frames = transcode(raw, dest)
            print(f"  {frames} frames @ {config.FEED_FPS:g} fps")

        for name, (recording, start, crop) in SITE_FOOTAGE.items():
            dest = config.VIDEO_DIR / name
            if dest.exists() and not force:
                print(f"✓ {name} (exists)")
                continue
            raw = Path(tmp) / recording
            print(f"↓ {name}  ← MEVA {recording}")
            download(MEVA_URL + recording, raw)
            frames = transcode(raw, dest, start, SITE_SECONDS, crop)
            raw.unlink()
            print(f"  {frames} frames @ {config.FEED_FPS:g} fps")

        for name, (url, start, seconds, crop) in MODE_FOOTAGE.items():
            dest = config.VIDEO_DIR / name
            if dest.exists() and not force:
                print(f"✓ {name} (exists)")
                continue
            raw = Path(tmp) / url.rsplit("/", 1)[1]
            print(f"↓ {name}  ← {url}")
            download(url, raw)
            frames = transcode(raw, dest, start, seconds, crop)
            raw.unlink()
            print(f"  {frames} frames @ {config.FEED_FPS:g} fps")


def fetch_models(force):
    if not config.REID_MODEL.exists() or force:
        from huggingface_hub import hf_hub_download
        from app.tracking.reid import export_onnx
        print(f"↓ person re-identification model  ← {REID_REPO}")
        export_onnx(hf_hub_download(REID_REPO, REID_FILE, revision=REID_REVISION), config.REID_MODEL)
    general = config.MODEL_DIR / config.GENERAL_MODEL
    if not general.exists() or force:
        print(f"↓ {config.GENERAL_MODEL}  ← Megvii YOLOX release (Apache-2.0)")
        download(YOLOX_URL + config.GENERAL_MODEL, general)
        expected = YOLOX_SHA256.get(config.GENERAL_MODEL)
        if expected and hashlib.sha256(general.read_bytes()).hexdigest() != expected:
            general.unlink()
            raise SystemExit(f"{config.GENERAL_MODEL}: SHA-256 does not match the pinned release; not installed")
    threat_onnx = onnx_path(config.THREAT_MODEL, config.THREAT_IMGSZ)
    if not threat_onnx.exists() or force:
        from huggingface_hub import hf_hub_download
        print(f"↓ weapon model  ← {THREAT_REPO}")
        shutil.copy(hf_hub_download(THREAT_REPO, "weights/best.pt", revision=THREAT_REVISION), config.THREAT_MODEL)
        # One-time export to ONNX; the running system needs only ONNX Runtime. This step needs the
        # ultralytics package (AGPL-3.0): pip install -r requirements-export.txt
        try:
            from ultralytics import YOLO
        except ImportError:
            print("  ! to export the weapon model: pip install -r requirements-export.txt, then run this again")
        else:
            print(f"⚙ {threat_onnx.name}")
            exported = YOLO(str(config.THREAT_MODEL)).export(format="onnx", imgsz=config.THREAT_IMGSZ, dynamic=True,
                                                             batch=16, verbose=False)
            shutil.move(exported, threat_onnx)


if __name__ == "__main__":
    main()
