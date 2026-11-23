"""Grader protocol and shared request/response records."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Protocol, Sequence

from src.evaluation.materials import MaterialDoc
from src.evaluation.schema import EvalItem


@dataclass(frozen=True)
class GradeRequest:
    question: str
    answer: str
    language: str
    rubric: dict = field(default_factory=dict)
    maximum_grade: float = 100.0


@dataclass
class RawGrade:
    success: bool
    score: Optional[float]
    confidence: Optional[float]
    feedback: str
    error_type: Optional[str]
    integrity_warnings: List[str]
    citations_kept: int
    citations_dropped: int
    retrieved_sources: List[str]
    provider: Optional[str]
    prompt_tokens: int
    completion_tokens: int
    tokens_estimated: bool


class TransientGraderError(Exception):
    """Retryable failure (429, 5xx, timeout); the runner catches it."""

    def __init__(self, message: str = "", retry_after: Optional[float] = None):
        super().__init__(message)
        self.retry_after = retry_after


class Grader(Protocol):
    name: str

    def prepare_namespace(
        self, namespace: str, docs: Sequence[MaterialDoc], workdir: Path
    ) -> None: ...

    def grade(self, namespace: str, item: EvalItem, request: GradeRequest) -> RawGrade: ...

    def close(self) -> None: ...


_DROPPED = re.compile(r"ungrounded_citations_removed:(\d+)")


def parse_dropped_count(warnings: Sequence[str]) -> int:
    total = 0
    for w in warnings:
        m = _DROPPED.search(w)
        if m:
            total += int(m.group(1))
    return total
