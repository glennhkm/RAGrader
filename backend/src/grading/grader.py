"""Essay grading orchestrator with multimodal document support."""

from typing import Dict, Any, List, Callable, Optional
from pathlib import Path
from loguru import logger

from ..ingestion import DocumentLoader, DocumentPreprocessor
from ..rag import RAGPipeline
from ..utils.config import Settings, VisionSettings, get_settings
from ..vectorstore.embeddings import EmbeddingMismatchError
from ..vectorstore.filters import sanitize_chunk_metadata


class EssayGrader:
    """Orchestrate essay grading with RAG pipeline and multimodal support."""
    
    def __init__(
        self,
        config: Dict[str, Any],
        provider: str = "provider_chain",
        model_name: str = None,
        enable_image_extraction: Optional[bool] = None,
        enable_vision_captioning: Optional[bool] = None,
        vision_settings: Optional[VisionSettings] = None,
        settings: Optional[Settings] = None,
    ):
        """
        Initialize essay grader.
        
        Args:
            config: Configuration dictionary
            provider: LLM provider ("provider_chain", "groq", "openrouter", or "huggingface")
            model_name: Model name override (optional)
            enable_image_extraction: Enable image extraction from documents
            enable_vision_captioning: Enable vision captioning for images
            vision_settings: Multimodal settings (defaults to settings.vision)
            settings: Settings forwarded to every component (defaults to get_settings())
        """
        self.config = config
        self.settings = settings or get_settings()
        vision = vision_settings or self.settings.vision
        multimodal = config.get('multimodal', {}) or {}

        # Resolution: explicit argument -> config dict (config.yaml values are
        # already env-resolved) -> central settings (env / defaults).
        if enable_image_extraction is None:
            enable_image_extraction = multimodal.get('enable_image_extraction', vision.enable_image_extraction)
        if enable_vision_captioning is None:
            enable_vision_captioning = multimodal.get('enable_vision_captioning', vision.enable_vision_captioning)
        self.enable_image_extraction = bool(enable_image_extraction)
        self.enable_vision_captioning = bool(enable_vision_captioning)
        
        # Initialize components
        self.document_loader = DocumentLoader(enable_multimodal=self.enable_image_extraction,
                                              settings=self.settings)
        self.preprocessor = DocumentPreprocessor(
            chunk_size=config['document_processing']['chunk_size'],
            chunk_overlap=config['document_processing']['chunk_overlap'],
            separators=config['document_processing']['separators'],
            include_image_captions=self.enable_vision_captioning
        )
        self.rag_pipeline = RAGPipeline(config, provider=provider, model_name=model_name,
                                        settings=self.settings)
        
        logger.info("EssayGrader initialized with multimodal support")
    
    def ingest_course_materials(
        self,
        file_paths: List[Path],
        course_id: Optional[str] = None,
        progress_callback: Callable = None,
        enable_vision: bool = None,
        vision_model: str = None,
        module: Optional[str] = None,
        tags: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Ingest course material documents (PDF, PPTX, DOCX, TXT) with image support.
        
        Args:
            file_paths: List of paths to document files
            course_id: Optional course ID to select collection
            progress_callback: Optional callback(current, total, message)
            enable_vision: Override vision processing setting
            vision_model: Vision model to use for captioning
            module: Optional module/week identifier attached to chunk metadata
            tags: Optional arbitrary tag key-value pairs attached to chunk metadata
            
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
            supported_extensions = ['.pdf', '.pptx', '.docx', '.txt']
            valid_paths = [
                p for p in file_paths 
                if p.suffix.lower() in supported_extensions
            ]
            
            if not valid_paths:
                return {
                    "success": False,
                    "message": "No supported files (PDF/PPTX/DOCX/TXT)",
                    "documents_loaded": 0,
                    "chunks_created": 0,
                    "images_extracted": 0,
                    "captions_generated": 0
                }
            
            # Load documents with multimodal support
            if progress_callback:
                progress_callback(0, 100, "Loading documents...")
            
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
                    "message": "No processable content found",
                    "documents_loaded": 0,
                    "chunks_created": 0,
                    "images_extracted": len(images),
                    "captions_generated": len(captions)
                }
            
            # Process with preprocessor (includes image captions)
            if progress_callback:
                progress_callback(70, 100, "Chunking documents...")
            
            chunks = self.preprocessor.process_multimodal_content(
                documents=documents,
                captions=captions
            )
            
            # Add to vector store
            if progress_callback:
                progress_callback(90, 100, "Saving to the vector store...")
            
            extra_meta = sanitize_chunk_metadata(module=module, tags=tags)
            if chunks and extra_meta:
                for chunk in chunks:
                    chunk.metadata.update(extra_meta)

            if chunks:
                # Uploading the same Moodle file again is a replacement, not an
                # append operation. Remove prior chunks only after parsing works.
                for source_name in result.get('files_processed', []):
                    self.rag_pipeline.vectorstore.delete_document_by_source(
                        source_name=source_name,
                        course_id=course_id,
                    )
                self.rag_pipeline.vectorstore.add_documents(chunks, course_id=course_id)
            
            # Count text and image chunks
            text_chunks = len([c for c in chunks if c.metadata.get('content_type') != 'image_caption'])
            image_chunks = len([c for c in chunks if c.metadata.get('content_type') == 'image_caption'])
            
            if progress_callback:
                progress_callback(100, 100, "Done")
            
            result_dict = {
                "success": True,
                "message": "Course materials processed successfully",
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
            
        except EmbeddingMismatchError:
            raise
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
        course_id: Optional[str] = None,
        metadata_filter: Optional[Dict[str, Any]] = None,
        language: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Grade a student essay with question context.
        
        Args:
            question: The question/prompt that was asked
            essay: Student essay/answer text
            rubric: Grading rubric
            course_id: Optional course ID to restrict retrieval context
            metadata_filter: Optional Chroma metadata filter dict
            language: Optional prompt language override ("auto", "en", "id")
            
        Returns:
            Grading results
        """
        logger.info("Grading essay with question context...")
        
        # Validate inputs
        if not question or not question.strip():
            return {
                "success": False,
                "error": "Question must not be empty"
            }
        
        if not essay or not essay.strip():
            return {
                "success": False,
                "error": "Essay/answer must not be empty"
            }
        
        if rubric is None:
            return {
                "success": False,
                "error": "Rubric must not be empty"
            }
        
        # Check if vector store has documents
        if self.rag_pipeline.vectorstore.get_count(course_id) == 0:
            return {
                "success": False,
                "error": "No course materials in the vector store. Upload materials first."
            }
        
        # Grade using RAG pipeline with question context
        result = self.rag_pipeline.grade_essay(
            question=question,
            essay=essay,
            rubric=rubric,
            course_id=course_id,
            metadata_filter=metadata_filter,
            language=language,
        )
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
            "supported_formats": ['.pdf', '.pptx', '.docx', '.txt']
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
            provider: LLM provider ("provider_chain", "openai_compatible", "local",
                "groq", "openrouter", or "huggingface")
            model_name: Model name (any id the provider accepts)
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

    def delete_course_material_file(self, course_id: str, filename: str) -> bool:
        """
        Delete a single course material file and its vector chunks.
        
        Args:
            course_id: Moodle course ID
            filename: The name of the file to remove
            
        Returns:
            True if deletion was successful, False otherwise
        """
        success = self.rag_pipeline.vectorstore.delete_document_by_source(
            source_name=filename,
            course_id=course_id
        )
        return success
