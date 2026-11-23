"""Cluster bootstrap and paired comparison (pure Python).

Rows are grouped by cluster (clusters in sorted key order); each resample
draws ``len(clusters)`` clusters with replacement using ``random.Random(seed)``
and concatenates their rows. The CI is the percentile interval over non-nan
resample statistics with linear interpolation between order statistics.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Callable, Dict, List, Sequence, Tuple, TypeVar

T = TypeVar("T")
NAN = float("nan")


@dataclass(frozen=True)
class Estimate:
    value: float
    low: float
    high: float
    n_items: int
    n_clusters: int
    dropped_resamples: int


def _group(rows: Sequence[T], cluster_of: Callable[[T], str]) -> List[List[T]]:
    groups: Dict[str, List[T]] = {}
    for row in rows:
        groups.setdefault(cluster_of(row), []).append(row)
    return [groups[k] for k in sorted(groups)]


def _resample_statistics(
    rows: Sequence[T],
    cluster_of: Callable[[T], str],
    statistic: Callable[[Sequence[T]], float],
    n_resamples: int,
    seed: int,
) -> List[float]:
    clusters = _group(rows, cluster_of)
    rng = random.Random(seed)
    out: List[float] = []
    for _ in range(n_resamples):
        sample: List[T] = []
        for _ in range(len(clusters)):
            sample.extend(clusters[rng.randrange(len(clusters))])
        out.append(statistic(sample))
    return out


def _percentile(sorted_vals: Sequence[float], q: float) -> float:
    pos = q * (len(sorted_vals) - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = pos - lo
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * frac


def _interval(value: float, stats: List[float], n_items: int, n_clusters: int,
              alpha: float) -> Estimate:
    kept = sorted(s for s in stats if not math.isnan(s))
    dropped = len(stats) - len(kept)
    if math.isnan(value) or not kept:
        return Estimate(value, NAN, NAN, n_items, n_clusters, dropped)
    return Estimate(value, _percentile(kept, alpha / 2),
                    _percentile(kept, 1 - alpha / 2), n_items, n_clusters, dropped)


def cluster_bootstrap(
    rows: Sequence[T],
    cluster_of: Callable[[T], str],
    statistic: Callable[[Sequence[T]], float],
    n_resamples: int = 2000,
    seed: int = 20261123,
    alpha: float = 0.05,
) -> Estimate:
    value = statistic(list(rows))
    stats = _resample_statistics(rows, cluster_of, statistic, n_resamples, seed)
    return _interval(value, stats, len(rows), len(_group(rows, cluster_of)), alpha)


def paired_difference(
    rows_a: Sequence[T],
    rows_b: Sequence[T],
    key_of: Callable[[T], str],
    cluster_of: Callable[[T], str],
    statistic: Callable[[Sequence[T]], float],
    n_resamples: int = 2000,
    seed: int = 20261123,
) -> Estimate:
    """statistic(B) - statistic(A) on the inner join by ``key_of``."""

    def index(rows: Sequence[T], side: str) -> Dict[str, T]:
        d: Dict[str, T] = {}
        for r in rows:
            k = key_of(r)
            if k in d:
                raise ValueError(f"duplicate key {k!r} in side {side}")
            d[k] = r
        return d

    ia, ib = index(rows_a, "A"), index(rows_b, "B")
    keys = sorted(set(ia) & set(ib))
    pairs: List[Tuple[T, T]] = [(ia[k], ib[k]) for k in keys]

    def diff(sample: Sequence[Tuple[T, T]]) -> float:
        return statistic([b for _, b in sample]) - statistic([a for a, _ in sample])

    # Cluster by the A-side row's cluster (the join keeps matched pairs together).
    cluster_pair = lambda p: cluster_of(p[0])
    value = diff(pairs)
    stats = _resample_statistics(pairs, cluster_pair, diff, n_resamples, seed)
    return _interval(value, stats, len(pairs), len(_group(pairs, cluster_pair)), 0.05)


def describe_difference(est: Estimate, higher_is_better: bool = True) -> str:
    """Spec 6.4 wording; ``"undefined"`` when the value or either bound is nan.

    The estimate is B - A. For a higher-is-better metric B improves when the CI lies above
    0; for a lower-is-better metric (an error such as MAE or ECE) when it lies below 0.
    """
    if any(math.isnan(x) for x in (est.value, est.low, est.high)):
        return "undefined"
    above, below = est.low > 0, est.high < 0
    if (above and higher_is_better) or (below and not higher_is_better):
        return "improves"
    if above or below:
        return "worsens"
    return "no detectable difference"
