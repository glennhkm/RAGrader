"""Image extraction from PDF and PowerPoint documents."""

import io
import base64
import hashlib
from pathlib import Path
from typing import List, Dict, Tuple
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
from loguru import logger

try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False
    logger.warning("PyMuPDF not installed. PDF image extraction will be limited.")

try:
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE
    HAS_PPTX = True
except ImportError:
    HAS_PPTX = False
    logger.warning("python-pptx not installed. PPT processing will not be available.")

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    logger.warning("Pillow not installed. Image processing will be limited.")


@dataclass
class ExtractedImage:
    """Represents an extracted image with metadata."""
    image_data: bytes
    image_format: str  # 'png', 'jpeg', etc.
    source_file: str
    page_number: int
    image_index: int
    width: int
    height: int
    image_hash: str  # For deduplication
    context_text: str = ""  # Surrounding text for context
    
    def to_base64(self) -> str:
        """Convert image data to base64 string."""
        return base64.b64encode(self.image_data).decode('utf-8')
    
    def get_data_uri(self) -> str:
        """Get data URI for the image."""
        b64 = self.to_base64()
        mime_type = f"image/{self.image_format.lower()}"
        return f"data:{mime_type};base64,{b64}"


class ImageExtractor:
    """Extract images from PDF and PowerPoint documents."""
    
    # Minimum image dimensions to consider (filter out icons, bullets, etc.)
    MIN_WIDTH = 100
    MIN_HEIGHT = 100
    MIN_AREA = 15000  # Minimum pixel area
    
    # Maximum images per document to prevent overload
    MAX_IMAGES_PER_DOC = 50
    
    # Supported formats
    SUPPORTED_IMAGE_FORMATS = {'png', 'jpeg', 'jpg', 'gif', 'bmp', 'tiff', 'webp'}
    
    def __init__(
        self,
        min_width: int = None,
        min_height: int = None,
        min_area: int = None,
        max_images: int = None
    ):
        """
        Initialize image extractor.
        
        Args:
            min_width: Minimum image width to extract
            min_height: Minimum image height to extract
            min_area: Minimum pixel area to extract
            max_images: Maximum images per document
        """
        self.min_width = min_width or self.MIN_WIDTH
        self.min_height = min_height or self.MIN_HEIGHT
        self.min_area = min_area or self.MIN_AREA
        self.max_images = max_images or self.MAX_IMAGES_PER_DOC
        
        self._check_dependencies()
        logger.info(
            f"ImageExtractor initialized: min_size={self.min_width}x{self.min_height}, "
            f"min_area={self.min_area}, max_images={self.max_images}"
        )
    
    def _check_dependencies(self):
        """Check required dependencies."""
        if not HAS_PIL:
            raise ImportError(
                "Pillow is required for image extraction. "
                "Install with: pip install Pillow"
            )
    
    def _compute_image_hash(self, image_data: bytes) -> str:
        """Compute hash for image deduplication."""
        return hashlib.md5(image_data).hexdigest()
    
    def _is_valid_image(self, width: int, height: int) -> bool:
        """Check if image meets minimum size requirements."""
        if width < self.min_width or height < self.min_height:
            return False
        if width * height < self.min_area:
            return False
        return True
    
    def _convert_to_png(self, image_data: bytes, original_format: str) -> Tuple[bytes, str]:
        """Convert image to PNG format for consistency."""
        try:
            img = Image.open(io.BytesIO(image_data))
            
            # Convert to RGB if necessary (for RGBA or palette images)
            if img.mode in ('RGBA', 'LA', 'P'):
                # Create white background for transparency
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Save as PNG
            buffer = io.BytesIO()
            img.save(buffer, format='PNG', optimize=True)
            return buffer.getvalue(), 'png'
            
        except Exception as e:
            logger.warning(f"Could not convert image: {e}")
            return image_data, original_format
    
    def extract_from_pdf(self, file_path: Path) -> List[ExtractedImage]:
        """
        Extract images from PDF file.
        
        Args:
            file_path: Path to PDF file
            
        Returns:
            List of ExtractedImage objects
        """
        if not HAS_PYMUPDF:
            logger.warning("PyMuPDF not available, cannot extract PDF images")
            return []
        
        images = []
        seen_hashes = set()
        
        try:
            doc = fitz.open(str(file_path))
            source_name = file_path.name
            
            logger.info(f"Extracting images from PDF: {source_name} ({len(doc)} pages)")
            
            for page_num in range(len(doc)):
                if len(images) >= self.max_images:
                    logger.warning(f"Reached max images limit ({self.max_images})")
                    break
                
                page = doc[page_num]
                
                # Get page text for context
                page_text = page.get_text()[:500] if page.get_text() else ""
                
                # Extract images from page
                image_list = page.get_images(full=True)
                
                for img_idx, img_info in enumerate(image_list):
                    if len(images) >= self.max_images:
                        break
                    
                    try:
                        # Get image reference number
                        xref = img_info[0]
                        
                        # Extract image
                        base_image = doc.extract_image(xref)
                        if not base_image:
                            continue
                        
                        image_data = base_image["image"]
                        image_format = base_image["ext"].lower()
                        width = base_image.get("width", 0)
                        height = base_image.get("height", 0)
                        
                        # Validate image size
                        if not self._is_valid_image(width, height):
                            logger.debug(
                                f"Skipping small image: {width}x{height} on page {page_num + 1}"
                            )
                            continue
                        
                        # Check for duplicates
                        img_hash = self._compute_image_hash(image_data)
                        if img_hash in seen_hashes:
                            logger.debug(f"Skipping duplicate image on page {page_num + 1}")
                            continue
                        seen_hashes.add(img_hash)
                        
                        # Convert to PNG for consistency
                        image_data, image_format = self._convert_to_png(image_data, image_format)
                        
                        # Create ExtractedImage object
                        extracted = ExtractedImage(
                            image_data=image_data,
                            image_format=image_format,
                            source_file=source_name,
                            page_number=page_num + 1,
                            image_index=img_idx + 1,
                            width=width,
                            height=height,
                            image_hash=img_hash,
                            context_text=page_text
                        )
                        
                        images.append(extracted)
                        logger.debug(
                            f"Extracted image {len(images)}: {width}x{height} "
                            f"from page {page_num + 1}"
                        )
                        
                    except Exception as e:
                        logger.warning(f"Error extracting image from page {page_num + 1}: {e}")
                        continue
            
            doc.close()
            logger.info(f"Extracted {len(images)} images from {source_name}")
            
        except Exception as e:
            logger.error(f"Error processing PDF {file_path}: {e}")
        
        return images
    
    def extract_from_pptx(self, file_path: Path) -> List[ExtractedImage]:
        """
        Extract images from PowerPoint file.
        
        Args:
            file_path: Path to PPTX file
            
        Returns:    
            List of ExtractedImage objects
        """
        if not HAS_PPTX:
            logger.warning("python-pptx not available, cannot extract PPT images")
            return []
        
        images = []
        seen_hashes = set()
        
        try:
            prs = Presentation(str(file_path))
            source_name = file_path.name
            
            logger.info(f"Extracting images from PPTX: {source_name} ({len(prs.slides)} slides)")
            
            for slide_num, slide in enumerate(prs.slides, 1):
                if len(images) >= self.max_images:  
                    logger.warning(f"Reached max images limit ({self.max_images})")
                    break
                
                # Get slide text for context
                slide_text = self._get_slide_text(slide)
                
                img_idx = 0
                for shape in slide.shapes:
                    if len(images) >= self.max_images:
                        break
                    
                    # Check if shape contains an image
                    if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                        try:
                            img_idx += 1
                            image = shape.image
                            image_data = image.blob
                            image_format = image.ext.lower()
                            
                            # Get image dimensions
                            img_pil = Image.open(io.BytesIO(image_data))
                            width, height = img_pil.size
                            
                            # Validate image size
                            if not self._is_valid_image(width, height):
                                logger.debug(
                                    f"Skipping small image: {width}x{height} on slide {slide_num}"
                                )
                                continue
                            
                            # Check for duplicates
                            img_hash = self._compute_image_hash(image_data)
                            if img_hash in seen_hashes:
                                logger.debug(f"Skipping duplicate image on slide {slide_num}")
                                continue
                            seen_hashes.add(img_hash)
                            
                            # Convert to PNG
                            image_data, image_format = self._convert_to_png(image_data, image_format)
                            
                            # Create ExtractedImage object
                            extracted = ExtractedImage(
                                image_data=image_data,
                                image_format=image_format,
                                source_file=source_name,
                                page_number=slide_num,
                                image_index=img_idx,
                                width=width,
                                height=height,
                                image_hash=img_hash,
                                context_text=slide_text
                            )
                            
                            images.append(extracted)
                            logger.debug(
                                f"Extracted image {len(images)}: {width}x{height} "
                                f"from slide {slide_num}"
                            )
                            
                        except Exception as e:
                            logger.warning(f"Error extracting image from slide {slide_num}: {e}")
                            continue
            
            logger.info(f"Extracted {len(images)} images from {source_name}")
            
        except Exception as e:
            logger.error(f"Error processing PPTX {file_path}: {e}")
        
        return images
    
    def _get_slide_text(self, slide) -> str:
        """Extract text from a PowerPoint slide."""
        texts = []
        
        try:
            for shape in slide.shapes:
                if hasattr(shape, "text") and shape.text:
                    texts.append(shape.text)
        except Exception as e:
            logger.debug(f"Error getting slide text: {e}")
        
        return " ".join(texts)[:500]  # Limit context text
    
    def extract_images(self, file_path: Path) -> List[ExtractedImage]:
        """
        Extract images from a document (PDF or PPTX).
        
        Args:
            file_path: Path to document file
            
        Returns:
            List of ExtractedImage objects
        """
        suffix = file_path.suffix.lower()
        
        if suffix == '.pdf':
            return self.extract_from_pdf(file_path)
        elif suffix in ['.pptx', '.ppt']:
            if suffix == '.ppt':
                logger.warning("Old .ppt format not supported, please convert to .pptx")
                return []
            return self.extract_from_pptx(file_path)
        else:
            logger.warning(f"Unsupported file format for image extraction: {suffix}")
            return []
    
    def get_supported_formats(self) -> List[str]:
        """Get list of supported document formats for image extraction."""
        formats = []
        if HAS_PYMUPDF:
            formats.append('.pdf')
        if HAS_PPTX:
            formats.append('.pptx')
        return formats
    
    def extract_from_multiple_files(
        self, 
        file_paths: List[Path],
        max_workers: int = 4,
        progress_callback=None
    ) -> Dict[str, List[ExtractedImage]]:
        """
        Extract images from multiple files in parallel.
        
        Uses ThreadPoolExecutor for faster extraction from multiple documents.
        
        Args:
            file_paths: List of file paths to process
            max_workers: Maximum number of parallel workers (default: 4)
            progress_callback: Optional callback function(current, total, message)
            
        Returns:
            Dictionary mapping file paths to lists of ExtractedImage objects
        """
        results = {}
        total_files = len(file_paths)
        
        if total_files == 0:
            return results
        
        logger.info(f"🖼️ Extracting images from {total_files} files (max {max_workers} workers)...")
        
        # For single file, just extract directly
        if total_files == 1:
            file_path = file_paths[0]
            if progress_callback:
                progress_callback(1, 1, f"Extracting images from {file_path.name}")
            results[str(file_path)] = self.extract_images(file_path)
            return results
        
        # For multiple files, use parallel processing
        completed = 0
        
        with ThreadPoolExecutor(max_workers=min(max_workers, total_files)) as executor:
            # Submit all tasks
            future_to_path = {
                executor.submit(self.extract_images, path): path 
                for path in file_paths
            }
            
            # Process completed tasks
            for future in as_completed(future_to_path):
                file_path = future_to_path[future]
                completed += 1
                
                if progress_callback:
                    progress_callback(
                        completed, total_files, 
                        f"Extracted images from {file_path.name}"
                    )
                
                try:
                    images = future.result()
                    results[str(file_path)] = images
                    logger.info(f"✅ [{completed}/{total_files}] {file_path.name}: {len(images)} images")
                except Exception as e:
                    logger.error(f"❌ [{completed}/{total_files}] Error extracting from {file_path.name}: {e}")
                    results[str(file_path)] = []
        
        # Summary
        total_images = sum(len(imgs) for imgs in results.values())
        logger.info(f"📊 Image extraction complete: {total_images} images from {total_files} files")
        
        return results
    
    def extract_images_batched(
        self, 
        file_path: Path,
        batch_size: int = 10,
        progress_callback=None
    ) -> List[ExtractedImage]:
        """
        Extract images from a single file with progress tracking per batch of pages.
        
        Useful for large PDFs where page-by-page progress is needed.
        
        Args:
            file_path: Path to document file
            batch_size: Number of pages to process before reporting progress
            progress_callback: Optional callback function(current, total, message)
            
        Returns:
            List of ExtractedImage objects
        """
        suffix = file_path.suffix.lower()
        
        if suffix != '.pdf':
            # For non-PDF files, use standard extraction
            return self.extract_images(file_path)
        
        if not HAS_PYMUPDF:
            logger.warning("PyMuPDF not available, cannot extract PDF images")
            return []
        
        images = []
        seen_hashes = set()
        
        try:
            doc = fitz.open(str(file_path))
            source_name = file_path.name
            total_pages = len(doc)
            
            logger.info(f"📄 Extracting images from PDF: {source_name} ({total_pages} pages, batch size: {batch_size})")
            
            for page_num in range(total_pages):
                if len(images) >= self.max_images:
                    logger.warning(f"Reached max images limit ({self.max_images})")
                    break
                
                # Report progress every batch_size pages
                if progress_callback and (page_num + 1) % batch_size == 0:
                    progress_callback(
                        page_num + 1, total_pages,
                        f"Processing page {page_num + 1}/{total_pages}"
                    )
                
                page = doc[page_num]
                page_text = page.get_text()[:500] if page.get_text() else ""
                image_list = page.get_images(full=True)
                
                for img_idx, img_info in enumerate(image_list):
                    if len(images) >= self.max_images:
                        break
                    
                    try:
                        xref = img_info[0]
                        base_image = doc.extract_image(xref)
                        if not base_image:
                            continue
                        
                        image_data = base_image["image"]
                        image_format = base_image["ext"].lower()
                        width = base_image.get("width", 0)
                        height = base_image.get("height", 0)
                        
                        if not self._is_valid_image(width, height):
                            continue
                        
                        img_hash = self._compute_image_hash(image_data)
                        if img_hash in seen_hashes:
                            continue
                        seen_hashes.add(img_hash)
                        
                        image_data, image_format = self._convert_to_png(image_data, image_format)
                        
                        extracted = ExtractedImage(
                            image_data=image_data,
                            image_format=image_format,
                            source_file=source_name,
                            page_number=page_num + 1,
                            image_index=img_idx + 1,
                            width=width,
                            height=height,
                            image_hash=img_hash,
                            context_text=page_text
                        )
                        
                        images.append(extracted)
                        
                    except Exception as e:
                        logger.warning(f"Error extracting image from page {page_num + 1}: {e}")
                        continue
            
            doc.close()
            
            if progress_callback:
                progress_callback(total_pages, total_pages, f"Complete: {len(images)} images")
            
            logger.info(f"✅ Extracted {len(images)} images from {source_name}")
            
        except Exception as e:
            logger.error(f"Error processing PDF {file_path}: {e}")
        
        return images
