"""Run the decision-layer pages without cameras or models, on made-up movements.

    python scripts/decision_preview.py            # then open http://localhost:8010/decision

Pages: /decision (ranked alerts), /pulse (Border Pulse), /shift-report, /verify (duty-phone SMS
check) and /demo.

For working on the decision layer and its screen without the 1.4 GB of models. Everything shown
is synthetic: never take screenshots from it for results.
"""
import argparse
import csv
import datetime as dt
import random
import sys
import tempfile
import time
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config  # noqa: E402
from app.decision import api as decision_api  # noqa: E402
from app.decision.engine import DecisionEngine  # noqa: E402
from app.decision.events import Movement  # noqa: E402

CAMERAS = {"gate-1": "Gate road", "nala-2": "Nala crossing", "field-3": "Field edge"}
USUAL = ["r2c0>r2c3", "r2c3>r2c0", "r1c0>r1c3"]


def seed(data_dir, days=16):
    """16 days of ordinary traffic so the engine starts in ranked mode, then a few odd movements."""
    rng = random.Random(4)
    today = dt.datetime.combine(dt.date.today(), dt.time())
    with open(data_dir / "movements.csv", "w", newline="", encoding="utf-8") as f:
        w = None
        for d in range(days, 0, -1):
            for cam in CAMERAS:
                for h in range(24):
                    for _ in range(rng.randint(3, 8) if 6 <= h <= 19 else rng.randint(0, 1)):
                        t = (today - dt.timedelta(days=d) + dt.timedelta(hours=h, minutes=rng.randint(0, 59))).timestamp()
                        e, x = rng.choice(USUAL).split(">")
                        m = Movement(cam, t, t + 20, e, x, speed=round(rng.uniform(0.3, 0.7), 2),
                                     dwell=round(rng.uniform(8, 30), 1), group=rng.choice([1, 1, 2]), crossed=True)
                        if w is None:
                            w = csv.DictWriter(f, fieldnames=list(m.row()))
                            w.writeheader()
                        w.writerow(m.row())
            if d <= 3:  # a new night path at the nala in the last days, walked by the same tracker ID
                for k in range(3):
                    t = (today - dt.timedelta(days=d) + dt.timedelta(hours=1, minutes=10 * k)).timestamp()
                    w.writerow(Movement("nala-2", t, t + 40, "r0c1", "r2c3", speed=0.2, dwell=40, low=0.5,
                                        crossed=True, person="P-207").row())
    (data_dir / "post.json").write_text('{"post_id": "BOP07", "alerts_per_shift": 12, '
                                        '"calendar": {"haat_weekdays": ["tue"]}}', encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=8010)
    args = ap.parse_args()
    data_dir = Path(tempfile.mkdtemp(prefix="rakshak-preview-"))
    seed(data_dir)
    engine = DecisionEngine(data_dir, CAMERAS, snapshot=lambda cam: b"\xff\xd8 preview jpeg \xff\xd9")
    now = time.time()
    odd = [Movement("nala-2", now - 900, now - 850, "r0c1", "r2c3", speed=0.1, dwell=50, low=0.7, group=3, crossed=True,
                    person="P-014"),
           Movement("field-3", now - 400, now - 380, "r0c3", "r2c0", speed=1.9, dwell=20, group=1, person="P-022"),
           Movement("gate-1", now - 120, now - 60, "r1c3", "r0c0", speed=0.2, dwell=120, group=4, person="P-031")]
    for m in odd:
        engine.process(m)
    decision_api.engine = engine

    app = FastAPI(title="Rakshak AI · decision preview")
    app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")
    app.include_router(decision_api.router)
    app.get("/api/cameras")(lambda: [{"id": c, "name": n} for c, n in CAMERAS.items()])
    app.get("/demo")(lambda: FileResponse(config.STATIC_DIR / "demo.html"))
    app.get("/api/threats/overview")(lambda: {"summary": {"active": 0, "in_progress": 0, "camera_issues": 0}})
    print(f"Synthetic preview data in {data_dir}. Open http://localhost:{args.port}/decision")
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
