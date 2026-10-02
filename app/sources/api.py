"""Camera sources: status API, the device upload stream, and the phone's HTTPS page.

A device (this browser's webcam, a USB camera, or a phone) sends JPEG frames over
/ws/sources/{id}/publish; the frames feed a LiveCamera, which is an ordinary dashboard camera
processed by the one shared detection loop.
"""
import io
import logging
import secrets
import threading

import segno
import uvicorn
from fastapi import APIRouter, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, RedirectResponse, Response

from .. import config
from . import network
from .feeds import LiveCamera

log = logging.getLogger(__name__)

router = APIRouter()
sources: dict[str, LiveCamera] = {}   # set by the server at startup
phone = {"url": None, "server": None}  # the HTTPS listener for phones
PHONE_SLOT = "live-mobile"
PHONE_FILES = {"phone.js", "phone.css", "capture.js"}


# ---------- Status (dashboard) ----------

@router.get("/api/sources")
def list_sources():
    server = phone["server"]
    return {
        "sources": [{"id": c.id, "name": c.name, "connected": c.streaming, "device": c.device,
                     "since": c.connected_at} for c in sources.values()],
        "phone": {"url": phone["url"], "ready": bool(server and server.started)},
        "adb": network.find_adb() is not None,
    }


@router.get("/api/sources/qr.svg")
def phone_qr():
    if not phone["url"]:
        raise HTTPException(503, "Phone connection is not available")
    buf = io.BytesIO()
    segno.make(phone["url"], error="m").save(buf, kind="svg", scale=6, border=2, dark="#0d1014", light="#ffffff")
    return Response(buf.getvalue(), media_type="image/svg+xml", headers={"Cache-Control": "no-store"})


@router.post("/api/sources/{source_id}/disconnect")
def disconnect_source(source_id: str):
    """Drop the connected device (it is told it was disconnected)."""
    cam = sources.get(source_id)
    if cam is None:
        raise HTTPException(404, "Unknown source")
    cam.disconnect(cam.publisher)
    return {"ok": True}


@router.post("/api/sources/usb-phone")
def usb_phone(request: Request):
    ok, message = network.connect_phone_over_usb(request.url.port or 80, "/phone")
    return {"ok": ok, "message": message}


# ---------- Device upload (both listeners) ----------

async def publish(ws: WebSocket, source_id: str, t: str = "", device: str = "Camera"):
    """Receives one device's frames (binary JPEG messages) for a source until it disconnects or
    another device takes the source over."""
    cam = sources.get(source_id)
    await ws.accept()
    if cam is None:
        await ws.close(code=4404)
        return
    # Devices on the network must present the pairing token from the QR code.
    if not network.is_loopback(ws.client.host) and not secrets.compare_digest(t, network.PAIRING_TOKEN):
        await ws.close(code=4403)
        return
    session, _ = cam.connect(device[:80])
    try:
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                break
            if msg.get("bytes") and not cam.receive(session, msg["bytes"]):
                await ws.close(code=4409)  # another device took this source over
                break
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        cam.disconnect(session)


router.add_api_websocket_route("/ws/sources/{source_id}/publish", publish)


def _phone_page():
    return FileResponse(config.STATIC_DIR / "phone.html")


router.add_api_route("/phone", _phone_page, methods=["GET"])  # also reached over USB (adb reverse)


# ---------- HTTPS listener for phones ----------
# Phones on the network only reach this small app: the camera page, its scripts and the upload
# stream (which needs the pairing token). The dashboard itself stays on localhost.

phone_app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
phone_app.add_api_route("/phone", _phone_page, methods=["GET"])
phone_app.add_api_websocket_route("/ws/sources/{source_id}/publish", publish)


@phone_app.get("/")
def phone_root():
    return RedirectResponse("/phone")


@phone_app.get("/static/{name}")
def phone_static(name: str):
    if name not in PHONE_FILES:
        raise HTTPException(404)
    return FileResponse(config.STATIC_DIR / name, headers={"Cache-Control": "no-cache"})


def start_phone_server():
    """Serve phone_app over HTTPS on the local network, in a background thread."""
    try:
        host = network.lan_ip()
        cert, key = network.ensure_certificate(host)
    except Exception:
        log.exception("Phone connection disabled: could not prepare the HTTPS certificate")
        return
    server = uvicorn.Server(uvicorn.Config(
        phone_app, host="0.0.0.0", port=config.PHONE_PORT, ssl_certfile=str(cert), ssl_keyfile=str(key),
        lifespan="off", log_level="warning"))
    phone["server"] = server
    phone["url"] = f"https://{host}:{config.PHONE_PORT}/phone?t={network.PAIRING_TOKEN}"
    threading.Thread(target=server.run, daemon=True, name="phone-https").start()
    log.info("Phone camera page: https://%s:%d/phone (scan the QR code in Camera Sources)", host, config.PHONE_PORT)
