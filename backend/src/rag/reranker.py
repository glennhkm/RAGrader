"""Reranking component using BAAI/bge-reranker-v2-m3 via Pinecone Inference API."""

from typing import List, Dict, Any, Tuple
from langchain_core.documents import Document
from loguru import logger

from ..utils.config import get_settings

try:
    from pinecone import Pinecone
    PINECONE_AVAILABLE = True
except ImportError:
    PINECONE_AVAILABLE = False
    logger.warning("Pinecone not installed. Run: pip install -U pinecone")


class BGEReranker:
    """
    Reranker using BAAI/bge-reranker-v2-m3 model via Pinecone Inference API.
    
    This is a high-performance, multilingual cross-encoder reranker that:
    - Works well on messy data and short queries
    - Returns medium-length passages (1-2 paragraphs)
    - Provides relevance scores between query-document pairs
    
    Model: BAAI/bge-reranker-v2-m3
    - Multilingual support (100+ languages)
    - Max input tokens: 1024
    - Hosted on Pinecone (cloud-based, no local compute)
    
    Reference: https://docs.pinecone.io/models/bge-reranker-v2-m3
    """
    
    # Available reranker models on Pinecone
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
    
    def __init__(
        self,
        model_name: str = "bge-reranker-v2-m3",
        api_key: str = None,
        truncate: str = "END",
        **kwargs  # Accept extra args for compatibility
    ):
        """
        Initialize BGE Reranker with Pinecone Inference API.
        
        Args:
            model_name: Pinecone model name for reranking (default: bge-reranker-v2-m3)
            api_key: Pinecone API key (defaults to PINECONE_API_KEY env var)
            truncate: How to handle long documents ("END" or "NONE")
        """
        if not PINECONE_AVAILABLE:
            raise ImportError(
                "Pinecone is not installed. Please install it with: pip install -U pinecone"
            )
        
        self.model_name = model_name
        self.truncate = truncate
        
        # Get API key
        self._api_key = api_key or get_settings().reranker.pinecone_api_key
        
        if not self._api_key:
            raise ValueError(
                "PINECONE_API_KEY not found. "
                "Please set it in .env file or pass api_key parameter"
            )
        
        # Initialize Pinecone client
        self.client = Pinecone(api_key=self._api_key)
        
        logger.info(f"✅ BGE Reranker initialized: {model_name}")
        logger.info("   Provider: Pinecone Inference API (Cloud)")
    
    def rerank(
        self,
        query: str,
        documents: List[Document],
        top_k: int = 3
    ) -> List[Tuple[Document, float]]:
        """
        Rerank documents based on relevance to query.
        
        Args:
            query: Query text
            documents: List of Document objects to rerank
            top_k: Number of top documents to return
            
        Returns:
            List of (Document, score) tuples, sorted by relevance (highest first)
        """
        if not documents:
            return []
        
        logger.info(f"Reranking {len(documents)} documents with BGE Reranker...")
        
        try:
            # Prepare documents for Pinecone API
            # Format: list of dicts with 'id' and 'text' keys
            doc_inputs = []
            for i, doc in enumerate(documents):
                doc_inputs.append({
                    "id": f"doc_{i}",
                    "text": doc.page_content[:4000]  # Limit text length for safety
                })
            
            # Call Pinecone rerank API
            result = self.client.inference.rerank(
                model=self.model_name,
                query=query,
                documents=doc_inputs,
                top_n=min(top_k, len(documents)),
                return_documents=False,  # We already have the documents
                parameters={
                    "truncate": self.truncate
                }
            )
            
            # Build result list with original documents and scores
            reranked = []
            for item in result.data:
                idx = item.index
                score = item.score
                if idx < len(documents):
                    reranked.append((documents[idx], score))
            
            logger.info(
                f"Reranked {len(documents)} documents to top {len(reranked)} "
                f"(scores: {[f'{s:.4f}' for _, s in reranked]})"
            )
            
            return reranked
            
        except Exception as e:
            logger.error(f"Pinecone rerank failed: {e}")
            logger.warning("Falling back to original order with default scores")
            # Return original order with placeholder scores
            return [(doc, 0.5) for doc in documents[:top_k]]
    
    def rerank_documents(
        self,
        query: str,
        documents: List[Document],
        top_k: int = 3
    ) -> List[Document]:
        """
        Rerank documents and return only Document objects (without scores).
        
        Args:
            query: Query text
            documents: List of Document objects to rerank
            top_k: Number of top documents to return
            
        Returns:
            List of reranked Document objects
        """
        reranked = self.rerank(query, documents, top_k)
        return [doc for doc, _ in reranked]
    
    def compute_scores(
        self,
        query: str,
        documents: List[str]
    ) -> List[float]:
        """
        Compute relevance scores for query-document pairs.
        
        Args:
            query: Query text
            documents: List of document texts
            
        Returns:
            List of relevance scores in original document order
        """
        if not documents:
            return []
        
        try:
            # Prepare documents
            doc_inputs = [{"id": f"doc_{i}", "text": text[:4000]} for i, text in enumerate(documents)]
            
            # Call API with all documents
            result = self.client.inference.rerank(
                model=self.model_name,
                query=query,
                documents=doc_inputs,
                top_n=len(documents),  # Return all with scores
                return_documents=False,
                parameters={"truncate": self.truncate}
            )
            
            # Map scores back to original order
            scores = [0.0] * len(documents)
            for item in result.data:
                if item.index < len(scores):
                    scores[item.index] = item.score
            
            return scores
            
        except Exception as e:
            logger.error(f"Score computation failed: {e}")
            return [0.5] * len(documents)
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get information about current reranker model."""
        model_info = self.RERANKER_MODELS.get(self.model_name, {})
        return {
            "model_name": self.model_name,
            "mode": "cloud",
            "provider": "pinecone",
            "name": model_info.get("name", self.model_name),
            "description": model_info.get("description", ""),
            "max_tokens": model_info.get("max_tokens", 1024),
            "truncate": self.truncate
        }


class BM25Reranker:
    """Fallback BM25-based reranker (lexical matching)."""
    
    def __init__(self):
        """Initialize BM25 reranker."""
        from rank_bm25 import BM25Okapi
        self.BM25Okapi = BM25Okapi
        logger.info("BM25 Reranker initialized (fallback)")
    
    def rerank(
        self,
        query: str,
        documents: List[Document],
        top_k: int = 5
    ) -> List[Tuple[Document, float]]:
        """
        Rerank documents using BM25.
        
        Args:
            query: Query text
            documents: List of Document objects
            top_k: Number of top documents to return
            
        Returns:
            List of (Document, score) tuples
        """
        if not documents:
            return []
        
        # Tokenize documents
        tokenized_docs = [doc.page_content.split() for doc in documents]
        
        # Create BM25 index
        bm25 = self.BM25Okapi(tokenized_docs)
        
        # Get scores
        tokenized_query = query.split()
        scores = bm25.get_scores(tokenized_query)
        
        # Pair and sort
        doc_score_pairs = list(zip(documents, scores))
        doc_score_pairs.sort(key=lambda x: x[1], reverse=True)
        
        result = doc_score_pairs[:top_k]
        logger.info(f"BM25 reranked to top {len(result)} documents")
        
        return result
    
    def rerank_documents(
        self,
        query: str,
        documents: List[Document],
        top_k: int = 3
    ) -> List[Document]:
        """Rerank and return only documents."""
        reranked = self.rerank(query, documents, top_k)
        return [doc for doc, _ in reranked]
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get reranker info."""
        return {
            "model_name": "BM25Okapi",
            "mode": "local",
            "provider": "rank_bm25",
            "description": "Lexical matching using BM25 algorithm"
        }


# Convenience alias for backward compatibility
LLMReranker = BGEReranker
