"""Essay grading orchestrator with multimodal document support."""

import os
from typing import Dict, Any, List, Callable, Optional
from pathlib import Path
from loguru import logger

from ..ingestion import DocumentLoader, DocumentPreprocessor
from ..rag import RAGPipeline


class EssayGrader:
    """Orchestrate essay grading with RAG pipeline and multimodal support."""
    
    def __init__(
        self,
        config: Dict[str, Any],
        provider: str = "groq",
        model_name: str = None,
        enable_image_extraction: Optional[bool] = None,
        enable_vision_captioning: Optional[bool] = None
    ):
        """
        Initialize essay grader.
        
        Args:
            config: Configuration dictionary
            provider: LLM provider ("groq" or "huggingface")
            model_name: Model name override (optional)
            enable_image_extraction: Enable image extraction from documents
            enable_vision_captioning: Enable vision captioning for images
        """
        self.config = config
        
        # Resolve multimodal settings from argument override, env variables, or config file
        if enable_image_extraction is None:
            env_val = os.getenv('ENABLE_IMAGE_EXTRACTION')
            if env_val is not None:
                self.enable_image_extraction = env_val.lower() == 'true'
            else:
                self.enable_image_extraction = config.get('multimodal', {}).get('enable_image_extraction', True)
        else:
            self.enable_image_extraction = enable_image_extraction
            
        if enable_vision_captioning is None:
            env_val = os.getenv('ENABLE_VISION_CAPTIONING')
            if env_val is not None:
                self.enable_vision_captioning = env_val.lower() == 'true'
            else:
                self.enable_vision_captioning = config.get('multimodal', {}).get('enable_vision_captioning', True)
        else:
            self.enable_vision_captioning = enable_vision_captioning
        
        # Initialize components
        self.document_loader = DocumentLoader(enable_multimodal=self.enable_image_extraction)
        self.preprocessor = DocumentPreprocessor(
            chunk_size=config['document_processing']['chunk_size'],
            chunk_overlap=config['document_processing']['chunk_overlap'],
            separators=config['document_processing']['separators'],
            include_image_captions=self.enable_vision_captioning
        )
        self.rag_pipeline = RAGPipeline(config, provider=provider, model_name=model_name)
        
        logger.info("EssayGrader initialized with multimodal support")
    
    def ingest_course_materials(
        self,
        file_paths: List[Path],
        course_id: Optional[str] = None,
        progress_callback: Callable = None,
        enable_vision: bool = None,
        vision_model: str = None
    ) -> Dict[str, Any]:
        """
        Ingest course material documents (PDF, PPTX) with image support.
        
        Args:
            file_paths: List of paths to document files
            course_id: Optional course ID to select collection
            progress_callback: Optional callback(current, total, message)
            enable_vision: Override vision processing setting
            vision_model: Vision model to use for captioning
            
        Returns:
            Ingestion result dictionary
        """
        logger.info(f"Ingesting {len(file_paths)} files with multimodal support...")
        
        try:
            # Apply vision settings if provided
            if enable_vision is not None:
                self.document_loader.toggle_image_extraction(enable_vision)
                self.document_loader.toggle_vision_captioning(enable_vision)
                self.preprocessor.toggle_image_captions(enable_vision)
                
            if vision_model and enable_vision:
                self.document_loader.multimodal_loader._vision_model = vision_model
                if self.document_loader.multimodal_loader.vision_captioner:
                    self.document_loader.multimodal_loader.vision_captioner.switch_model(vision_model)
            
            # Filter supported files
            supported_extensions = ['.pdf', '.pptx']
            valid_paths = [
                p for p in file_paths 
                if p.suffix.lower() in supported_extensions
            ]
            
            if not valid_paths:
                return {
                    "success": False,
                    "message": "Tidak ada file yang didukung (PDF/PPTX)",
                    "documents_loaded": 0,
                    "chunks_created": 0,
                    "images_extracted": 0,
                    "captions_generated": 0
                }
            
            # Load documents with multimodal support
            if progress_callback:
                progress_callback(0, 100, "Memuat dokumen...")
            
            result = self.document_loader.load_multiple_documents(
                valid_paths,
                progress_callback=progress_callback
            )
            
            documents = result.get('documents', [])
            images = result.get('images', [])
            captions = result.get('captions', [])
            
            if not documents and not captions:
                return {
                    "success": False,
                    "message": "Tidak ada konten yang dapat diproses",
                    "documents_loaded": 0,
                    "chunks_created": 0,
                    "images_extracted": len(images),
                    "captions_generated": len(captions)
                }
            
            # Process with preprocessor (includes image captions)
            if progress_callback:
                progress_callback(70, 100, "Memproses chunk...")
            
            chunks = self.preprocessor.process_multimodal_content(
                documents=documents,
                captions=captions
            )
            
            # Add to vector store
            if progress_callback:
                progress_callback(90, 100, "Menyimpan ke database...")
            
            if chunks:
                self.rag_pipeline.vectorstore.add_documents(chunks, course_id=course_id)
            
            # Count text and image chunks
            text_chunks = len([c for c in chunks if c.metadata.get('content_type') != 'image_caption'])
            image_chunks = len([c for c in chunks if c.metadata.get('content_type') == 'image_caption'])
            
            if progress_callback:
                progress_callback(100, 100, "Selesai!")
            
            result_dict = {
                "success": True,
                "message": "Materi kuliah berhasil diproses",
                "documents_loaded": len(documents),
                "chunks_created": len(chunks),
                "text_chunks": text_chunks,
                "image_chunks": image_chunks,
                "images_extracted": len(images),
                "captions_generated": len(captions),
                "total_documents_in_db": self.rag_pipeline.vectorstore.get_count(course_id),
                "files_processed": result.get('files_processed', []),
                "errors": result.get('errors', []),
                "vision_enabled": enable_vision if enable_vision is not None else self.enable_vision_captioning,
                "vision_model_used": vision_model if vision_model else "default"
            }
            
            logger.info(f"Ingestion complete: {result_dict}")
            return result_dict
            
        except Exception as e:
            logger.error(f"Error during ingestion: {e}")
            return {
                "success": False,
                "message": f"Error: {str(e)}",
                "documents_loaded": 0,
                "chunks_created": 0,
                "images_extracted": 0,
                "captions_generated": 0
            }
    
    def ingest_course_materials_legacy(self, pdf_paths: List[Path]) -> Dict[str, Any]:
        """
        Legacy method for ingesting PDFs (backward compatibility).
        
        Args:
            pdf_paths: List of paths to PDF files
            
        Returns:
            Ingestion result dictionary
        """
        return self.ingest_course_materials(pdf_paths)
    
    def update_chunking_config(
        self,
        chunk_size: int = None,
        chunk_overlap: int = None
    ):
        """
        Update chunking configuration.
        
        Args:
            chunk_size: New chunk size
            chunk_overlap: New overlap size
        """
        self.preprocessor.update_config(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )
        logger.info("Chunking configuration updated")
    
    def toggle_image_extraction(self, enabled: bool):
        """Enable or disable image extraction."""
        self.enable_image_extraction = enabled
        self.document_loader.toggle_image_extraction(enabled)
        logger.info(f"Image extraction {'enabled' if enabled else 'disabled'}")
    
    def toggle_vision_captioning(self, enabled: bool):
        """Enable or disable vision captioning."""
        self.enable_vision_captioning = enabled
        self.document_loader.toggle_vision_captioning(enabled)
        self.preprocessor.toggle_image_captions(enabled)
        logger.info(f"Vision captioning {'enabled' if enabled else 'disabled'}")
    
    def grade_essay(
        self,
        question: str,
        essay: str,
        rubric: Dict[str, Any],
        course_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Grade a student essay with question context.
        
        Args:
            question: The question/prompt that was asked
            essay: Student essay/answer text
            rubric: Grading rubric
            course_id: Optional course ID to restrict retrieval context
            
        Returns:
            Grading results
        """
        logger.info("Grading essay with question context...")
        
        # Validate inputs
        if not question or not question.strip():
            return {
                "success": False,
                "error": "Pertanyaan tidak boleh kosong"
            }
        
        if not essay or not essay.strip():
            return {
                "success": False,
                "error": "Esai/Jawaban tidak boleh kosong"
            }
        
        if not rubric:
            return {
                "success": False,
                "error": "Rubrik tidak boleh kosong"
            }
        
        # Check if vector store has documents
        if self.rag_pipeline.vectorstore.get_count(course_id) == 0:
            return {
                "success": False,
                "error": "Tidak ada materi kuliah di database. Silakan unggah materi terlebih dahulu."
            }
        
        # Grade using RAG pipeline with question context
        result = self.rag_pipeline.grade_essay(question, essay, rubric, course_id=course_id)
        result['success'] = 'error' not in result
        
        return result
    
    def get_system_status(self, course_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get system status information.
        
        Args:
            course_id: Optional course ID to get stats for
            
        Returns:
            Status dictionary
        """
        vectorstore_info = self.rag_pipeline.get_vectorstore_info(course_id)
        chunking_config = self.preprocessor.get_config()
        llm_info = self.rag_pipeline.get_llm_info()
        embedding_info = self.rag_pipeline.get_embedding_info()
        retriever_config = self.rag_pipeline.get_retriever_config()
        
        # Build retrieval_info with reranking status
        retrieval_info = {
            "reranking_enabled": retriever_config.get('enable_reranking', True),
            "top_k": retriever_config.get('top_k', 5),
            "rerank_top_k": retriever_config.get('rerank_top_k', 3)
        }
        
        # Multimodal status
        multimodal_status = {
            "image_extraction_enabled": self.enable_image_extraction,
            "vision_captioning_enabled": self.enable_vision_captioning,
            "supported_formats": ['.pdf', '.pptx']
        }
        
        return {
            "vectorstore": vectorstore_info,
            "chunking_config": chunking_config,
            "llm_model": llm_info.get('model', self.config['llm']['model_name']),
            "llm_provider": llm_info.get('provider', 'groq'),
            "embedding_model": embedding_info.get('model', self.config['embeddings']['model_name']),
            "embedding_info": embedding_info,
            "retriever_config": retriever_config,
            "retrieval_info": retrieval_info,
            "multimodal": multimodal_status
        }
    
    def switch_llm(self, provider: str, model_name: str):
        """
        Switch LLM provider and model.
        
        Args:
            provider: LLM provider ("groq" or "huggingface")
            model_name: Model name
        """
        self.rag_pipeline.switch_llm(provider, model_name)
        logger.info(f"LLM switched to {provider}/{model_name}")
    
    def switch_embedding_model(self, new_model: str) -> Dict[str, Any]:
        """
        Switch embedding model.
        Note: This creates a new collection. Previous documents need to be re-uploaded.
        
        Args:
            new_model: New embedding model name
            
        Returns:
            Status dictionary
        """
        result = self.rag_pipeline.switch_embedding_model(new_model)
        if result['success']:
            self.config['embeddings']['model_name'] = new_model
            logger.info(f"Embedding model switched to {new_model}")
        return result
    
    def set_reranking(self, enable: bool) -> Dict[str, Any]:
        """
        Enable or disable reranking.
        
        Args:
            enable: True to enable, False to disable
            
        Returns:
            Status dictionary
        """
        result = self.rag_pipeline.set_reranking(enable)
        logger.info(f"Reranking {'enabled' if enable else 'disabled'}")
        return result
    
    def get_available_embedding_models(self) -> Dict[str, Dict]:
        """Get available embedding models."""
        from ..vectorstore.embeddings import EmbeddingGenerator
        return EmbeddingGenerator.get_available_models()
    
    def get_available_providers(self) -> Dict[str, Any]:
        """Get available LLM providers and models."""
        from ..rag.llm import LLMWrapper
        return LLMWrapper.get_available_providers()
    
    def get_available_vision_models(self) -> Dict[str, Dict]:
        """Get available vision captioning models."""
        from ..ingestion.vision_captioner import VisionCaptioner
        return VisionCaptioner.get_available_models()
    
    def clear_vector_store(self, course_id: Optional[str] = None):
        """
        Clear all documents from vector store for a course.
        
        Args:
            course_id: Optional course ID to clear collection for
        """
        self.rag_pipeline.vectorstore.clear(course_id=course_id)
        logger.info(f"Vector store cleared for course: {course_id}")
