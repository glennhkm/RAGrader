"""RAG pipeline orchestration."""

from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
from loguru import logger

from ..vectorstore import VectorStore
from ..vectorstore.embeddings import EmbeddingGenerator
from .llm import LLMWrapper
from .retriever import Retriever
from .prompt_builder import PromptBuilder
from ..ingestion.document_loader import DocumentLoader


class RAGPipeline:
    """End-to-end RAG pipeline for essay grading."""
    
    def __init__(self, config: Dict[str, Any], provider: str = "provider_chain", model_name: str = None):
        """
        Initialize RAG pipeline with configuration.
        
        Args:
            config: Configuration dictionary
            provider: LLM provider ("provider_chain", "groq", "openrouter", or "huggingface")
            model_name: Model name override (optional)
        """
        self.config = config
        self.provider = provider
        
        # Initialize components
        logger.info("Initializing RAG pipeline...")
        logger.info(f"Using provider: {provider}")
        
        # Vector store
        self.vectorstore = VectorStore(
            persist_directory=Path(config['vectorstore']['persist_directory']),
            collection_name=config['vectorstore']['collection_name'],
            embedding_model=config['embeddings']['model_name'],
            device=config['embeddings']['device'],
            client_mode=config['vectorstore'].get('client_mode', 'persistent'),
            host=config['vectorstore'].get('host', 'localhost'),
            port=config['vectorstore'].get('port', 8000),
            ssl=config['vectorstore'].get('ssl', False),
        )
        
        # Track current embedding model
        self.current_embedding_model = config['embeddings']['model_name']
        
        # Determine model name
        if model_name:
            llm_model = model_name
        else:
            llm_model = config['llm']['model_name']
        
        # LLM with provider support
        self.llm = LLMWrapper(
            model_name=llm_model,
            temperature=config['llm']['temperature'],
            max_new_tokens=config['llm']['max_new_tokens'],
            device=config['llm']['device'],
            provider=provider
        )
        
        # Store current LLM info
        self.current_model = llm_model
        
        # Retriever with BGE reranker support (via Pinecone)
        retrieval_config = config['retrieval']
        self.retriever = Retriever(
            vectorstore=self.vectorstore,
            top_k=retrieval_config['top_k'],
            enable_reranking=retrieval_config['enable_reranking'],
            rerank_top_k=retrieval_config['rerank_top_k'],
            reranker_type=retrieval_config.get('reranker_type', 'bge'),
            reranker_model=retrieval_config.get('reranker_model', 'bge-reranker-v2-m3')
        )
        
        # Prompt builder
        self.prompt_builder = PromptBuilder()
        
        logger.info("RAG pipeline initialized successfully")
    
    def grade_essay(
        self,
        question: str,
        essay: str,
        rubric: Dict[str, Any],
        course_id: Optional[str] = None,
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Grade an essay using RAG pipeline with optional namespace and metadata filter.
        
        Args:
            question: The question/prompt that was asked
            essay: Student essay/answer text
            rubric: Grading rubric
            course_id: Optional course ID / namespace to retrieve from
            metadata_filter: Optional Chroma metadata filter dict
            
        Returns:
            Grading results dictionary
        """
        logger.info("Starting essay grading with question context...")
        
        try:
            # Step 1: Retrieve relevant course materials based on QUESTION + ANSWER
            logger.info("Mengambil materi kuliah yang relevan...")
            # Combine question and answer for better retrieval
            query = f"Pertanyaan: {question}\n\nJawaban: {essay}"
            retrieved_docs = self.retriever.retrieve(
                query,
                course_id=course_id,
                metadata_filter=metadata_filter,
            )
            
            if not retrieved_docs:
                logger.warning("No relevant materials found within scope")
                return {
                    "success": False,
                    "score": 0,
                    "feedback": "Cannot grade: no relevant course materials found in the selected scope.",
                    "citations": [],
                    "confidence": 0.0,
                    "retrieved_documents": [],
                    "error": "No relevant materials retrieved",
                }
            
            # Step 2: Build prompt with question context
            logger.info("Membuat prompt penilaian...")
            prompt = self.prompt_builder.build_prompt(
                question=question,
                essay=essay,
                rubric=rubric,
                retrieved_docs=retrieved_docs
            )
            
            # Step 3: Generate grading with LLM
            logger.info("Menghasilkan penilaian dengan LLM...")
            llm_response = self.llm.generate(prompt)
            
            # Step 4: Parse response
            logger.info("Mengurai respons LLM...")
            result = self.prompt_builder.parse_llm_response(llm_response)
            
            # Add question and retrieved documents to result
            result['question'] = question
            result['retrieved_documents'] = [
                {
                    'content': doc.page_content[:200] + '...',
                    'source': doc.metadata.get('source', 'Tidak Diketahui'),
                    'page': doc.metadata.get('page', 'N/A')
                }
                for doc in retrieved_docs
            ]
            
            # Add prompt used for transparency/evaluation
            result['prompt_used'] = getattr(self.prompt_builder, 'last_prompt', None)
            
            logger.info(f"Penilaian selesai. Skor: {result.get('score', 'N/A')}")
            return result
            
        except Exception as e:
            logger.error(f"Error saat menilai: {e}")
            return {
                "score": 0,
                "feedback": f"Error saat menilai: {str(e)}",
                "citations": [],
                "confidence": 0.0,
                "error": str(e)
            }
    
    def get_vectorstore_info(self, course_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get information about vector store.
        
        Args:
            course_id: Optional course ID to get info for
            
        Returns:
            Vector store information
        """
        return {
            "document_count": self.vectorstore.get_count(course_id),
            "collection_name": self.vectorstore._get_collection_name(course_id)
        }
    
    def switch_llm(self, provider: str, model_name: str):
        """
        Switch LLM provider and model on the fly.
        
        Args:
            provider: LLM provider ("groq" or "huggingface")
            model_name: Model name
        """
        logger.info(f"Switching LLM to {provider}/{model_name}")
        
        self.llm = LLMWrapper(
            model_name=model_name,
            temperature=self.config['llm']['temperature'],
            max_new_tokens=self.config['llm']['max_new_tokens'],
            device=self.config['llm']['device'],
            provider=provider
        )
        
        self.provider = provider
        self.current_model = model_name
        
        logger.info(f"LLM switched successfully to {provider}/{model_name}")
    
    def get_llm_info(self) -> Dict[str, Any]:
        """Get current LLM information."""
        return {
            "provider": self.provider,
            "model": self.current_model,
            "runtime": self.llm.get_provider_info(),
            "available_providers": LLMWrapper.get_available_providers()
        }
    
    def switch_embedding_model(self, new_model: str) -> Dict[str, Any]:
        """
        Switch embedding model on the fly.
        Note: This creates a new collection for the new embedding model.
        Previous documents won't be accessible until re-uploaded.
        
        Args:
            new_model: New embedding model name
            
        Returns:
            Status dictionary
        """
        logger.info(f"Switching embedding model to {new_model}")
        
        result = self.vectorstore.switch_embedding_model(new_model)
        
        if result['success']:
            self.current_embedding_model = new_model
            # Update config for future reference
            self.config['embeddings']['model_name'] = new_model
        
        return result
    
    def set_reranking(self, enable: bool) -> Dict[str, Any]:
        """
        Enable or disable reranking in retriever.
        
        Args:
            enable: True to enable, False to disable
            
        Returns:
            Status dictionary
        """
        return self.retriever.set_reranking(enable)
    
    def get_retriever_config(self) -> Dict[str, Any]:
        """Get current retriever configuration."""
        return self.retriever.get_config()
    
    def get_embedding_info(self) -> Dict[str, Any]:
        """Get current embedding model information."""
        return self.vectorstore.get_embedding_info()
    
    @staticmethod
    def get_available_embedding_models() -> Dict[str, Dict]:
        """Get all available embedding models."""
        return EmbeddingGenerator.get_available_models()
    
    @staticmethod
    def extract_answer_from_document(
        file_path: Path,
        enable_vision: bool = False,
        include_image_captions: bool = True
    ) -> Dict[str, Any]:
        """
        Extract student answer from an uploaded document (PDF/DOCX/PPTX).
        
        This method extracts text content and optionally image captions from
        a document that contains the student's answer. The extracted content
        can then be used as the 'essay' input for grading.
        
        Args:
            file_path: Path to the uploaded document
            enable_vision: Whether to use vision model for image captioning
            include_image_captions: Whether to include image captions in the extracted text
            
        Returns:
            Dictionary with:
                - success: bool
                - extracted_text: str (combined text from document)
                - images_found: int (number of images found)
                - image_captions: List[str] (captions if vision enabled)
                - pages_processed: int
                - error: str (if any)
        """
        logger.info(f"Extracting answer from document: {file_path}")
        
        try:
            # Initialize document loader with multimodal support if vision is enabled
            loader = DocumentLoader(enable_multimodal=enable_vision)
            
            # Load the document
            result = loader.load_document(file_path)
            
            documents = result.get('documents', [])
            images = result.get('images', [])
            captions = result.get('captions', [])
            
            if not documents:
                return {
                    'success': False,
                    'extracted_text': '',
                    'images_found': 0,
                    'image_captions': [],
                    'pages_processed': 0,
                    'error': 'Tidak ada teks yang dapat diekstrak dari dokumen'
                }
            
            # Combine all document text
            text_parts = []
            pages_processed = set()
            
            for doc in documents:
                text_parts.append(doc.page_content)
                page = doc.metadata.get('page')
                if page is not None:
                    pages_processed.add(page)
            
            extracted_text = "\n\n".join(text_parts)
            
            # Process image captions if available and requested
            caption_texts = []
            if include_image_captions and captions:
                for cap in captions:
                    try:
                        caption_text = cap.caption if hasattr(cap, 'caption') else str(cap)
                        if caption_text:
                            caption_texts.append(caption_text)
                    except Exception:
                        continue
                
                # Append image captions to the extracted text
                if caption_texts:
                    extracted_text += "\n\n--- Deskripsi Gambar dalam Dokumen ---\n"
                    for i, caption in enumerate(caption_texts, 1):
                        extracted_text += f"\n[Gambar {i}]: {caption}"
            
            logger.info(f"Successfully extracted answer from document: "
                       f"{len(text_parts)} text sections, {len(images)} images")
            
            return {
                'success': True,
                'extracted_text': extracted_text.strip(),
                'images_found': len(images),
                'image_captions': caption_texts,
                'pages_processed': len(pages_processed) if pages_processed else len(documents),
                'error': None
            }
            
        except Exception as e:
            logger.error(f"Error extracting answer from document: {e}")
            return {
                'success': False,
                'extracted_text': '',
                'images_found': 0,
                'image_captions': [],
                'pages_processed': 0,
                'error': str(e)
            }
    
    def grade_essay_from_document(
        self,
        question: str,
        document_path: Path,
        rubric: Dict[str, Any],
        enable_vision: bool = False,
        include_image_captions: bool = True
    ) -> Dict[str, Any]:
        """
        Grade an essay from an uploaded document.
        
        This is a convenience method that combines extract_answer_from_document
        and grade_essay into a single call.
        
        Args:
            question: The question/prompt that was asked
            document_path: Path to the student's answer document
            rubric: Grading rubric
            enable_vision: Whether to use vision model for image captioning
            include_image_captions: Whether to include image captions
            
        Returns:
            Grading results dictionary with additional extraction info
        """
        logger.info(f"Grading essay from document: {document_path}")
        
        # First extract the answer from the document
        extraction_result = self.extract_answer_from_document(
            file_path=document_path,
            enable_vision=enable_vision,
            include_image_captions=include_image_captions
        )
        
        if not extraction_result['success']:
            return {
                'score': 0,
                'feedback': f"Gagal mengekstrak jawaban dari dokumen: {extraction_result['error']}",
                'citations': [],
                'confidence': 0.0,
                'error': extraction_result['error'],
                'extraction_info': extraction_result
            }
        
        extracted_text = extraction_result['extracted_text']
        
        if not extracted_text.strip():
            return {
                'score': 0,
                'feedback': "Dokumen tidak mengandung teks jawaban yang dapat dinilai.",
                'citations': [],
                'confidence': 0.0,
                'error': 'Empty document',
                'extraction_info': extraction_result
            }
        
        # Grade the extracted essay
        grading_result = self.grade_essay(
            question=question,
            essay=extracted_text,
            rubric=rubric
        )
        
        # Add extraction info to the result
        grading_result['extraction_info'] = {
            'source_document': str(document_path),
            'images_found': extraction_result['images_found'],
            'image_captions_included': len(extraction_result['image_captions']),
            'pages_processed': extraction_result['pages_processed'],
            'extracted_text_length': len(extracted_text)
        }
        
        return grading_result
