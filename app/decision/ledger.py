"""Tamper-evident ledger: every alert and evidence clip is sealed when it is written.

Each entry holds the SHA-256 of its clip (if any) and the hash of the previous entry, and the
entry's own hash is signed with this post's Ed25519 key. Any later change shows up in verify():
an edited or deleted clip, an edited entry, a deleted or reordered entry, or an entry signed by a
different key. Once an hour an 'anchor' entry records the Merkle root of every entry written
since the previous anchor, which is what Sector HQ stores; the ledger head also travels in every
alert SMS, so HQ holds an anchor even when the data link is down.

Clips deleted under the retention policy are recorded by a signed 'retention' entry, so a
deletion by policy verifies and any other deletion does not.

This is a permissioned, blockchain-style log: offline posts cannot run a consensus protocol,
so each post keeps its own signed chain and HQ keeps the anchors.
"""
import base64
import datetime as dt
import hashlib
import io
import json
import os
import threading
import time
import zipfile
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

GENESIS = "0" * 64
SMS_LIMIT = 160


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def merkle_root(hashes):
    level = [bytes.fromhex(h) for h in hashes] or [bytes(32)]
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [hashlib.sha256(a + b).digest() for a, b in zip(level[::2], level[1::2])]
    return level[0].hex()


def merkle_proof(hashes, index):
    """Sibling hashes from leaf `index` up to the root of merkle_root(hashes): [[hex, 'L' or 'R']]."""
    level = [bytes.fromhex(h) for h in hashes]
    proof = []
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        sibling = index ^ 1
        proof.append([level[sibling].hex(), "L" if sibling < index else "R"])
        level = [hashlib.sha256(a + b).digest() for a, b in zip(level[::2], level[1::2])]
        index //= 2
    return proof


def verify_merkle_proof(leaf, proof, root):
    h = bytes.fromhex(leaf)
    for sibling, side in proof:
        s = bytes.fromhex(sibling)
        h = hashlib.sha256(s + h if side == "L" else h + s).digest()
    return h.hex() == root


def load_or_create_key(path):
    """This post's signing key. Keep it out of git (data/ is ignored); in the field, store it in
    the box's TPM or an encrypted volume."""
    path = Path(path)
    if path.exists():
        return serialization.load_pem_private_key(path.read_bytes(), password=None)
    key = Ed25519PrivateKey.generate()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                       serialization.NoEncryption()))
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return key


def public_bytes(key):
    pub = key.public_key() if isinstance(key, Ed25519PrivateKey) else key
    return pub.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def public_key_from_hex(text):
    return Ed25519PublicKey.from_public_bytes(bytes.fromhex(text.strip()))


def entry_body(e):
    return {k: e.get(k) for k in ("seq", "t", "kind", "data", "prev", "clip", "clip_sha256")}


def check_entry(e, pub, label=None):
    """Problems with one entry on its own: its hash and its signature."""
    label = e.get("seq") if label is None else label
    problems = []
    if hashlib.sha256(canonical(entry_body(e))).hexdigest() != e.get("hash"):
        problems.append(f"entry {label}: contents changed after sealing")
    try:
        pub.verify(bytes.fromhex(e.get("sig", "")), bytes.fromhex(e.get("hash", "")))
    except (InvalidSignature, ValueError):
        problems.append(f"entry {label}: signature does not match this post's key")
    return problems


class Ledger:
    def __init__(self, path, key, clip_dir=None):
        self.path = Path(path)
        self.clip_dir = Path(clip_dir) if clip_dir else self.path.parent
        self.key = key
        self.entries = []
        self.lock = threading.Lock()
        if self.path.exists():
            self.entries = [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line]

    @property
    def head(self):
        return self.entries[-1]["hash"] if self.entries else GENESIS

    def append(self, kind, data, clip=None, t=None):
        """Seal an entry. clip: path of an evidence file (hashed now, stored by name)."""
        with self.lock:
            body = {"seq": len(self.entries), "t": round(t if t is not None else time.time(), 3), "kind": kind,
                    "data": data, "prev": self.head,
                    "clip": Path(clip).name if clip else None, "clip_sha256": sha256_file(clip) if clip else None}
            digest = hashlib.sha256(canonical(body)).hexdigest()
            entry = {**body, "hash": digest, "sig": self.key.sign(bytes.fromhex(digest)).hex()}
            self.entries.append(entry)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            return entry

    def anchor(self, start, end):
        """Append an 'anchor' entry with the Merkle root of every entry written since the previous
        anchor. start/end label the hour it closes; entries are chosen by position, not by their
        time stamp, because an alert is stamped with when the movement began and may be written
        after that hour's anchor."""
        with self.lock:
            last = next((e for e in reversed(self.entries) if e["kind"] == "anchor"), None)
            first = last["data"]["to_seq"] + 1 if last else 0
            hashes = [e["hash"] for e in self.entries[first:] if e["kind"] != "anchor"]
            to_seq = len(self.entries) - 1
        return self.append("anchor", {"from": start, "to": end, "from_seq": first, "to_seq": to_seq,
                                      "count": len(hashes), "root": merkle_root(hashes)}, t=end)

    def anchor_for(self, seq):
        """(anchor entry, Merkle proof) covering entry `seq`, or (None, None) if not anchored yet."""
        for a in self.entries[seq + 1:]:
            if a["kind"] == "anchor" and a["data"].get("from_seq", -1) <= seq <= a["data"].get("to_seq", -1):
                covered = [e["hash"] for e in self.entries[a["data"]["from_seq"]:a["data"]["to_seq"] + 1]
                           if e["kind"] != "anchor"]
                return a, merkle_proof(covered, covered.index(self.entries[seq]["hash"]))
        return None, None

    def retire_clip(self, seq, reason):
        """Delete an entry's evidence clip under the retention policy, and record that in the ledger."""
        e = self.entries[seq]
        clip = self.clip_dir / e["clip"]
        if clip.exists():
            clip.unlink()
        return self.append("retention", {"entry": seq, "clip": e["clip"], "clip_sha256": e["clip_sha256"],
                                         "reason": reason})

    def verify(self, public_key=None, entries=None):
        """List of problems found (empty = intact)."""
        pub = public_key or self.key.public_key()
        entries = self.entries if entries is None else entries
        retired = {e["data"].get("entry") for e in entries if e.get("kind") == "retention"}
        problems, prev = [], GENESIS
        for i, e in enumerate(entries):
            if e.get("seq") != i:
                problems.append(f"entry {i}: sequence {e.get('seq')} out of place (deleted or reordered entry)")
            if e.get("prev") != prev:
                problems.append(f"entry {i}: does not follow the previous entry (chain broken)")
            problems += check_entry(e, pub, label=i)
            if e.get("clip"):
                clip = self.clip_dir / e["clip"]
                if not clip.exists():
                    if i not in retired:
                        problems.append(f"entry {i}: evidence clip {e['clip']} is missing")
                elif sha256_file(clip) != e.get("clip_sha256"):
                    problems.append(f"entry {i}: evidence clip {e['clip']} was modified")
            prev = e.get("hash")
        return problems


# ---------------------------------------------------------------- one-SMS alert
def sms_alert(key, post, camera, t, code, ledger_head):
    """A signed alert that fits one 160-character SMS:
    'RK1 <post> <camera> <HHMM> <code> L<ledger head, 8 hex> <Ed25519 signature, 86 chars base64url>'."""
    text = f"RK1 {post} {camera} {dt.datetime.fromtimestamp(t):%H%M} {code} L{ledger_head[:8]}"
    sig = base64.urlsafe_b64encode(key.sign(text.encode())).decode().rstrip("=")
    message = f"{text} {sig}"
    if len(message) > SMS_LIMIT:
        raise ValueError(f"alert is {len(message)} characters; shorten post/camera/code ids")
    return message


def verify_sms(message, public_key):
    text, _, sig = message.rpartition(" ")
    try:
        public_key.verify(base64.urlsafe_b64decode(sig + "=" * (-len(sig) % 4)), text.encode())
        return True
    except (InvalidSignature, ValueError):
        return False


# ---------------------------------------------------------------- BSA s.63(4) Part A draft
def certificate_part_a(entry, post, device, officer="________________"):
    """A DRAFT of the Part A details for a certificate under s.63(4) of the Bharatiya Sakshya
    Adhiniyam, 2023, pre-filled from a sealed ledger entry. It must be checked, completed and
    signed by the person in charge of the device; Part B is certified by an expert."""
    when = dt.datetime.fromtimestamp(entry["t"]).strftime("%d-%m-%Y %H:%M:%S")
    return "\n".join([
        "DRAFT - Certificate under Section 63(4), Bharatiya Sakshya Adhiniyam, 2023 - PART A",
        "(to be verified, completed and signed by the person in charge of the device)",
        "",
        f"Electronic record : {entry.get('clip') or 'ledger entry ' + str(entry['seq'])}",
        f"Produced by       : {device} at {post}",
        f"Recorded at       : {when}",
        f"Hash algorithm    : SHA-256",
        f"Hash value        : {entry.get('clip_sha256') or entry['hash']}",
        f"Ledger entry      : #{entry['seq']}, entry hash {entry['hash']}",
        "",
        "The device was operating properly during the relevant period, and the record was",
        "produced in its ordinary course of use.",
        "",
        f"Name / designation: {officer}          Signature: ____________   Date: ________",
        "",
        "Part B (expert certificate) to be completed separately.",
    ])


# ---------------------------------------------------------------- evidence packet
PACKET_README = """Rakshak AI evidence packet

entry.json              the sealed ledger entry for this alert
<clip>                  the evidence clip; its SHA-256 is in entry.json
chain.jsonl             every ledger entry from this one to the ledger head at export time
anchor.json             the hourly anchor that covers this entry (if that hour has closed)
merkle_proof.json       proof that this entry is inside that anchor's Merkle root
public_key.txt          this post's Ed25519 public key; compare it with the key registered at Sector HQ
certificate_part_a.txt  DRAFT BSA s.63(4) Part A, to be checked, completed and signed

Verify:  python -m app.decision.verify --packet <this file> [--pub <key registered at HQ>]
"""


def evidence_packet(ledger, seq, certificate):
    """A ZIP with everything needed to check one alert without access to the post."""
    entry = ledger.entries[seq]
    anchor, proof = ledger.anchor_for(seq)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("entry.json", json.dumps(entry, indent=2, ensure_ascii=False))
        if entry.get("clip") and (ledger.clip_dir / entry["clip"]).exists():
            z.write(ledger.clip_dir / entry["clip"], entry["clip"])
        z.writestr("chain.jsonl", "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in ledger.entries[seq:]))
        if anchor:
            z.writestr("anchor.json", json.dumps(anchor, indent=2))
            z.writestr("merkle_proof.json", json.dumps(proof))
        z.writestr("public_key.txt", public_bytes(ledger.key).hex())
        z.writestr("certificate_part_a.txt", certificate)
        z.writestr("README.txt", PACKET_README)
    return buf.getvalue()


def verify_packet(data, public_key=None):
    """Problems found in an evidence packet (bytes or path); empty = everything checks out.
    public_key: the key HQ has registered for this post; defaults to the one in the packet."""
    if not isinstance(data, (bytes, bytearray)):
        data = Path(data).read_bytes()
    problems = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = set(z.namelist())
        pub = public_key or public_key_from_hex(z.read("public_key.txt").decode())
        entry = json.loads(z.read("entry.json"))
        problems += check_entry(entry, pub)
        if entry.get("clip"):
            if entry["clip"] not in names:
                problems.append(f"evidence clip {entry['clip']} is not in the packet")
            elif hashlib.sha256(z.read(entry["clip"])).hexdigest() != entry.get("clip_sha256"):
                problems.append(f"evidence clip {entry['clip']} does not match its sealed hash")
        chain = [json.loads(line) for line in z.read("chain.jsonl").decode().splitlines() if line]
        if not chain or chain[0].get("hash") != entry.get("hash"):
            problems.append("chain.jsonl does not start with this entry")
        for a, b in zip(chain, chain[1:]):
            if b.get("prev") != a.get("hash") or b.get("seq") != a.get("seq", -2) + 1:
                problems.append(f"chain broken between entries {a.get('seq')} and {b.get('seq')}")
        for e in chain[1:]:
            problems += check_entry(e, pub)
        if "anchor.json" in names:
            anchor = json.loads(z.read("anchor.json"))
            problems += check_entry(anchor, pub)
            proof = json.loads(z.read("merkle_proof.json"))
            if not verify_merkle_proof(entry["hash"], proof, anchor["data"]["root"]):
                problems.append("entry is not inside the anchor's Merkle root")
    return problems
