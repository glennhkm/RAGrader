"""Rerankers for retrieved course-material chunks.

``create_reranker(settings)`` selects one of:

- ``bm25``: local lexical BM25 (rank-bm25), no network, no GPU
- ``local_cross_encoder``: in-process fastembed ``TextCrossEncoder`` or
  sentence-transformers ``CrossEncoder`` (optional extras)
- ``http_rerank``: standard ``/rerank`` APIs (Cohere/Jina/vLLM/Infinity/
  SiliconFlow style, or Hugging Face TEI style)
- ``llm_rerank``: any OpenAI-compatible chat endpoint scoring passages as JSON
- ``pinecone``: Pinecone Inference (``bge-reranker-v2-m3``), legacy ``bge``

Every reranker shares one failure policy: if scoring fails, the original
vector-search order is kept, so reranking can never fail a grading request.
"""

import json
import re
from threading import Lock
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from langchain_core.documents import Document
from loguru import logger

from ..utils.config import RerankerSettings, get_settings

try:
    from pinecone import Pinecone
    PINECONE_AVAILABLE = True
except ImportError:
    Pinecone = None
    PINECONE_AVAILABLE = False

MAX_PASSAGE_CHARS = 4000


class BaseReranker:
    """Common ranking/fallback logic; subclasses implement ``_score``."""

    kind = "base"
    model_name = ""

    def _score(self, query: str, documents: List[Document]) -> List[Tuple[int, float]]:
        """Return (document index, relevance score) pairs; higher is more relevant."""
        raise NotImplementedError

    def rerank(self, query: str, documents: List[Document], top_k: int = 3) -> List[Tuple[Document, float]]:
        """Rank documents by relevance, keeping vector order on any failure."""
        if not documents:
            return []
        top_k = max(1, min(int(top_k), len(documents)))
        try:
            scored = self._score(query, documents)
        except Exception as exc:
            logger.warning(f"{self.kind} reranker failed ({exc}); keeping vector-search order")
            return [(doc, 0.0) for doc in documents[:top_k]]

        ranked: List[Tuple[Document, float]] = []
        seen = set()
        for index, score in sorted(scored, key=lambda pair: pair[1], reverse=True):
            if isinstance(index, bool) or not isinstance(index, int):
                continue
            if 0 <= index < len(documents) and index not in seen:
                seen.add(index)
                ranked.append((documents[index], float(score)))
        if not ranked:
            logger.warning(f"{self.kind} reranker returned no usable results; keeping vector-search order")
            return [(doc, 0.0) for doc in documents[:top_k]]
        # Remote rerankers may return fewer items than requested: keep the
        # remaining documents in vector order so grading still sees evidence.
        for index, doc in enumerate(documents):
            if len(ranked) >= top_k:
                break
            if index not in seen:
                ranked.append((doc, 0.0))
        logger.info(f"{self.kind} reranked {len(documents)} documents to top {min(top_k, len(ranked))}")
        return ranked[:top_k]

    def rerank_documents(self, query: str, documents: List[Document], top_k: int = 3) -> List[Document]:
        """Rerank and return only the documents."""
        return [doc for doc, _ in self.rerank(query, documents, top_k)]

    def get_model_info(self) -> Dict[str, Any]:
        return {"type": self.kind, "model_name": self.model_name}


def _passages(documents: Sequence[Document]) -> List[str]:
    return [doc.page_content[:MAX_PASSAGE_CHARS] for doc in documents]


class BM25Reranker(BaseReranker):
    """Lexical BM25 reranker (local, no network)."""

    kind = "bm25"
    model_name = "BM25Okapi"

    def __init__(self, **_kwargs):
        from rank_bm25 import BM25Okapi
        self.BM25Okapi = BM25Okapi

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        return re.findall(r"\w+", text.lower())

    def _score(self, query, documents):
        corpus = [self._tokenize(doc.page_content) or [""] for doc in documents]
        scores = self.BM25Okapi(corpus).get_scores(self._tokenize(query))
        return [(i, float(score)) for i, score in enumerate(scores)]

    def get_model_info(self) -> Dict[str, Any]:
        return {
            "type": self.kind,
            "model_name": self.model_name,
            "mode": "local",
            "provider": "rank_bm25",
            "description": "Lexical matching using BM25 algorithm",
        }


class PineconeReranker(BaseReranker):
    """Cross-encoder reranking via Pinecone Inference (e.g. bge-reranker-v2-m3)."""

    kind = "pinecone"
    RERANKER_MODELS = {
        "bge-reranker-v2-m3": {
            "name": "BGE Reranker v2 M3",
            "description": "High-performance multilingual reranker by BAAI",
            "max_tokens": 1024,
            "provider": "pinecone"
        },
        "cohere-rerank-3.5": {
            "name": "Cohere Rerank 3.5",
            "description": "Cohere's latest reranking model",
            "max_tokens": 4096,
            "provider": "pinecone"
        }
    }

    def __init__(self, model_name: str = "bge-reranker-v2-m3", api_key: str = None,
                 truncate: str = "END", client: Any = None, **_kwargs):
        if client is None:
            if not PINECONE_AVAILABLE:
                raise ImportError(
                    "RERANKER_TYPE=pinecone requires the pinecone package: "
                    "pip install -r requirements-optional.txt"
                )
            api_key = api_key or get_settings().reranker.pinecone_api_key
            if not api_key:
                raise ValueError("PINECONE_API_KEY is required for RERANKER_TYPE=pinecone (bge)")
            client = Pinecone(api_key=api_key)
        self.model_name = model_name
        self.truncate = truncate
        self.client = client
        logger.info(f"Pinecone reranker initialized: {model_name}")

    def _score(self, query, documents):
        result = self.client.inference.rerank(
            model=self.model_name,
            query=query,
            documents=[{"id": f"doc_{i}", "text": text} for i, text in enumerate(_passages(documents))],
            top_n=len(documents),
            return_documents=False,
            parameters={"truncate": self.truncate},
        )
        return [(item.index, float(item.score)) for item in result.data]

    def compute_scores(self, query: str, documents: List[str]) -> List[float]:
        """Relevance scores in original order (0.0 for missing, 0.5 on failure)."""
        docs = [Document(page_content=text) for text in documents]
        try:
            scores = [0.0] * len(docs)
            for index, score in self._score(query, docs):
                if 0 <= index < len(scores):
                    scores[index] = score
            return scores
        except Exception as exc:
            logger.error(f"Score computation failed: {exc}")
            return [0.5] * len(docs)

    def get_model_info(self) -> Dict[str, Any]:
        info = self.RERANKER_MODELS.get(self.model_name, {})
        return {
            "type": self.kind,
            "model_name": self.model_name,
            "mode": "cloud",
            "provider": "pinecone",
            "name": info.get("name", self.model_name),
            "description": info.get("description", ""),
            "max_tokens": info.get("max_tokens", 1024),
            "truncate": self.truncate,
        }


# Backward-compatible name used by earlier releases.
BGEReranker = PineconeReranker


class HTTPReranker(BaseReranker):
    """Standard ``/rerank`` HTTP APIs.

    ``api_style="cohere"`` (Cohere, Jina, vLLM, Infinity, SiliconFlow):
    ``{"model", "query", "documents", "top_n"}`` -> ``{"results": [{"index", "relevance_score"}]}``.
    ``api_style="tei"`` (Hugging Face Text Embeddings Inference):
    ``{"query", "texts"}`` -> ``[{"index", "score"}]``.
    """

    kind = "http_rerank"

    def __init__(self, base_url: str, model: str = "", api_key: str = "", api_style: str = "cohere",
                 timeout: float = 30.0, http_client: Any = None):
        if not base_url:
            raise ValueError("RERANKER_TYPE=http_rerank requires RERANKER_BASE_URL")
        if api_style not in {"cohere", "tei"}:
            raise ValueError("RERANKER_API_STYLE must be 'cohere' or 'tei'")
        base = base_url.rstrip("/")
        self.url = base if base.endswith("/rerank") else f"{base}/rerank"
        self.model_name = model
        self.api_style = api_style
        self._headers = {"Content-Type": "application/json"}
        if api_key:
            self._headers["Authorization"] = f"Bearer {api_key}"
        if http_client is None:
            import httpx
            http_client = httpx.Client(timeout=timeout)
        self._http = http_client

    def _score(self, query, documents):
        passages = _passages(documents)
        if self.api_style == "tei":
            payload: Dict[str, Any] = {"query": query, "texts": passages, "truncate": True}
        else:
            payload = {"query": query, "documents": passages, "top_n": len(passages)}
            if self.model_name:
                payload["model"] = self.model_name
        response = self._http.post(self.url, json=payload, headers=self._headers)
        response.raise_for_status()
        body = response.json()
        items = body.get("results", body.get("data", [])) if isinstance(body, dict) else body
        scored = []
        for item in items or []:
            if not isinstance(item, dict):
                continue
            score = item.get("relevance_score", item.get("score"))
            index = item.get("index")
            if isinstance(index, int) and isinstance(score, (int, float)):
                scored.append((index, float(score)))
        return scored

    def get_model_info(self) -> Dict[str, Any]:
        return {"type": self.kind, "model_name": self.model_name, "url": self.url, "api_style": self.api_style}


class LLMReranker(BaseReranker):
    """Rerank with any OpenAI-compatible chat model returning JSON scores."""

    kind = "llm_rerank"
    PROMPT = (
        "You rank course-material passages by how useful they are as evidence for grading "
        "the student answer below. Score each passage from 0.0 (irrelevant) to 1.0 (essential).\n\n"
        "QUERY:\n{query}\n\nPASSAGES:\n{passages}\n\n"
        'Reply with JSON only: {{"ranking": [{{"index": <passage number>, "score": <0.0-1.0>}}, ...]}}'
    )

    def __init__(self, base_url: str, model: str, api_key: str = "", timeout: float = 30.0,
                 client_factory: Optional[Callable[..., Any]] = None):
        if not base_url or not model:
            raise ValueError("RERANKER_TYPE=llm_rerank requires RERANKER_BASE_URL and RERANKER_MODEL")
        if client_factory is None:
            from openai import OpenAI
            client_factory = OpenAI
        self.model_name = model
        self._client = client_factory(base_url=base_url, api_key=api_key or "not-needed",
                                      timeout=timeout, max_retries=0)

    def _score(self, query, documents):
        passages = "\n\n".join(f"[{i}] {text[:1500]}" for i, text in enumerate(_passages(documents)))
        completion = self._client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "user", "content": self.PROMPT.format(query=query, passages=passages)}],
            temperature=0.0,
            max_tokens=512,
        )
        content = completion.choices[0].message.content or ""
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if not match:
            raise ValueError("LLM reranker returned no JSON object")
        ranking = json.loads(match.group(0)).get("ranking", [])
        scored = []
        for item in ranking:
            if not isinstance(item, dict):
                continue
            try:
                scored.append((int(item["index"]), float(item["score"])))
            except (KeyError, TypeError, ValueError):
                continue
        return scored


_CROSS_ENCODER_CACHE: Dict[Tuple[str, str, str], Any] = {}
_CROSS_ENCODER_LOCK = Lock()


class LocalCrossEncoderReranker(BaseReranker):
    """In-process neural reranking (fastembed TextCrossEncoder or sentence-transformers CrossEncoder)."""

    kind = "local_cross_encoder"

    def __init__(self, model: str, device: str = "cpu", backend: Optional[str] = None):
        self.model_name = model
        self.device = device
        self.backend, self._model = self._load(model, device, backend)

    @staticmethod
    def _load(model: str, device: str, backend: Optional[str]):
        backends = [backend] if backend else ["fastembed", "sentence_transformers"]
        errors = []
        model_rejected = False
        for name in backends:
            key = (name, model, device)
            with _CROSS_ENCODER_LOCK:
                if key in _CROSS_ENCODER_CACHE:
                    return name, _CROSS_ENCODER_CACHE[key]
                try:
                    if name == "fastembed":
                        from fastembed.rerank.cross_encoder import TextCrossEncoder
                        kwargs = {"cuda": True} if device == "cuda" else {}
                        if device == "mps":
                            logger.warning("fastembed has no MPS support; cross-encoder runs on CPU")
                        loaded = TextCrossEncoder(model_name=model, **kwargs)
                    else:
                        from sentence_transformers import CrossEncoder
                        loaded = CrossEncoder(model, device=device)
                except ImportError as exc:
                    errors.append(f"{name}: not installed ({exc})")
                    continue
                except ValueError as exc:
                    # fastembed rejects models outside its catalog; try the next backend.
                    model_rejected = True
                    errors.append(f"{name}: {exc}")
                    continue
                _CROSS_ENCODER_CACHE[key] = loaded
                return name, loaded
        if model_rejected:
            raise ValueError(
                f"No local cross-encoder backend can load RERANKER_MODEL={model!r} "
                "(fastembed default: 'BAAI/bge-reranker-v2-m3'). " + "; ".join(errors)
            )
        raise ImportError(
            "RERANKER_TYPE=local_cross_encoder requires fastembed or sentence-transformers "
            "(pip install -r requirements-local.txt). " + "; ".join(errors)
        )

    def _score(self, query, documents):
        passages = _passages(documents)
        if self.backend == "fastembed":
            scores = list(self._model.rerank(query, passages))
        else:
            scores = list(self._model.predict([(query, text) for text in passages]))
        return [(i, float(score)) for i, score in enumerate(scores)]

    def get_model_info(self) -> Dict[str, Any]:
        return {"type": self.kind, "model_name": self.model_name, "backend": self.backend,
                "device": self.device, "mode": "local"}


def create_reranker(settings: Optional[RerankerSettings] = None) -> Optional[BaseReranker]:
    """Build the configured reranker, or ``None`` when reranking is disabled."""
    settings = settings or get_settings().reranker
    if not settings.enabled or settings.type == "none":
        return None
    kind = settings.type
    if kind == "bm25":
        return BM25Reranker()
    if kind == "pinecone":
        return PineconeReranker(model_name=settings.model, api_key=settings.pinecone_api_key)
    if kind == "http_rerank":
        return HTTPReranker(base_url=settings.base_url, model=settings.model, api_key=settings.api_key,
                            api_style=settings.api_style, timeout=settings.timeout)
    if kind == "llm_rerank":
        return LLMReranker(base_url=settings.base_url, model=settings.model, api_key=settings.api_key,
                           timeout=settings.timeout)
    if kind == "local_cross_encoder":
        return LocalCrossEncoderReranker(model=settings.model, device=settings.device)
    raise ValueError(f"Unknown RERANKER_TYPE: {kind}")
