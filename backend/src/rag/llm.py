"""LLM wrapper for Groq/OpenRouter fallback and legacy HuggingFace inference."""

import time
from dataclasses import replace
from typing import Dict, Any, List, Optional
from loguru import logger
from openai import OpenAI

from ..utils.config import LLMEndpointSettings, LLMSettings, get_settings

# Backward-compatible name for the endpoint type used by the fallback chain.
ProviderEndpoint = LLMEndpointSettings


class LLMWrapper:
    """Wrapper for LLM supporting Groq/OpenRouter fallback and legacy providers."""
    
    # Available providers and their models
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
            "name": "Groq/OpenRouter Fallback Chain",
            "models": [
                "openai/gpt-oss-120b",
            ],
            "default_model": "openai/gpt-oss-120b"
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
        model_name: str = "openai/gpt-oss-120b",
        temperature: float = 0.3,
        max_new_tokens: int = 2048,
        device: str = "cpu",  # Not used, kept for compatibility
        provider: str = "provider_chain",
        settings: Optional[LLMSettings] = None,
    ):
        """
        Initialize LLM wrapper with specified provider.
        
        Args:
            model_name: Model name (provider-specific)
            temperature: Sampling temperature
            max_new_tokens: Maximum tokens to generate
            device: Not used (cloud-based), kept for compatibility
            provider: LLM provider ("provider_chain", "groq", "openrouter", or "huggingface")
            settings: LLM settings (defaults to get_settings().llm); endpoints,
                keys and timeouts come from here, never from the environment
        """
        self._settings = settings or get_settings().llm
        self.model_name = model_name
        self.temperature = temperature
        self.max_new_tokens = max_new_tokens
        self.device = "cloud"  # Always cloud-based
        self.provider = provider.lower()
        self.request_timeout = self._settings.request_timeout
        self.total_timeout = self._settings.total_timeout
        
        logger.info(f"Initializing LLM with provider: {self.provider}")
        logger.info(f"Model: {model_name}")
        
        self._last_provider = None
        self._provider_failures: List[Dict[str, str]] = []

        if self.provider in {"provider_chain", "chain", "auto"}:
            self._init_provider_chain()
        elif self.provider == "openrouter":
            self._init_provider_chain(["openrouter", "groq"])
        elif self.provider == "groq":
            self._init_provider_chain(["groq", "openrouter"])
        elif self.provider == "huggingface":
            self._init_huggingface()
        else:
            raise ValueError(
                f"Unknown provider: {provider}. Use 'provider_chain', 'groq', 'openrouter', or 'huggingface'"
            )

    def _init_provider_chain(self, preferred_order: Optional[List[str]] = None):
        """Initialize the OpenAI-compatible fallback chain from settings."""
        provider_order = preferred_order or list(self._settings.provider_order)
        self.provider_endpoints = [
            endpoint if endpoint.model_overridden else replace(endpoint, model=self.model_name)
            for endpoint in self._settings.chain(provider_order)
        ]

        if not self.provider_endpoints:
            raise ValueError(
                "No LLM endpoint configured for provider order "
                f"{', '.join(provider_order)}. Set GROQ_API_KEY, OPENROUTER_API_KEY "
                "or LLM_CUSTOM_<N>_BASE_URL in .env"
            )

        self._use_provider_chain = True
        logger.info(
            "Provider fallback chain initialized: "
            + ", ".join(endpoint.name for endpoint in self.provider_endpoints)
        )

    def _init_huggingface(self):
        """Initialize HuggingFace Inference API."""
        hf_endpoints = self._settings.presets.get("huggingface", ())
        api_token = hf_endpoints[0].api_key if hf_endpoints else ""
        if not api_token:
            raise ValueError(
                "HUGGINGFACE_API_TOKEN not found in environment. "
                "Please set it in .env file"
            )
        
        logger.info(f"Initializing HuggingFace Inference API: {self.model_name}")
        logger.info("Using HuggingFace serverless inference")
        
        try:
            # Use OpenAI-compatible client for HuggingFace
            self.client = OpenAI(
                base_url="https://router.huggingface.co/v1",
                api_key=api_token,
                timeout=self.request_timeout,
                max_retries=0,
            )
            logger.info("HuggingFace Inference API initialized successfully")
            
        except Exception as e:
            logger.error(f"Error initializing HuggingFace LLM: {e}")
            raise
    
    def generate(self, prompt: str) -> str:
        """
        Generate text from prompt.
        
        Args:
            prompt: Input prompt
            
        Returns:
            Generated text
        """
        try:
            if getattr(self, "_use_provider_chain", False):
                return self._generate_with_provider_chain(prompt)
            return self._generate_openai_style(prompt)
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            raise

    def _generate_with_provider_chain(self, prompt: str) -> str:
        """Generate with fallback across Groq and OpenRouter endpoints."""
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
                self._last_provider = endpoint.name
                return completion.choices[0].message.content.strip()
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
        return OpenAI(
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
    
    def _generate_openai_style(self, prompt: str) -> str:
        """Generate using OpenAI-compatible client (HuggingFace)."""
        completion = self.client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=self.temperature,
            max_tokens=self.max_new_tokens,
            timeout=self.request_timeout,
        )
        return completion.choices[0].message.content.strip()
    
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
            "provider_chain": [
                endpoint.name for endpoint in getattr(self, "provider_endpoints", [])
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
