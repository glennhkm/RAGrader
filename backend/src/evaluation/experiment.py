"""Experiment configuration (YAML), its loader and the result-defining config hash."""

import dataclasses
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .schema import DATASETS

GRADERS = {"stub", "inprocess", "http"}
CONTEXT_MODES = {"rag", "oracle", "no_context"}
VARIANT_SETS = {None, "consistency", "injection"}
ALLOWED_SPLITS: Dict[str, set] = {
    "engsaf": {"dev", "test"},
    "scientsbank": {"dev", "test_uq", "test_ua"},
    "jk_case": {"case"},
    "synthetic": {"smoke"},
}
REQUIRED = ("name", "phase", "grader", "provider", "datasets")
DEFAULTS: Dict[str, Any] = {
    "model": None,
    "context_mode": "rag",
    "temperature": None,
    "repeats": 1,
    "variant_set": None,
    "price_in_per_mtok": 0.0,
    "price_out_per_mtok": 0.0,
    "concurrency": 4,
    "max_cost_usd": 5.0,
}


@dataclass(frozen=True)
class ExperimentConfig:
    name: str
    phase: str
    grader: str
    model: Optional[str]
    provider: str
    context_mode: str
    temperature: Optional[float]
    datasets: Dict[str, List[str]]
    repeats: int
    variant_set: Optional[str]
    price_in_per_mtok: float
    price_out_per_mtok: float
    concurrency: int
    max_cost_usd: float
    overrides: Dict[str, Any]


def load_experiment(path: Path) -> ExperimentConfig:
    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    if not isinstance(raw, dict):
        raise ValueError("experiment file must be a mapping")
    known = {f.name for f in dataclasses.fields(ExperimentConfig)}
    for k in raw:
        if k not in known:
            raise ValueError(f"unknown key: {k}")
    for k in REQUIRED:
        if k not in raw:
            raise ValueError(f"missing key: {k}")
    values = {**DEFAULTS, "overrides": {}, **raw}
    if values["overrides"] is None:
        values["overrides"] = {}

    if values["grader"] not in GRADERS:
        raise ValueError(f"invalid grader: {values['grader']}")
    if values["context_mode"] not in CONTEXT_MODES:
        raise ValueError(f"invalid context_mode: {values['context_mode']}")
    if values["variant_set"] not in VARIANT_SETS:
        raise ValueError(f"invalid variant_set: {values['variant_set']}")
    datasets = values["datasets"]
    if not isinstance(datasets, dict) or not datasets:
        raise ValueError("datasets must be a non-empty mapping")
    for ds, splits in datasets.items():
        if ds not in DATASETS:
            raise ValueError(f"unknown dataset: {ds}")
        if not isinstance(splits, list) or not splits:
            raise ValueError(f"splits for {ds} must be a non-empty list")
        for s in splits:
            if s not in ALLOWED_SPLITS[ds]:
                raise ValueError(f"invalid split for {ds}: {s}")
    values["datasets"] = {ds: list(s) for ds, s in datasets.items()}
    return ExperimentConfig(**values)


def prompt_template_hash() -> str:
    from src.rag.prompts import PROMPT_TEMPLATES

    blob = json.dumps(PROMPT_TEMPLATES, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def config_hash(cfg: ExperimentConfig, snapshot_hashes: Dict[str, str]) -> str:
    """16-hex hash of everything that determines results.

    ``concurrency`` and ``max_cost_usd`` are excluded: they do not change results.
    """
    body = dataclasses.asdict(cfg)
    body.pop("concurrency")
    body.pop("max_cost_usd")
    payload = {"config": body, "prompt": prompt_template_hash(), "data": snapshot_hashes}
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]
