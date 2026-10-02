"""Check a post's ledger or an evidence packet, and time the check.

    python -m app.decision.verify                         # this post: data/ledger + data/evidence
    python -m app.decision.verify --ledger L --clips DIR --pub HEX
    python -m app.decision.verify --packet A-0001.zip [--pub HEX]
    python -m app.decision.verify --pubkey                # this post's public key, to register at HQ

--pub is the post's public key as registered at Sector HQ. Without it the ledger is checked
against this post's own key file, and a packet against the key it carries (which proves the
packet is internally consistent, not who made it).
"""
import argparse
import sys
import time
from pathlib import Path

from cryptography.hazmat.primitives import serialization

from .. import config
from .ledger import Ledger, public_bytes, public_key_from_hex, verify_packet

KEY_FILE = config.DATA_DIR / "keys" / "ledger_ed25519.pem"


def _own_key():
    if not KEY_FILE.exists():
        raise SystemExit(f"No key at {KEY_FILE}; pass --pub with the post's public key.")
    return serialization.load_pem_private_key(KEY_FILE.read_bytes(), password=None)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ledger", default=str(config.DATA_DIR / "ledger" / "ledger.jsonl"))
    ap.add_argument("--clips", default=str(config.DATA_DIR / "evidence"))
    ap.add_argument("--packet", help="evidence packet (.zip) to check instead of a ledger")
    ap.add_argument("--pub", help="post public key (64 hex characters)")
    ap.add_argument("--pubkey", action="store_true", help="print this post's public key and exit")
    args = ap.parse_args(argv)

    if args.pubkey:
        print(public_bytes(_own_key()).hex())
        return 0
    pub = public_key_from_hex(args.pub) if args.pub else None
    t0 = time.perf_counter()
    if args.packet:
        problems = verify_packet(Path(args.packet), pub)
        what = f"packet {args.packet}"
    else:
        key = _own_key() if pub is None else None
        ledger = Ledger(args.ledger, key, clip_dir=args.clips)
        problems = ledger.verify(public_key=pub or key.public_key())
        what = f"{len(ledger.entries)} ledger entries"
    seconds = time.perf_counter() - t0
    if problems:
        print(f"FAILED: {len(problems)} problem(s) in {what} ({seconds:.3f} s)")
        for p in problems:
            print("  " + p)
        return 1
    print(f"OK: {what} verified in {seconds:.3f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
