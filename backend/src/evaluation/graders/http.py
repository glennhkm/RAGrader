"""HTTP grader: grades through a running RAGrader ``/v1`` API."""

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

import httpx

from src.cli import ApiError, RagApiClient
from src.evaluation.graders.base import (
    GradeRequest,
    RawGrade,
    TransientGraderError,
    parse_dropped_count,
)
from src.evaluation.materials import MaterialDoc, write_materials
from src.evaluation.schema import EvalItem


def http_namespace(config_hash: str, dataset: str) -> str:
    """Namespace that never contains the dataset name verbatim."""
    tag = hashlib.sha256(dataset.encode("utf-8")).hexdigest()[:6]
    return f"eval-{config_hash[:12]}-{tag}"


def _retry_after(response: httpx.Response) -> Optional[float]:
    try:
        return float(response.headers.get("Retry-After"))
    except (TypeError, ValueError):
        return None


class HttpGrader:
    name = "http"

    def __init__(self, api_url: str, token: str, http_client: Optional[httpx.Client] = None,
                 timeout: float = 300.0):
        self._http = http_client or httpx.Client(timeout=timeout)
        self._client = RagApiClient(api_url, token, timeout=timeout, http_client=self._http)
        self._base = api_url.rstrip("/")
        self._headers = dict(self._client._headers)

    # -- setup ---------------------------------------------------------------

    def prepare_namespace(
        self, namespace: str, docs: Sequence[MaterialDoc], workdir: Path
    ) -> None:
        listing = self._client._request("GET", f"/v1/namespaces/{namespace}/materials")
        present = set(listing.get("uploaded_files") or [])
        paths = write_materials(docs, Path(workdir) / "materials" / "http")
        for path in paths:
            if path.name in present:
                continue
            self._client.upload(namespace, path)

    # -- grading -------------------------------------------------------------

    def _post(self, namespace: str, payload: Dict[str, Any]) -> httpx.Response:
        headers = dict(self._headers)
        headers["X-Request-ID"] = uuid.uuid4().hex
        try:
            return self._http.post(
                f"{self._base}/v1/namespaces/{namespace}/grade", json=payload, headers=headers)
        except httpx.HTTPError as exc:  # timeouts and connection failures
            raise TransientGraderError(f"{type(exc).__name__}: {exc}") from exc

    def grade(self, namespace: str, item: EvalItem, request: GradeRequest) -> RawGrade:
        payload = {
            "question": request.question,
            "essay": request.answer,
            "rubric": request.rubric or {},
            "maximum_grade": request.maximum_grade,
            "language": request.language,
        }
        response = self._post(namespace, payload)
        status = response.status_code
        if status == 429 or status >= 500:
            raise TransientGraderError(f"HTTP {status}", retry_after=_retry_after(response))
        prompt_tokens = len(json.dumps(payload)) // 4
        if status >= 400:
            return self._failed("http_error", {}, prompt_tokens)
        try:
            body = response.json()
        except ValueError:
            return self._failed("http_error", {}, prompt_tokens)

        error = body.get("error")
        error_text = "" if error is None else str(error)
        if "Failed to parse" in error_text:
            return self._failed("parse_failure", body, prompt_tokens)
        if body.get("success") is False:
            kind = "no_materials" if "No relevant materials" in error_text else "provider_error"
            return self._failed(kind, body, prompt_tokens)
        return self._raw(body, True, body.get("score"), body.get("confidence"), None,
                         prompt_tokens)

    def _failed(self, error_type: str, body: Dict[str, Any], prompt_tokens: int) -> RawGrade:
        return self._raw(body, False, None, None, error_type, prompt_tokens)

    @staticmethod
    def _raw(body: Dict[str, Any], success: bool, score: Optional[float],
             confidence: Optional[float], error_type: Optional[str],
             prompt_tokens: int) -> RawGrade:
        warnings = [str(w) for w in (body.get("integrity_warnings") or [])]
        sources = [str(d.get("source")) for d in (body.get("retrieved_documents") or [])
                   if isinstance(d, dict)]
        feedback = str(body.get("feedback") or "")
        return RawGrade(
            success=success, score=score, confidence=confidence, feedback=feedback,
            error_type=error_type, integrity_warnings=warnings,
            citations_kept=len(body.get("citations") or []),
            citations_dropped=parse_dropped_count(warnings), retrieved_sources=sources,
            provider=None, prompt_tokens=prompt_tokens,
            completion_tokens=len(feedback) // 4, tokens_estimated=True,
        )

    def close(self) -> None:
        self._http.close()
