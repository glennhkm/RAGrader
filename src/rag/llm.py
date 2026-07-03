"""LLM wrapper for Groq/OpenRouter fallback and legacy HuggingFace inference."""

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv
from loguru import logger
from openai import OpenAI
from langchain_groq import ChatGroq


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


@dataclass
class ProviderEndpoint:
    """Runtime provider endpoint used by the fallback chain."""

    name: str
    base_url: str
    api_key_env: str
    model: str


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
        provider: str = "provider_chain"
    ):
        """
        Initialize LLM wrapper with specified provider.
        
        Args:
            model_name: Model name (provider-specific)
            temperature: Sampling temperature
            max_new_tokens: Maximum tokens to generate
            device: Not used (cloud-based), kept for compatibility
            provider: LLM provider ("provider_chain", "groq", "openrouter", or "huggingface")
        """
        self.model_name = model_name
        self.temperature = temperature
        self.max_new_tokens = max_new_tokens
        self.device = "cloud"  # Always cloud-based
        self.provider = provider.lower()
        
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
        """Initialize Groq/OpenRouter fallback chain using available environment keys."""
        provider_order = preferred_order or self._provider_order_from_env()
        self.provider_endpoints = self._build_provider_endpoints(provider_order)

        if not self.provider_endpoints:
            raise ValueError(
                "No Groq/OpenRouter API key found. Set GROQ_API_KEY or OPENROUTER_API_KEY in .env"
            )

        self._use_provider_chain = True
        self._use_openai_client = False
        logger.info(
            "Provider fallback chain initialized: "
            + ", ".join(endpoint.name for endpoint in self.provider_endpoints)
        )

    def _provider_order_from_env(self) -> List[str]:
        raw = os.getenv("LLM_PROVIDER_ORDER", "groq,openrouter")
        order = [item.strip().lower() for item in raw.split(",") if item.strip()]
        return order or ["groq", "openrouter"]

    def _build_provider_endpoints(self, provider_order: List[str]) -> List[ProviderEndpoint]:
        endpoints: List[ProviderEndpoint] = []
        for provider_name in provider_order:
            if provider_name == "groq":
                endpoints.extend(self._collect_numbered_provider_keys(
                    provider_name="groq",
                    base_url="https://api.groq.com/openai/v1",
                    api_key_prefix="GROQ_API_KEY",
                    model=os.getenv("GROQ_MODEL", self.model_name),
                    max_index=int(os.getenv("GROQ_KEY_MAX_INDEX", "6")),
                ))
            elif provider_name == "openrouter":
                endpoints.extend(self._collect_numbered_provider_keys(
                    provider_name="openrouter",
                    base_url="https://openrouter.ai/api/v1",
                    api_key_prefix="OPENROUTER_API_KEY",
                    model=os.getenv("OPENROUTER_MODEL", self.model_name),
                    max_index=int(os.getenv("OPENROUTER_KEY_MAX_INDEX", "7")),
                ))
            else:
                logger.warning(f"Skipping unknown provider in LLM_PROVIDER_ORDER: {provider_name}")
        return endpoints

    def _collect_numbered_provider_keys(
        self,
        provider_name: str,
        base_url: str,
        api_key_prefix: str,
        model: str,
        max_index: int,
    ) -> List[ProviderEndpoint]:
        endpoints: List[ProviderEndpoint] = []
        env_names = [api_key_prefix] + [f"{api_key_prefix}_{idx}" for idx in range(1, max_index + 1)]
        seen = set()
        for env_name in env_names:
            if env_name in seen:
                continue
            seen.add(env_name)
            if os.getenv(env_name):
                suffix = env_name.removeprefix(api_key_prefix).lstrip("_")
                endpoints.append(
                    ProviderEndpoint(
                        name=f"{provider_name}{suffix}",
                        base_url=base_url,
                        api_key_env=env_name,
                        model=model,
                    )
                )
        return endpoints
    
    def _init_groq(self):
        """Initialize Groq LLM."""
        api_token = os.getenv("GROQ_API_KEY")
        if not api_token:
            raise ValueError(
                "GROQ_API_KEY not found in environment. "
                "Please set it in .env file"
            )
        
        logger.info(f"Initializing Groq API LLM: {self.model_name}")
        logger.info("Using Groq cloud-based inference (ultra-fast)")
        
        try:
            self.llm = ChatGroq(
                model=self.model_name,
                temperature=self.temperature,
                max_tokens=self.max_new_tokens,
                groq_api_key=api_token,
                request_timeout=120
            )
            self._use_openai_client = False
            logger.info("Groq LLM initialized successfully")
            
        except Exception as e:
            logger.error(f"Error initializing Groq LLM: {e}")
            raise
    
    def _init_huggingface(self):
        """Initialize HuggingFace Inference API."""
        api_token = os.getenv("HUGGINGFACE_API_TOKEN")
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
            )
            self._use_openai_client = True
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
            if self._use_openai_client:
                return self._generate_openai_style(prompt)
            else:
                return self._generate_langchain_style(prompt)
                
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            raise

    def _generate_with_provider_chain(self, prompt: str) -> str:
        """Generate with fallback across Groq and OpenRouter endpoints."""
        self._provider_failures = []
        last_error: Optional[Exception] = None

        for endpoint in self.provider_endpoints:
            api_key = os.getenv(endpoint.api_key_env)
            if not api_key:
                continue

            try:
                logger.info(f"Generating response via {endpoint.name} ({endpoint.model})")
                client = self._create_openai_client(endpoint=endpoint, api_key=api_key)
                completion = client.chat.completions.create(
                    model=endpoint.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=self.temperature,
                    max_tokens=self.max_new_tokens,
                    timeout=120,
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
                        time.sleep(min(retry_after, 5))
                continue

        raise RuntimeError(
            "All LLM providers failed. Last error: "
            + (str(last_error) if last_error else "unknown error")
        )

    def _create_openai_client(self, endpoint: ProviderEndpoint, api_key: str) -> OpenAI:
        """Create OpenAI-compatible client with provider-specific headers."""
        default_headers = None
        if endpoint.name.startswith("openrouter"):
            default_headers = {
                "HTTP-Referer": os.getenv("OPENROUTER_SITE_URL", "http://localhost"),
                "X-Title": os.getenv("OPENROUTER_APP_NAME", "RAG Essay Grading API"),
            }
        return OpenAI(
            base_url=endpoint.base_url,
            api_key=api_key,
            default_headers=default_headers,
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
    
    def _generate_langchain_style(self, prompt: str) -> str:
        """Generate using LangChain style (Groq)."""
        response = self.llm.invoke(prompt)
        if hasattr(response, 'content'):
            return response.content.strip()
        return str(response).strip()
    
    def _generate_openai_style(self, prompt: str) -> str:
        """Generate using OpenAI-compatible client (HuggingFace)."""
        completion = self.client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=self.temperature,
            max_tokens=self.max_new_tokens,
        )
        return completion.choices[0].message.content.strip()
    
    def get_llm_instance(self):
        """Get the underlying LLM instance for LangChain."""
        if hasattr(self, 'llm'):
            return self.llm
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
