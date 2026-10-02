"""Sector HQ store: the signed ledger entries of every post, checked as they arrive.

Posts forward their ledger (alerts, operator actions, hourly anchors) whenever the link is up; see
app/decision/sync.py. HQ accepts an entry only if it extends that post's chain (next sequence
number, previous hash matches) and carries a valid signature from the key registered for the
post. An anchor's Merkle root is recomputed from the entries it covers. HQ never needs the clips:
a clip produced later is checked against the hash HQ already holds.
"""
import json
import sqlite3
import threading
import time
from pathlib import Path

from app.decision.ledger import GENESIS, check_entry, merkle_root, public_key_from_hex, verify_sms


class HQStore:
    def __init__(self, path, posts):
        """posts: {post id: public key hex}, registered when each edge box is installed."""
        self.keys = {post: public_key_from_hex(pub) for post, pub in posts.items()}
        self.lock = threading.Lock()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS entries (
                post TEXT, seq INTEGER, t REAL, kind TEXT, hash TEXT, entry TEXT, received REAL,
                PRIMARY KEY (post, seq));
            CREATE TABLE IF NOT EXISTS problems (post TEXT, seq INTEGER, problem TEXT, received REAL);
        """)

    def head(self, post):
        row = self.db.execute("SELECT seq, hash FROM entries WHERE post = ? ORDER BY seq DESC LIMIT 1",
                              (post,)).fetchone()
        return {"post": post, "seq": row[0] if row else -1, "hash": row[1] if row else GENESIS}

    def receive(self, post, entries):
        """Store the entries that extend this post's chain; stop at the first one that does not."""
        if post not in self.keys:
            return {"accepted": 0, "head": None, "problems": [f"post {post} is not registered at HQ"]}
        pub, now = self.keys[post], time.time()
        accepted, problems = 0, []
        with self.lock:
            head = self.head(post)
            for e in entries:
                if e.get("seq", -1) <= head["seq"]:
                    continue  # already held (a retry after a lost reply)
                issues = []
                if e.get("seq") != head["seq"] + 1:
                    issues.append(f"entry {e.get('seq')}: expected entry {head['seq'] + 1} next")
                elif e.get("prev") != head["hash"]:
                    issues.append(f"entry {e.get('seq')}: does not follow the entry HQ holds")
                issues += check_entry(e, pub)
                if not issues and e.get("kind") == "anchor":
                    issues += self._check_anchor(post, e)
                if issues:
                    problems += issues
                    self.db.executemany("INSERT INTO problems VALUES (?, ?, ?, ?)",
                                        [(post, e.get("seq"), p, now) for p in issues])
                    break
                self.db.execute("INSERT INTO entries VALUES (?, ?, ?, ?, ?, ?, ?)",
                                (post, e["seq"], e["t"], e["kind"], e["hash"], json.dumps(e), now))
                head = {"post": post, "seq": e["seq"], "hash": e["hash"]}
                accepted += 1
            self.db.commit()
        return {"accepted": accepted, "head": head, "problems": problems}

    def _check_anchor(self, post, anchor):
        d = anchor["data"]
        rows = self.db.execute("SELECT hash FROM entries WHERE post = ? AND seq BETWEEN ? AND ? AND kind != 'anchor' "
                               "ORDER BY seq", (post, d.get("from_seq", 0), d.get("to_seq", -1))).fetchall()
        if merkle_root([r[0] for r in rows]) != d.get("root"):
            return [f"entry {anchor['seq']}: anchor root does not match the entries HQ holds"]
        return []

    def posts(self):
        out = []
        for post in sorted(self.keys):
            row = self.db.execute("SELECT COUNT(*), MAX(received) FROM entries WHERE post = ?", (post,)).fetchone()
            bad = self.db.execute("SELECT COUNT(*) FROM problems WHERE post = ?", (post,)).fetchone()[0]
            out.append({**self.head(post), "entries": row[0], "last_received": row[1], "problems": bad})
        return out

    def entries(self, post=None, kind=None, limit=100):
        sql, args = "SELECT post, entry FROM entries WHERE 1 = 1", []
        if post:
            sql, args = sql + " AND post = ?", args + [post]
        if kind:
            sql, args = sql + " AND kind = ?", args + [kind]
        rows = self.db.execute(sql + " ORDER BY t DESC LIMIT ?", args + [limit]).fetchall()
        return [{"post": p, **json.loads(e)} for p, e in rows]

    def which_post_signed(self, message):
        """The registered post whose key signed this alert SMS, or None."""
        return next((post for post, pub in self.keys.items() if verify_sms(message, pub)), None)
