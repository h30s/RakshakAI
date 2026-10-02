"""Tests for evidence handling: anchors, Merkle proofs, retention, evidence packets, verify CLI."""
import datetime as dt
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.decision import verify as verify_cli
from app.decision.ledger import (Ledger, certificate_part_a, evidence_packet, merkle_proof, merkle_root,
                                 public_bytes, verify_merkle_proof, verify_packet)

T0 = dt.datetime(2026, 8, 4, 10, 0).timestamp()


def sealed_ledger(tmp, n=5, key=None):
    key = key or Ed25519PrivateKey.generate()
    led = Ledger(tmp / "ledger.jsonl", key, clip_dir=tmp)
    for i in range(n):
        clip = tmp / f"A-{i:04d}.jpg"
        clip.write_bytes(f"jpeg {i}".encode())
        led.append("alert", {"alert": f"A-{i:04d}"}, clip=clip, t=T0 + i)
    return led, key


class MerkleTest(unittest.TestCase):
    def test_every_leaf_has_a_valid_proof(self):
        for n in (1, 2, 3, 5, 8, 13):
            leaves = [f"{i:064x}" for i in range(n)]
            root = merkle_root(leaves)
            for i, leaf in enumerate(leaves):
                self.assertTrue(verify_merkle_proof(leaf, merkle_proof(leaves, i), root), (n, i))
            if n > 1:
                self.assertFalse(verify_merkle_proof(leaves[0], merkle_proof(leaves, 1), root))


class AnchorTest(unittest.TestCase):
    def test_late_entry_is_covered_by_the_next_anchor(self):
        """An alert is stamped with when the movement began; if it is written after that hour's
        anchor, the next anchor must still cover it (anchors go by position, not time)."""
        with tempfile.TemporaryDirectory() as tmp:
            led, _ = sealed_ledger(Path(tmp), n=2)
            first = led.anchor(T0 - 3600, T0 + 3600)
            late = led.append("alert", {"alert": "A-late"}, t=T0 + 3599)  # began before the anchor's end
            second = led.anchor(T0 + 3600, T0 + 7200)
            self.assertEqual((first["data"]["from_seq"], first["data"]["to_seq"], first["data"]["count"]), (0, 1, 2))
            self.assertEqual(second["data"]["count"], 1)
            anchor, proof = led.anchor_for(late["seq"])
            self.assertEqual(anchor["seq"], second["seq"])
            self.assertTrue(verify_merkle_proof(late["hash"], proof, anchor["data"]["root"]))
            self.assertEqual(led.anchor_for(0)[0]["seq"], first["seq"])
            self.assertEqual(led.verify(), [])


class RetentionTest(unittest.TestCase):
    def test_retired_clip_verifies_but_a_deleted_one_does_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            led, _ = sealed_ledger(tmp, n=3)
            led.retire_clip(1, "30-day retention; alert not escalated")
            self.assertFalse((tmp / "A-0001.jpg").exists())
            self.assertEqual(led.verify(), [])
            (tmp / "A-0002.jpg").unlink()  # deleted outside the policy
            problems = led.verify()
            self.assertEqual(len(problems), 1)
            self.assertIn("A-0002.jpg is missing", problems[0])


class PacketTest(unittest.TestCase):
    def packet(self, tmp):
        led, key = sealed_ledger(tmp)
        led.anchor(T0 - 1, T0 + 3600)
        led.append("action", {"alert": "A-0002", "status": "escalated"}, t=T0 + 4000)
        cert = certificate_part_a(led.entries[2], "BOP07", "edge box")
        return evidence_packet(led, 2, cert), key

    def test_packet_verifies_and_contains_the_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, key = self.packet(Path(tmp))
            self.assertEqual(verify_packet(data), [])
            self.assertEqual(verify_packet(data, key.public_key()), [])
            names = zipfile.ZipFile(io.BytesIO(data)).namelist()
            for name in ("entry.json", "A-0002.jpg", "chain.jsonl", "anchor.json", "merkle_proof.json",
                         "public_key.txt", "certificate_part_a.txt", "README.txt"):
                self.assertIn(name, names)

    def test_tampered_packets_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, key = self.packet(Path(tmp))

            def rewrite(change):
                src = zipfile.ZipFile(io.BytesIO(data))
                out = io.BytesIO()
                with zipfile.ZipFile(out, "w") as z:
                    for name in src.namelist():
                        z.writestr(name, change(name, src.read(name)))
                return out.getvalue()

            edited_clip = rewrite(lambda n, b: b + b"x" if n == "A-0002.jpg" else b)
            self.assertTrue(any("does not match its sealed hash" in p for p in verify_packet(edited_clip)))

            def edit_entry(n, b):
                if n != "entry.json":
                    return b
                e = json.loads(b)
                e["data"]["alert"] = "A-9999"
                return json.dumps(e).encode()
            self.assertTrue(any("changed after sealing" in p for p in verify_packet(rewrite(edit_entry))))

            other = Ed25519PrivateKey.generate()
            self.assertTrue(verify_packet(data, other.public_key()))  # not the key HQ registered


class VerifyCliTest(unittest.TestCase):
    def test_cli_reports_ok_and_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            led, key = sealed_ledger(tmp)
            pub = public_bytes(key).hex()
            args = ["--ledger", str(tmp / "ledger.jsonl"), "--clips", str(tmp), "--pub", pub]
            self.assertEqual(verify_cli.main(args), 0)
            (tmp / "A-0003.jpg").write_bytes(b"edited")
            self.assertEqual(verify_cli.main(args), 1)


if __name__ == "__main__":
    unittest.main()
