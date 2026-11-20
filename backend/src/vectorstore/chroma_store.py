"""ChromaDB vector store management with dynamic embedding support."""

import time
from pathlib import Path
from typing import List, Optional, Dict, Any
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from loguru import logger
import chromadb
from chromadb.errors import NotFoundError

from .embeddings import EmbeddingGenerator
from .filters import build_collection_name


class VectorStore:
    """Manage ChromaDB vector store for course materials with dynamic embedding support."""
    
    def __init__(
        self,
        persist_directory: Path,
        collection_name: str = "course_materials",
        embedding_model: str = "BAAI/bge-m3",
        device: str = "cpu",
        client_mode: str = "persistent",
        host: str = "localhost",
        port: int = 8000,
        ssl: bool = False,
    ):
        """
        Initialize vector store.
        
        Args:
            persist_directory: Directory to persist ChromaDB
            collection_name: Base name of the collection
            embedding_model: HuggingFace embedding model name
            device: Device for embeddings ('cpu' or 'cuda')
            client_mode: Chroma client mode ('persistent' or 'http')
            host: Chroma server host in HTTP mode
            port: Chroma server port in HTTP mode
            ssl: Whether the Chroma HTTP connection uses TLS
        """
        self.persist_directory = Path(persist_directory)
        self.base_collection_name = collection_name
        self.current_embedding_model = embedding_model
        
        # Ensure directory exists
        self.persist_directory.mkdir(parents=True, exist_ok=True)
        
        # Initialize embeddings
        self.embedding_generator = EmbeddingGenerator(
            model_name=embedding_model,
            device=device
        )
        
        # Embedded Chroma is suitable for one process only. Replicated API
        # deployments use one Chroma server through HttpClient.
        self.client_mode = str(client_mode).lower()
        if self.client_mode == "http":
            self.client = chromadb.HttpClient(
                host=str(host),
                port=int(port),
                ssl=bool(ssl),
            )
            self.client.heartbeat()
            logger.info(f"Connected to Chroma server at {host}:{port}")
        elif self.client_mode == "persistent":
            self.client = chromadb.PersistentClient(path=str(self.persist_directory))
            logger.info(f"Using embedded Chroma at {self.persist_directory}")
        else:
            raise ValueError("CHROMA_CLIENT_MODE must be 'persistent' or 'http'")
        
        # Cache of LangChain Chroma vectorstores
        self._vectorstores: Dict[str, Chroma] = {}
        
        logger.info(f"VectorStore client initialized pointing to {self.persist_directory}")
        logger.info(f"Default base collection: {self.collection_name}")
        logger.info(f"Embedding model: {embedding_model}")

    def heartbeat(self) -> bool:
        """Check that the Chroma backend is reachable."""
        self.client.heartbeat()
        return True
    
    def _get_collection_name(self, course_id: Optional[str] = None) -> str:
        """Generate a Chroma-safe collection name from embedding model and namespace."""
        return build_collection_name(
            base_collection_name=self.base_collection_name,
            embedding_model=self.current_embedding_model,
            namespace=course_id,
        )
            
    @property
    def collection_name(self) -> str:
        """Returns the default collection name for backward compatibility."""
        return self._get_collection_name(None)
        
    def _get_vectorstore(self, course_id: Optional[str] = None) -> Chroma:
        """Get or create the Chroma vector store instance for a given course."""
        col_name = self._get_collection_name(course_id)
        if self.client_mode == "http":
            # Do not retain a process-local collection wrapper in replicated
            # mode. Another replica can delete and recreate the collection.
            return Chroma(
                client=self.client,
                collection_name=col_name,
                embedding_function=self.embedding_generator.get_embeddings_instance(),
            )
        if col_name not in self._vectorstores:
            self._vectorstores[col_name] = Chroma(
                client=self.client,
                collection_name=col_name,
                embedding_function=self.embedding_generator.get_embeddings_instance()
            )
            logger.info(f"Loaded/Created Chroma collection: {col_name}")
        return self._vectorstores[col_name]
    
    def switch_embedding_model(self, new_model: str) -> Dict[str, Any]:
        """
        Switch to a different embedding model.
        This will update embedding generator and clear cached vectorstores.
        
        Args:
            new_model: New embedding model name
            
        Returns:
            Status dictionary
        """
        if new_model == self.current_embedding_model:
            return {
                "success": True,
                "message": f"Already using {new_model}",
                "collection": self._get_collection_name(),
                "document_count": self.get_count()
            }
        
        try:
            logger.info(f"Switching embedding model from {self.current_embedding_model} to {new_model}")
            
            # Switch embedding generator
            self.embedding_generator.switch_model(new_model)
            
            # Update state
            self.current_embedding_model = new_model
            
            # Clear vectorstore cache so they reload with the new embedding function
            self._vectorstores.clear()
            
            return {
                "success": True,
                "message": f"Switched to {new_model}",
                "collection": self._get_collection_name(),
                "document_count": self.get_count()
            }
            
        except Exception as e:
            logger.error(f"Error switching embedding model: {e}")
            return {
                "success": False,
                "message": str(e),
                "collection": self._get_collection_name(),
                "document_count": self.get_count()
            }
    
    def add_documents(
        self, 
        documents: List[Document],
        course_id: Optional[str] = None,
        batch_size: int = 10,
        max_retries: int = 3,
        retry_delay: float = 5.0
    ) -> List[str]:
        """
        Add documents to vector store with batching and retry logic.
        
        Uses batching to avoid timeout errors with HuggingFace API.
        
        Args:
            documents: List of Document objects
            course_id: Optional course ID to select collection
            batch_size: Number of documents per batch (default: 10)
            max_retries: Maximum retries per batch on failure
            retry_delay: Delay between retries in seconds
            
        Returns:
            List of document IDs
        """
        if not documents:
            logger.warning("No documents to add")
            return []
        
        total_docs = len(documents)
        col_name = self._get_collection_name(course_id)
        logger.info(f"Adding {total_docs} documents to Chroma collection: {col_name}...")
        logger.info(f"📦 Using batch size: {batch_size}, max retries: {max_retries}")
        
        all_ids = []
        num_batches = (total_docs + batch_size - 1) // batch_size
        
        # Get dynamic vector store
        vs = self._get_vectorstore(course_id)
        
        for batch_idx in range(num_batches):
            start_idx = batch_idx * batch_size
            end_idx = min(start_idx + batch_size, total_docs)
            batch = documents[start_idx:end_idx]
            
            logger.info(f"📤 Processing batch {batch_idx + 1}/{num_batches} ({len(batch)} documents)...")
            
            # Retry logic for each batch
            for attempt in range(max_retries):
                try:
                    # LangChain Chroma uses add_documents
                    ids = vs.add_documents(batch)
                    all_ids.extend(ids)
                    logger.info(f"   ✅ Batch {batch_idx + 1} completed successfully")
                    
                    # Small delay between batches to avoid rate limiting
                    if batch_idx < num_batches - 1:
                        time.sleep(0.5)
                    
                    break  # Success, exit retry loop
                    
                except Exception as e:
                    logger.warning(f"   ⚠️ Batch {batch_idx + 1} attempt {attempt + 1}/{max_retries} failed: {e}")
                    
                    if attempt < max_retries - 1:
                        wait_time = retry_delay * (attempt + 1)
                        logger.info(f"   ⏳ Waiting {wait_time}s before retry...")
                        time.sleep(wait_time)
                    else:
                        logger.error(f"   ❌ Batch {batch_idx + 1} failed after {max_retries} attempts")
                        raise Exception(f"Failed to add batch {batch_idx + 1} after {max_retries} attempts: {e}")
        
        logger.info(f"✅ Successfully added all {total_docs} documents in {num_batches} batches")
        return all_ids
    
    def similarity_search(
        self,
        query: str,
        k: int = 5,
        filter: Optional[Dict[str, Any]] = None,
        course_id: Optional[str] = None
    ) -> List[Document]:
        """
        Search for similar documents in course collection.
        
        Args:
            query: Query text
            k: Number of results to return
            filter: Metadata filter
            course_id: Optional course ID to select collection
            
        Returns:
            List of relevant Document objects
        """
        vs = self._get_vectorstore(course_id)
        try:
            results = vs.similarity_search(
                query=query,
                k=k,
                filter=filter
            )
            logger.info(f"Found {len(results)} similar documents in collection: {vs._collection.name}")
            return results
            
        except Exception as e:
            logger.error(f"Error during similarity search: {e}")
            return []
    
    def similarity_search_with_score(
        self,
        query: str,
        k: int = 5,
        filter: Optional[Dict[str, Any]] = None,
        course_id: Optional[str] = None
    ) -> List[tuple[Document, float]]:
        """
        Search for similar documents with relevance scores in course collection.
        
        Args:
            query: Query text
            k: Number of results to return
            filter: Metadata filter
            course_id: Optional course ID to select collection
            
        Returns:
            List of (Document, score) tuples
        """
        vs = self._get_vectorstore(course_id)
        try:
            results = vs.similarity_search_with_score(
                query=query,
                k=k,
                filter=filter
            )
            logger.info(f"Found {len(results)} documents with scores in collection: {vs._collection.name}")
            return results
            
        except Exception as e:
            logger.error(f"Error during similarity search with score: {e}")
            return []
    
    def delete_document_by_source(self, source_name: str, course_id: Optional[str] = None) -> bool:
        """
        Delete all document chunks originating from a specific source/file.
        
        Args:
            source_name: The name of the file/source (e.g. 'syllabus.pdf')
            course_id: Optional course ID to select collection
            
        Returns:
            True if deletion was successful, False otherwise
        """
        col_name = self._get_collection_name(course_id)
        logger.info(f"Attempting to delete document '{source_name}' from collection: {col_name}")
        try:
            collection = self.client.get_collection(name=col_name)
            
            # Query for documents with matching source metadata.
            results = collection.get(where={"source": {"$eq": source_name}})
            
            if results and results.get('ids'):
                ids = results['ids']
                logger.info(f"Deleting {len(ids)} chunks for file '{source_name}' in collection '{col_name}'")
                collection.delete(ids=ids)
                return True
            else:
                # Normal on a first upload (replace-before-add) and on idempotent deletes.
                logger.info(f"No chunks found for file '{source_name}' in collection '{col_name}'")
                return False
                
        except NotFoundError:
            logger.info(f"Collection {col_name} does not exist; nothing to delete")
            return False
        except Exception as e:
            logger.error(f"Error deleting chunks for '{source_name}': {e}")
            return False

    def clear(self, course_id: Optional[str] = None):
        """
        Clear the collection for the course or default collection.
        
        Args:
            course_id: Optional course ID to select collection
        """
        col_name = self._get_collection_name(course_id)
        try:
            self.client.get_collection(name=col_name)
            self.client.delete_collection(name=col_name)
            logger.info(f"Vector store collection cleared: {col_name}")
            
            # Remove from cached dict
            if col_name in self._vectorstores:
                del self._vectorstores[col_name]
            
        except NotFoundError:
            logger.info(f"Vector store collection already absent: {col_name}")
            self._vectorstores.pop(col_name, None)
        except Exception as e:
            logger.error(f"Error clearing vector store collection {col_name}: {e}")
            raise
    
    def get_count(self, course_id: Optional[str] = None) -> int:
        """
        Get number of documents in course collection.
        
        Args:
            course_id: Optional course ID to select collection
            
        Returns:
            Number of documents
        """
        col_name = self._get_collection_name(course_id)
        try:
            collection = self.client.get_collection(name=col_name)
            return collection.count()
        except NotFoundError:
            return 0
        except Exception as e:
            logger.error(f"Could not get document count for collection {col_name}: {e}")
            raise
    
    def as_retriever(self, course_id: Optional[str] = None, **kwargs):
        """
        Get vector store as a retriever for LangChain.
        
        Args:
            course_id: Optional course ID to select collection
            **kwargs: Additional arguments for retriever
            
        Returns:
            VectorStoreRetriever instance
        """
        vs = self._get_vectorstore(course_id)
        return vs.as_retriever(**kwargs)
    
    def get_embedding_info(self, course_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get information about current embedding model and collection.
        
        Args:
            course_id: Optional course ID to select collection
            
        Returns:
            Embedding model information
        """
        col_name = self._get_collection_name(course_id)
        return {
            "model": self.current_embedding_model,
            "collection": col_name,
            "info": self.embedding_generator.get_model_info()
        }
    
    @classmethod
    def get_available_embedding_models(cls) -> Dict[str, Dict]:
        """Get all available embedding models."""
        return EmbeddingGenerator.get_available_models()
