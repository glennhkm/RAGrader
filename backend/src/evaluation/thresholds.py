"""Dev-fitted score-to-label thresholds (0-100 score -> 3 ordinal labels)."""
from __future__ import annotations

import json
import math
from bisect import bisect_left
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

from src.evaluation.metrics import qwk

N_LABELS = 3
_MAX = 100


@dataclass(frozen=True)
class Thresholds:
    t1: float
    t2: float
    fitted_on: str
    qwk_dev: float


def apply_thresholds(score: float, th: Thresholds) -> int:
    if score < th.t1:
        return 0
    if score < th.t2:
        return 1
    return 2


def _qwk_from_confusion(obs: list[list[int]], n: int) -> float:
    rows = [sum(r) for r in obs]
    cols = [sum(obs[i][j] for i in range(N_LABELS)) for j in range(N_LABELS)]
    num = den = 0.0
    for i in range(N_LABELS):
        for j in range(N_LABELS):
            w = (i - j) ** 2 / 4
            num += w * obs[i][j]
            den += w * rows[i] * cols[j] / n
    if den == 0:
        return math.nan
    return 1.0 - num / den


def fit_thresholds(scores: Sequence[float], gold: Sequence[int], fitted_on: str) -> Thresholds:
    if len(scores) != len(gold):
        raise ValueError("scores and gold must have equal length")
    n = len(gold)
    if n == 0 or len(set(gold)) < 2:
        raise ValueError("cannot fit thresholds: dev labels or scores are constant")
    by_label = [sorted(s for s, g in zip(scores, gold) if g == k) for k in range(N_LABELS)]
    # lt[k][t] = number of label-k items with score < t, for integer t in 0..100
    lt = [[bisect_left(by_label[k], t) for t in range(_MAX + 1)] for k in range(N_LABELS)]
    totals = [len(b) for b in by_label]

    best_key = None
    best = None
    for t1 in range(1, _MAX):
        for t2 in range(t1 + 1, _MAX + 1):
            obs = [
                [lt[k][t1], lt[k][t2] - lt[k][t1], totals[k] - lt[k][t2]]
                for k in range(N_LABELS)
            ]
            q = _qwk_from_confusion(obs, n)
            if math.isnan(q):
                continue
            key = (-q, abs(t1 - 34) + abs(t2 - 67), t1, t2)
            # compare QWK with tolerance so float noise does not defeat tie-breaks
            if best_key is None or q > -best_key[0] + 1e-12 or (
                abs(q + best_key[0]) <= 1e-12 and key[1:] < best_key[1:]
            ):
                best_key, best = key, (t1, t2)
    if best is None:
        raise ValueError("cannot fit thresholds: dev labels or scores are constant")
    t1, t2 = best
    th = Thresholds(float(t1), float(t2), fitted_on, 0.0)
    q = qwk(list(gold), [apply_thresholds(s, th) for s in scores], N_LABELS)
    return Thresholds(float(t1), float(t2), fitted_on, q)


def case_study_label(score_0_100: float) -> int:
    points = math.floor(score_0_100 * 25 / 100 + 0.5)
    if points <= 8:
        return 0
    if points <= 17:
        return 1
    return 2


def save_thresholds(path, th: Thresholds) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(th), indent=2), encoding="utf-8")


def load_thresholds(path) -> Thresholds:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    return Thresholds(float(d["t1"]), float(d["t2"]), str(d["fitted_on"]), float(d["qwk_dev"]))
