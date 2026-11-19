"""Multimodal document loader for PDF, PowerPoint, Word, and text files."""

from pathlib import Path
from typing import List, Dict, Any, Callable
from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document
from loguru import logger

try:
    from pptx import Presentation
    HAS_PPTX = True
except ImportError:
    HAS_PPTX = False
    logger.warning("python-pptx not installed. PPT processing disabled.")

try:
    from docx import Document as DocxDocument
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False
    logger.warning("python-docx not installed. DOCX processing disabled.")

from .image_extractor import ImageExtractor
from .vision_captioner import VisionCaptioner


class MultimodalDocumentLoader:
    """Load and process PDF, PowerPoint, Word, and text documents."""
    
    SUPPORTED_FORMATS = {
        '.pdf': 'PDF Document',
        '.pptx': 'PowerPoint Presentation',
        '.docx': 'Word Document',
        '.txt': 'Plain Text Document',
    }
    
    def __init__(
        self,
        enable_image_extraction: bool = True,
        enable_vision_captioning: bool = True,
        vision_model: str = None,
        min_image_width: int = 100,
        min_image_height: int = 100,
        max_images_per_doc: int = 50,
        settings=None,
    ):
        """
        Initialize multimodal document loader.
        
        Args:
            enable_image_extraction: Whether to extract images
            enable_vision_captioning: Whether to generate captions for images
            vision_model: Vision model for captioning
            min_image_width: Minimum image width to extract
            min_image_height: Minimum image height to extract
            max_images_per_doc: Maximum images to extract per document
        """
        self.enable_image_extraction = enable_image_extraction
        self.enable_vision_captioning = enable_vision_captioning
        
        # Initialize image extractor
        self.image_extractor = ImageExtractor(
            min_width=min_image_width,
            min_height=min_image_height,
            max_images=max_images_per_doc
        ) if enable_image_extraction else None
        
        self._settings = settings
        # Initialize vision captioner (lazy loading)
        self.vision_captioner = None
        self._vision_model = vision_model
        
        logger.info(
            f"MultimodalDocumentLoader initialized: "
            f"image_extraction={enable_image_extraction}, "
            f"vision_captioning={enable_vision_captioning}"
        )
    
    def _init_vision_captioner(self):
        """Lazy initialize vision captioner."""
        if self.vision_captioner is None and self.enable_vision_captioning:
            try:
                self.vision_captioner = VisionCaptioner(
                    model_name=self._vision_model,
                    settings=self._settings.vision if self._settings else None,
                    prompt_settings=self._settings.prompt if self._settings else None,
                )
            except Exception as e:
                logger.warning(f"Could not initialize vision captioner: {e}")
                self.enable_vision_captioning = False
    
    def get_supported_formats(self) -> Dict[str, str]:
        """Get supported file formats."""
        formats = {'.pdf': 'PDF Document'}
        if HAS_PPTX:
            formats['.pptx'] = 'PowerPoint Presentation'
        if HAS_DOCX:
            formats['.docx'] = 'Word Document'
        formats['.txt'] = 'Plain Text Document'
        return formats
    
    def load_pdf(
        self,
        file_path: Path,
        progress_callback: Callable = None
    ) -> Dict[str, Any]:
        """
        Load PDF file with text and images.
        
        Args:
            file_path: Path to PDF file
            progress_callback: Optional callback(current, total, message)
            
        Returns:
            Dictionary with documents, images, and captions
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        result = {
            'documents': [],
            'images': [],
            'captions': [],
            'source_file': str(file_path.name),
            'file_type': 'pdf'
        }
        
        # Load text content
        if progress_callback:
            progress_callback(0, 100, f"Loading text from {file_path.name}...")
        
        try:
            loader = PyPDFLoader(str(file_path))
            documents = loader.load()
            
            # Add metadata
            for i, doc in enumerate(documents):
                doc.metadata.update({
                    'source': str(file_path.name),
                    'page': i + 1,
                    'total_pages': len(documents),
                    'content_type': 'text',
                    'file_type': 'pdf'
                })
            
            result['documents'] = documents
            logger.info(f"Loaded {len(documents)} pages of text from {file_path.name}")
            
        except Exception as e:
            logger.error(f"Error loading PDF text: {e}")
            raise
        
        # Extract images
        if self.enable_image_extraction and self.image_extractor:
            if progress_callback:
                progress_callback(30, 100, f"Extracting images from {file_path.name}...")
            
            try:
                images = self.image_extractor.extract_from_pdf(file_path)
                result['images'] = images
                logger.info(f"Extracted {len(images)} images from {file_path.name}")
            except Exception as e:
                logger.warning(f"Error extracting images: {e}")
        
        # Generate captions
        if self.enable_vision_captioning and result['images']:
            self._init_vision_captioner()
            
            if self.vision_captioner:
                if progress_callback:
                    progress_callback(50, 100, f"Generating image captions...")
                
                try:
                    def caption_progress(current, total, msg):
                        if progress_callback:
                            # Map captioning progress to 50-90% of total progress
                            pct = 50 + int((current / total) * 40)
                            progress_callback(pct, 100, msg)
                    
                    captions = self.vision_captioner.caption_images(
                        result['images'],
                        progress_callback=caption_progress
                    )
                    result['captions'] = captions
                    logger.info(f"Generated {len(captions)} image captions")
                except Exception as e:
                    logger.warning(f"Error generating captions: {e}")
        
        if progress_callback:
            progress_callback(100, 100, f"Completed processing {file_path.name}")
        
        return result
    
    def load_pptx(
        self,
        file_path: Path,
        progress_callback: Callable = None
    ) -> Dict[str, Any]:
        """
        Load PowerPoint file with text and images.
        
        Args:
            file_path: Path to PPTX file
            progress_callback: Optional callback(current, total, message)
            
        Returns:
            Dictionary with documents, images, and captions
        """
        if not HAS_PPTX:
            raise ImportError("python-pptx is required for PowerPoint processing")
        
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        result = {
            'documents': [],
            'images': [],
            'captions': [],
            'source_file': str(file_path.name),
            'file_type': 'pptx'
        }
        
        # Load text content from slides
        if progress_callback:
            progress_callback(0, 100, f"Loading text from {file_path.name}...")
        
        try:
            prs = Presentation(str(file_path))
            documents = []
            
            for slide_num, slide in enumerate(prs.slides, 1):
                # Extract text from all shapes
                slide_texts = []
                
                for shape in slide.shapes:
                    if hasattr(shape, "text") and shape.text:
                        slide_texts.append(shape.text)
                
                if slide_texts:
                    content = "\n".join(slide_texts)
                    
                    doc = Document(
                        page_content=content,
                        metadata={
                            'source': str(file_path.name),
                            'page': slide_num,
                            'total_pages': len(prs.slides),
                            'content_type': 'text',
                            'file_type': 'pptx',
                            'slide_number': slide_num
                        }
                    )
                    documents.append(doc)
            
            result['documents'] = documents
            logger.info(f"Loaded {len(documents)} slides of text from {file_path.name}")
            
        except Exception as e:
            logger.error(f"Error loading PPTX text: {e}")
            raise
        
        # Extract images
        if self.enable_image_extraction and self.image_extractor:
            if progress_callback:
                progress_callback(30, 100, f"Extracting images from {file_path.name}...")
            
            try:
                images = self.image_extractor.extract_from_pptx(file_path)
                result['images'] = images
                logger.info(f"Extracted {len(images)} images from {file_path.name}")
            except Exception as e:
                logger.warning(f"Error extracting images: {e}")
        
        # Generate captions
        if self.enable_vision_captioning and result['images']:
            self._init_vision_captioner()
            
            if self.vision_captioner:
                if progress_callback:
                    progress_callback(50, 100, f"Generating image captions...")
                
                try:
                    def caption_progress(current, total, msg):
                        if progress_callback:
                            pct = 50 + int((current / total) * 40)
                            progress_callback(pct, 100, msg)
                    
                    captions = self.vision_captioner.caption_images(
                        result['images'],
                        progress_callback=caption_progress
                    )
                    result['captions'] = captions
                except Exception as e:
                    logger.warning(f"Error generating captions: {e}")
        
        if progress_callback:
            progress_callback(100, 100, f"Completed processing {file_path.name}")
        
        return result

    def load_docx(
        self,
        file_path: Path,
        progress_callback: Callable = None
    ) -> Dict[str, Any]:
        """Load text content from a DOCX file."""
        if not HAS_DOCX:
            raise ImportError("python-docx is required for DOCX processing")

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if progress_callback:
            progress_callback(0, 100, f"Loading text from {file_path.name}...")

        try:
            docx = DocxDocument(str(file_path))
            parts = [paragraph.text.strip() for paragraph in docx.paragraphs if paragraph.text.strip()]

            for table in docx.tables:
                for row in table.rows:
                    cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                    if cells:
                        parts.append(" | ".join(cells))

            content = "\n".join(parts).strip()
            documents = []
            if content:
                documents.append(Document(
                    page_content=content,
                    metadata={
                        'source': str(file_path.name),
                        'page': 1,
                        'total_pages': 1,
                        'content_type': 'text',
                        'file_type': 'docx'
                    }
                ))

            logger.info(f"Loaded DOCX text from {file_path.name}: {len(content)} characters")
            if progress_callback:
                progress_callback(100, 100, f"Completed processing {file_path.name}")

            return {
                'documents': documents,
                'images': [],
                'captions': [],
                'source_file': str(file_path.name),
                'file_type': 'docx'
            }

        except Exception as e:
            logger.error(f"Error loading DOCX text: {e}")
            raise

    def load_txt(
        self,
        file_path: Path,
        progress_callback: Callable = None
    ) -> Dict[str, Any]:
        """Load text content from a plain text file."""
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if progress_callback:
            progress_callback(0, 100, f"Loading text from {file_path.name}...")

        content = file_path.read_text(encoding='utf-8', errors='ignore').strip()
        documents = []
        if content:
            documents.append(Document(
                page_content=content,
                metadata={
                    'source': str(file_path.name),
                    'page': 1,
                    'total_pages': 1,
                    'content_type': 'text',
                    'file_type': 'txt'
                }
            ))

        logger.info(f"Loaded TXT text from {file_path.name}: {len(content)} characters")
        if progress_callback:
            progress_callback(100, 100, f"Completed processing {file_path.name}")

        return {
            'documents': documents,
            'images': [],
            'captions': [],
            'source_file': str(file_path.name),
            'file_type': 'txt'
        }
    
    def load_document(
        self,
        file_path: Path,
        progress_callback: Callable = None
    ) -> Dict[str, Any]:
        """
        Load any supported document type.
        
        Args:
            file_path: Path to document
            progress_callback: Optional callback
            
        Returns:
            Dictionary with documents, images, and captions
        """
        suffix = file_path.suffix.lower()
        
        if suffix == '.pdf':
            return self.load_pdf(file_path, progress_callback)
        elif suffix == '.pptx':
            return self.load_pptx(file_path, progress_callback)
        elif suffix == '.docx':
            return self.load_docx(file_path, progress_callback)
        elif suffix == '.txt':
            return self.load_txt(file_path, progress_callback)
        else:
            raise ValueError(f"Unsupported file format: {suffix}")
    
    def load_multiple_documents(
        self,
        file_paths: List[Path],
        progress_callback: Callable = None
    ) -> Dict[str, Any]:
        """
        Load multiple documents.
        
        Args:
            file_paths: List of file paths
            progress_callback: Optional callback
            
        Returns:
            Combined results
        """
        combined = {
            'documents': [],
            'images': [],
            'captions': [],
            'files_processed': [],
            'errors': []
        }
        
        total_files = len(file_paths)
        
        for i, file_path in enumerate(file_paths):
            if progress_callback:
                progress_callback(
                    i, total_files,
                    f"Processing file {i + 1}/{total_files}: {file_path.name}"
                )
            
            try:
                result = self.load_document(file_path)
                combined['documents'].extend(result['documents'])
                combined['images'].extend(result['images'])
                combined['captions'].extend(result['captions'])
                combined['files_processed'].append(str(file_path.name))
                
            except Exception as e:
                logger.warning(f"Error processing {file_path}: {e}")
                combined['errors'].append({
                    'file': str(file_path.name),
                    'error': str(e)
                })
        
        logger.info(
            f"Processed {len(combined['files_processed'])} files: "
            f"{len(combined['documents'])} documents, "
            f"{len(combined['images'])} images, "
            f"{len(combined['captions'])} captions"
        )
        
        return combined
    
    def set_vision_model(self, model_name: str) -> Dict[str, Any]:
        """Switch vision captioning model."""
        if self.vision_captioner:
            return self.vision_captioner.switch_model(model_name)
        else:
            self._vision_model = model_name
            return {"success": True, "message": f"Vision model set to {model_name}"}
    
    def toggle_image_extraction(self, enabled: bool):
        """Enable or disable image extraction."""
        self.enable_image_extraction = enabled
        logger.info(f"Image extraction {'enabled' if enabled else 'disabled'}")
    
    def toggle_vision_captioning(self, enabled: bool):
        """Enable or disable vision captioning."""
        self.enable_vision_captioning = enabled
        if enabled:
            self._init_vision_captioner()
        logger.info(f"Vision captioning {'enabled' if enabled else 'disabled'}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get loader status."""
        status = {
            'image_extraction_enabled': self.enable_image_extraction,
            'vision_captioning_enabled': self.enable_vision_captioning,
            'supported_formats': self.get_supported_formats()
        }
        
        if self.vision_captioner:
            status['vision_model'] = self.vision_captioner.get_current_model_info()
        
        return status


# Backward compatible class
class DocumentLoader:
    """
    Document loader with multimodal support.
    Supports PDF, PPTX, DOCX, and TXT with optional image extraction for PDF/PPTX.
    """
    
    def __init__(self, enable_multimodal: bool = True, settings=None):
        """
        Initialize document loader.
        
        Args:
            enable_multimodal: Whether to enable image extraction and captioning
            settings: Optional Settings forwarded to the vision captioner
        """
        self.enable_multimodal = enable_multimodal
        self.multimodal_loader = MultimodalDocumentLoader(
            enable_image_extraction=enable_multimodal,
            enable_vision_captioning=enable_multimodal,
            settings=settings,
        )
        self.supported_formats = list(self.multimodal_loader.get_supported_formats().keys())
    
    def load_pdf(self, file_path: Path) -> List[Document]:
        """
        Load PDF file and extract text (legacy interface).
        
        Args:
            file_path: Path to PDF file
            
        Returns:
            List of Document objects
        """
        result = self.multimodal_loader.load_pdf(file_path)
        return result['documents']
    
    def load_document(
        self,
        file_path: Path,
        progress_callback: Callable = None
    ) -> Dict[str, Any]:
        """
        Load document with full multimodal support.
        
        Args:
            file_path: Path to document
            progress_callback: Optional progress callback
            
        Returns:
            Dictionary with documents, images, and captions
        """
        return self.multimodal_loader.load_document(file_path, progress_callback)
    
    def load_multiple_pdfs(self, file_paths: List[Path]) -> List[Document]:
        """
        Load multiple PDF files (legacy interface).
        
        Args:
            file_paths: List of paths to PDF files
            
        Returns:
            Combined list of Document objects
        """
        all_documents = []
        
        for file_path in file_paths:
            try:
                documents = self.load_pdf(file_path)
                all_documents.extend(documents)
            except Exception as e:
                logger.warning(f"Skipping {file_path}: {e}")
                continue
        
        return all_documents
    
    def load_multiple_documents(
        self,
        file_paths: List[Path],
        progress_callback: Callable = None
    ) -> Dict[str, Any]:
        """
        Load multiple documents with multimodal support.
        
        Args:
            file_paths: List of file paths
            progress_callback: Optional progress callback
            
        Returns:
            Combined results dictionary
        """
        return self.multimodal_loader.load_multiple_documents(
            file_paths,
            progress_callback
        )
    
    def toggle_image_extraction(self, enabled: bool):
        """Enable or disable image extraction."""
        self.multimodal_loader.toggle_image_extraction(enabled)
    
    def toggle_vision_captioning(self, enabled: bool):
        """Enable or disable vision captioning."""
        self.multimodal_loader.toggle_vision_captioning(enabled)
    
    def get_status(self) -> Dict[str, Any]:
        """Get loader status."""
        return self.multimodal_loader.get_status()
