"""Frozen question-disjoint splits, example banks, budget samples and split files."""

import dataclasses
import hashlib
import json
import random
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

from .schema import EvalItem

DEFAULT_SEED = 20261123
BANK_MAX = 9


def snapshot_hash(items: Sequence[EvalItem]) -> str:
    """sha256 over canonical JSON of the items sorted by item_id, fields sorted."""
    rows = [dataclasses.asdict(i) for i in sorted(items, key=lambda i: i.item_id)]
    blob = json.dumps(rows, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def split_by_question(items: Sequence[EvalItem], dev_fraction: float = 0.4,
                      seed: int = DEFAULT_SEED) -> List[EvalItem]:
    counts: Dict[str, int] = defaultdict(int)
    for item in items:
        counts[item.question_id] += 1
    questions = sorted(counts)
    random.Random(seed).shuffle(questions)
    target = dev_fraction * len(items)
    dev_questions = set()
    dev_count = 0
    for q in questions:
        if dev_count >= target:
            break
        dev_questions.add(q)
        dev_count += counts[q]
    return [dataclasses.replace(i, split="dev" if i.question_id in dev_questions else "test")
            for i in items]


def _group(items: Sequence[EvalItem], key) -> Dict[str, List[EvalItem]]:
    groups: Dict[str, List[EvalItem]] = defaultdict(list)
    for item in items:
        groups[key(item)].append(item)
    return groups


def carve_banks(items: Sequence[EvalItem], seed: int = DEFAULT_SEED) -> List[EvalItem]:
    """Mark min(9, n // 3) items per (split, question) as bank examples."""
    banked = set()
    groups = _group(items, lambda i: (i.split, i.question_id))
    for (split, question_id), group in groups.items():
        ordered = sorted(group, key=lambda i: i.item_id)
        random.Random(f"{seed}:bank:{split}:{question_id}").shuffle(ordered)
        for item in ordered[:min(BANK_MAX, len(ordered) // 3)]:
            banked.add(item.item_id)
    return [dataclasses.replace(i, role="bank") if i.item_id in banked else i for i in items]


def budget_sample(items: Sequence[EvalItem], split: str, cap: int,
                  seed: int = DEFAULT_SEED) -> List[EvalItem]:
    """Cut eval items of `split` down to about `cap`, proportional per question."""
    items = list(items)
    target = [i for i in items if i.split == split and i.role == "eval"]
    total = len(target)
    if total <= cap:
        return items
    drop = set()
    for question_id, group in _group(target, lambda i: i.question_id).items():
        keep = min(len(group), max(1, round(len(group) * cap / total)))
        ordered = sorted(group, key=lambda i: i.item_id)
        random.Random(f"{seed}:sample:{split}:{question_id}").shuffle(ordered)
        drop.update(i.item_id for i in ordered[keep:])
    return [i for i in items if i.item_id not in drop]


@dataclass
class SplitFile:
    dataset: str
    snapshot: str
    seed: int
    splits: Dict[str, List[str]]
    banks: Dict[str, List[str]]
    counts: Dict[str, int]


def _hash_id(item_id: str) -> str:
    return hashlib.sha256(item_id.encode("utf-8")).hexdigest()[:16]


def write_split_file(path, split_file: SplitFile, hash_ids: bool) -> None:
    def conv(mapping: Dict[str, List[str]]) -> Dict[str, List[str]]:
        return {k: sorted(_hash_id(i) if hash_ids else i for i in v) for k, v in mapping.items()}

    data = {
        "dataset": split_file.dataset,
        "snapshot": split_file.snapshot,
        "seed": split_file.seed,
        "splits": conv(split_file.splits),
        "banks": conv(split_file.banks),
        "counts": dict(split_file.counts),
    }
    if hash_ids:
        data["hashed"] = True
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                    encoding="utf-8")


def read_split_file(path) -> SplitFile:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return SplitFile(
        dataset=data["dataset"], snapshot=data["snapshot"], seed=data["seed"],
        splits=data["splits"], banks=data["banks"], counts=data["counts"],
    )


def _build_split_file(name: str, items: Sequence[EvalItem], seed: int) -> SplitFile:
    splits: Dict[str, List[str]] = {}
    banks: Dict[str, List[str]] = {}
    for item in items:
        target = splits if item.role == "eval" else banks
        target.setdefault(item.split, []).append(item.item_id)
        (banks if item.role == "eval" else splits).setdefault(item.split, [])
    splits = {k: sorted(v) for k, v in sorted(splits.items())}
    banks = {k: sorted(v) for k, v in sorted(banks.items())}
    counts = {k: len(v) for k, v in splits.items()}
    counts.update({f"{k}_bank": len(v) for k, v in banks.items()})
    return SplitFile(name, snapshot_hash(items), seed, splits, banks, counts)


def _assert_unique_ids(items: Sequence[EvalItem]) -> None:
    """Item ids key results, banks and pairs; the message names the count, never an id."""
    n = len(items) - len({i.item_id for i in items})
    if n:
        raise ValueError(f"{n} duplicate item_ids; deduplicate the source before splitting")


def prepare_dataset(name: str, items: List[EvalItem]) -> Tuple[List[EvalItem], SplitFile]:
    seed = DEFAULT_SEED
    items = list(items)
    _assert_unique_ids(items)
    if name == "engsaf":
        items = split_by_question(items, seed=seed)
        items = carve_banks(items, seed=seed)
        items = budget_sample(items, "dev", 600, seed=seed)
        items = budget_sample(items, "test", 1000, seed=seed)
    elif name == "scientsbank":
        items = [dataclasses.replace(i, split="dev") if i.split == "train" else i
                 for i in items]
        items = carve_banks(items, seed=seed)
        items = budget_sample(items, "dev", 600, seed=seed)
    elif name == "jk_case":
        items = [dataclasses.replace(i, split="case") for i in items]
    elif name == "synthetic":
        items = [dataclasses.replace(i, split="smoke") for i in items]
    else:
        raise ValueError(f"Unknown dataset: {name}")
    return items, _build_split_file(name, items, seed)
