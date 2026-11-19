"""LLM wrapper: any OpenAI-compatible endpoint, fallback chains, and presets.

Every remote provider (Groq, OpenRouter, HuggingFace Router, custom_N
endpoints, or a single ``openai_compatible`` server such as Ollama, vLLM,
LM Studio, llama.cpp server, LiteLLM or OpenAI) runs through the same
OpenAI-compatible chain executor with per-request and total deadlines.
"""

import time
from dataclasses import replace
from types import MappingProxyType
from typing import Any, Callable, Dict, List, Optional
from loguru import logger
from openai import OpenAI

from ..utils.config import LLMEndpointSettings, LLMSettings, get_settings

# Backward-compatible name for the endpoint type used by the fallback chain.
ProviderEndpoint = LLMEndpointSettings

_PRESET_ORDERS = {
    "groq": ["groq", "openrouter"],
    "openrouter": ["openrouter", "groq"],
    "huggingface": ["huggingface"],
}
_CHAIN_ALIASES = {"provider_chain", "chain", "auto"}


class LLMWrapper:
    """Grade-prompt generator over OpenAI-compatible providers.

    Model strings are never validated against a list: ``PROVIDERS`` is only a
    catalog of suggestions for UIs and status endpoints.
    """
    
    # Suggested models per provider (documentation only, not an allow-list).
    PROVIDERS = {
        "groq": {
            "name": "Groq (Ultra-Fast)",
            "models": [
                "openai/gpt-oss-120b",
                "llama-3.1-8b-instant",
                "llama-3.3-70b-versatile",
                "llama-3.1-70b-versatile",
                "mixtral-8x7b-32768",
            ],
            "default_model": "openai/gpt-oss-120b"
        },
        "openrouter": {
            "name": "OpenRouter",
            "models": [
                "openai/gpt-oss-120b",
                "meta-llama/llama-3.3-70b-instruct",
                "qwen/qwen-2.5-72b-instruct",
            ],
            "default_model": "openai/gpt-oss-120b"
        },
        "provider_chain": {
            "name": "Fallback Chain (Groq, OpenRouter, custom_N endpoints)",
            "models": [
                "openai/gpt-oss-120b",
            ],
            "default_model": "openai/gpt-oss-120b"
        },
        "openai_compatible": {
            "name": "Any OpenAI-Compatible Endpoint (Ollama, vLLM, LM Studio, llama.cpp, LiteLLM, OpenAI)",
            "models": [
                "qwen2.5:14b-instruct",
                "llama3.1:8b-instruct",
                "gpt-4o-mini",
            ],
            "default_model": "qwen2.5:14b-instruct"
        },
        "local": {
            "name": "In-Process llama.cpp (GGUF, requires requirements-local.txt)",
            "models": [],
            "default_model": ""
        },
        "huggingface": {
            "name": "HuggingFace Inference",
            "models": [
                "Qwen/Qwen2.5-72B-Instruct",
                "Qwen/Qwen3-30B-A3B-Instruct-2507",
                "openai/gpt-oss-120b",
                "meta-llama/Llama-3.3-70B-Instruct",
                "mistralai/Mistral-Small-24B-Instruct-2501",
                "microsoft/phi-4",
                "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B",
            ],
            "default_model": "openai/gpt-oss-120b"
        }
    }
    
    def __init__(
        self,
        model_name: Optional[str] = None,
        temperature: Optional[float] = None,
        max_new_tokens: Optional[int] = None,
        device: str = "cpu",  # Not used, kept for compatibility
        provider: Optional[str] = None,
        settings: Optional[LLMSettings] = None,
        client_factory: Optional[Callable[..., Any]] = None,
    ):
        """
        Initialize LLM wrapper with specified provider.
        
        Args:
            model_name: Model name; any string the provider accepts (default: LLM_MODEL)
            temperature: Sampling temperature (default: LLM_TEMPERATURE)
            max_new_tokens: Maximum tokens to generate (default: LLM_MAX_NEW_TOKENS)
            device: Not used, kept for compatibility
            provider: provider_chain | openai_compatible | local | groq | openrouter |
                huggingface (default: LLM_PROVIDER)
            settings: LLM settings (defaults to get_settings().llm); endpoints,
                keys and timeouts come from here, never from the environment
            client_factory: Callable building an OpenAI-compatible client
                (tests inject fakes; defaults to ``openai.OpenAI``)
        """
        self._settings = settings or get_settings().llm
        self._client_factory = client_factory
        self.model_name = model_name or self._settings.model
        self.temperature = self._settings.temperature if temperature is None else temperature
        self.max_new_tokens = self._settings.max_new_tokens if max_new_tokens is None else max_new_tokens
        self.device = "cloud"
        self.provider = (provider or self._settings.provider).lower()
        self.request_timeout = self._settings.request_timeout
        self.total_timeout = self._settings.total_timeout
        self.provider_endpoints: List[LLMEndpointSettings] = []
        self._local_llm = None
        
        logger.info(f"Initializing LLM with provider: {self.provider}")
        logger.info(f"Model: {self.model_name}")
        
        self._last_provider = None
        self._provider_failures: List[Dict[str, str]] = []

        if self.provider in _CHAIN_ALIASES:
            self._init_provider_chain()
        elif self.provider in _PRESET_ORDERS:
            self._init_provider_chain(_PRESET_ORDERS[self.provider])
        elif self.provider in {"openai_compatible", "openai"}:
            self._init_openai_compatible()
        elif self.provider == "local":
            self._init_local()
        else:
            raise ValueError(
                f"Unknown provider: {self.provider}. Use 'provider_chain', 'openai_compatible', "
                "'local', 'groq', 'openrouter', or 'huggingface'"
            )

    def _with_wrapper_model(self, endpoint: LLMEndpointSettings) -> LLMEndpointSettings:
        return endpoint if endpoint.model_overridden else replace(endpoint, model=self.model_name)

    def _init_provider_chain(self, preferred_order: Optional[List[str]] = None):
        """Initialize the OpenAI-compatible fallback chain from settings."""
        provider_order = preferred_order or list(self._settings.provider_order)
        self.provider_endpoints = [
            self._with_wrapper_model(endpoint)
            for endpoint in self._settings.chain(provider_order)
        ]

        if not self.provider_endpoints:
            if provider_order == ["huggingface"]:
                hint = "Set HUGGINGFACE_API_TOKEN"
            else:
                hint = ("Set GROQ_API_KEY, OPENROUTER_API_KEY or LLM_CUSTOM_<N>_BASE_URL, "
                        "or use LLM_PROVIDER=openai_compatible with LLM_BASE_URL")
            raise ValueError(
                f"No LLM endpoint configured for provider order {', '.join(provider_order)}. {hint} in .env"
            )

        self._use_provider_chain = True
        logger.info(
            "Provider fallback chain initialized: "
            + ", ".join(endpoint.name for endpoint in self.provider_endpoints)
        )

    def _init_openai_compatible(self):
        """Single OpenAI-compatible endpoint (Ollama, vLLM, LM Studio, OpenAI, ...)."""
        if not self._settings.base_url:
            raise ValueError(
                "LLM_PROVIDER=openai_compatible requires LLM_BASE_URL "
                "(e.g. http://localhost:11434/v1 for Ollama); LLM_API_KEY is optional"
            )
        self.provider_endpoints = [LLMEndpointSettings(
            name="openai_compatible",
            base_url=self._settings.base_url,
            api_key=self._settings.api_key,
            model=self.model_name,
            extra_headers=MappingProxyType({}),
        )]
        self._use_provider_chain = True
        logger.info(f"OpenAI-compatible endpoint initialized: {self._settings.base_url}")

    def _init_local(self):
        """In-process llama.cpp model (optional dependency, loaded lazily)."""
        from .local_llm import LocalLlamaCppLLM

        self._local_llm = LocalLlamaCppLLM(
            self._settings,
            temperature=self.temperature,
            max_new_tokens=self.max_new_tokens,
        )
        self._use_provider_chain = False
        logger.info("In-process local LLM initialized")
    
    def generate(self, prompt: str) -> str:
        """
        Generate text from prompt.
        
        Args:
            prompt: Input prompt
            
        Returns:
            Generated text
        """
        try:
            if self._local_llm is not None:
                text = self._local_llm.generate(prompt)
                self._last_provider = "local"
                return text
            return self._generate_with_provider_chain(prompt)
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            raise

    def _generate_with_provider_chain(self, prompt: str) -> str:
        """Generate with fallback across the configured OpenAI-compatible endpoints."""
        self._provider_failures = []
        last_error: Optional[Exception] = None
        deadline = time.monotonic() + self.total_timeout

        for endpoint in self.provider_endpoints:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            # Self-hosted OpenAI-compatible servers often need no key, but the
            # SDK requires a non-empty value.
            api_key = endpoint.api_key or "not-needed"

            try:
                logger.info(f"Generating response via {endpoint.name} ({endpoint.model})")
                timeout = min(self.request_timeout, remaining)
                client = self._create_openai_client(
                    endpoint=endpoint,
                    api_key=api_key,
                    timeout=timeout,
                )
                completion = client.chat.completions.create(
                    model=endpoint.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=self.temperature,
                    max_tokens=self.max_new_tokens,
                    timeout=timeout,
                )
                content = completion.choices[0].message.content if completion.choices else None
                if not content or not str(content).strip():
                    raise RuntimeError("empty completion content")
                self._last_provider = endpoint.name
                return str(content).strip()
            except Exception as exc:
                last_error = exc
                error_type = self._classify_provider_error(exc)
                self._provider_failures.append({
                    "provider": endpoint.name,
                    "error_type": error_type,
                    "message": str(exc)[:500],
                })
                logger.warning(
                    f"Provider {endpoint.name} failed with {error_type}; trying next provider"
                )
                if error_type == "rate_limit":
                    retry_after = self._extract_retry_after_seconds(exc)
                    if retry_after:
                        sleep_seconds = min(retry_after, 2, max(0.0, deadline - time.monotonic()))
                        if sleep_seconds:
                            time.sleep(sleep_seconds)
                continue

        raise RuntimeError(
            "All LLM providers failed. Last error: "
            + (str(last_error) if last_error else "unknown error")
        )

    def _create_openai_client(
        self, endpoint: ProviderEndpoint, api_key: str, timeout: float
    ) -> OpenAI:
        """Create OpenAI-compatible client with provider-specific headers."""
        default_headers = dict(endpoint.extra_headers) or None
        factory = self._client_factory or OpenAI
        return factory(
            base_url=endpoint.base_url,
            api_key=api_key,
            default_headers=default_headers,
            timeout=timeout,
            max_retries=0,
        )

    def _classify_provider_error(self, exc: Exception) -> str:
        text = str(exc).lower()
        status_code = getattr(exc, "status_code", None)
        if status_code == 429 or "rate limit" in text or "rate_limit" in text or "too many requests" in text:
            return "rate_limit"
        if status_code in {401, 403} or "unauthorized" in text or "invalid api key" in text:
            return "auth"
        if status_code and 500 <= int(status_code) < 600:
            return "server_error"
        if "timeout" in text or "timed out" in text:
            return "timeout"
        return "provider_error"

    def _extract_retry_after_seconds(self, exc: Exception) -> Optional[float]:
        response = getattr(exc, "response", None)
        headers = getattr(response, "headers", {}) if response is not None else {}
        retry_after = headers.get("retry-after") if headers else None
        if not retry_after:
            return None
        try:
            return float(retry_after)
        except ValueError:
            return None
    
    def get_llm_instance(self):
        """Return None; LangChain LLM client has been replaced by OpenAI-compatible clients."""
        return None
    
    def get_provider_info(self) -> Dict[str, Any]:
        """Get information about the current provider."""
        return {
            "provider": self.provider,
            "model": self.model_name,
            "temperature": self.temperature,
            "max_tokens": self.max_new_tokens,
            "last_provider": self._last_provider,
            "provider_chain": [endpoint.name for endpoint in self.provider_endpoints],
            "endpoints": [
                {"name": endpoint.name, "base_url": endpoint.base_url, "model": endpoint.model}
                for endpoint in self.provider_endpoints
            ],
            "provider_failures": self._provider_failures,
        }
    
    @classmethod
    def get_available_providers(cls) -> Dict[str, Any]:
        """Get list of available providers and their models."""
        return cls.PROVIDERS
    
    @classmethod
    def get_provider_models(cls, provider: str) -> list:
        """Get available models for a provider."""
        provider = provider.lower()
        if provider in cls.PROVIDERS:
            return cls.PROVIDERS[provider]["models"]
        return []
