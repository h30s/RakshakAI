"""Sector HQ service: receives each post's signed ledger and keeps the audit trail.

    uvicorn hq.server:app --port 9000

Register posts in HQ_DATA_DIR/posts.json (default hq_data/posts.json) as {"BOP07": "<public key
hex>"}; get a post's key on its edge box with `python -m app.decision.verify --pubkey`. Entries
are accepted only if they carry that key's signature, so the upload endpoint needs no password
to stay trustworthy (put it behind the SSB network or a VPN all the same).
"""
import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .store import HQStore

DATA_DIR = Path(os.getenv("HQ_DATA_DIR", Path(__file__).resolve().parent.parent / "hq_data"))
REGISTRY = DATA_DIR / "posts.json"

app = FastAPI(title="Rakshak AI · Sector HQ")
store = HQStore(DATA_DIR / "hq.sqlite",
                json.loads(REGISTRY.read_text(encoding="utf-8")) if REGISTRY.exists() else {})


class EntriesIn(BaseModel):
    entries: list[dict]


class SmsIn(BaseModel):
    message: str


@app.get("/api/hq/posts")
def posts():
    return store.posts()


@app.get("/api/hq/posts/{post}/head")
def head(post: str):
    if post not in store.keys:
        raise HTTPException(404, f"post {post} is not registered at HQ")
    return store.head(post)


@app.post("/api/hq/posts/{post}/entries")
def receive(post: str, body: EntriesIn):
    if post not in store.keys:
        raise HTTPException(404, f"post {post} is not registered at HQ")
    return store.receive(post, body.entries)


@app.get("/api/hq/alerts")
def alerts(post: str | None = None, limit: int = 100):
    return store.entries(post, kind="alert", limit=min(limit, 1000))


@app.post("/api/hq/sms/verify")
def sms_verify(body: SmsIn):
    """Paste an alert SMS: which registered post signed it (null = forged or altered)."""
    return {"post": store.which_post_signed(body.message.strip())}
