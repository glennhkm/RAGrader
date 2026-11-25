"""In-process grader: the product EssayGrader with an isolated vector store.

``context_mode`` selects the retrieval context:

- ``"rag"``: the product retriever over the ingested per-question materials;
- ``"oracle"``: an upper bound, where the only context is the item's gold document;
- ``"no_context"``: a lower bound, where the only context is a fixed placeholder.

Thread safety: the runner calls ``grade`` from several threads at once, while the
grader, its pipeline and its LLM wrapper are shared. ``RAGPipeline.grade_essay``
calls the retriever and the LLM synchronously in the calling thread, so the
per-call state is kept in a ``threading.local``. ``grade`` stores the gold
document for its own thread before grading, and ``_FixedRetriever`` reads it back.
The LLM wrapper's ``generate`` is wrapped once, so that each thread snapshots
``last_usage`` and the serving provider right after its own completion. No lock
serialises grading. The snapshot is taken after the wrapper returns, so a
completion that finishes on another thread in that short window could still be
attributed to the wrong call. Only token and provider bookkeeping is affected,
never scores.
"""

import copy
import re
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from langchain_core.documents import Document

from src.api.request_utils import normalize_grade
from src.evaluation.graders.base import (
    GradeRequest,
    RawGrade,
    TransientGraderError,
    parse_dropped_count,
)
from src.evaluation.graders.pacing import RateLimiter
from src.evaluation.materials import MaterialDoc, gold_source, write_materials
from src.evaluation.schema import EvalItem
from src.grading.grader import EssayGrader
from src.utils.config import Settings, get_settings
from src.vectorstore.embeddings import EmbeddingMismatchError

CONTEXT_MODES = ("rag", "oracle", "no_context")
NO_CONTEXT_TEXT = "(No course materials are available for this question.)"
_TRANSIENT = re.compile(
    # 413: gateways also return it when their own upstream quota is short.
    r"\b(413|429|500|502|503|504)\b|rate.?limit|too many requests|timed? ?out|timeout"
    r"|connection (error|reset|refused|aborted)|upstream_error",
    re.IGNORECASE,
)


def _is_transient(text: str) -> bool:
    return bool(_TRANSIENT.search(text or ""))


class _FixedRetriever:
    """Returns one fixed document per call, replacing the product retriever."""

    def __init__(self, local: threading.local, fixed: Optional[Document] = None):
        self._local = local
        self._fixed = fixed

    def retrieve(self, query, course_id=None, metadata_filter=None) -> List[Document]:
        if self._fixed is not None:
            return [self._fixed]
        doc = getattr(self._local, "document", None)
        if doc is None:
            raise RuntimeError("no oracle document set for this thread")
        return [doc]


class InProcessGrader:
    name = "inprocess"

    def __init__(
        self,
        model: str,
        provider: str = "openrouter",
        temperature: Optional[float] = None,
        context_mode: str = "rag",
        settings: Optional[Settings] = None,
        grader_factory: Callable[..., EssayGrader] = EssayGrader,
        requests_per_minute: Optional[int] = None,
    ):
        if context_mode not in CONTEXT_MODES:
            raise ValueError(f"unknown context_mode: {context_mode}")
        self.model = model
        self.provider = provider
        self.temperature = temperature
        self.context_mode = context_mode
        self.settings = settings or get_settings()
        self._factory = grader_factory
        self._limiter = RateLimiter(requests_per_minute) if requests_per_minute else None
        self._config: Optional[Dict[str, Any]] = None
        self._grader: Any = None
        self._texts: Dict[str, Dict[str, str]] = {}
        self._local = threading.local()

    # -- setup ---------------------------------------------------------------

    def prepare_namespace(
        self, namespace: str, docs: Sequence[MaterialDoc], workdir: Path
    ) -> None:
        workdir = Path(workdir)
        if self.context_mode == "oracle":
            if any(d.path or not d.text for d in docs):
                raise ValueError("oracle mode needs text references")
        if self._grader is None:
            self._build(workdir)
        paths = write_materials(docs, workdir / "materials" / _safe(namespace))
        result = self._grader.ingest_course_materials(paths, course_id=_course_id(namespace))
        if isinstance(result, dict) and result.get("success") is False:
            raise RuntimeError(f"ingestion failed for namespace {namespace}: "
                               f"{result.get('message') or result.get('error')}")
        self._texts[namespace] = {d.source: d.text for d in docs}

    def _build(self, workdir: Path) -> None:
        config = copy.deepcopy(dict(self.settings.raw))
        vs = config.setdefault("vectorstore", {})
        vs["persist_directory"] = str(workdir / "chroma")
        vs["client_mode"] = "persistent"
        vs["collection_name"] = "eval"
        if self.temperature is not None:
            config.setdefault("llm", {})["temperature"] = self.temperature
        self._config = config
        grader = self._factory(config, provider=self.provider, model_name=self.model,
                               settings=self.settings)
        self._grader = grader
        pipeline = grader.rag_pipeline
        if self._limiter is not None:
            self._pace(pipeline.llm,
                       pipeline.vectorstore.embedding_generator.get_embeddings_instance())
        self._wrap_llm(pipeline.llm)
        if self.context_mode == "oracle":
            pipeline.retriever = _FixedRetriever(self._local)
        elif self.context_mode == "no_context":
            pipeline.retriever = _FixedRetriever(self._local, Document(
                page_content=NO_CONTEXT_TEXT, metadata={"source": "none", "page": "N/A"}))

    def _pace(self, llm: Any, embeddings: Any) -> None:
        """One provider request slot per LLM call and per embedding call."""
        nested = threading.local()
        for obj, name in ((llm, "generate"), (embeddings, "embed_query"),
                          (embeddings, "embed_documents")):
            original = getattr(obj, name)

            def paced(arg, _original=original):
                if getattr(nested, "active", False):  # embed_query calls embed_documents
                    return _original(arg)
                self._limiter.wait()
                nested.active = True
                try:
                    return _original(arg)
                finally:
                    nested.active = False

            setattr(obj, name, paced)

    def _wrap_llm(self, llm: Any) -> None:
        original = llm.generate
        local = self._local

        def generate(prompt):
            out = original(prompt)
            local.call = {
                "prompt": prompt,
                "raw": out,
                "usage": getattr(llm, "last_usage", None),
                "served": getattr(llm, "last_served_provider", None),
                "last": getattr(llm, "_last_provider", None),
            }
            return out

        llm.generate = generate

    # -- grading -------------------------------------------------------------

    def grade(self, namespace: str, item: EvalItem, request: GradeRequest) -> RawGrade:
        if self._grader is None or namespace not in self._texts:
            raise RuntimeError(f"namespace not prepared: {namespace}")
        self._local.call = None
        if self.context_mode == "oracle":
            source = gold_source(item)
            text = self._texts[namespace].get(source)
            if not text:
                raise ValueError("oracle mode needs text references")
            self._local.document = Document(
                page_content=text, metadata={"source": source, "page": "N/A"})

        rubric = request.rubric or {"criteria": {}}
        try:
            result = self._grader.grade_essay(
                request.question, request.answer, rubric, _course_id(namespace),
                language=request.language,
            )
        except EmbeddingMismatchError:
            raise
        except Exception as exc:  # noqa: BLE001 - mapped to a failed grade
            if _is_transient(str(exc)):
                raise TransientGraderError(str(exc)) from exc
            return self._failed("provider_error", {"feedback": str(exc)})

        error = result.get("error")
        error_text = "" if error is None else str(error)
        if "Failed to parse" in error_text:
            return self._failed("parse_failure", result)
        if result.get("success") is False and "No relevant materials" in error_text:
            return self._failed("no_materials", result)
        if error is not None and _is_transient(error_text):
            raise TransientGraderError(error_text)
        if error is not None or result.get("success") is False:
            return self._failed("provider_error", result)

        score, _, confidence = normalize_grade(result, request.rubric, request.maximum_grade)
        return self._raw(result, success=True, score=score, confidence=confidence,
                         error_type=None)

    def _failed(self, error_type: str, result: Dict[str, Any]) -> RawGrade:
        return self._raw(result, success=False, score=None, confidence=None,
                         error_type=error_type)

    def _raw(self, result: Dict[str, Any], success: bool, score: Optional[float],
             confidence: Optional[float], error_type: Optional[str]) -> RawGrade:
        warnings = [str(w) for w in (result.get("integrity_warnings") or [])]
        citations = result.get("citations") or []
        sources = [str(d.get("source")) for d in (result.get("retrieved_documents") or [])
                   if isinstance(d, dict)]
        prompt_tokens, completion_tokens, estimated = self._tokens(result)
        return RawGrade(
            success=success, score=score, confidence=confidence,
            feedback=str(result.get("feedback") or ""), error_type=error_type,
            integrity_warnings=warnings, citations_kept=len(citations),
            citations_dropped=parse_dropped_count(warnings), retrieved_sources=sources,
            provider=self._served_provider(), prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens, tokens_estimated=estimated,
        )

    def _tokens(self, result: Dict[str, Any]):
        call = getattr(self._local, "call", None)
        if call is None:
            return 0, 0, False  # no completion was requested
        usage = call.get("usage") or {}
        prompt_tokens = usage.get("prompt_tokens")
        completion_tokens = usage.get("completion_tokens")
        if prompt_tokens is not None and completion_tokens is not None:
            return int(prompt_tokens), int(completion_tokens), False
        prompt = result.get("prompt_used") or call.get("prompt") or ""
        raw = call.get("raw") or ""
        return len(str(prompt)) // 4, len(str(raw)) // 4, True

    def _served_provider(self) -> str:
        call = getattr(self._local, "call", None) or {}
        return call.get("served") or call.get("last") or self.provider

    def close(self) -> None:
        self._grader = None
        self._texts.clear()


def _course_id(namespace: str) -> str:
    return f"eval:{namespace}"


def _safe(namespace: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", namespace) or "_"
