import random
import tempfile
import time
import unittest
from pathlib import Path

from src.evaluation.metrics import qwk
from src.evaluation.thresholds import (
    Thresholds,
    apply_thresholds,
    case_study_label,
    fit_thresholds,
    load_thresholds,
    save_thresholds,
)


class ThresholdTest(unittest.TestCase):
    def test_fit_separates_clean_data(self):
        scores = [5, 10, 20, 45, 50, 55, 80, 90, 95]
        gold = [0, 0, 0, 1, 1, 1, 2, 2, 2]
        th = fit_thresholds(scores, gold, "unit")
        self.assertEqual(1.0, th.qwk_dev)
        self.assertTrue(20 < th.t1 <= 45 and 55 < th.t2 <= 80)
        self.assertEqual([0, 0, 0, 1, 1, 1, 2, 2, 2], [apply_thresholds(s, th) for s in scores])

    def test_tie_break_prefers_thirds(self):
        th = fit_thresholds([0, 50, 100], [0, 1, 2], "unit")
        self.assertEqual((34.0, 67.0), (th.t1, th.t2))

    def test_constant_dev_raises(self):
        with self.assertRaises(ValueError):
            fit_thresholds([50, 50], [1, 1], "unit")

    def test_case_study_conversion_boundaries(self):
        self.assertEqual([0, 1, 1, 2, 2], [case_study_label(s) for s in (32, 34, 68, 70, 100)])

    def test_apply_boundaries(self):
        th = Thresholds(30.0, 60.0, "u", 0.0)
        self.assertEqual([0, 1, 1, 2], [apply_thresholds(s, th) for s in (29.9, 30, 59.9, 60)])

    def test_fast_and_matches_metrics_qwk(self):
        rng = random.Random(1)
        gold = [rng.randint(0, 2) for _ in range(600)]
        scores = [min(100, max(0, g * 40 + rng.gauss(10, 18))) for g in gold]
        start = time.time()
        th = fit_thresholds(scores, gold, "unit")
        self.assertLess(time.time() - start, 5)
        pred = [apply_thresholds(s, th) for s in scores]
        self.assertAlmostEqual(qwk(gold, pred, 3), th.qwk_dev)

    def test_save_load_roundtrip(self):
        th = Thresholds(34.0, 67.0, "unit", 0.5)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "sub" / "th.json"
            save_thresholds(p, th)
            self.assertEqual(th, load_thresholds(p))


if __name__ == "__main__":
    unittest.main()
