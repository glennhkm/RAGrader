import unittest

from src.evaluation.stats import (
    Estimate,
    _resample_statistics,
    cluster_bootstrap,
    describe_difference,
    paired_difference,
)


def mean(rows):
    return sum(rows) / len(rows) if rows else float("nan")


class StatsTest(unittest.TestCase):
    def test_resamples_whole_clusters(self):
        rows = [("a", 0.0), ("b", 1.0), ("b", 1.0), ("b", 1.0)]
        seen = set()
        for seed in range(30):
            stats = _resample_statistics(
                rows, lambda r: r[0], lambda rs: mean([v for _, v in rs]), 50, seed
            )
            seen.update(round(s, 6) for s in stats)
        self.assertTrue(seen <= {0.0, 0.75, 1.0})

    def test_deterministic_for_seed(self):
        rows = [(str(i % 7), i % 3) for i in range(70)]
        f = lambda rs: mean([v for _, v in rs])
        self.assertEqual(cluster_bootstrap(rows, lambda r: r[0], f),
                         cluster_bootstrap(rows, lambda r: r[0], f))

    def test_nan_resamples_are_dropped_and_counted(self):
        rows = [("a", 1), ("b", 2)]
        stat = lambda rs: float("nan") if len({v for _, v in rs}) == 1 else 1.0
        est = cluster_bootstrap(rows, lambda r: r[0], stat, n_resamples=200)
        self.assertGreater(est.dropped_resamples, 0)
        self.assertEqual(1.0, est.low)

    def test_all_nan_gives_nan_interval(self):
        rows = [("a", 1), ("b", 2)]
        est = cluster_bootstrap(rows, lambda r: r[0], lambda rs: float("nan"), n_resamples=20)
        self.assertTrue(est.low != est.low and est.high != est.high)
        self.assertEqual(20, est.dropped_resamples)

    def test_paired_difference_identical_runs_is_zero(self):
        rows = [(f"i{i}", str(i % 5), i % 3) for i in range(50)]
        est = paired_difference(rows, rows, lambda r: r[0], lambda r: r[1],
                                lambda rs: mean([v for *_, v in rs]))
        self.assertEqual((0.0, 0.0, 0.0), (est.value, est.low, est.high))
        self.assertEqual("no detectable difference", describe_difference(est))

    def test_paired_drops_unmatched_and_detects_improvement(self):
        a = [(f"i{i}", str(i % 5), 0) for i in range(50)] + [("only_a", "x", 9)]
        b = [(f"i{i}", str(i % 5), 1) for i in range(50)] + [("only_b", "y", 9)]
        est = paired_difference(a, b, lambda r: r[0], lambda r: r[1],
                                lambda rs: mean([v for *_, v in rs]))
        self.assertEqual(50, est.n_items)
        self.assertEqual(5, est.n_clusters)
        self.assertEqual(1.0, est.value)
        self.assertEqual("improves", describe_difference(est))

    def test_paired_duplicate_keys_raise(self):
        a = [("k", "c", 1), ("k", "c", 2)]
        with self.assertRaises(ValueError):
            paired_difference(a, a, lambda r: r[0], lambda r: r[1], lambda rs: 0.0)

    def test_describe_worsens(self):
        self.assertEqual("worsens", describe_difference(Estimate(-1, -2, -0.5, 1, 1, 0)))


if __name__ == "__main__":
    unittest.main()
