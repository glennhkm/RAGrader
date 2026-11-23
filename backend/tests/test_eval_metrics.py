import math
import unittest

from src.evaluation.metrics import (
    accuracy,
    adjacent_accuracy,
    auroc,
    ece,
    hit_at_k,
    macro_f1,
    mae,
    mrr,
    qwk,
    spearman,
)

GOLD = [0, 0, 1, 1, 2, 2, 2, 1, 0, 2, 1, 0]
PRED = [0, 1, 1, 2, 2, 2, 1, 1, 0, 2, 0, 0]


class MetricsTest(unittest.TestCase):
    def test_qwk_matches_sklearn(self):
        self.assertAlmostEqual(0.75, qwk(GOLD, PRED, 3), places=12)

    def test_accuracy_and_macro_f1_match_sklearn(self):
        self.assertAlmostEqual(0.6666666666666666, accuracy(GOLD, PRED), places=12)
        self.assertAlmostEqual(0.6666666666666666, macro_f1(GOLD, PRED), places=12)
        self.assertAlmostEqual(
            0.6666666666666666, macro_f1([0, 1, 1, 0, 1, 0], [0, 1, 0, 0, 1, 1]), places=12
        )

    def test_spearman_matches_scipy_with_ties(self):
        x = [0.1, 0.4, 0.35, 0.8, 0.8, 0.2, 0.55, 0.9]
        y = [1, 2, 2, 3, 4, 1, 3, 3]
        self.assertAlmostEqual(0.8948415654446609, spearman(x, y), places=12)

    def test_auroc_matches_sklearn_with_ties(self):
        self.assertAlmostEqual(
            0.9375,
            auroc([1, 0, 1, 1, 0, 0, 1, 0], [0.9, 0.4, 0.7, 0.4, 0.2, 0.4, 0.8, 0.1]),
            places=12,
        )

    def test_ece_hand_computed(self):
        self.assertAlmostEqual(
            0.082, ece([0.95, 0.92, 0.15, 0.55, 0.58], [1, 1, 0, 1, 0]), places=12
        )

    def test_ece_last_bin_closed_at_one(self):
        self.assertAlmostEqual(0.0, ece([1.0, 1.0], [1, 1]))

    def test_adjacent_accuracy_and_mae(self):
        self.assertAlmostEqual(1.0, adjacent_accuracy(GOLD, PRED))
        self.assertAlmostEqual(4 / 12, mae(GOLD, PRED))

    def test_retrieval_metrics(self):
        ranked = [["a", "b"], ["b", "a"], ["c", "d"]]
        self.assertAlmostEqual(1 / 3, hit_at_k(ranked, ["a", "a", "a"], 1))
        self.assertAlmostEqual(2 / 3, hit_at_k(ranked, ["a", "a", "a"], 3))
        self.assertAlmostEqual((1 + 0.5 + 0) / 3, mrr(ranked, ["a", "a", "a"]))

    def test_mrr_duplicates_count_at_first_position(self):
        self.assertAlmostEqual(0.5, mrr([["x", "a", "a"]], ["a"]))

    def test_undefined_metrics_are_nan(self):
        self.assertTrue(math.isnan(qwk([1, 1, 1], [1, 1, 1], 3)))
        self.assertTrue(math.isnan(auroc([1, 1], [0.2, 0.3])))
        self.assertTrue(math.isnan(spearman([1, 1, 1], [1, 2, 3])))
        self.assertTrue(math.isnan(accuracy([], [])))
        self.assertTrue(math.isnan(mae([], [])))
        self.assertTrue(math.isnan(ece([], [])))
        self.assertTrue(math.isnan(mrr([], [])))

    def test_length_mismatch_raises(self):
        for fn in (accuracy, macro_f1, adjacent_accuracy, mae, spearman, auroc, ece, mrr):
            with self.assertRaises(ValueError):
                fn([1, 0], [1])
        with self.assertRaises(ValueError):
            qwk([1], [1, 2], 3)
        with self.assertRaises(ValueError):
            hit_at_k([["a"]], [], 1)


if __name__ == "__main__":
    unittest.main()
