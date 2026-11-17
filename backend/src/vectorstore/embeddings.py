"""Embedding generator using HuggingFace Inference API with multiple model support."""

from typing import List, Dict, Any
import os
from langchain_huggingface import HuggingFaceEndpointEmbeddings
from loguru import logger


class EmbeddingGenerator:
    """Generate embeddings using HuggingFace Inference API (cloud-based)."""
    
    # Available embedding models from HuggingFace
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
        model_name: str = "BAAI/bge-m3",
        device: str = "cpu"  # Not used, kept for compatibility
    ):
        """
        Initialize embedding generator with HuggingFace Inference API.
        
        Args:
            model_name: HuggingFace model name
            device: Not used (cloud-based), kept for compatibility
        """
        self.model_name = model_name
        self.device = "cloud"  # Always cloud-based
        self._api_token = None
        
        self._init_embeddings()
    
    def _init_embeddings(self):
        """Initialize or reinitialize embeddings with current model."""
        # Get API token from environment
        self._api_token = os.getenv("HUGGINGFACE_API_TOKEN")
        if not self._api_token:
            raise ValueError(
                "HUGGINGFACE_API_TOKEN not found in environment. "
                "Please set it in .env file"
            )
        
        logger.info(f"Initializing HuggingFace Inference API embeddings: {self.model_name}")
        logger.info("Using cloud-based inference (no local GPU/CPU computation)")
        
        self.embeddings = HuggingFaceEndpointEmbeddings(
            model=self.model_name,
            huggingfacehub_api_token=self._api_token
        )
        
        logger.info("Embedding model initialized successfully (HF Inference API)")
    
    def switch_model(self, model_name: str) -> bool:
        """
        Switch to a different embedding model.
        
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
            self.model_name = model_name
            self._init_embeddings()
            return True
        except Exception as e:
            logger.error(f"Failed to switch embedding model: {e}")
            return False
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple documents.
        
        Args:
            texts: List of text strings
            
        Returns:
            List of embedding vectors
        """
        return self.embeddings.embed_documents(texts)
    
    def embed_query(self, text: str) -> List[float]:
        """
        Generate embedding for a single query.
        
        Args:
            text: Query text
            
        Returns:
            Embedding vector
        """
        return self.embeddings.embed_query(text)
    
    def get_embeddings_instance(self):
        """Get the underlying embeddings instance for LangChain."""
        return self.embeddings
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get current model information."""
        model_info = self.EMBEDDING_MODELS.get(self.model_name, {})
        return {
            "model_name": self.model_name,
            "name": model_info.get("name", self.model_name),
            "description": model_info.get("description", ""),
            "dimensions": model_info.get("dimensions", "unknown"),
            "max_tokens": model_info.get("max_tokens", "unknown")
        }
    
    @classmethod
    def get_available_models(cls) -> Dict[str, Dict]:
        """Get all available embedding models."""
        return cls.EMBEDDING_MODELS
    
    @classmethod
    def get_model_names(cls) -> List[str]:
        """Get list of model names."""
        return list(cls.EMBEDDING_MODELS.keys())
