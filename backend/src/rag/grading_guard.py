"""Integrity checks around LLM grading: answer fencing, injection signals, citation grounding.

The student answer is untrusted input that is placed inside the grading prompt,
and the LLM's self-reported citations and confidence are untrusted output. This
module keeps both sides honest without extra LLM calls:

* :func:`fence_answer` neutralises text that would close the ``<student_answer>``
  fence the prompt templates wrap the answer in.
* :func:`detect_injection` flags answers that try to instruct the grader.
* :func:`ground_citations` keeps only citations whose text really occurs in a
  retrieved chunk, and takes their source and page from that chunk.
* :func:`apply_integrity_checks` combines the above. Any warning caps the
  confidence at :data:`SUSPECT_CONFIDENCE_CAP`, below every review threshold
  the plugins and CLI use, so a human looks at the grade.
"""

import re
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from langchain_core.documents import Document

SUSPECT_CONFIDENCE_CAP = 0.3

_FENCE_TAG_RE = re.compile(r"<\s*(/?)\s*student_answer\b[^>]*>", re.IGNORECASE)

# High-precision signals only: a match never changes the score, it only routes
# the grade to human review, so a rare false positive is cheap.
_INJECTION_PATTERNS: Tuple[Tuple[str, "re.Pattern[str]"], ...] = (
    ("override_instructions", re.compile(
        r"\b(ignore|disregard|forget|override)\b[^.\n]{0,40}"
        r"\b(instructions?|prompts?|rules|rubric|guidelines)\b", re.IGNORECASE)),
    ("override_instructions", re.compile(
        r"\b(abaikan|lupakan|acuhkan|hiraukan)\b[^.\n]{0,40}"
        r"\b(instruksi|perintah|aturan|prompt|rubrik|pedoman)\b", re.IGNORECASE)),
    ("grade_request", re.compile(
        r"\b(give|award|assign|set|grant)\b[^.\n]{0,30}\b(score|grade|marks?|points)\b"
        r"[^.\n]{0,20}(\b100\b|\bfull\b|\bmaximum\b|\bmax\b|\bperfect\b|\bA\+)", re.IGNORECASE)),
    ("grade_request", re.compile(
        r"\b(give|award|assign|grant)\b[^.\n]{0,20}\b(full|maximum|max|perfect|top)\s+"
        r"(score|grade|marks?|points)\b", re.IGNORECASE)),
    ("grade_request", re.compile(
        r"\b(beri|berikan|kasih|kasihkan)\b[^.\n]{0,30}\b(nilai|skor|poin)\b"
        r"[^.\n]{0,20}\b(100|penuh|maksimal|sempurna|tertinggi)\b", re.IGNORECASE)),
    ("role_markup", re.compile(
        r"(^\s*(system|assistant)\s*:|<\|?\s*(im_start|im_end|system|endoftext)\s*\|?>|\[/?INST\])",
        re.IGNORECASE | re.MULTILINE)),
    ("grading_json", re.compile(r'"\s*(score|confidence|criterion_scores)\s*"\s*:', re.IGNORECASE)),
    ("fence_tag", _FENCE_TAG_RE),
)

_NON_WORD_RE = re.compile(r"[\W_]+", re.UNICODE)
_ELLIPSIS_RE = re.compile(r"\.\.\.+|…")
# Share of a quote's word trigrams that must occur in one chunk when the quote
# is not an exact (normalised) substring: tolerates a word added or dropped.
_TRIGRAM_COVERAGE = 0.6


def fence_answer(essay: Optional[str]) -> str:
    """Return the answer with any ``<student_answer>`` tag made inert (``[student_answer]``)."""
    return _FENCE_TAG_RE.sub(lambda m: f"[{m.group(1)}student_answer]", essay or "")


def detect_injection(text: Optional[str]) -> List[str]:
    """Return the sorted, de-duplicated labels of injection signals found in ``text``."""
    text = text or ""
    return sorted({label for label, pattern in _INJECTION_PATTERNS if pattern.search(text)})


def _tokens(text: str) -> List[str]:
    return _NON_WORD_RE.sub(" ", text.casefold()).split()


def _trigrams(tokens: Sequence[str]) -> set:
    return {tuple(tokens[i:i + 3]) for i in range(len(tokens) - 2)}


def _segment_in(segment: List[str], doc_tokens: List[str], doc_joined: str, doc_trigrams: set) -> bool:
    if f" {' '.join(segment)} " in doc_joined:
        return True
    if len(segment) < 3:
        return False
    grams = _trigrams(segment)
    return len(grams & doc_trigrams) / len(grams) >= _TRIGRAM_COVERAGE


def _grounding_doc(text: str, docs: Sequence[Document]) -> Optional[Document]:
    """Return the first document that contains every ellipsis-separated part of ``text``."""
    segments = [seg for seg in (_tokens(part) for part in _ELLIPSIS_RE.split(text)) if seg]
    if not segments:
        return None
    for doc in docs:
        doc_tokens = _tokens(doc.page_content or "")
        doc_joined = f" {' '.join(doc_tokens)} "
        doc_trigrams = _trigrams(doc_tokens)
        if all(_segment_in(seg, doc_tokens, doc_joined, doc_trigrams) for seg in segments):
            return doc
    return None


def ground_citations(
    citations: Any, docs: Sequence[Document]
) -> Tuple[List[Dict[str, Any]], int]:
    """Keep citations found in ``docs`` (source/page taken from the chunk); return (kept, dropped)."""
    if not isinstance(citations, list):
        return [], 0
    kept: List[Dict[str, Any]] = []
    dropped = 0
    for citation in citations:
        if not isinstance(citation, Mapping):
            dropped += 1
            continue
        doc = _grounding_doc(str(citation.get("text") or ""), docs)
        if doc is None:
            dropped += 1
            continue
        grounded = dict(citation)
        metadata = doc.metadata or {}
        if metadata.get("source"):
            grounded["source"] = metadata["source"]
        # The chunk is the only trustworthy page reference; drop a model-claimed one.
        grounded["page"] = metadata.get("page")
        kept.append(grounded)
    return kept, dropped


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def apply_integrity_checks(
    result: Dict[str, Any], essay: Optional[str], docs: Sequence[Document]
) -> Dict[str, Any]:
    """Ground citations, flag injection attempts and cap confidence when anything is off.

    Adds ``integrity_warnings`` (a list of short machine-readable strings) to
    ``result`` and returns it.
    """
    warnings: List[str] = list(result.get("integrity_warnings") or [])

    signals = detect_injection(essay)
    if signals:
        warnings.append("possible_prompt_injection:" + ",".join(signals))

    kept, dropped = ground_citations(result.get("citations"), docs)
    result["citations"] = kept
    if dropped:
        warnings.append(f"ungrounded_citations_removed:{dropped}")

    if warnings:
        confidence = _as_float(result.get("confidence"))
        if 1.0 < confidence <= 100.0:  # some models answer on a 0-100 scale
            confidence /= 100.0
        result["confidence"] = min(max(confidence, 0.0), SUSPECT_CONFIDENCE_CAP)
    result["integrity_warnings"] = warnings
    return result
