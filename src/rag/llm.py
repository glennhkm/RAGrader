"""LLM wrapper for multiple providers (Groq & HuggingFace Inference)."""

import os
from typing import Optional, Dict, Any
from loguru import logger
from openai import OpenAI
from langchain_groq import ChatGroq


class LLMWrapper:
    """Wrapper for LLM supporting multiple providers (Groq, HuggingFace)."""
    
    # Available providers and their models
    PROVIDERS = {
        "groq": {
            "name": "Groq (Ultra-Fast)",
            "models": [
                "llama-3.1-8b-instant",
                "llama-3.3-70b-versatile",
                "llama-3.1-70b-versatile",
                "mixtral-8x7b-32768",
            ],
            "default_model": "llama-3.1-8b-instant"
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
        provider: str = "huggingface"  # Provider: "groq" or "huggingface"
    ):
        """
        Initialize LLM wrapper with specified provider.
        
        Args:
            model_name: Model name (provider-specific)
            temperature: Sampling temperature
            max_new_tokens: Maximum tokens to generate
            device: Not used (cloud-based), kept for compatibility
            provider: LLM provider ("groq" or "huggingface")
        """
        self.model_name = model_name
        self.temperature = temperature
        self.max_new_tokens = max_new_tokens
        self.device = "cloud"  # Always cloud-based
        self.provider = provider.lower()
        
        logger.info(f"Initializing LLM with provider: {self.provider}")
        logger.info(f"Model: {model_name}")
        
        if self.provider == "groq":
            self._init_groq()
        elif self.provider == "huggingface":
            self._init_huggingface()
        else:
            raise ValueError(f"Unknown provider: {provider}. Use 'groq' or 'huggingface'")
    
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
            if self._use_openai_client:
                return self._generate_openai_style(prompt)
            else:
                return self._generate_langchain_style(prompt)
                
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            raise
    
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
            "max_tokens": self.max_new_tokens
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
