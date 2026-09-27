"""Threat monitoring API: the Overview tab, incident actions and the Reports page."""
import csv
import io
import time

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from .. import config
from .store import OPEN, STATUS_TEXT, public

router = APIRouter()
monitor = None  # ThreatMonitor, set by the server at startup


class StatusChange(BaseModel):
    status: str
    note: str = ""


class Note(BaseModel):
    note: str


@router.get("/reports")
def reports_page():
    return FileResponse(config.STATIC_DIR / "reports.html")


@router.get("/api/threats/overview")
def overview():
    return monitor.overview()


def _filtered(status="all", q="", days=0):
    now = time.time()
    q = q.strip().lower()
    out = []
    for i in reversed(monitor.store.all()):
        if status == "open" and i["status"] not in OPEN:
            continue
        if status not in ("all", "open") and i["status"] != status:
            continue
        if days and now - i["detected_at"] > days * 86400:
            continue
        if q and q not in f"{i['id']} {i['type']} {i['camera']} {i['location']}".lower():
            continue
        out.append(i)
    return out


@router.get("/api/threats")
def list_threats(status: str = "all", q: str = "", days: int = 0):
    items = _filtered(status, q, days)
    everything = monitor.store.all()
    return {
        "now": time.time(),
        "counts": {s: sum(1 for i in everything if i["status"] == s) for s in STATUS_TEXT} | {"total": len(everything)},
        "threats": [public(i) for i in items],
    }


@router.get("/api/threats/export.csv")
def export_csv(status: str = "all", q: str = "", days: int = 0):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["ID", "Detected", "Camera", "Location", "Threat type", "Threat score", "Level", "Status",
                "Action taken", "Resolved", "Time to resolve (min)"])
    fmt = lambda t: time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t)) if t else ""
    for i in _filtered(status, q, days):
        p = public(i)
        w.writerow([p["id"], fmt(p["detected_at"]), p["camera"], p["location"], p["type"], p["score"], p["level"],
                    p["status_text"], p["last_action"] or "", fmt(p["resolved_at"]),
                    round(p["time_to_resolve"] / 60, 1) if p["time_to_resolve"] else ""])
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="threat-report.csv"'})


def _incident(threat_id):
    incident = monitor.store.get(threat_id)
    if incident is None:
        raise HTTPException(404, "Unknown threat")
    return incident


@router.get("/api/threats/{threat_id}")
def threat(threat_id: str):
    return public(_incident(threat_id), with_history=True)


@router.get("/api/threats/{threat_id}/snapshot.jpg")
def threat_snapshot(threat_id: str):
    _incident(threat_id)
    path = monitor.store.snapshot_path(threat_id)
    if path is None:
        raise HTTPException(404, "No snapshot")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "max-age=86400"})


@router.post("/api/threats/{threat_id}/status")
def set_status(threat_id: str, change: StatusChange):
    _incident(threat_id)
    try:
        incident = monitor.store.set_status(threat_id, change.status, change.note)
    except ValueError:
        raise HTTPException(400, "Unknown status")
    monitor.store.save_if_dirty()
    return public(incident, with_history=True)


@router.post("/api/threats/{threat_id}/note")
def add_note(threat_id: str, note: Note):
    _incident(threat_id)
    incident = monitor.store.add_note(threat_id, note.note)
    monitor.store.save_if_dirty()
    return public(incident, with_history=True)
