"""Store-and-forward to Sector HQ: the ledger itself is the outbox.

Every few seconds the forwarder asks HQ which entry it holds last for this post and sends the
rest in batches. With the link down nothing is lost: entries wait in the ledger and go when the
link returns, oldest first, so HQ always receives an unbroken chain. The hourly anchors travel
the same way. Enabled when post.json has "hq_url".
"""
import json
import logging
import threading
import time
import urllib.request

log = logging.getLogger(__name__)


def http_transport(base_url, timeout=10):
    if not base_url.lower().startswith(("http://", "https://")):
        raise ValueError(f"hq_url must be an http(s) URL, not {base_url!r}")

    def request(method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(base_url.rstrip("/") + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return json.loads(res.read())
    return request


class Forwarder(threading.Thread):
    def __init__(self, ledger, post, request, interval=5.0, batch=200, max_backoff=300.0):
        super().__init__(daemon=True, name="hq-sync")
        self.ledger, self.post, self.request = ledger, post, request
        self.interval, self.batch, self.max_backoff = interval, batch, max_backoff
        self.status = {"link": "unknown", "hq_seq": None, "pending": len(ledger.entries), "last_ok": None,
                       "error": None}

    def sync_once(self):
        """Send everything HQ does not hold yet. Returns the number of entries HQ accepted."""
        head = self.request("GET", f"/api/hq/posts/{self.post}/head")
        seq = head["seq"]
        if seq >= 0 and (seq >= len(self.ledger.entries) or self.ledger.entries[seq]["hash"] != head["hash"]):
            raise RuntimeError(f"HQ holds a different entry {seq} for {self.post}; check both ledgers")
        sent = 0
        while seq + 1 < len(self.ledger.entries):
            chunk = self.ledger.entries[seq + 1:seq + 1 + self.batch]
            res = self.request("POST", f"/api/hq/posts/{self.post}/entries", {"entries": chunk})
            if res.get("problems"):
                raise RuntimeError("HQ rejected entries: " + "; ".join(res["problems"]))
            if not res.get("accepted"):
                break
            sent += res["accepted"]
            seq = res["head"]["seq"]
        self.status.update(link="up", hq_seq=seq, pending=len(self.ledger.entries) - 1 - seq,
                           last_ok=time.time(), error=None)
        return sent

    def run(self):
        wait = self.interval
        while True:
            try:
                self.sync_once()
                wait = self.interval
            except Exception as exc:  # link down, HQ down, or a rejected entry
                held = self.status["hq_seq"] if self.status["hq_seq"] is not None else -1
                self.status.update(link="down", error=str(exc), pending=len(self.ledger.entries) - 1 - held)
                wait = min(self.max_backoff, wait * 2)
                log.info("HQ sync failed (%s); retrying in %.0f s", exc, wait)
            time.sleep(wait)
