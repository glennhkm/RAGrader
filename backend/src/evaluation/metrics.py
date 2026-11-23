"""Pure-Python agreement, calibration and retrieval metrics.

No numpy/pandas/scikit-learn/scipy. Conventions (spec section 8, item 6):

* Undefined results return ``nan`` (never raise): empty inputs, QWK when the
  expected-weighted disagreement is 0, Spearman with a constant input or fewer
  than two points, AUROC with only one class present, ECE/MRR/hit@k on empty
  inputs.
* Any length mismatch between paired inputs raises ``ValueError``.
* Ties: Spearman and AUROC use average ranks (ties share the mean rank);
  AUROC counts tied positive/negative score pairs as one half.
* macro_f1 uses labels = sorted union of gold and pred (sklearn default); a
  label with precision+recall of 0 contributes an F1 of 0.
* qwk expects integer labels in ``range(n_labels)`` with quadratic weights
  (i-j)^2/(n_labels-1)^2.
* ece uses equal-width bins [k/n, (k+1)/n), the last bin closed at 1.0.
* mrr uses the reciprocal rank of the first match (0 if absent); duplicates
  of a source count at their first position.
"""

from __future__ import annotations

import math
from typing import Sequence

NAN = float("nan")


def _check(a: Sequence, b: Sequence) -> None:
    if len(a) != len(b):
        raise ValueError(f"length mismatch: {len(a)} != {len(b)}")


def qwk(gold: Sequence[int], pred: Sequence[int], n_labels: int) -> float:
    _check(gold, pred)
    n = len(gold)
    if n == 0 or n_labels < 2:
        return NAN
    obs = [[0.0] * n_labels for _ in range(n_labels)]
    for g, p in zip(gold, pred):
        if not (0 <= g < n_labels and 0 <= p < n_labels):
            raise ValueError("label out of range")
        obs[g][p] += 1
    rows = [sum(r) for r in obs]
    cols = [sum(obs[i][j] for i in range(n_labels)) for j in range(n_labels)]
    denom = (n_labels - 1) ** 2
    num = den = 0.0
    for i in range(n_labels):
        for j in range(n_labels):
            w = (i - j) ** 2 / denom
            num += w * obs[i][j]
            den += w * rows[i] * cols[j] / n
    if den == 0:
        return NAN
    return 1.0 - num / den


def accuracy(gold: Sequence, pred: Sequence) -> float:
    _check(gold, pred)
    if not gold:
        return NAN
    return sum(1 for g, p in zip(gold, pred) if g == p) / len(gold)


def macro_f1(gold: Sequence, pred: Sequence) -> float:
    _check(gold, pred)
    if not gold:
        return NAN
    labels = sorted(set(gold) | set(pred))
    total = 0.0
    for lab in labels:
        tp = sum(1 for g, p in zip(gold, pred) if g == lab and p == lab)
        fp = sum(1 for g, p in zip(gold, pred) if g != lab and p == lab)
        fn = sum(1 for g, p in zip(gold, pred) if g == lab and p != lab)
        d = 2 * tp + fp + fn
        total += (2 * tp / d) if d else 0.0
    return total / len(labels)


def adjacent_accuracy(gold: Sequence[int], pred: Sequence[int]) -> float:
    _check(gold, pred)
    if not gold:
        return NAN
    return sum(1 for g, p in zip(gold, pred) if abs(g - p) <= 1) / len(gold)


def mae(a: Sequence[float], b: Sequence[float]) -> float:
    _check(a, b)
    if not a:
        return NAN
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a)


def _avg_ranks(values: Sequence[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman(x: Sequence[float], y: Sequence[float]) -> float:
    _check(x, y)
    if len(x) < 2:
        return NAN
    rx, ry = _avg_ranks(x), _avg_ranks(y)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    sxy = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    sxx = sum((a - mx) ** 2 for a in rx)
    syy = sum((b - my) ** 2 for b in ry)
    if sxx == 0 or syy == 0:
        return NAN
    return sxy / math.sqrt(sxx * syy)


def auroc(y_true: Sequence[int], scores: Sequence[float]) -> float:
    _check(y_true, scores)
    n_pos = sum(1 for t in y_true if t == 1)
    n_neg = len(y_true) - n_pos
    if n_pos == 0 or n_neg == 0:
        return NAN
    ranks = _avg_ranks(scores)
    rank_sum = sum(r for r, t in zip(ranks, y_true) if t == 1)
    return (rank_sum - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


def ece(confidences: Sequence[float], correct: Sequence[int], n_bins: int = 10) -> float:
    _check(confidences, correct)
    n = len(confidences)
    if n == 0:
        return NAN
    sums = [[0.0, 0.0, 0] for _ in range(n_bins)]  # conf, correct, count
    for c, ok in zip(confidences, correct):
        b = min(int(c * n_bins), n_bins - 1)
        sums[b][0] += c
        sums[b][1] += ok
        sums[b][2] += 1
    return sum(
        cnt / n * abs(cor / cnt - conf / cnt) for conf, cor, cnt in sums if cnt
    )


def hit_at_k(ranked: Sequence[Sequence[str]], gold: Sequence[str], k: int) -> float:
    _check(ranked, gold)
    if not ranked:
        return NAN
    return sum(1 for r, g in zip(ranked, gold) if g in list(r)[:k]) / len(ranked)


def mrr(ranked: Sequence[Sequence[str]], gold: Sequence[str]) -> float:
    _check(ranked, gold)
    if not ranked:
        return NAN
    total = 0.0
    for r, g in zip(ranked, gold):
        for pos, src in enumerate(r, start=1):
            if src == g:
                total += 1 / pos
                break
    return total / len(ranked)
