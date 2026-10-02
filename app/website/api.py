"""Public website: the landing page (/) and visitor feedback on the prototype.

Feedback is appended to data/feedback.jsonl. Anyone can submit it; only this machine can read it
back (/feedback and /api/feedback), because entries may contain names and email addresses.
"""
import json
import threading
import time
import uuid

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .. import config
from ..sources.network import is_loopback

router = APIRouter()
FEEDBACK_FILE = config.DATA_DIR / "feedback.jsonl"
ROLES = {"government", "security", "academia", "industry", "student", "other"}
_lock = threading.Lock()
_last_by_ip = {}
MIN_INTERVAL_S = 10  # one submission per visitor every few seconds is plenty


class Feedback(BaseModel):
    role: str = Field(max_length=20)
    rating: int = Field(ge=1, le=5)
    useful: str = Field("", max_length=2000)
    improve: str = Field("", max_length=2000)
    organisation: str = Field("", max_length=120)
    name: str = Field("", max_length=80)
    email: str = Field("", max_length=120)
    follow_up: bool = False
    tried_demo: bool = False


@router.get("/")
def landing():
    return FileResponse(config.STATIC_DIR / "landing.html")


@router.get("/app")
def operations_console():
    return FileResponse(config.STATIC_DIR / "index.html")


@router.post("/api/feedback", status_code=201)
def submit_feedback(fb: Feedback, request: Request):
    if fb.role not in ROLES:
        raise HTTPException(422, "Unknown role")
    ip = request.client.host if request.client else ""
    now = time.time()
    with _lock:
        if now - _last_by_ip.get(ip, 0) < MIN_INTERVAL_S:
            raise HTTPException(429, "Please wait a few seconds before sending again")
        _last_by_ip[ip] = now
        entry = {"id": uuid.uuid4().hex[:10], "at": now, **fb.model_dump()}
        FEEDBACK_FILE.parent.mkdir(parents=True, exist_ok=True)
        with FEEDBACK_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return {"ok": True}


def _local_only(request: Request):
    if not (request.client and is_loopback(request.client.host)):
        raise HTTPException(403, "Feedback can only be read on the machine running Rakshak AI")


@router.get("/api/feedback")
def list_feedback(request: Request):
    _local_only(request)
    if not FEEDBACK_FILE.exists():
        return []
    with _lock:
        lines = FEEDBACK_FILE.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in reversed(lines) if line.strip()]


@router.get("/feedback")
def feedback_page(request: Request):
    _local_only(request)
    return FileResponse(config.STATIC_DIR / "feedback.html")
