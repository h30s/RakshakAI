"""Tests for the decision layer. Run: python -m unittest discover tests   (or: pytest)"""
import csv
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.decision.baseline import Baseline
from app.decision.budget import ALERT, DIGEST, AlertBudget, WatchOrder
from app.decision.calendar import FESTIVAL, HAAT, NORMAL, SEAL, PostCalendar
from app.decision.engine import DecisionEngine, load_movements
from app.decision.events import Movement, TrackAccumulator, summarise
from app.decision.ledger import Ledger, certificate_part_a, merkle_root, sms_alert, verify_packet, verify_sms

T0 = dt.datetime(2026, 8, 4, 10, 0).timestamp()  # a Tuesday, 10:00


def mv(t, path="r2c0>r2c3", cam="cam-1", **kw):
    e, x = path.split(">")
    return Movement(cam, t, t + 20, e, x, **{"speed": 0.5, "dwell": 20, **kw})


class EventsTest(unittest.TestCase):
    def test_crossing_group_and_posture(self):
        samples = [(T0 + i, (0.40, 0.30 + 0.1 * i, 0.50, 0.50 + 0.1 * i), 1) for i in range(4)]
        m = summarise("cam-1", samples, fences=[(0.0, 0.75, 1.0, 0.75)])
        self.assertTrue(m.crossed)
        self.assertEqual(m.group, 2)
        self.assertEqual(m.entry, "r1c1")
        low = summarise("cam-1", [(T0 + i, (0.1 + 0.05 * i, 0.8, 0.4 + 0.05 * i, 0.9), 0) for i in range(4)])
        self.assertEqual(low.low, 1.0)
        self.assertFalse(low.crossed)

    def test_accumulator_closes_tracks(self):
        acc = TrackAccumulator(gap_s=2)
        frame = np.zeros((360, 640, 3), np.uint8)
        for i in range(5):
            acc.observe(T0 + i, [("cam-1", frame, [{"label": "person", "pid": "P-001",
                                                    "box": (100 + 20 * i, 100, 140 + 20 * i, 200)}])])
        acc.flush(T0 + 10)
        done = acc.pop_finished()
        self.assertEqual(len(done), 1)
        self.assertEqual(done[0].person, "P-001")


class CalendarTest(unittest.TestCase):
    def test_day_types(self):
        cal = PostCalendar(haat_weekdays=["tue"], festivals=["2026-08-05"],
                           seals=[{"from": "2026-08-06T18:00", "to": "2026-08-07T18:00"}])
        self.assertEqual(cal.day_type(T0), HAAT)
        self.assertEqual(cal.day_type(T0 + 86400), FESTIVAL)
        self.assertEqual(cal.day_type(T0 + 2 * 86400 + 10 * 3600), SEAL)
        self.assertEqual(cal.day_type(T0 + 5 * 86400), NORMAL)


class BaselineTest(unittest.TestCase):
    def test_off_path_scores_higher(self):
        b = Baseline()
        for d in range(7):
            for k in range(30):
                b.add(mv(T0 + d * 86400 + k * 60), NORMAL)
        usual, _ = b.score(mv(T0 + 8 * 86400), NORMAL)
        odd, terms = b.score(mv(T0 + 8 * 86400, path="r0c3>r2c0"), NORMAL)
        self.assertGreater(odd, usual + 2)
        self.assertGreater(terms["off usual path"], 2)
        self.assertEqual(b.days_seen, 7)


class BudgetTest(unittest.TestCase):
    def test_threshold_and_cap(self):
        day = dt.datetime(2026, 8, 4, 6, 0).timestamp()  # exactly 3 shifts: 06:00 to 06:00
        history = [(day + i * 60, float(i)) for i in range(3 * 480)]
        budget = AlertBudget(per_shift=12)
        budget.calibrate(history)
        self.assertEqual(sum(1 for _, s in history if s >= budget.threshold) / 3, 12)
        budget.surge.manual = False  # cap only; surge mode is tested separately
        sent = [budget.decide(mv(T0 + 86400 + i), 1e6)[0] for i in range(20)]
        self.assertEqual(sent.count(ALERT), 12)

    def test_always_alert_and_watch_order(self):
        budget = AlertBudget(per_shift=1)
        budget.calibrate([(T0 + i, float(i)) for i in range(100)])
        budget.used[(dt.date(2026, 8, 5), 0)] = 99
        seal = mv(T0 + 86400, crossed=True)
        self.assertEqual(budget.decide(seal, 0.0, sealed=True)[0], ALERT)
        budget.add_watch_order(WatchOrder("cam-2", T0 + 10 ** 6, factor=0.5))
        self.assertEqual(budget._threshold_for("cam-2", T0 + 86400), budget.threshold * 0.5)

    def test_learning_mode_is_a_tripwire(self):
        budget = AlertBudget()
        self.assertEqual(budget.decide(mv(T0, crossed=True), 0)[0], ALERT)
        self.assertEqual(budget.decide(mv(T0), 0)[0], DIGEST)

    def test_surge_lifts_the_cap(self):
        budget = AlertBudget(per_shift=2)
        budget.calibrate([(T0 - 86400 * d + i * 600, 1.0 if i % 20 else 9.0) for d in range(1, 8) for i in range(144)])
        night = dt.datetime(2026, 8, 5, 2, 0).timestamp()
        out = [budget.decide(mv(night + i * 120), 50.0) for i in range(15)]
        self.assertTrue(budget.surge.active)
        self.assertGreater(sum(1 for d, _ in out if d == ALERT), 2)
        self.assertTrue(any(r.startswith("Surge") for _, r in out))


class LedgerTest(unittest.TestCase):
    def test_seal_verify_and_tamper(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            key = Ed25519PrivateKey.generate()
            led = Ledger(tmp / "ledger.jsonl", key, clip_dir=tmp)
            clip = tmp / "a.jpg"
            clip.write_bytes(b"evidence")
            e = led.append("alert", {"alert": "A-0001"}, clip=clip, t=T0)
            led.append("action", {"alert": "A-0001", "status": "escalated"}, t=T0 + 5)
            anchor = led.anchor(T0 - 1, T0 + 10)
            self.assertEqual(anchor["data"]["count"], 2)
            self.assertEqual(anchor["data"]["root"], merkle_root([x["hash"] for x in led.entries[:2]]))
            self.assertEqual(led.verify(), [])
            self.assertEqual(Ledger(tmp / "ledger.jsonl", key, clip_dir=tmp).verify(), [])  # reload
            clip.write_bytes(b"edited!!")
            self.assertTrue(any("modified" in p for p in led.verify()))
            self.assertIn("SHA-256", certificate_part_a(e, "BOP07", "edge box"))

    def test_sms_fits_and_verifies(self):
        key = Ed25519PrivateKey.generate()
        msg = sms_alert(key, "BOP07", "cam-03", T0, "OFFPATH", "ab" * 32)
        self.assertLessEqual(len(msg), 160)
        self.assertTrue(verify_sms(msg, key.public_key()))
        self.assertFalse(verify_sms(msg.replace("cam-03", "cam-04"), key.public_key()))


class EngineTest(unittest.TestCase):
    def test_end_to_end_learning_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "post.json").write_text('{"post_id": "BOP07", "fences": {"cam-1": [[0, 0.6, 1, 0.6]]}}')
            eng = DecisionEngine(tmp, {"cam-1": "Gate"}, snapshot=lambda cam: b"jpeg-bytes")
            frame = np.zeros((360, 640, 3), np.uint8)
            for i in range(6):  # walks down the frame, crossing the fence at y = 0.6
                eng.observe(T0 + i, [("cam-1", frame, [{"label": "person", "pid": "P-001",
                                                         "box": (300, 40 + 40 * i, 340, 120 + 40 * i)}])])
            eng.tick(T0 + 30)
            ov = eng.overview()
            self.assertEqual(ov["mode"], "learning")
            self.assertEqual(len(ov["alerts"]), 1)
            self.assertLessEqual(len(ov["alerts"][0]["sms"]), 160)
            self.assertEqual(eng.ledger.verify(), [])
            self.assertEqual(len(load_movements(tmp / "movements.csv")), 1)
            self.assertIn("PART A", eng.certificate(ov["alerts"][0]["id"]))
            self.assertEqual(verify_packet(eng.packet(ov["alerts"][0]["id"])), [])

    def test_learning_mode_respects_the_budget_but_not_for_critical(self):
        budget = AlertBudget(per_shift=2)
        sent = [budget.decide(mv(T0 + i, crossed=True), 0)[0] for i in range(5)]
        self.assertEqual(sent.count(ALERT), 2)
        self.assertEqual(budget.decide(mv(T0 + 10, crossed=True), 0, sealed=True)[0], ALERT)

    def test_borrowed_baseline_until_enough_own_days(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            other = [mv(T0 - 20 * 86400 + d * 86400 + k * 60, cam="other-cam") for d in range(10) for k in range(40)]
            with open(tmp / "similar_post.csv", "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(other[0].row()))
                w.writeheader()
                w.writerows(m.row() for m in other)
            (tmp / "post.json").write_text(json.dumps({"post_id": "BOP08", "borrow_baseline": "similar_post.csv"}))
            eng = DecisionEngine(tmp, {"cam-1": "Gate"})
            self.assertEqual(eng.mode, "borrowed")
            self.assertEqual(eng.min_days, 14)
            usual, _ = eng.baseline.score(mv(T0, cam="cam-1"), NORMAL)  # a camera the other post never had
            odd, _ = eng.baseline.score(mv(T0, cam="cam-1", path="r0c3>r2c0"), NORMAL)
            self.assertGreater(odd, usual)

    def test_drift_watch_and_retention(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            eng = DecisionEngine(tmp, {"cam-1": "Gate"})
            now = T0 + 40 * 86400
            (tmp / "evidence").mkdir()
            for i in range(12):
                clip = tmp / "evidence" / f"c{i}.jpg"
                clip.write_bytes(b"jpeg")
                eng.ledger.append("alert", {"alert": f"A-{i:04d}"}, clip=clip, t=T0 + i)
                eng.ledger.append("action", {"alert": f"A-{i:04d}", "status": "escalated" if i < 3 else "dismissed"},
                                  t=now - 3600)
            d = eng.drift(now)
            self.assertEqual((d["taps"], d["precision"], d["rebaseline"]), (12, 0.25, True))
            with open(tmp / "movements.csv", "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(mv(T0).row()))
                w.writeheader()
                w.writerows([mv(now - 200 * 86400).row(), mv(now - 86400).row()])
            clips, rows = eng.apply_retention(now)
            self.assertEqual((clips, rows), (9, 1))  # escalated alerts keep their clips
            self.assertTrue((tmp / "evidence" / "c0.jpg").exists())
            self.assertFalse((tmp / "evidence" / "c5.jpg").exists())
            self.assertEqual(eng.ledger.verify(), [])
            self.assertEqual(eng.apply_retention(now), (0, 0))


if __name__ == "__main__":
    unittest.main()
