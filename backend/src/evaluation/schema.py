"""Data records, dataset registry and JSONL helpers for the evaluation harness."""

import dataclasses
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, Type, TypeVar

logger = logging.getLogger(__name__)

DATASETS: Dict[str, str] = {
    "engsaf": "private",
    "jk_case": "private",
    "scientsbank": "public",
    "synthetic": "public",
}


def is_private(dataset: str) -> bool:
    return DATASETS[dataset] == "private"


@dataclass(frozen=True)
class EvalItem:
    item_id: str
    dataset: str
    question_id: str
    question: str
    answer: str
    language: str
    gold_label: int
    label_scale: int
    split: str
    role: str = "eval"
    reference_text: Optional[str] = None
    reference_document: Optional[str] = None
    gold_score: Optional[float] = None
    gold_label_raw: Optional[str] = None
    derived_from: Optional[str] = None
    variant: Optional[str] = None


@dataclass(frozen=True)
class EvalResult:
    item_id: str
    config_hash: str
    dataset: str
    question_id: str
    split: str
    gold_label: int
    success: bool
    score: Optional[float]
    confidence: Optional[float]
    error_type: Optional[str] = None
    integrity_warnings: Tuple[str, ...] = ()
    citations_kept: int = 0
    citations_dropped: int = 0
    retrieved_sources: Tuple[str, ...] = ()
    gold_source: Optional[str] = None
    provider: Optional[str] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    tokens_estimated: bool = False
    latency_s: float = 0.0
    repeat: int = 0
    variant: Optional[str] = None
    derived_from: Optional[str] = None
    gold_score: Optional[float] = None
    gold_label_raw: Optional[str] = None
    feedback: str = ""


@dataclass
class RunManifest:
    git_sha: Optional[str] = None
    git_dirty: Optional[bool] = None
    backend_version: Optional[str] = None
    prompt_template_sha256: Optional[str] = None
    config_file: Optional[str] = None
    config_hash: Optional[str] = None
    model: Optional[str] = None
    provider: Optional[str] = None
    temperature: Optional[float] = None
    seed: Optional[int] = None
    response_format: Optional[str] = None
    embedding_model: Optional[str] = None
    dataset_snapshots: Dict[str, Any] = field(default_factory=dict)
    split_hashes: Dict[str, Any] = field(default_factory=dict)
    item_counts: Dict[str, Any] = field(default_factory=dict)
    thresholds: Dict[str, Any] = field(default_factory=dict)
    thresholds_source: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    estimated_cost_usd: Optional[float] = None
    failures: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


_T = TypeVar("_T")
_TUPLE_FIELDS = {"integrity_warnings", "retrieved_sources"}


def _dump(record) -> str:
    return json.dumps(dataclasses.asdict(record), ensure_ascii=False)


def write_jsonl(path: Path, records: Iterable[Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(_dump(record) + "\n")


def append_jsonl(path: Path, record: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(_dump(record) + "\n")
        f.flush()
        os.fsync(f.fileno())


def _read(path: Path, cls: Type[_T]) -> List[_T]:
    out: List[_T] = []
    with open(Path(path), "r", encoding="utf-8") as f:
        lines = f.read().split("\n")
    # A trailing element without newline termination may be a partial write.
    for idx, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            if idx == len(lines) - 1:
                logger.warning("Ignoring partial trailing line in %s", path)
                continue
            raise
        for key in _TUPLE_FIELDS:
            if key in data and isinstance(data[key], list):
                data[key] = tuple(data[key])
        out.append(cls(**data))
    return out


def read_items(path: Path) -> List[EvalItem]:
    return _read(path, EvalItem)


def read_results(path: Path) -> List[EvalResult]:
    return _read(path, EvalResult)
