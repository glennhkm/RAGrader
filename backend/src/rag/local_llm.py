"""Optional in-process LLM backend using llama.cpp (``LLM_PROVIDER=local``).

Intended for air-gapped, single-process deployments that cannot run an
Ollama/vLLM daemon. Most self-hosted setups should prefer
``LLM_PROVIDER=openai_compatible`` pointed at a local server instead.

Requires the optional ``llama-cpp-python`` package (see
``requirements-local.txt``) and a GGUF model file in ``LLM_LOCAL_MODEL_PATH``.
"""

from pathlib import Path
from threading import Lock
from typing import Any, Dict, Tuple

from loguru import logger

from ..utils.config import ConfigError, LLMSettings

_MODEL_CACHE: Dict[Tuple[str, int, int], Any] = {}
_MODEL_LOCK = Lock()


def _load_llama(model_path: str, n_ctx: int, n_gpu_layers: int) -> Any:
    key = (model_path, n_ctx, n_gpu_layers)
    with _MODEL_LOCK:
        if key in _MODEL_CACHE:
            return _MODEL_CACHE[key]
        try:
            from llama_cpp import Llama
        except ImportError as exc:
            raise ConfigError(
                "LLM_PROVIDER=local requires llama-cpp-python: uncomment it in "
                "requirements-local.txt and pip install -r requirements-local.txt "
                "(or use LLM_PROVIDER=openai_compatible with Ollama/vLLM)"
            ) from exc
        logger.info(f"Loading local GGUF model {Path(model_path).name} (n_ctx={n_ctx}, n_gpu_layers={n_gpu_layers})")
        model = Llama(model_path=model_path, n_ctx=n_ctx, n_gpu_layers=n_gpu_layers, verbose=False)
        _MODEL_CACHE[key] = model
        return model


class LocalLlamaCppLLM:
    """Chat-completion style generation with a GGUF model loaded once per process."""

    def __init__(self, settings: LLMSettings, temperature: float = 0.3, max_new_tokens: int = 2048):
        model_path = settings.local_model_path
        if not model_path:
            raise ConfigError("LLM_PROVIDER=local requires LLM_LOCAL_MODEL_PATH pointing to a .gguf file")
        if not Path(model_path).is_file():
            raise ConfigError(f"LLM_LOCAL_MODEL_PATH does not point to a file: {model_path}")
        self.model_path = model_path
        self.temperature = temperature
        self.max_new_tokens = max_new_tokens
        self._model = _load_llama(model_path, settings.local_n_ctx, settings.local_n_gpu_layers)

    def generate(self, prompt: str) -> str:
        result = self._model.create_chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=self.temperature,
            max_tokens=self.max_new_tokens,
        )
        content = (result.get("choices") or [{}])[0].get("message", {}).get("content")
        if not content or not str(content).strip():
            raise RuntimeError("Local LLM returned an empty completion")
        return str(content).strip()
