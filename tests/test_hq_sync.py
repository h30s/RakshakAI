"""Tests for store-and-forward to Sector HQ (app/decision/sync.py, hq/store.py)."""
import copy
import datetime as dt
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.decision.ledger import Ledger, public_bytes, sms_alert
from app.decision.sync import Forwarder
from hq.store import HQStore

T0 = dt.datetime(2026, 8, 4, 10, 0).timestamp()


class Link:
    """In-process transport to an HQStore that can be cut, like a real link."""

    def __init__(self, store):
        self.store, self.up = store, True

    def __call__(self, method, path, body=None):
        if not self.up:
            raise ConnectionError("link down")
        post = path.split("/")[4]
        if path.endswith("/head"):
            return self.store.head(post)
        return self.store.receive(post, copy.deepcopy(body["entries"]))


class SyncTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        tmp = Path(self.tmp.name)
        self.key = Ed25519PrivateKey.generate()
        self.ledger = Ledger(tmp / "post" / "ledger.jsonl", self.key)
        self.hq = HQStore(tmp / "hq" / "hq.sqlite", {"BOP07": public_bytes(self.key).hex()})
        self.link = Link(self.hq)
        self.fwd = Forwarder(self.ledger, "BOP07", self.link, batch=3)

    def tearDown(self):
        self.hq.db.close()
        self.tmp.cleanup()

    def add(self, n, start=0):
        for i in range(start, start + n):
            self.ledger.append("alert", {"alert": f"A-{i:04d}"}, t=T0 + i)

    def test_store_and_forward_across_a_link_outage(self):
        self.add(4)
        self.assertEqual(self.fwd.sync_once(), 4)
        self.link.up = False
        self.add(5, start=4)
        self.ledger.anchor(T0, T0 + 3600)
        with self.assertRaises(ConnectionError):
            self.fwd.sync_once()
        self.assertEqual(self.hq.head("BOP07")["seq"], 3)  # nothing new reached HQ
        self.link.up = True
        self.assertEqual(self.fwd.sync_once(), 6)  # 5 alerts + the anchor, in order, in batches of 3
        self.assertEqual(self.hq.head("BOP07")["hash"], self.ledger.head)
        self.assertEqual(self.fwd.status["pending"], 0)
        self.assertEqual(self.fwd.sync_once(), 0)  # idempotent

    def test_hq_rejects_forged_or_altered_entries(self):
        self.add(2)
        forged = Ledger(Path(self.tmp.name) / "forged.jsonl", Ed25519PrivateKey.generate())
        forged.append("alert", {"alert": "A-0000"}, t=T0)
        res = self.hq.receive("BOP07", forged.entries)
        self.assertEqual(res["accepted"], 0)
        self.assertTrue(any("signature" in p for p in res["problems"]))

        altered = copy.deepcopy(self.ledger.entries)
        altered[1]["data"]["alert"] = "A-9999"
        res = self.hq.receive("BOP07", altered)
        self.assertEqual(res["accepted"], 1)  # the first entry is fine; HQ stops at the altered one
        self.assertTrue(any("changed after sealing" in p for p in res["problems"]))
        self.assertEqual(self.hq.posts()[0]["problems"], 2)  # both attempts are on record at HQ

        res = self.hq.receive("BOP99", self.ledger.entries)
        self.assertIn("not registered", res["problems"][0])

    def test_gap_in_the_chain_is_refused(self):
        self.add(3)
        res = self.hq.receive("BOP07", [self.ledger.entries[0], self.ledger.entries[2]])
        self.assertEqual(res["accepted"], 1)
        self.assertIn("expected entry 1", res["problems"][0])

    def test_anchor_root_is_recomputed_at_hq(self):
        self.add(3)
        self.ledger.anchor(T0, T0 + 3600)
        self.assertEqual(self.fwd.sync_once(), 4)
        self.assertEqual(self.hq.entries("BOP07", kind="anchor")[0]["data"]["count"], 3)

    def test_hq_names_the_post_that_signed_an_sms(self):
        msg = sms_alert(self.key, "BOP07", "cam-03", T0, "OFFPATH", "ab" * 32)
        self.assertEqual(self.hq.which_post_signed(msg), "BOP07")
        self.assertIsNone(self.hq.which_post_signed(msg.replace("cam-03", "cam-04")))


if __name__ == "__main__":
    unittest.main()
