"""Decision layer API: ranked alerts, the shift budget, surge mode, Watch Orders and the ledger."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse, Response
from pydantic import BaseModel

from .. import config

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


@router.get("/decision")
def decision_page():
    return FileResponse(config.STATIC_DIR / "decision.html")


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
