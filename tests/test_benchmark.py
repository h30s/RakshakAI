"""Tests for the benchmark's own maths and plumbing (on synthetic data - never results)."""
import csv
import tempfile
import unittest
from pathlib import Path

from app.decision.calendar import PostCalendar
from app.decision.engine import load_movements
from benchmark.run import (DEFAULTS, STAGES, ece, evaluate, fleiss_kappa, isotonic, load_staged, rate,
                           review_sheet, synthetic, synthetic_ratings)


class StatsTest(unittest.TestCase):
    def test_fleiss_kappa(self):
        self.assertEqual(fleiss_kappa({i: [1, 1, 1] if i % 2 else [0, 0, 0] for i in range(10)}), 1.0)
        # Wikipedia-style check: raters split evenly on every item -> worse than chance.
        self.assertLess(fleiss_kappa({i: [1, 0] for i in range(10)}), 0)
        self.assertIsNone(fleiss_kappa({}))

    def test_isotonic_is_monotone_and_ece(self):
        f = isotonic([1, 2, 3, 4, 5, 6], [0, 1, 0, 1, 1, 1])
        preds = [f(x) for x in range(0, 8)]
        self.assertEqual(preds, sorted(preds))
        self.assertEqual(ece([0.0, 1.0, 1.0], [0, 1, 1]), 0.0)
        self.assertAlmostEqual(ece([0.9] * 10, [1] * 5 + [0] * 5), 0.4)


class PipelineTest(unittest.TestCase):
    def test_ablation_review_and_rating(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            mfile, sfile = synthetic(tmp)
            ev, results = evaluate(load_movements(mfile), load_staged(sfile), PostCalendar(), 12, 7, DEFAULTS)
            self.assertEqual(set(ev["ablation"]), set(STAGES))
            self.assertEqual(ev["rakshak_alerts_per_shift"], ev["ablation"]["full"]["alerts_per_shift"])
            self.assertGreaterEqual(ev["ablation"]["line"]["alerts_per_shift"], ev["ablation"]["full"]["alerts_per_shift"])
            self.assertLessEqual(ev["ablation"]["full"]["alerts_per_shift"], ev["ablation"]["baseline"]["alerts_per_shift"])
            self.assertIn("night shift", ev["by_shift_type"])

            n, n_full, n_line = review_sheet(results, tmp / "review", 30, seed=1)
            with open(tmp / "review" / "sheet.csv", newline="", encoding="utf-8") as f:
                header = next(csv.reader(f))
            self.assertNotIn("rakshak_alert", header)  # reviewers must not see which system raised it
            self.assertLessEqual(n, n_full + n_line)
            r = rate(synthetic_ratings(tmp, tmp / "review" / "key.csv"), tmp / "review" / "key.csv")
            self.assertEqual(r["reviewers"], 3)
            self.assertEqual(r["rakshak"]["rated"], n_full)
            self.assertIsNotNone(r["calibration"])


if __name__ == "__main__":
    unittest.main()
