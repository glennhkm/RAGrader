"""Retrieval component with optional, pluggable reranking."""

from dataclasses import replace
from typing import List, Dict, Any, Optional
from langchain_core.documents import Document
from loguru import logger

from ..utils.config import RerankerSettings, get_settings
from .reranker import BaseReranker, BM25Reranker, create_reranker

_TYPE_ALIASES = {"bge": "pinecone", "disabled": "none", "cross_encoder": "local_cross_encoder"}


def _normalize_type(reranker_type: Optional[str]) -> str:
    value = (reranker_type or "pinecone").strip().lower()
    return _TYPE_ALIASES.get(value, value)


class Retriever:
    """Retrieve relevant documents with optional reranking."""
    
    # Supported reranker types (RERANKER_TYPE); "bge" is a legacy alias of "pinecone".
    RERANKER_TYPES = {
        "none": "Disabled (vector similarity order only)",
        "bm25": "BM25 (lexical matching, local, fast)",
        "local_cross_encoder": "Local cross-encoder (fastembed / sentence-transformers)",
        "http_rerank": "Standard /rerank API (Cohere, Jina, vLLM, TEI, Infinity, SiliconFlow)",
        "llm_rerank": "OpenAI-compatible chat model scoring passages",
        "pinecone": "bge-reranker-v2-m3 via Pinecone Inference (legacy 'bge')",
    }
    
    def __init__(
        self,
        vectorstore,
        top_k: int = 20,
        enable_reranking: bool = True,
        rerank_top_k: int = 5,
        reranker_type: str = "bge",
        reranker_model: str = "bge-reranker-v2-m3",
        reranker: Optional[BaseReranker] = None,
        settings: Optional[RerankerSettings] = None,
        **kwargs  # Accept extra args for compatibility
    ):
        """
        Initialize retriever.
        
        Args:
            vectorstore: VectorStore instance
            top_k: Number of documents to retrieve before reranking
            enable_reranking: Whether to enable reranking
            rerank_top_k: Number of documents kept (with or without reranking)
            reranker_type: none | bm25 | local_cross_encoder | http_rerank | llm_rerank |
                pinecone (legacy "bge")
            reranker_model: Model for the selected reranker
            reranker: Pre-built reranker (overrides type/model; used by tests)
            settings: Reranker settings for endpoints/keys (defaults to get_settings().reranker)
        """
        self.vectorstore = vectorstore
        self.top_k = top_k
        self.enable_reranking = enable_reranking
        self.rerank_top_k = rerank_top_k
        self.reranker_type = _normalize_type(reranker_type)
        self.reranker_model = reranker_model
        self._settings = settings
        # Set when the configured reranker could not start and BM25 is used instead.
        self.requested_reranker_type = self.reranker_type
        self.reranker_error: Optional[str] = None
        
        self._reranker: Optional[BaseReranker] = reranker
        if reranker is not None:
            self.reranker_type = getattr(reranker, "kind", self.reranker_type)
        elif enable_reranking:
            self._init_reranker()
        
        logger.info(
            f"Retriever initialized: top_k={top_k}, "
            f"reranking={'enabled' if enable_reranking else 'disabled'}, "
            f"reranker_type={self.reranker_type}"
        )

    def _reranker_settings(self) -> RerankerSettings:
        base = self._settings or get_settings().reranker
        return replace(base, enabled=True, type=self.reranker_type, model=self.reranker_model,
                       top_k=self.top_k, rerank_top_k=self.rerank_top_k)
    
    def _init_reranker(self):
        """Initialize the configured reranker, falling back to BM25 if it cannot start."""
        if self.reranker_type == "none":
            self._reranker = None
            return
        self.requested_reranker_type = self.reranker_type
        self.reranker_error = None
        try:
            self._reranker = create_reranker(self._reranker_settings())
            logger.info(f"Reranker initialized: {self.reranker_type} ({self.reranker_model})")
        except Exception as e:
            # Grading keeps working, but this is a misconfiguration the operator
            # must see: log it as an error and report it in the status endpoints.
            self.reranker_error = str(e)
            logger.error(
                f"Configured reranker {self.reranker_type} ({self.reranker_model}) failed to start: {e}. "
                "Falling back to BM25; fix the RERANKER_* settings to restore it."
            )
            self._reranker = BM25Reranker()
            self.reranker_type = "bm25"
    
    def set_reranker_type(self, reranker_type: str, model_name: str = None) -> Dict[str, Any]:
        """
        Switch reranker type.
        
        Args:
            reranker_type: Any RERANKER_TYPES key (or legacy "bge")
            model_name: Model name for the reranker
            
        Returns:
            Status dictionary
        """
        old_type = self.reranker_type
        self.reranker_type = _normalize_type(reranker_type)
        if model_name:
            self.reranker_model = model_name
        self._init_reranker()
        
        return {
            "success": True,
            "reranker_type": self.reranker_type,
            "previous_type": old_type,
            "model": "BM25" if self.reranker_type == "bm25" else self.reranker_model
        }
    
    def set_reranking(self, enable: bool) -> Dict[str, Any]:
        """
        Enable or disable reranking.
        
        Args:
            enable: True to enable, False to disable
            
        Returns:
            Status dictionary
        """
        old_state = self.enable_reranking
        self.enable_reranking = enable
        
        if enable and self._reranker is None:
            self._init_reranker()
        
        status = "enabled" if enable else "disabled"
        logger.info(f"Reranking {status}")
        
        return {
            "success": True,
            "reranking_enabled": enable,
            "previous_state": old_state,
            "message": f"Reranking {status}"
        }
    
    def get_config(self) -> Dict[str, Any]:
        """Get current retriever configuration."""
        return {
            "top_k": self.top_k,
            "enable_reranking": self.enable_reranking,
            "rerank_top_k": self.rerank_top_k,
            "reranker_type": self.reranker_type,
            "reranker_model": "BM25" if self.reranker_type == "bm25" else self.reranker_model,
            "requested_reranker_type": self.requested_reranker_type,
            "reranker_fallback": self.reranker_error is not None,
            "reranker_error": self.reranker_error,
            "available_rerankers": self.RERANKER_TYPES
        }
    
    def update_config(
        self,
        top_k: int = None,
        enable_reranking: bool = None,
        rerank_top_k: int = None,
        reranker_type: str = None
    ):
        """
        Update retriever configuration.
        
        Args:
            top_k: Number of documents to retrieve
            enable_reranking: Enable/disable reranking
            rerank_top_k: Number of documents after reranking
            reranker_type: Any RERANKER_TYPES key (or legacy "bge")
        """
        if top_k is not None:
            self.top_k = top_k
        if enable_reranking is not None:
            self.enable_reranking = enable_reranking
            if enable_reranking and self._reranker is None:
                self._init_reranker()
        if rerank_top_k is not None:
            self.rerank_top_k = rerank_top_k
        if reranker_type is not None and _normalize_type(reranker_type) != self.reranker_type:
            self.reranker_type = _normalize_type(reranker_type)
            self._init_reranker()
        
        logger.info(
            f"Retriever config updated: top_k={self.top_k}, "
            f"reranking={self.enable_reranking}, reranker={self.reranker_type}"
        )
    
    def _search_vectorstore(
        self,
        query: str,
        course_id: Optional[str] = None,
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> List[Document]:
        """Run initial similarity search on the vector store."""
        # Over-fetch top_k candidates only when a reranker will narrow them down.
        reranking = self.enable_reranking and self._reranker is not None
        k_val = self.top_k if reranking else self.rerank_top_k
        return self.vectorstore.similarity_search(
            query=query,
            k=k_val,
            filter=metadata_filter,
            course_id=course_id,
        )

    def retrieve(
        self,
        query: str,
        course_id: Optional[str] = None,
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> List[Document]:
        """
        Retrieve relevant documents with optional metadata filter and reranking.
        
        Args:
            query: Query text
            course_id: Optional course ID / namespace to retrieve from
            metadata_filter: Optional Chroma metadata filter dict
            
        Returns:
            List of relevant documents
        """
        # Get initial results from vector store (semantic search)
        results = self._search_vectorstore(
            query=query,
            course_id=course_id,
            metadata_filter=metadata_filter,
        )
        
        if not results:
            logger.warning("No documents retrieved")
            return []
        
        # Apply reranking if enabled
        if self.enable_reranking and len(results) > 1 and self._reranker is not None:
            results = self._reranker.rerank_documents(
                query=query,
                documents=results,
                top_k=self.rerank_top_k
            )
        
        return results
    
    def retrieve_with_scores(
        self,
        query: str,
        course_id: Optional[str] = None,
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> List[tuple[Document, float]]:
        """
        Retrieve documents with relevance scores and optional metadata filter.
        
        Args:
            query: Query text
            course_id: Optional course ID / namespace to retrieve from
            metadata_filter: Optional Chroma metadata filter dict
            
        Returns:
            List of (document, score) tuples
        """
        # Get initial results from vector store
        results = self._search_vectorstore(
            query=query,
            course_id=course_id,
            metadata_filter=metadata_filter,
        )
        
        if not results:
            logger.warning("No documents retrieved")
            return []
        
        # Apply reranking if enabled and get scores
        if self.enable_reranking and len(results) > 1 and self._reranker is not None:
            results_with_scores = self._reranker.rerank(
                query=query,
                documents=results,
                top_k=self.rerank_top_k
            )
            logger.info(f"Retrieved and reranked {len(results_with_scores)} documents with scores")
            return results_with_scores
        else:
            # Return without reranking scores (use placeholder scores)
            results_with_scores = [(doc, 1.0) for doc in results]
            logger.info(f"Retrieved {len(results_with_scores)} documents")
            return results_with_scores
    
    def get_reranker_info(self) -> Dict[str, Any]:
        """Get information about current reranker."""
        if self._reranker is None:
            return {"status": "not initialized"}
        return self._reranker.get_model_info()
