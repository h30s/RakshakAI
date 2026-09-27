"""HTTP API for person journeys."""
import time

from fastapi import APIRouter, HTTPException

from ..pipeline import display_delay

router = APIRouter(prefix="/api/persons")
tracker = None  # JourneyTracker, set by the server at startup


def _displayed_now():
    # The video on screen runs behind real time; report journeys as of what the viewer sees.
    return time.time() - display_delay.seconds


@router.get("")
def list_persons(q: str = "", status: str = "all", limit: int = 200):
    """People seen so far, active first. q filters by ID or location; status is
    all | active | moved (seen in two or more locations)."""
    now = _displayed_now()
    items = tracker.persons_list(now) if tracker else []
    if status == "active":
        items = [p for p in items if p["active"]]
    elif status == "moved":
        items = [p for p in items if p["steps"] > 1]
    q = q.strip().lower()
    if q:
        items = [p for p in items if q in p["id"].lower() or q in p["location"].lower()]
    return {"as_of": now, "persons": items[:limit]}


@router.get("/summary")
def summary():
    active, total = tracker.counts(_displayed_now()) if tracker else (0, 0)
    return {"active": active, "total": total}


@router.get("/{pid}")
def person(pid: str):
    now = _displayed_now()
    p = tracker.person(pid.upper(), now) if tracker else None
    if p is None:
        raise HTTPException(404, "Unknown person ID")
    return {**p, "as_of": now}
