"""FastAPI server: serves the dashboard, streams feeds over one WebSocket, exposes detected objects."""
import asyncio
import logging
import time
from contextlib import asynccontextmanager

import cv2
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .modes import api as modes_api
from .modes.feeds import ModeCamera
from .pipeline import Camera, DetectionLoop
from .sources import api as sources_api
from .sources.feeds import LiveCamera
from .threats import api as threats_api
from .threats.monitor import ThreatMonitor
from .threats.store import IncidentStore
from .tracking import api as tracking_api
from .tracking.feeds import SyncedCamera
from .tracking.tracker import JourneyTracker
from .website import api as website_api

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("cctv")

cameras: list[Camera] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    mode_clips = [clip for m in config.DETECTION_MODES for clip in m["clips"]]
    missing = [f for _, _, f in config.CAMERAS + mode_clips if not (config.VIDEO_DIR / f).exists()]
    if missing:
        raise RuntimeError(f"Missing videos {missing} in {config.VIDEO_DIR} — run scripts/fetch_assets.py first")
    site_of = {cam: site for site, cams in config.TRACKING_SITES.items() for cam in cams}
    clocks = {site: time.monotonic() for site in config.TRACKING_SITES}
    files = {cam_id: config.VIDEO_DIR / file for cam_id, _, file in config.CAMERAS}
    loop_frames = {site: min(frame_count(files[c]) for c in cams) for site, cams in config.TRACKING_SITES.items()}
    for i, (cam_id, name, file) in enumerate(config.CAMERAS):
        if cam_id in site_of:  # recorded simultaneously with the rest of its site: play in lockstep
            site = site_of[cam_id]
            cameras.append(SyncedCamera(i, cam_id, name, files[cam_id], clocks[site], loop_frames[site]))
        else:
            cameras.append(Camera(i, cam_id, name, config.VIDEO_DIR / file))
    # Live sources (webcam, USB camera, phone): ordinary dashboard cameras fed by a device.
    for cam_id, name in config.LIVE_SOURCES:
        sources_api.sources[cam_id] = LiveCamera(len(cameras), cam_id, name)
        cameras.append(sources_api.sources[cam_id])
    tracker = JourneyTracker({c.id: c.name for c in cameras})
    tracking_api.tracker = tracker
    # Detection-modes clips: same detection loop, but they only play while watched on /modes
    # and are not dashboard cameras (not in /ws, /api/cameras or journey tracking).
    for i, (clip_id, name, file) in enumerate(mode_clips, start=len(cameras)):
        modes_api.clips[clip_id] = ModeCamera(i, clip_id, name, config.VIDEO_DIR / file)

    def track(t, group):
        group = [item for item in group if item[0] not in modes_api.clips]
        if group:
            tracker.update(t, group)

    feeds = cameras + list(modes_api.clips.values())
    loop = DetectionLoop(feeds, on_results=track)  # loads the models before any feed starts
    for cam in feeds:
        cam.start()
    loop.start()
    # Threat monitoring (Overview tab): camera health and weapon incidents on dashboard cameras.
    threats_api.monitor = ThreatMonitor(cameras, loop, IncidentStore())
    threats_api.monitor.start()
    sources_api.start_phone_server()
    log.info("Started %d cameras", len(cameras))
    yield


def frame_count(path):
    cap = cv2.VideoCapture(str(path))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    return n


app = FastAPI(title="CCTV Object Detection", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")


@app.middleware("http")
async def revalidate_static(request, call_next):
    """Make browsers re-check the page, scripts and styles on every load (cheap 304s), so an
    updated dashboard is picked up without a hard refresh."""
    response = await call_next(request)
    if request.url.path in ("/", "/app", "/modes", "/reports", "/feedback") or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache"
    return response
app.include_router(tracking_api.router)
app.include_router(modes_api.router)
app.include_router(sources_api.router)
app.include_router(threats_api.router)
app.include_router(website_api.router)


@app.get("/modes")
def modes_page():
    return FileResponse(config.STATIC_DIR / "modes.html")


@app.get("/api/cameras")
def list_cameras():
    site_of = {cam: site for site, cams in config.TRACKING_SITES.items() for cam in cams}
    site_of.update({cam: config.LIVE_GROUP for cam in sources_api.sources})
    return [{"index": c.index, "id": c.id, "name": c.name, "group": site_of.get(c.id, config.DEFAULT_GROUP),
             "multi_camera": c.id in config.TRACKING_SITES.get(site_of.get(c.id), ()),
             "live": c.id in sources_api.sources} for c in cameras]


@app.get("/api/cameras/{cam_id}/objects")
def camera_objects(cam_id: str):
    cam = next((c for c in cameras if c.id == cam_id), None)
    if cam is None:
        raise HTTPException(404, "Unknown camera")
    return cam.objects.snapshot(cam.display_idx)


@app.websocket("/ws")
async def stream(ws: WebSocket):
    """Pushes every camera's latest frame + detections as binary messages."""
    await ws.accept()
    sent = [-1] * len(cameras)
    try:
        while True:
            for cam in cameras:
                if cam.packet is not None and cam.packet_idx != sent[cam.index]:
                    sent[cam.index] = cam.packet_idx
                    await ws.send_bytes(cam.packet)
            await asyncio.sleep(0.5 / config.FEED_FPS)
    except (WebSocketDisconnect, RuntimeError):
        pass
