"""Deterministic offline grader used for harness tests and dry runs."""

import re
from pathlib import Path
from typing import Dict, List, Sequence, Set

from src.evaluation.graders.base import GradeRequest, RawGrade
from src.evaluation.materials import MaterialDoc, gold_source
from src.evaluation.schema import EvalItem

_TOKEN = re.compile(r"[a-z0-9]+")
_INJECTION = "ignore previous instructions"
_MAX_SOURCES = 5


def tokens(text: str) -> Set[str]:
    return set(_TOKEN.findall(text.lower()))


def jaccard(a: Set[str], b: Set[str]) -> float:
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


class StubGrader:
    name = "stub"

    def __init__(self) -> None:
        self._sources: Dict[str, List[str]] = {}

    def prepare_namespace(
        self, namespace: str, docs: Sequence[MaterialDoc], workdir: Path
    ) -> None:
        self._sources[namespace] = sorted(d.source for d in docs)

    def grade(self, namespace: str, item: EvalItem, request: GradeRequest) -> RawGrade:
        if namespace not in self._sources:
            raise RuntimeError(f"namespace not prepared: {namespace}")
        gold = gold_source(item)
        rest = [s for s in self._sources[namespace] if s != gold]
        retrieved = ([gold] + rest)[:_MAX_SOURCES]
        overlap = jaccard(tokens(request.answer), tokens(item.reference_text or ""))
        score = round(100 * overlap ** 0.5, 2)
        confidence = round(0.5 + overlap / 2, 4)
        warnings: List[str] = []
        if _INJECTION in request.answer.casefold():
            warnings.append("possible_prompt_injection:override_instructions")
            confidence = min(confidence, 0.3)
        return RawGrade(
            success=True, score=score, confidence=confidence, feedback="stub",
            error_type=None, integrity_warnings=warnings, citations_kept=1,
            citations_dropped=0, retrieved_sources=retrieved, provider="stub",
            prompt_tokens=2000, completion_tokens=300, tokens_estimated=False,
        )

    def close(self) -> None:
        pass
