"""API and stream for the detection modes page (/modes)."""
import asyncio

import cv2
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import Response

from .. import config
from .feeds import ModeCamera

router = APIRouter()
clips: dict[str, ModeCamera] = {}  # set by the server at startup
_posters: dict[str, bytes] = {}


@router.get("/api/modes")
def list_modes():
    return [{**{k: m[k] for k in ("id", "name", "tagline", "about", "challenges")},
             "clips": [{"id": clip_id, "name": name} for clip_id, name, _ in m["clips"]]}
            for m in config.DETECTION_MODES]


def _clip(clip_id):
    cam = clips.get(clip_id)
    if cam is None:
        raise HTTPException(404, "Unknown clip")
    return cam


@router.get("/api/modes/clips/{clip_id}/objects")
def clip_objects(clip_id: str):
    cam = _clip(clip_id)
    return cam.objects.snapshot(cam.display_idx) if cam.display_idx >= 0 else []


@router.get("/api/modes/clips/{clip_id}/poster.jpg")
def clip_poster(clip_id: str):
    """A still from the clip, for the mode cards and while the live analysis starts."""
    cam = _clip(clip_id)
    if clip_id not in _posters:
        cap = cv2.VideoCapture(str(cam.path))
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) // 3)
        ok, frame = cap.read()
        cap.release()
        if not ok:
            raise HTTPException(500, "Cannot read clip")
        _posters[clip_id] = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])[1].tobytes()
    return Response(_posters[clip_id], media_type="image/jpeg", headers={"Cache-Control": "max-age=3600"})


@router.websocket("/ws/modes/{clip_id}")
async def stream_clip(ws: WebSocket, clip_id: str):
    """Streams one clip (same binary messages as /ws). The clip plays while connected."""
    cam = clips.get(clip_id)
    await ws.accept()
    if cam is None:
        await ws.close(code=4404)
        return
    closed = asyncio.Event()

    async def watch_disconnect():  # nothing is sent while the clip buffers, so listen for the close
        try:
            while (await ws.receive())["type"] != "websocket.disconnect":
                pass
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            closed.set()

    listener = asyncio.create_task(watch_disconnect())
    cam.watch()
    sent = -1
    try:
        while not closed.is_set():
            if cam.packet is not None and cam.packet_idx != sent:
                sent = cam.packet_idx
                await ws.send_bytes(cam.packet)
            await asyncio.sleep(0.5 / config.FEED_FPS)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        cam.unwatch()
        listener.cancel()
