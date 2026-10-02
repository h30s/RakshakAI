"""Tests for live decisions, restart recovery, external hits, latency and the shift report."""
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from app.decision.baseline import Baseline
from app.decision.calendar import NORMAL
from app.decision.engine import DecisionEngine, load_movements
from app.decision.events import Movement, summarise

T0 = dt.datetime(2026, 8, 4, 23, 0).timestamp()  # a night hour
FRAME = np.zeros((360, 640, 3), np.uint8)
POST = {"post_id": "BOP07", "fences": {"cam-1": [[0, 0.6, 1, 0.6]]}, "restricted_zones": {"cam-1": [[0, 0.6, 1, 1]]}}


def walk_down(eng, start, steps, pid="P-001"):
    """A person walking down the frame, crossing the fence at y = 0.6 after a few steps."""
    for i in range(steps):
        eng.observe(start + i, [("cam-1", FRAME, [{"label": "person", "pid": pid,
                                                  "box": (300, 40 + 40 * i, 340, 120 + 40 * i)}])])
        eng.tick(start + i + 0.1)


class LiveTest(unittest.TestCase):
    def engine(self, tmp, cfg=POST):
        (tmp / "post.json").write_text(json.dumps(cfg))
        return DecisionEngine(tmp, {"cam-1": "Gate"}, snapshot=lambda cam: b"jpeg")

    def test_crossing_alerts_while_the_person_is_still_in_view(self):
        with tempfile.TemporaryDirectory() as tmp:
            eng = self.engine(Path(tmp))
            walk_down(eng, T0, 6)  # still in view: no track has closed yet
            self.assertEqual(eng.acc.pop_finished(), [])
            self.assertEqual(len(eng.alerts), 1)
            a = eng.alerts[0]
            self.assertIn("night", a["reason"])  # fence breach into the restricted zone at night
            self.assertLess(a["latency"]["server"], 1.0)
            # The person leaves: the movement is logged once, not alerted a second time.
            eng.tick(T0 + 30)
            self.assertEqual(len(eng.alerts), 1)
            self.assertEqual(len(load_movements(Path(tmp) / "movements.csv")), 1)
            self.assertEqual(eng.ledger.verify(), [])

    def test_restart_keeps_ids_statuses_and_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            eng = self.engine(tmp)
            walk_down(eng, T0, 6)
            eng.set_status("A-0001", "escalated")
            again = self.engine(tmp)
            self.assertEqual([(a["id"], a["status"]) for a in again.alerts], [("A-0001", "escalated")])
            self.assertEqual(sum(again.budget.used.values()), 1)
            walk_down(again, T0 + 600, 6, pid="P-002")
            self.assertEqual(again.alerts[-1]["id"], "A-0002")  # no id reuse, no clip overwritten
            self.assertEqual(again.ledger.verify(), [])

    def test_external_hit_joins_the_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            eng = self.engine(Path(tmp))
            a = eng.external_hit("anpr", "cam-1", "UP32AB1234", confidence=0.91, t=T0)
            self.assertEqual(a["reason"], "ANPR hit: UP32AB1234 (91%)")
            self.assertIn(" ANPR ", a["sms"])
            self.assertEqual(eng.ledger.entries[-1]["data"]["source"], "anpr")
            self.assertLessEqual(len(a["sms"]), 160)

    def test_latency_is_recorded_once_per_channel(self):
        with tempfile.TemporaryDirectory() as tmp:
            eng = self.engine(Path(tmp))
            a = eng.external_hit("frs", "cam-1", "W-07", t=T0)
            eng.delivered(a["id"], "console", now=T0 + 1.5)
            eng.delivered(a["id"], "console", now=T0 + 9)  # a second render does not count
            eng.delivered(a["id"], "sms", now=T0 + 3.0)
            stats = eng.latency_stats()
            self.assertEqual((stats["console"]["n"], stats["console"]["p50"]), (1, 1.5))
            self.assertEqual(stats["sms"]["p95"], 3.0)
            self.assertTrue((Path(tmp) / "latency.csv").exists())

    def test_shift_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            eng = self.engine(Path(tmp))
            walk_down(eng, T0, 6)
            eng.set_status("A-0001", "acknowledged")
            r = eng.shift_report(T0)
            self.assertEqual(r["shift"]["number"], 3)  # 22:00-06:00
            self.assertEqual(len(r["alerts"]), 1)
            self.assertTrue(r["ledger"]["intact"])
            # The operator's tap is stamped with the real clock, so it belongs to today's shift.
            self.assertEqual(eng.shift_report()["actions"][0]["data"]["status"], "acknowledged")


class LoiterTest(unittest.TestCase):
    def test_zone_dwell_and_loiter_term(self):
        samples = [(T0 + 5 * i, (0.4, 0.62, 0.5, 0.8), 0) for i in range(10)]  # 45 s in the zone
        m = summarise("cam-1", samples, restricted=[(0, 0.6, 1, 1)])
        self.assertEqual(m.zone_dwell, 45)
        b = Baseline()
        for k in range(50):
            b.add(Movement("cam-1", T0 + k, T0 + k + 10, "r1c1", "r1c1", speed=0.5, dwell=10), NORMAL)
        _, terms = b.score(m, NORMAL)
        self.assertGreater(terms["loiter in restricted zone"], 2)
        _, short = b.score(Movement("cam-1", T0, T0 + 10, "r1c1", "r1c1", zone_dwell=10), NORMAL)
        self.assertEqual(short["loiter in restricted zone"], 0)


if __name__ == "__main__":
    unittest.main()
