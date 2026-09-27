"""Watches the dashboard cameras: camera health, and confirmed weapons -> threat incidents.

It reads each camera's object log at the frame currently on screen (like the camera panel), so
an alert never appears before the operator can see the weapon in the video. It only reads what
the detection pipeline already produced; it does no detection of its own.
"""
import itertools
import logging
import threading
import time
from collections import deque

import cv2

from .. import config
from ..sources.feeds import LiveCamera
from .store import ACTIVE, IN_PROGRESS, OPEN, RESOLVED, level, public

log = logging.getLogger(__name__)

ONLINE, PROBLEM, OFFLINE = "online", "problem", "offline"
STATUS_TEXT = {ONLINE: "Online", PROBLEM: "Signal problem", OFFLINE: "Offline"}


def location_of(camera_name):
    """"Parking — Camera 2" -> "Parking"."""
    return camera_name.split(" — ")[0]


def clock(t):
    return time.strftime("%H:%M", time.localtime(t))


class ThreatMonitor(threading.Thread):
    def __init__(self, cameras, loop, store):
        super().__init__(daemon=True, name="threat-monitor")
        self.cameras, self.loop, self.store = cameras, loop, store
        self.started = time.time()
        self.frames = {}          # camera id -> (last frame index, when it changed)
        self.health = {}          # camera id -> (status or None when not listed, issue)
        self.activity = {}        # camera id -> (time, what was in view)
        self.known = {}           # (camera id, object log, object id) -> incident id
        self.events = deque(maxlen=60)  # camera status changes for Recent activity
        self.lock = threading.Lock()

    def run(self):
        while True:
            try:
                self.tick()
                self.store.save_if_dirty()
            except Exception:
                log.exception("Threat monitor failed")
            time.sleep(1.0)

    def tick(self):
        now = time.time()
        for cam in self.cameras:
            status, issue = self._health(cam, now)
            previous = self.health.get(cam.id)
            with self.lock:
                self.health[cam.id] = (status, issue)
                if previous is not None and previous[0] != status and status is not None:
                    self._camera_event(cam, now, previous[0], status, issue)
                elif previous is None and status is not None and isinstance(cam, LiveCamera):
                    self.events.append({"t": now, "kind": "camera", "level": "ok", "text": f"{cam.name} connected"})
            if status != OFFLINE:
                self._observe(cam, now)

    # ---------- camera health ----------
    def _health(self, cam, now):
        """(status, issue); status None = not listed (a live source that is not in use)."""
        if isinstance(cam, LiveCamera):
            if cam.publisher is None:
                if cam.disconnected_at and now - cam.disconnected_at < config.LIVE_LOST_KEEP_S:
                    return OFFLINE, f"No signal: disconnected at {clock(cam.disconnected_at)}"
                return None, None
            if not cam.streaming:
                return PROBLEM, "Connected, but no video is arriving"
        idx = cam.latest[0] if cam.latest else None
        seen = self.frames.get(cam.id)
        if idx is not None and (seen is None or seen[0] != idx):
            self.frames[cam.id] = seen = (idx, now)
        age = now - seen[1] if seen else now - self.started
        if age > config.OFFLINE_S:
            return OFFLINE, f"No signal for {age:.0f} s"
        if age > config.SIGNAL_PROBLEM_S:
            return PROBLEM, f"Video interrupted ({age:.0f} s without a frame)"
        stall = max(config.DETECTION_STALL_S, 4 * self.loop.cycle_time)
        with cam.lock:
            last_det = cam.det_idx[-1] if cam.det_idx else None
        if last_det is None:
            since = now - (cam.connected_at if isinstance(cam, LiveCamera) and cam.connected_at else self.started)
            if since > stall:
                return PROBLEM, "Detection is not running on this camera"
        elif (idx - last_det) / config.FEED_FPS > stall:
            return PROBLEM, f"Detection stalled (last analysed {(idx - last_det) / config.FEED_FPS:.0f} s ago)"
        return ONLINE, None

    def _camera_event(self, cam, now, before, after, issue):
        if after == ONLINE:
            text, lvl = f"{cam.name} is back online", "ok"
        else:
            text, lvl = f"{cam.name}: {STATUS_TEXT[after].lower()} — {issue}", "bad" if after == OFFLINE else "warn"
        self.events.append({"t": now, "kind": "camera", "level": lvl, "text": text})

    # ---------- weapons -> incidents ----------
    def _observe(self, cam, now):
        shown = cam.display_idx
        if shown < 0:
            return
        newest = cam.latest[0] if cam.latest else shown
        shown_at = now - max(0, newest - shown) / config.FEED_FPS  # capture time of the shown frame
        objects_log = cam.objects
        items = objects_log.snapshot(shown)
        in_view = [o for o in items if o["in_view"]]
        if in_view:
            counts = {}
            for o in in_view:
                counts[o["label"]] = counts.get(o["label"], 0) + 1
            plural = lambda label, n: label if n == 1 else f"{n} {'people' if label == 'Person' else label.lower() + 's'}"
            self.activity[cam.id] = (now, ", ".join(plural(label, n)
                                                    for label, n in sorted(counts.items(), key=lambda kv: -kv[1])))
        for o in in_view:
            if not o["threat"]:
                continue
            key = (cam.id, id(objects_log), o["id"])
            label, conf = o["label"].lower(), o["confidence"] / 100
            incident = self.store.get(self.known[key]) if key in self.known else None
            if incident is not None:
                if incident["status"] in OPEN:  # a resolved weapon still in view does not re-alert
                    self.store.seen_again(incident, conf, shown_at, new_object=False)
                continue
            incident = self.store.open_incident_for(cam.id, label)
            if incident is not None:  # same kind of weapon again on this camera: same incident
                self.known[key] = incident["id"]
                self.store.seen_again(incident, conf, shown_at, new_object=True)
                continue
            incident = self.store.recently_resolved_for(cam.id, label, config.RESOLVED_QUIET_S)
            if incident is not None:  # just resolved: note it there rather than alarm again
                self.known[key] = incident["id"]
                self.store.seen_after_resolution(incident, shown_at)
                continue
            incident = self.store.create(camera_id=cam.id, camera=cam.name, location=location_of(cam.name),
                                         label=label, confidence=conf, detected_at=shown_at,
                                         thumbnail=o["thumbnail"])
            self.known[key] = incident["id"]
            jpeg = self._snapshot(cam, shown, label)
            if jpeg:
                self.store.save_snapshot(incident, jpeg)
        if len(self.known) > 5000:
            self.known = dict(itertools.islice(self.known.items(), 2500, None))

    @staticmethod
    def _snapshot(cam, idx, label):
        """The frame on screen when the weapon was first shown, with its box drawn."""
        got = cam.buffered_frame(idx)
        if not got:
            return None
        frame_idx, frame = got
        for d in cam._detections_for(frame_idx):
            if d["threat"] and d["label"] == label:
                x1, y1, x2, y2 = map(int, d["box"])
                cv2.rectangle(frame, (x1, y1), (x2, y2), (79, 77, 255), 2)
                text = f"{label.title()} {round(d['conf'] * 100)}%"
                (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                ty = max(y1, th + 6)
                cv2.rectangle(frame, (x1, ty - th - 6), (x1 + tw + 8, ty), (79, 77, 255), -1)
                cv2.putText(frame, text, (x1 + 4, ty - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return buf.tobytes() if ok else None

    # ---------- the Overview tab ----------
    def overview(self):
        now = time.time()
        incidents = self.store.all()
        open_ = [i for i in incidents if i["status"] in OPEN]
        cam_score = {}
        for i in open_:
            weight = 1.0 if i["status"] == ACTIVE else config.IN_PROGRESS_WEIGHT
            cam_score[i["camera_id"]] = max(cam_score.get(i["camera_id"], 0), round(i["score"] * weight))
        latest_by_cam = {}
        for i in incidents:
            latest_by_cam[i["camera_id"]] = i

        with self.lock:
            health = dict(self.health)
            events = list(self.events)
        cameras = []
        for order, cam in enumerate(self.cameras):
            status, issue = health.get(cam.id, (None, None))
            if status is None:
                continue
            score = cam_score.get(cam.id, 0)
            latest = latest_by_cam.get(cam.id)
            act = self.activity.get(cam.id)
            cameras.append({
                "id": cam.id, "name": cam.name, "area": location_of(cam.name), "status": status,
                "status_text": STATUS_TEXT[status], "issue": issue, "score": score, "level": level(score),
                "open_threats": sum(1 for i in open_ if i["camera_id"] == cam.id),
                "latest_threat": {"id": latest["id"], "type": latest["type"], "t": latest["detected_at"],
                                  "status": latest["status"]} if latest else None,
                "last_activity": {"t": act[0], "text": act[1]} if act else None,
                "order": order,
            })
        rank = {OFFLINE: 0, PROBLEM: 1, ONLINE: 2}
        cameras.sort(key=lambda c: (-c["score"], rank[c["status"]], c["order"]))

        top = max(cam_score.values(), default=0)
        overall = min(100, top + 5 * max(0, len(open_) - 1)) if open_ else 0

        areas = {}
        for c in cameras:
            a = areas.setdefault(c["area"], {"area": c["area"], "score": 0, "open": 0, "recent": 0, "cameras": []})
            a["score"] = max(a["score"], c["score"])
            a["open"] += c["open_threats"]
            a["cameras"].append(c["name"])
        for i in incidents:
            if now - i["detected_at"] < config.AREA_WINDOW_S and i["location"] in areas:
                areas[i["location"]]["recent"] += 1
        risky = []
        for a in areas.values():
            a["level"] = level(a["score"]) if a["score"] else ("Low" if a["recent"] else None)
            if a["level"]:
                risky.append(a)
        risky.sort(key=lambda a: (-a["score"], -a["recent"]))

        today = time.localtime(now)[:3]
        activity = [{"t": h["t"], "kind": "threat", "incident": i["id"],
                     "level": "bad" if h["event"] == "detected" else "ok" if h["event"] == RESOLVED else "warn",
                     "text": self._history_text(i, h)}
                    for i in incidents[-40:] for h in i["history"]]
        activity = sorted(activity + events, key=lambda e: -e["t"])[:12]

        online = sum(1 for c in cameras if c["status"] == ONLINE)
        return {
            "now": now,
            "summary": {
                "score": overall, "level": level(overall),
                "active": sum(1 for i in open_ if i["status"] == ACTIVE),
                "in_progress": sum(1 for i in open_ if i["status"] == IN_PROGRESS),
                "resolved": sum(1 for i in incidents if i["status"] == RESOLVED),
                "resolved_today": sum(1 for i in incidents if i["status"] == RESOLVED
                                      and time.localtime(i["resolved_at"])[:3] == today),
                "cameras_total": len(cameras), "cameras_online": online, "camera_issues": len(cameras) - online,
                "high_risk_areas": sum(1 for a in risky if a["level"] in ("High", "Medium")),
            },
            "cameras": cameras,
            "areas": risky,
            "alerts": [public(i) for i in sorted(incidents, key=lambda i: -i["detected_at"])[:10]],
            "open": [public(i) for i in sorted(open_, key=lambda i: (i["status"] != ACTIVE, -i["score"], -i["detected_at"]))],
            "activity": activity,
        }

    @staticmethod
    def _history_text(incident, h):
        if h["event"] == "detected":
            return f"{incident['type']} detected on {incident['camera']} ({incident['id']})"
        text = f"{incident['id']} ({incident['type']}, {incident['location']}): {h['text'].lower()}"
        return f"{text} — “{h['note']}”" if h.get("note") else text
