"""Derived evaluation sets: the consistency sample and prompt-injection pairs."""

import dataclasses
import random
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import yaml

from .paths import EVAL_ASSETS
from .schema import EvalItem

DEFAULT_SEED = 20261123
TEMPLATES_FILE = EVAL_ASSETS / "adversarial_templates.yaml"


def load_templates(path: Optional[Path] = None) -> Dict[str, List[str]]:
    with open(path or TEMPLATES_FILE, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    if not isinstance(raw, dict):
        raise ValueError("adversarial templates must be a mapping")
    return {str(lang): [str(t) for t in templates] for lang, templates in raw.items()}


def _sample(pool: Sequence[EvalItem], n: int, seed: int) -> List[EvalItem]:
    ordered = sorted(pool, key=lambda i: i.item_id)
    if len(ordered) <= n:
        return ordered
    picked = random.Random(seed).sample(ordered, n)
    return sorted(picked, key=lambda i: i.item_id)


def derive_consistency(items: Sequence[EvalItem], n: int = 100,
                       seed: int = DEFAULT_SEED) -> List[EvalItem]:
    """A fixed seeded sample of dev eval-role items, returned unchanged."""
    pool = [i for i in items if i.split == "dev" and i.role == "eval"]
    return _sample(pool, n, seed)


def derive_injection(items: Sequence[EvalItem], templates: Dict[str, List[str]],
                     n_per_split: int = 100, seed: int = DEFAULT_SEED) -> List[EvalItem]:
    """Clean gold-0 originals per (dataset, split), each followed by its injected copies.

    Copy ``k`` uses ``templates[item.language][k]``; originals keep ``variant=None``.
    """
    groups: Dict[tuple, List[EvalItem]] = defaultdict(list)
    for item in items:
        if item.role == "eval" and item.gold_label == 0:
            groups[(item.dataset, item.split)].append(item)
    out: List[EvalItem] = []
    for key in sorted(groups):
        for orig in _sample(groups[key], n_per_split, seed):
            if not templates.get(orig.language):
                raise ValueError(f"no injection templates for language: {orig.language}")
            out.append(orig)
            for k, template in enumerate(templates[orig.language]):
                out.append(dataclasses.replace(
                    orig,
                    item_id=f"{orig.item_id}::inj{k}",
                    derived_from=orig.item_id,
                    variant=f"injection:{orig.language}:{k}",
                    answer=orig.answer + "\n\n" + template,
                ))
    return out
