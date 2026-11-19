"""Text preprocessing and chunking with multimodal support."""

from typing import List, Dict, Any
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from loguru import logger

from .vision_captioner import ImageCaption


class DocumentPreprocessor:
    """Preprocess and chunk documents with multimodal (text + image) support."""
    
    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        separators: List[str] = None,
        include_image_captions: bool = True
    ):
        """
        Initialize preprocessor with chunking configuration.
        
        Args:
            chunk_size: Size of each chunk in characters
            chunk_overlap: Overlap between chunks
            separators: List of separators for splitting
            include_image_captions: Whether to create chunks from image captions
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators or ["\n\n", "\n", ". ", " ", ""]
        self.include_image_captions = include_image_captions
        
        self._initialize_splitter()
        logger.info(
            f"Preprocessor initialized: chunk_size={chunk_size}, "
            f"overlap={chunk_overlap}, image_captions={include_image_captions}"
        )
    
    def _initialize_splitter(self):
        """Initialize text splitter with current configuration."""
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            separators=self.separators,
            length_function=len,
        )
    
    def update_config(
        self,
        chunk_size: int = None,
        chunk_overlap: int = None,
        separators: List[str] = None,
        include_image_captions: bool = None
    ):
        """
        Update chunking configuration.
        
        Args:
            chunk_size: New chunk size
            chunk_overlap: New overlap size
            separators: New separators list
            include_image_captions: Include image captions in chunks
        """
        if chunk_size is not None:
            self.chunk_size = chunk_size
        if chunk_overlap is not None:
            self.chunk_overlap = chunk_overlap
        if separators is not None:
            self.separators = separators
        if include_image_captions is not None:
            self.include_image_captions = include_image_captions
        
        self._initialize_splitter()
        logger.info(f"Configuration updated: chunk_size={self.chunk_size}, overlap={self.chunk_overlap}")
    
    def preprocess_text(self, text: str) -> str:
        """
        Clean and normalize text.
        
        Args:
            text: Raw text
            
        Returns:
            Cleaned text
        """
        # Remove excessive whitespace
        text = ' '.join(text.split())
        return text
    
    def chunk_documents(self, documents: List[Document]) -> List[Document]:
        """
        Split documents into chunks.
        
        Args:
            documents: List of Document objects
            
        Returns:
            List of chunked Document objects
        """
        logger.info(f"Chunking {len(documents)} documents...")
        
        # Preprocess text in each document
        for doc in documents:
            doc.page_content = self.preprocess_text(doc.page_content)
        
        # Split into chunks
        chunks = self.text_splitter.split_documents(documents)
        
        # Add chunk metadata
        for i, chunk in enumerate(chunks):
            chunk.metadata.update({
                'chunk_id': i,
                'chunk_size': len(chunk.page_content)
            })
        
        logger.info(f"Created {len(chunks)} chunks")
        return chunks
    
    def create_image_caption_documents(
        self,
        captions: List[ImageCaption]
    ) -> List[Document]:
        """
        Create Document objects from image captions.
        
        Args:
            captions: List of ImageCaption objects
            
        Returns:
            List of Document objects for image captions
        """
        if not self.include_image_captions or not captions:
            return []
        
        documents = []
        
        logger.info(f"\n{'='*70}")
        logger.info(f"📄 CREATING IMAGE CAPTION DOCUMENTS FOR VECTORIZATION")
        logger.info(f"{'='*70}")
        
        for i, caption in enumerate(captions):
            # Create document from caption
            content = self._format_image_caption(caption)
            
            doc = Document(
                page_content=content,
                metadata={
                    'source': caption.image.source_file,
                    'page': caption.image.page_number,
                    'content_type': 'image_caption',
                    'image_index': caption.image.image_index,
                    'image_width': caption.image.width,
                    'image_height': caption.image.height,
                    'vision_model': caption.model_used,
                    'caption_confidence': caption.confidence
                }
            )
            documents.append(doc)
            
            # Log each document being created
            logger.info(f"\n{'─'*70}")
            logger.info(f"📷 Image Caption Document #{i+1}")
            logger.info(f"{'─'*70}")
            logger.info(f"Source: {caption.image.source_file}")
            logger.info(f"Page/Slide: {caption.image.page_number}")
            logger.info(f"Image Index: {caption.image.image_index}")
            logger.info(f"Dimensions: {caption.image.width}x{caption.image.height}")
            logger.info(f"Vision Model: {caption.model_used}")
            logger.info(f"Confidence: {caption.confidence}")
            logger.info(f"\n📝 CONTENT TO BE VECTORIZED:")
            logger.info(f"{'─'*50}")
            logger.info(f"{content}")
            logger.info(f"{'─'*50}")
            logger.info(f"Content Length: {len(content)} characters")
        
        logger.info(f"\n{'='*70}")
        logger.info(f"✅ Created {len(documents)} image caption documents for vectorization")
        logger.info(f"{'='*70}\n")
        
        return documents
    
    def _format_image_caption(self, caption: ImageCaption) -> str:
        """
        Format image caption into searchable text.
        
        Args:
            caption: ImageCaption object
            
        Returns:
            Formatted caption string
        """
        parts = [
            f"[IMAGE: {caption.image.source_file} - Page/Slide {caption.image.page_number}]",
            "",
            caption.caption
        ]
        
        return "\n".join(parts)
    
    def process_multimodal_content(
        self,
        documents: List[Document],
        captions: List[ImageCaption] = None
    ) -> List[Document]:
        """
        Process both text documents and image captions.
        
        Args:
            documents: List of text Document objects
            captions: List of ImageCaption objects (optional)
            
        Returns:
            Combined list of chunked documents
        """
        all_chunks = []
        
        # Process text documents
        if documents:
            text_chunks = self.chunk_documents(documents)
            all_chunks.extend(text_chunks)
        
        # Process image captions
        if captions and self.include_image_captions:
            caption_docs = self.create_image_caption_documents(captions)
            
            # Chunk caption documents if they're long
            if caption_docs:
                caption_chunks = self.chunk_documents(caption_docs)
                all_chunks.extend(caption_chunks)
        
        # Re-number chunk IDs
        for i, chunk in enumerate(all_chunks):
            chunk.metadata['chunk_id'] = i
        
        logger.info(
            f"Total chunks: {len(all_chunks)} "
            f"(text: {len([c for c in all_chunks if c.metadata.get('content_type') != 'image_caption'])}, "
            f"image captions: {len([c for c in all_chunks if c.metadata.get('content_type') == 'image_caption'])})"
        )
        
        return all_chunks
    
    def get_config(self) -> Dict[str, Any]:
        """
        Get current configuration.
        
        Returns:
            Configuration dictionary
        """
        return {
            'chunk_size': self.chunk_size,
            'chunk_overlap': self.chunk_overlap,
            'separators': self.separators,
            'include_image_captions': self.include_image_captions
        }
    
    def toggle_image_captions(self, enabled: bool):
        """Enable or disable image caption inclusion."""
        self.include_image_captions = enabled
        logger.info(f"Image caption inclusion {'enabled' if enabled else 'disabled'}")
