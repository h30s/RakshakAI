"""Decision layer API: ranked alerts, the shift budget, surge mode, Watch Orders, the ledger,
live push to the console, C2 feeds, Border Pulse and the shift report."""
import asyncio
import hmac
import time

from fastapi import APIRouter, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field

from .. import config
from .engine import load_movements
from .ledger import public_bytes
from .pulse import pulse

router = APIRouter()
engine = None  # DecisionEngine, set by the server at startup


class WatchOrderIn(BaseModel):
    camera: str
    minutes: int = 60
    reason: str = ""


class SurgeIn(BaseModel):
    mode: str  # "auto", "on" or "off"


class StatusIn(BaseModel):
    status: str  # "acknowledged", "escalated" or "dismissed"


class DeliveredIn(BaseModel):
    channel: str = "console"


class ExternalHitIn(BaseModel):
    source: str = Field(max_length=20)       # "frs", "anpr", "watchlist", ...
    camera: str = Field(max_length=40)
    label: str = Field(max_length=40)         # watchlist id or plate, as the source system names it
    confidence: float | None = Field(None, ge=0, le=1)


# ---------------------------------------------------------------- pages
@router.get("/decision")
def decision_page():
    return FileResponse(config.STATIC_DIR / "decision.html")


@router.get("/pulse")
def pulse_page():
    return FileResponse(config.STATIC_DIR / "pulse.html")


@router.get("/shift-report")
def shift_report_page():
    return FileResponse(config.STATIC_DIR / "shift-report.html")


@router.get("/verify")
def verify_page():
    """Offline SMS check for the duty phone: paste an alert SMS, the page checks its signature."""
    return FileResponse(config.STATIC_DIR / "verify.html")


# Keeps /verify working with no network once it has been opened (needs HTTPS, as for the phone
# camera page). Network first, so an updated page is picked up whenever the post is reachable.
VERIFY_SW = """const CACHE = "rk-verify-v1";
const FILES = ["/verify", "/static/i18n.js", "/static/vendor/nacl-fast.min.js"];
self.addEventListener("install", (e) => e.waitUntil(caches.open(CACHE).then((c) => c.addAll(FILES))));
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || !FILES.includes(url.pathname)) return;
  e.respondWith(fetch(e.request).then((res) => {
    const copy = res.clone();
    caches.open(CACHE).then((c) => c.put(url.pathname, copy));
    return res;
  }).catch(() => caches.match(url.pathname)));
});
"""


@router.get("/verify-sw.js")
def verify_service_worker():
    return Response(VERIFY_SW, media_type="text/javascript", headers={"Cache-Control": "no-cache"})


# ---------------------------------------------------------------- alerts
@router.get("/api/decision/overview")
def overview():
    return engine.overview()


@router.post("/api/decision/alerts/{alert_id}/status")
def alert_status(alert_id: str, change: StatusIn):
    if change.status not in ("acknowledged", "escalated", "dismissed"):
        raise HTTPException(400, "Unknown status")
    alert = engine.set_status(alert_id, change.status)
    if alert is None:
        raise HTTPException(404, "Unknown alert")
    return alert


@router.post("/api/decision/alerts/{alert_id}/delivered")
def alert_delivered(alert_id: str, body: DeliveredIn):
    """The console reports the moment it first showed an alert (console latency)."""
    if body.channel != "console":
        raise HTTPException(400, "Unknown channel")
    alert = engine.delivered(alert_id, body.channel)
    if alert is None:
        raise HTTPException(404, "Unknown alert")
    return {"id": alert_id, "latency": alert["latency"]}


@router.get("/api/decision/alerts/{alert_id}/certificate", response_class=PlainTextResponse)
def certificate(alert_id: str):
    text = engine.certificate(alert_id)
    if text is None:
        raise HTTPException(404, "Unknown alert")
    return text


@router.get("/api/decision/alerts/{alert_id}/packet")
def packet(alert_id: str):
    data = engine.packet(alert_id)
    if data is None:
        raise HTTPException(404, "Unknown alert")
    return Response(data, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{alert_id}-evidence.zip"'})


@router.post("/api/decision/external-hits")
def external_hit(hit: ExternalHitIn, x_rakshak_token: str | None = Header(None)):
    """A hit from SSB's existing FRS / ANPR joins the ranked queue as an always-alert. Hits
    bypass the budget, so when post.json sets "integration_token" every request must carry it
    (header X-Rakshak-Token); otherwise anyone on the post LAN could flood the operator."""
    token = engine.cfg.get("integration_token")
    if token and not hmac.compare_digest(token, x_rakshak_token or ""):
        raise HTTPException(401, "Missing or wrong X-Rakshak-Token")
    return engine.external_hit(hit.source, hit.camera, hit.label, hit.confidence)


@router.get("/api/decision/latency")
def latency():
    return engine.latency_stats()


@router.get("/api/decision/shift-report")
def shift_report(at: float | None = None):
    return engine.shift_report(at)


@router.get("/api/decision/pulse")
def border_pulse(weeks: int = 4):
    return pulse(load_movements(engine.movements_csv), time.time(), weeks_before=max(1, min(weeks, 8)))


@router.get("/api/decision/pubkey", response_class=PlainTextResponse)
def pubkey():
    """This post's Ed25519 public key (hex), for the duty phone, HQ and C2 consumers."""
    return public_bytes(engine.ledger.key).hex()


# ---------------------------------------------------------------- budget controls
@router.post("/api/decision/rebaseline")
def rebaseline():
    """Refit the baseline now (e.g. after a drift warning) instead of waiting for the night."""
    engine.relearn()
    engine.ledger.append("rebaseline", {"mode": engine.mode, "days_learned": engine.days_learned})
    return engine.overview()


@router.post("/api/decision/watch-orders")
def watch_order(order: WatchOrderIn):
    w = engine.watch_order(order.camera, order.minutes, order.reason)
    return {"camera": w.camera, "until": w.until, "reason": w.reason}


@router.post("/api/decision/surge")
def surge(change: SurgeIn):
    if change.mode not in ("auto", "on", "off"):
        raise HTTPException(400, "mode must be auto, on or off")
    engine.set_surge(change.mode)
    return engine.overview()["surge"]


@router.get("/api/decision/ledger/verify")
def verify_ledger():
    problems = engine.ledger.verify()
    return {"entries": len(engine.ledger.entries), "head": engine.ledger.head, "intact": not problems,
            "problems": problems}


# ---------------------------------------------------------------- live push
@router.websocket("/ws/decision")
async def decision_stream(ws: WebSocket):
    """The console's live view: the overview, pushed whenever it changes (checked 5x a second)."""
    await ws.accept()
    sent = None
    try:
        while True:
            if engine.version != sent:
                sent = engine.version
                await ws.send_json(engine.overview())
            await asyncio.sleep(0.2)
    except (WebSocketDisconnect, RuntimeError):
        pass


@router.websocket("/ws/c2")
async def c2_stream(ws: WebSocket, from_seq: int = 0):
    """Command-and-control feed: every signed ledger entry from `from_seq`, then live."""
    await ws.accept()
    seq = max(0, from_seq)
    try:
        while True:
            entries = engine.ledger.entries
            while seq < len(entries):
                await ws.send_json(entries[seq])
                seq += 1
            await asyncio.sleep(0.2)
    except (WebSocketDisconnect, RuntimeError):
        pass
