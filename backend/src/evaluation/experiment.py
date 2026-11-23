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
    # First N eval items by item_id per (dataset, split); None means no limit.
    max_items_per_split: Optional[int] = None


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
    if values["overrides"]:
        # Nothing applies them yet: accepting them would record settings that were not used.
        raise ValueError("overrides are not supported until Cycle 4b; remove the "
                         "'overrides' entries from the experiment file")

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
    limit = values.get("max_items_per_split")
    if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int)
                              or limit < 1):
        raise ValueError("max_items_per_split must be a positive integer")
    return ExperimentConfig(**values)


_PLAIN = (str, int, float, bool, type(None))


def _plain(value: Any) -> Any:
    return value if isinstance(value, _PLAIN) else None


def effective_settings(cfg: ExperimentConfig, settings: Any) -> Dict[str, Any]:
    """The grading settings a run actually uses (no secrets: keys and tokens are never read).

    ``settings`` is ``src.utils.config.get_settings()`` (only that module reads the
    environment). The stub grader uses none; the http grader's settings belong to the remote
    server and cannot be observed from here.
    """
    if cfg.grader == "stub":
        return {"grader": "stub"}
    if cfg.grader == "http":
        return {"grader": "http",
                "note": "grading settings belong to the remote server; not observable here"}
    raw = getattr(settings, "raw", None) or {}
    chunking = raw.get("document_processing") or {}
    out = {
        "grader": "inprocess",
        "context_mode": cfg.context_mode,
        "llm_provider": cfg.provider,
        "llm_model": cfg.model if cfg.model is not None else settings.llm.model,
        "llm_temperature": (cfg.temperature if cfg.temperature is not None
                            else settings.llm.temperature),
        "llm_max_new_tokens": settings.llm.max_new_tokens,
        "embedding_provider": settings.embeddings.provider,
        "embedding_model": settings.embeddings.model,
        "retrieval_top_k": settings.reranker.top_k,
        "reranking_enabled": settings.reranker.enabled,
        "reranker_type": settings.reranker.type,
        "reranker_model": settings.reranker.model,
        "rerank_top_k": settings.reranker.rerank_top_k,
        "chunk_size": chunking.get("chunk_size"),
        "chunk_overlap": chunking.get("chunk_overlap"),
    }
    return {k: _plain(v) for k, v in out.items()}


def prompt_template_hash() -> str:
    from src.rag.prompts import PROMPT_TEMPLATES

    blob = json.dumps(PROMPT_TEMPLATES, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def config_hash(cfg: ExperimentConfig, snapshot_hashes: Dict[str, str]) -> str:
    """16-hex hash of everything that determines results.

    ``concurrency`` and ``max_cost_usd`` are excluded: they do not change results.
    ``max_items_per_split`` is included only when set, so configurations without a limit
    keep the hash they had before the field existed.
    """
    body = dataclasses.asdict(cfg)
    body.pop("concurrency")
    body.pop("max_cost_usd")
    if body.get("max_items_per_split") is None:
        body.pop("max_items_per_split", None)
    payload = {"config": body, "prompt": prompt_template_hash(), "data": snapshot_hashes}
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]
