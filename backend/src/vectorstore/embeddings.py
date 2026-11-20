"""Embedding providers: HuggingFace Inference, any OpenAI-compatible API, or local.

``EmbeddingGenerator`` keeps its public API (``get_embeddings_instance()``,
``switch_model()``, ``get_model_info()``) and selects the backend from
``EMBEDDING_PROVIDER``:

- ``huggingface`` (default, legacy): HuggingFace Inference API, needs
  ``HUGGINGFACE_API_TOKEN``.
- ``openai_compatible``: any ``/v1/embeddings`` server (OpenAI, Ollama, vLLM,
  LiteLLM, HF TEI, Infinity, Jina, ...), key optional.
- ``local``: in-process ``fastembed`` or ``sentence-transformers``
  (``pip install -r requirements-local.txt``), no network calls.
"""

from threading import Lock
from typing import Any, Callable, Dict, List, Optional, Tuple

from langchain_core.embeddings import Embeddings
from loguru import logger

from ..utils.config import LOCAL_FASTEMBED_EMBEDDING_MODEL, EmbeddingSettings, get_settings


class EmbeddingMismatchError(RuntimeError):
    """A vector collection was built with a different embedding provider/model/dimension."""


class OpenAICompatibleEmbeddings(Embeddings):
    """LangChain embeddings over the OpenAI ``/v1/embeddings`` API contract."""

    def __init__(
        self,
        model: str,
        base_url: str,
        api_key: str = "",
        batch_size: int = 64,
        timeout: float = 60.0,
        client_factory: Optional[Callable[..., Any]] = None,
    ):
        if not base_url:
            raise ValueError(
                "EMBEDDING_PROVIDER=openai_compatible requires EMBEDDING_BASE_URL "
                "(e.g. http://localhost:11434/v1 for Ollama); EMBEDDING_API_KEY is optional"
            )
        if client_factory is None:
            from openai import OpenAI

            client_factory = OpenAI
        self.model = model
        self.batch_size = max(1, int(batch_size))
        # Self-hosted servers often need no key, but the SDK requires a value.
        self._client = client_factory(
            base_url=base_url,
            api_key=api_key or "not-needed",
            timeout=timeout,
            max_retries=2,
        )

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        vectors: List[List[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = [text if text else " " for text in texts[start:start + self.batch_size]]
            response = self._client.embeddings.create(model=self.model, input=batch)
            items = sorted(response.data, key=lambda item: item.index)
            if len(items) != len(batch):
                raise RuntimeError(
                    f"Embedding API returned {len(items)} vectors for {len(batch)} inputs"
                )
            vectors.extend([list(map(float, item.embedding)) for item in items])
        return vectors

    def embed_query(self, text: str) -> List[float]:
        return self.embed_documents([text])[0]


_LOCAL_MODEL_CACHE: Dict[Tuple[str, str, str], Any] = {}
_LOCAL_MODEL_LOCK = Lock()


def _load_local_model(backend: str, model: str, device: str) -> Any:
    """Load (once per process) a fastembed or sentence-transformers model."""
    key = (backend, model, device)
    with _LOCAL_MODEL_LOCK:
        if key in _LOCAL_MODEL_CACHE:
            return _LOCAL_MODEL_CACHE[key]
        if backend == "fastembed":
            try:
                from fastembed import TextEmbedding
            except ImportError as exc:
                raise ImportError(
                    "EMBEDDING_PROVIDER=local with EMBEDDING_LOCAL_BACKEND=fastembed requires "
                    "fastembed: pip install -r requirements-local.txt"
                ) from exc
            kwargs = {"cuda": True} if device == "cuda" else {}
            if device == "mps":
                logger.warning(
                    "fastembed has no MPS support; embedding on CPU. Use "
                    "EMBEDDING_LOCAL_BACKEND=sentence_transformers to run on MPS."
                )
            try:
                loaded = TextEmbedding(model_name=model, **kwargs)
            except ValueError as exc:
                raise ValueError(
                    f"fastembed cannot load EMBEDDING_MODEL={model!r} ({exc}). Pick a "
                    f"fastembed model (default {LOCAL_FASTEMBED_EMBEDDING_MODEL!r}; see "
                    "fastembed.TextEmbedding.list_supported_models()) or set "
                    "EMBEDDING_LOCAL_BACKEND=sentence_transformers for any Hugging Face model."
                ) from exc
        else:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise ImportError(
                    "EMBEDDING_LOCAL_BACKEND=sentence_transformers requires sentence-transformers: "
                    "pip install sentence-transformers"
                ) from exc
            loaded = SentenceTransformer(model, device=device)
        _LOCAL_MODEL_CACHE[key] = loaded
        return loaded


class LocalEmbeddings(Embeddings):
    """In-process embeddings (no network) via fastembed or sentence-transformers."""

    def __init__(self, model: str, backend: str = "fastembed", device: str = "cpu", batch_size: int = 64):
        self.model = model
        self.backend = backend
        self.device = device
        self.batch_size = max(1, int(batch_size))
        self._model = _load_local_model(backend, model, device)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        if self.backend == "fastembed":
            vectors = self._model.embed(list(texts), batch_size=self.batch_size)
        else:
            vectors = self._model.encode(
                list(texts),
                batch_size=self.batch_size,
                normalize_embeddings=True,
                convert_to_numpy=True,
            )
        return [[float(value) for value in vector] for vector in vectors]

    def embed_query(self, text: str) -> List[float]:
        return self.embed_documents([text])[0]


class EmbeddingGenerator:
    """Select and wrap the configured embedding backend."""
    
    # Suggested models (documentation only; any model id is accepted)
    EMBEDDING_MODELS = {
        "BAAI/bge-m3": {
            "name": "BGE-M3 (Multilingual)",
            "description": "State-of-the-art multilingual embedding model, excellent for semantic search",
            "dimensions": 1024,
            "max_tokens": 8192
        },
        "sentence-transformers/all-MiniLM-L6-v2": {
            "name": "MiniLM-L6-v2 (Fast)",
            "description": "Fast and efficient, good balance of speed and quality",
            "dimensions": 384,
            "max_tokens": 256
        },
        "intfloat/multilingual-e5-large": {
            "name": "E5-Large Multilingual",
            "description": "High quality multilingual embeddings, larger model",
            "dimensions": 1024,
            "max_tokens": 512
        },
        "intfloat/multilingual-e5-base": {
            "name": "E5-Base Multilingual",
            "description": "Good quality multilingual embeddings, balanced size",
            "dimensions": 768,
            "max_tokens": 512
        },
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2": {
            "name": "Paraphrase Multilingual MiniLM",
            "description": "Optimized for paraphrase detection and semantic similarity",
            "dimensions": 384,
            "max_tokens": 128
        }
    }
    
    def __init__(
        self,
        model_name: Optional[str] = None,
        device: Optional[str] = None,
        settings: Optional[EmbeddingSettings] = None,
        client_factory: Optional[Callable[..., Any]] = None,
    ):
        """
        Initialize the embedding backend.
        
        Args:
            model_name: Embedding model id (default: EMBEDDING_MODEL); any id is accepted
            device: Device for local models (default: EMBEDDING_DEVICE; "cloud" means "cpu")
            settings: Embedding settings (defaults to get_settings().embeddings)
            client_factory: OpenAI-compatible client factory (tests)
        """
        self._settings = settings or get_settings().embeddings
        self._client_factory = client_factory
        self.provider = self._settings.provider
        self.model_name = model_name or self._settings.model
        requested = (device or self._settings.device or "cpu").lower()
        self.device = "cpu" if requested in {"cloud", ""} else requested
        self._dimension: Optional[int] = None
        self.embeddings: Embeddings = self._build(self.model_name)

    def _build(self, model_name: str) -> Embeddings:
        """Construct the backend for ``model_name`` without mutating state."""
        if self.provider == "openai_compatible":
            logger.info(f"Initializing OpenAI-compatible embeddings: {model_name} @ {self._settings.base_url}")
            return OpenAICompatibleEmbeddings(
                model=model_name,
                base_url=self._settings.base_url,
                api_key=self._settings.api_key,
                batch_size=self._settings.batch_size,
                client_factory=self._client_factory,
            )
        if self.provider == "local":
            logger.info(f"Initializing local embeddings ({self._settings.local_backend}): {model_name} on {self.device}")
            return LocalEmbeddings(
                model=model_name,
                backend=self._settings.local_backend,
                device=self.device,
                batch_size=self._settings.batch_size,
            )

        token = self._settings.huggingface_token
        if not token:
            raise ValueError(
                "HUGGINGFACE_API_TOKEN not found. Set it in .env, or choose "
                "EMBEDDING_PROVIDER=openai_compatible or EMBEDDING_PROVIDER=local"
            )
        from langchain_huggingface import HuggingFaceEndpointEmbeddings

        logger.info(f"Initializing HuggingFace Inference API embeddings: {model_name}")
        return HuggingFaceEndpointEmbeddings(model=model_name, huggingfacehub_api_token=token)

    def switch_model(self, model_name: str) -> bool:
        """
        Switch to a different embedding model (state unchanged on failure).
        
        Args:
            model_name: New model name
            
        Returns:
            True if switch successful
        """
        if model_name == self.model_name:
            logger.info(f"Already using {model_name}")
            return True
        
        try:
            logger.info(f"Switching embedding model from {self.model_name} to {model_name}")
            self.embeddings = self._build(model_name)
            self.model_name = model_name
            self._dimension = None
            return True
        except Exception as e:
            logger.error(f"Failed to switch embedding model: {e}")
            return False
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple documents."""
        return self.embeddings.embed_documents(texts)
    
    def embed_query(self, text: str) -> List[float]:
        """Generate embedding for a single query."""
        return self.embeddings.embed_query(text)
    
    def get_embeddings_instance(self) -> Embeddings:
        """Get the underlying embeddings instance for LangChain."""
        return self.embeddings

    def get_dimension(self) -> int:
        """Vector dimension of the active model (probed once and cached)."""
        if self._dimension is None:
            self._dimension = len(self.embed_query("dimension probe"))
        return self._dimension

    def identity(self) -> Dict[str, Any]:
        """Provider/model/dimension recorded on vector collections."""
        return {
            "embedding_provider": self.provider,
            "embedding_model": self.model_name,
            "embedding_dimension": self.get_dimension(),
        }
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get current model information."""
        model_info = self.EMBEDDING_MODELS.get(self.model_name, {})
        return {
            "provider": self.provider,
            "model_name": self.model_name,
            "name": model_info.get("name", self.model_name),
            "description": model_info.get("description", ""),
            "dimensions": self._dimension or model_info.get("dimensions", "unknown"),
            "max_tokens": model_info.get("max_tokens", "unknown"),
            "device": self.device if self.provider == "local" else "remote",
        }
    
    @classmethod
    def get_available_models(cls) -> Dict[str, Dict]:
        """Get all suggested embedding models."""
        return cls.EMBEDDING_MODELS
    
    @classmethod
    def get_model_names(cls) -> List[str]:
        """Get list of suggested model names."""
        return list(cls.EMBEDDING_MODELS.keys())
