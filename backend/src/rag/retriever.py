"""Retrieval component with optional reranking using BGE Reranker."""

from typing import List, Dict, Any, Optional
from langchain_core.documents import Document
from loguru import logger

from .reranker import BGEReranker, BM25Reranker


class Retriever:
    """Retrieve relevant documents with optional BGE reranking."""
    
    # Reranker types
    RERANKER_TYPES = {
        "bge": "bge-reranker-v2-m3 (Cross-Encoder via Pinecone API)",
        "bm25": "BM25 (Lexical Matching, Fast)"
    }
    
    def __init__(
        self,
        vectorstore,
        top_k: int = 20,
        enable_reranking: bool = True,
        rerank_top_k: int = 5,
        reranker_type: str = "bge",
        reranker_model: str = "bge-reranker-v2-m3",
        **kwargs  # Accept extra args for compatibility
    ):
        """
        Initialize retriever.
        
        Args:
            vectorstore: VectorStore instance
            top_k: Number of documents to retrieve initially
            enable_reranking: Whether to enable reranking
            rerank_top_k: Number of documents after reranking
            reranker_type: Type of reranker ("bge" or "bm25")
            reranker_model: Model name for BGE reranker
        """
        self.vectorstore = vectorstore
        self.top_k = top_k
        self.enable_reranking = enable_reranking
        self.rerank_top_k = rerank_top_k
        self.reranker_type = reranker_type
        self.reranker_model = reranker_model
        
        # Initialize reranker
        self._reranker = None
        if enable_reranking:
            self._init_reranker()
        
        logger.info(
            f"Retriever initialized: top_k={top_k}, "
            f"reranking={'enabled' if enable_reranking else 'disabled'}, "
            f"reranker_type={reranker_type}"
        )
    
    def _init_reranker(self):
        """Initialize the reranker based on configuration."""
        try:
            if self.reranker_type == "bge":
                self._reranker = BGEReranker(
                    model_name=self.reranker_model
                )
                logger.info(f"✅ BGE Reranker initialized: {self.reranker_model}")
            else:
                self._reranker = BM25Reranker()
                logger.info("BM25 Reranker initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize {self.reranker_type} reranker: {e}")
            logger.info("Falling back to BM25 reranker")
            self._reranker = BM25Reranker()
            self.reranker_type = "bm25"
    
    def set_reranker_type(self, reranker_type: str, model_name: str = None) -> Dict[str, Any]:
        """
        Switch reranker type.
        
        Args:
            reranker_type: "bge" or "bm25"
            model_name: Model name for BGE reranker
            
        Returns:
            Status dictionary
        """
        old_type = self.reranker_type
        self.reranker_type = reranker_type
        
        if model_name:
            self.reranker_model = model_name
        
        self._init_reranker()
        
        return {
            "success": True,
            "reranker_type": reranker_type,
            "previous_type": old_type,
            "model": self.reranker_model if reranker_type == "bge" else "BM25"
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
        
        # Initialize reranker if enabling and not already initialized
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
            "reranker_model": self.reranker_model if self.reranker_type == "bge" else "BM25",
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
            reranker_type: Type of reranker ("bge" or "bm25")
        """
        if top_k is not None:
            self.top_k = top_k
        if enable_reranking is not None:
            self.enable_reranking = enable_reranking
            if enable_reranking and self._reranker is None:
                self._init_reranker()
        if rerank_top_k is not None:
            self.rerank_top_k = rerank_top_k
        if reranker_type is not None and reranker_type != self.reranker_type:
            self.reranker_type = reranker_type
            self._init_reranker()
        
        logger.info(
            f"Retriever config updated: top_k={self.top_k}, "
            f"reranking={self.enable_reranking}, reranker={self.reranker_type}"
        )
    
    def retrieve(self, query: str, course_id: Optional[str] = None) -> List[Document]:
        """
        Retrieve relevant documents with optional reranking.
        
        Args:
            query: Query text
            course_id: Optional course ID to retrieve from
            
        Returns:
            List of relevant documents
        """
        # Get initial results from vector store (semantic search)
        k_val = self.top_k if self.enable_reranking else self.rerank_top_k
        results = self.vectorstore.similarity_search(
            query=query,
            k=k_val,
            course_id=course_id
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
    
    def retrieve_with_scores(self, query: str, course_id: Optional[str] = None) -> List[tuple[Document, float]]:
        """
        Retrieve documents with relevance scores.
        
        Args:
            query: Query text
            course_id: Optional course ID to retrieve from
            
        Returns:
            List of (document, score) tuples
        """
        # Get initial results from vector store
        k_val = self.top_k if self.enable_reranking else self.rerank_top_k
        results = self.vectorstore.similarity_search(
            query=query,
            k=k_val,
            course_id=course_id
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
        
        if hasattr(self._reranker, 'get_model_info'):
            return self._reranker.get_model_info()
        else:
            return {
                "type": self.reranker_type,
                "model": "BM25" if self.reranker_type == "bm25" else self.reranker_model
            }
