"""Threat incidents: what was detected where, how serious it is and whether it is handled.

An incident is opened when a confirmed weapon appears on a dashboard camera. Further sightings
of the same kind of weapon on that camera are added to the open incident rather than opening a
new one, so a weapon that stays in view (or a looping demo clip) raises one alert, not dozens.
The operator marks an incident "Working on it" (in progress) or "Resolved". Everything is kept
in DATA_DIR/threats.json (and snapshots in DATA_DIR/snapshots) for the Reports page.
"""
import json
import logging
import threading
import time

from .. import config

log = logging.getLogger(__name__)

ACTIVE, IN_PROGRESS, RESOLVED = "active", "in_progress", "resolved"
STATUS_TEXT = {ACTIVE: "Active", IN_PROGRESS: "In progress", RESOLVED: "Resolved"}
OPEN = (ACTIVE, IN_PROGRESS)


def threat_score(label, confidence):
    severity = config.THREAT_SEVERITY.get(label, 70)
    return round(severity * (0.75 + 0.25 * confidence))


def level(score):
    return next((name for threshold, name in config.THREAT_LEVELS if score >= threshold), "None")


class IncidentStore:
    def __init__(self, path=None):
        self.path = path or config.DATA_DIR / "threats.json"
        self.snapshot_dir = self.path.parent / "snapshots"
        self.incidents = []  # oldest first
        self.next_number = 1
        self.lock = threading.RLock()
        self.dirty = False
        self._load()

    # ---------- persistence ----------
    def _load(self):
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.incidents, self.next_number = data["incidents"], data["next_number"]
            log.info("Loaded %d threat incidents from %s", len(self.incidents), self.path)
        except (OSError, ValueError, KeyError):
            log.exception("Could not read %s; starting a new incident history", self.path)

    def save_if_dirty(self):
        with self.lock:
            if not self.dirty:
                return
            data = json.dumps({"next_number": self.next_number, "incidents": self.incidents})
            self.dirty = False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(data, encoding="utf-8")
        tmp.replace(self.path)

    def save_snapshot(self, incident, jpeg):
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        (self.snapshot_dir / f"{incident['id']}.jpg").write_bytes(jpeg)
        with self.lock:
            incident["snapshot"] = True
            self.dirty = True

    def snapshot_path(self, incident_id):
        path = self.snapshot_dir / f"{incident_id}.jpg"
        return path if path.exists() else None

    # ---------- detection side ----------
    def open_incident_for(self, camera_id, label):
        with self.lock:
            return next((i for i in reversed(self.incidents)
                         if i["camera_id"] == camera_id and i["label"] == label and i["status"] in OPEN), None)

    def recently_resolved_for(self, camera_id, label, within):
        now = time.time()
        with self.lock:
            return next((i for i in reversed(self.incidents)
                         if i["camera_id"] == camera_id and i["label"] == label and i["status"] == RESOLVED
                         and now - i["resolved_at"] < within), None)

    def seen_after_resolution(self, incident, when):
        with self.lock:
            incident["last_seen"] = max(incident["last_seen"], when)
            if not any(h["event"] == "seen_again" for h in incident["history"][-1:]):
                incident["history"].append({"t": when, "event": "seen_again",
                                            "text": "Seen again shortly after it was resolved (no new alert)"})
            self.dirty = True

    def create(self, *, camera_id, camera, location, label, confidence, detected_at, thumbnail):
        with self.lock:
            score = threat_score(label, confidence)
            incident = {
                "id": f"T-{self.next_number:04d}", "label": label, "type": label.title(),
                "camera_id": camera_id, "camera": camera, "location": location,
                "detected_at": detected_at, "last_seen": detected_at, "sightings": 1,
                "confidence": round(confidence * 100), "score": score, "level": level(score),
                "status": ACTIVE, "updated_at": detected_at, "resolved_at": None,
                "thumbnail": thumbnail, "snapshot": False,
                "history": [{"t": detected_at, "event": "detected",
                             "text": f"{label.title()} detected on {camera}"}],
            }
            self.next_number += 1
            self.incidents.append(incident)
            self.dirty = True
        log.warning("Threat %s: %s on %s (score %d)", incident["id"], incident["type"], camera, score)
        return incident

    def seen_again(self, incident, confidence, when, new_object):
        with self.lock:
            incident["last_seen"] = max(incident["last_seen"], when)
            if new_object:
                incident["sightings"] += 1
            if round(confidence * 100) > incident["confidence"]:
                incident["confidence"] = round(confidence * 100)
                incident["score"] = threat_score(incident["label"], confidence)
                incident["level"] = level(incident["score"])
            self.dirty = True

    # ---------- operator side ----------
    def set_status(self, incident_id, status, note=""):
        if status not in STATUS_TEXT:
            raise ValueError("Unknown status")
        with self.lock:
            incident = self.get(incident_id)
            if incident is None:
                return None
            now = time.time()
            note = note.strip()[:500]
            if status != incident["status"]:
                incident["status"] = status
                incident["resolved_at"] = now if status == RESOLVED else None
                text = {ACTIVE: "Reopened", IN_PROGRESS: "Marked working on it", RESOLVED: "Marked resolved"}[status]
                incident["history"].append({"t": now, "event": status, "text": text, "note": note})
            elif note:
                incident["history"].append({"t": now, "event": "note", "text": "Note added", "note": note})
            incident["updated_at"] = now
            self.dirty = True
            return incident

    def add_note(self, incident_id, note):
        with self.lock:
            incident = self.get(incident_id)
            if incident is None or not note.strip():
                return incident
            now = time.time()
            incident["history"].append({"t": now, "event": "note", "text": "Note added", "note": note.strip()[:500]})
            incident["updated_at"] = now
            self.dirty = True
            return incident

    # ---------- queries ----------
    def get(self, incident_id):
        with self.lock:
            return next((i for i in self.incidents if i["id"] == incident_id), None)

    def all(self):
        with self.lock:
            return list(self.incidents)


def public(incident, with_history=False):
    """An incident as the API returns it."""
    out = {k: v for k, v in incident.items() if k != "history"}
    out["status_text"] = STATUS_TEXT[incident["status"]]
    out["time_to_resolve"] = (incident["resolved_at"] - incident["detected_at"]) if incident["resolved_at"] else None
    actions = [h for h in incident["history"] if h["event"] in (*STATUS_TEXT, "note")]  # operator actions
    last = actions[-1] if actions else None
    out["last_action"] = (f"{last['text']}: {last['note']}" if last.get("note") else last["text"]) if last else None
    if with_history:
        out["history"] = incident["history"]
    return out
