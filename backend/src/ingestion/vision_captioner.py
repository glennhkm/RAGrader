"""Vision captioning for images using Vision Language Models via HuggingFace Router."""

import os
import time
from typing import List, Dict, Any
from dataclasses import dataclass
from loguru import logger

# Use OpenAI client for HuggingFace Router (same approach as llm.py)
from openai import OpenAI

from .image_extractor import ExtractedImage


@dataclass
class ImageCaption:
    """Represents an image with its generated caption."""
    image: ExtractedImage
    caption: str
    model_used: str
    confidence: float = 1.0
    processing_time: float = 0.0


class VisionCaptioner:
    """Generate captions for images using Vision Language Models via HuggingFace Router.
    
    Uses the same approach as llm.py - OpenAI-compatible client with HuggingFace Router.
    Base URL: https://router.huggingface.co/v1
    """
    
    # HuggingFace Router base URL (same as llm.py)
    HUGGINGFACE_BASE_URL = "https://router.huggingface.co/v1"
    
    # Available Vision LLM models that support image input via HuggingFace Router
    # Based on actual API response - only these models are allowed
    VISION_MODELS = {
        "Qwen/Qwen2.5-VL-72B-Instruct": {
            "name": "Qwen2.5-VL 72B",
            "description": "Qwen2.5 Vision-Language 72B - most capable for detailed descriptions",
            "type": "multimodal",
            "max_tokens": 2048
        },
        "Qwen/Qwen2.5-VL-7B-Instruct": {
            "name": "Qwen2.5-VL 7B",
            "description": "Qwen2.5 Vision-Language 7B - fast and accurate",
            "type": "multimodal",
            "max_tokens": 1024
        },
        "mistralai/Pixtral-12B-2409": {
            "name": "Pixtral 12B",
            "description": "Mistral's Pixtral - excellent for visual understanding",
            "type": "multimodal",
            "max_tokens": 1024
        },
        "nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-BF16": {
            "name": "Nemotron Nano 12B VL",
            "description": "NVIDIA Nemotron - efficient vision-language model",
            "type": "multimodal",
            "max_tokens": 1024
        }
    }
    
    DEFAULT_MODEL = "Qwen/Qwen2.5-VL-7B-Instruct"
    
#     # Prompt for educational image description
#     EDUCATIONAL_PROMPT = """Describe this educational image in detail. Focus on:
# 1. Main subjects, objects, and visual elements
# 2. Any text, labels, or annotations visible
# 3. Diagrams, charts, flowcharts, or technical illustrations
# 4. Key concepts or information conveyed visually
# 5. Educational context and learning points

# Provide a comprehensive, detailed description:"""

    # Prompt for educational image description
    EDUCATIONAL_PROMPT = """Jelaskan gambar ini secara detail dengan fokus pada hal-hal berikut:
1. Subjek utama, objek, dan elemen visual penting
2. Teks, label, atau anotasi yang terlihat
3. Diagram, grafik, flowchart, atau ilustrasi teknis apa pun
4. Konsep atau informasi kunci yang ditampilkan secara visual
Berikan deskripsi yang komprehensif dan mendalam."""
    
    def __init__(
        self,
        model_name: str = None,
        api_token: str = None,
        prompt_template: str = None,
        max_retries: int = 3,
        retry_delay: float = 2.0
    ):
        """
        Initialize Vision Captioner using HuggingFace Router (same as llm.py approach).
        
        Args:
            model_name: HuggingFace model name for vision captioning
            api_token: HuggingFace API token
            prompt_template: Custom prompt for detailed descriptions
            max_retries: Maximum retries on API failure
            retry_delay: Delay between retries in seconds
        """
        self.model_name = model_name or self.DEFAULT_MODEL
        self.api_token = api_token or os.getenv("HUGGINGFACE_API_TOKEN")
        self.prompt_template = prompt_template or self.EDUCATIONAL_PROMPT
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        if not self.api_token:
            raise ValueError(
                "HUGGINGFACE_API_TOKEN not found. "
                "Set it in environment or pass as api_token parameter."
            )
        
        self._init_client()
        logger.info(f"VisionCaptioner initialized with model: {self.model_name}")
        logger.info(f"Using HuggingFace Router: {self.HUGGINGFACE_BASE_URL}")
    
    def _init_client(self):
        """Initialize OpenAI-compatible client for HuggingFace Router.
        
        Same approach as llm.py - using OpenAI client with HuggingFace base URL.
        """
        logger.info(f"Initializing OpenAI client with HuggingFace Router...")
        logger.info(f"Base URL: {self.HUGGINGFACE_BASE_URL}")
        
        self.client = OpenAI(
            base_url=self.HUGGINGFACE_BASE_URL,
            api_key=self.api_token,
        )
        
        logger.info("HuggingFace Router client initialized successfully")
    
    def _get_model_info(self) -> Dict[str, Any]:
        """Get info about the current model."""
        return self.VISION_MODELS.get(self.model_name, {
            "name": self.model_name,
            "type": "multimodal",
            "max_tokens": 512
        })
    
    def _caption_image_via_router(self, image: ExtractedImage) -> str:
        """
        Generate caption using HuggingFace Router with OpenAI-compatible API.
        
        This uses the same approach as llm.py for reliable API calls.
        
        Args:
            image: ExtractedImage object
            
        Returns:
            Caption string
        """
        model_info = self._get_model_info()
        max_tokens = model_info.get("max_tokens", 512)
        
        # Encode image to base64
        image_b64 = image.to_base64()
        
        # Build message with image (OpenAI vision format)
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_b64}"
                        }
                    },
                    {
                        "type": "text",
                        "text": self.prompt_template
                    }
                ]
            }
        ]
        
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                logger.info(f"🌐 API Call attempt {attempt + 1}/{self.max_retries}")
                logger.info(f"   Model: {self.model_name}")
                logger.info(f"   Base URL: {self.HUGGINGFACE_BASE_URL}")
                
                # Use chat.completions.create (same as llm.py)
                completion = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=0.3,
                )
                
                caption = completion.choices[0].message.content.strip()
                logger.info(f"✅ API call successful!")
                
                return caption
                
            except Exception as e:
                last_error = e
                logger.warning(
                    f"⚠️ Caption attempt {attempt + 1}/{self.max_retries} failed: {e}"
                )
                
                if attempt < self.max_retries - 1:
                    wait_time = self.retry_delay * (attempt + 1)
                    logger.info(f"   Waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
        
        # All retries failed
        raise Exception(f"All {self.max_retries} attempts failed. Last error: {last_error}")
    
    def caption_image(self, image: ExtractedImage) -> ImageCaption:
        """
        Generate caption for a single image.
        
        Args:
            image: ExtractedImage object
            
        Returns:
            ImageCaption object with the generated caption
        """
        start_time = time.time()
        
        # Log image info before captioning
        logger.info(f"{'='*60}")
        logger.info(f"🖼️  PROCESSING IMAGE")
        logger.info(f"{'='*60}")
        logger.info(f"📄 Source: {image.source_file}")
        logger.info(f"📑 Page/Slide: {image.page_number}")
        logger.info(f"🔢 Image Index: {image.image_index}")
        logger.info(f"📐 Dimensions: {image.width}x{image.height} pixels")
        logger.info(f"🤖 Model: {self.model_name}")
        logger.info(f"🌐 API: HuggingFace Router ({self.HUGGINGFACE_BASE_URL})")
        
        try:
            # Use the router-based API call
            caption_text = self._caption_image_via_router(image)
            
            # Log raw caption result
            logger.info(f"{'─'*60}")
            logger.info(f"📝 RAW CAPTION (from Vision AI):")
            logger.info(f"{'─'*60}")
            logger.info(f"{caption_text}")
            logger.info(f"{'─'*60}")
            
            # Enhance caption with context
            enhanced_caption = self._enhance_caption(caption_text, image)
            
            processing_time = time.time() - start_time
            
            # Log enhanced caption (will be vectorized)
            logger.info(f"✨ ENHANCED CAPTION (to be vectorized):")
            logger.info(f"{'─'*60}")
            logger.info(f"{enhanced_caption}")
            logger.info(f"{'─'*60}")
            logger.info(f"⏱️  Processing time: {processing_time:.2f}s")
            logger.info(f"{'='*60}\n")
            
            return ImageCaption(
                image=image,
                caption=enhanced_caption,
                model_used=self.model_name,
                confidence=1.0,
                processing_time=processing_time
            )
            
        except Exception as e:
            logger.error(f"❌ Error captioning image: {e}")
            processing_time = time.time() - start_time
            
            # Return a basic caption on error
            return ImageCaption(
                image=image,
                caption=f"[Image from {image.source_file}, page {image.page_number}]",
                model_used=self.model_name,
                confidence=0.0,
                processing_time=processing_time
            )
    
    def _enhance_caption(self, caption: str, image: ExtractedImage) -> str:
        """
        Enhance caption with metadata and context.
        
        Args:
            caption: Raw caption from VLM
            image: ExtractedImage with metadata
            
        Returns:
            Enhanced caption string
        """
        # Build enhanced caption
        parts = [
            f"[Image from {image.source_file}, page/slide {image.page_number}]",
            f"Description: {caption}"
        ]
        
        # Add context if available
        if image.context_text:
            context_preview = image.context_text[:200]
            parts.append(f"Context: {context_preview}...")
        
        return "\n".join(parts)
    
    def caption_images(
        self,
        images: List[ExtractedImage],
        batch_size: int = 5,
        batch_delay: float = 1.0,
        progress_callback=None
    ) -> List[ImageCaption]:
        """
        Generate captions for multiple images with batching.
        
        Uses batching to prevent API overload and timeout errors.
        
        Args:
            images: List of ExtractedImage objects
            batch_size: Number of images to process before pause (default: 5)
            batch_delay: Delay in seconds between batches (default: 1.0)
            progress_callback: Optional callback function(current, total, message)
            
        Returns:
            List of ImageCaption objects
        """
        captions = []
        total = len(images)
        
        # Calculate number of batches
        num_batches = (total + batch_size - 1) // batch_size
        
        logger.info(f"\n{'#'*70}")
        logger.info(f"#  VISION CAPTIONING SESSION START")
        logger.info(f"#  Total images to process: {total}")
        logger.info(f"#  Batch size: {batch_size} images")
        logger.info(f"#  Number of batches: {num_batches}")
        logger.info(f"#  Model: {self.model_name}")
        logger.info(f"#  API: HuggingFace Router ({self.HUGGINGFACE_BASE_URL})")
        logger.info(f"{'#'*70}\n")
        
        for i, image in enumerate(images):
            if progress_callback:
                progress_callback(
                    i + 1, total,
                    f"Processing image {i + 1}/{total} from {image.source_file}"
                )
            
            # Calculate current batch
            current_batch = (i // batch_size) + 1
            position_in_batch = (i % batch_size) + 1
            
            logger.info(f"[{i + 1}/{total}] Batch {current_batch}/{num_batches}, Image {position_in_batch}/{batch_size}")
            
            try:
                caption = self.caption_image(image)
                captions.append(caption)
                
                # Add delay between batches (not after every image)
                if (i + 1) % batch_size == 0 and i + 1 < total:
                    logger.info(f"📦 Batch {current_batch} complete. Waiting {batch_delay}s before next batch...")
                    time.sleep(batch_delay)
                
            except Exception as e:
                logger.error(f"❌ Failed to caption image {i + 1}: {e}")
                # Create placeholder caption
                captions.append(ImageCaption(
                    image=image,
                    caption=f"[Unable to process image from {image.source_file}]",
                    model_used=self.model_name,
                    confidence=0.0
                ))
        
        successful = sum(1 for c in captions if c.confidence > 0)
        failed = total - successful
        
        # Log summary
        logger.info(f"\n{'#'*70}")
        logger.info(f"#  VISION CAPTIONING SESSION COMPLETE")
        logger.info(f"{'#'*70}")
        logger.info(f"✅ Successfully captioned: {successful}/{total}")
        if failed > 0:
            logger.warning(f"❌ Failed: {failed}/{total}")
        
        # Log all captions summary
        logger.info(f"\n{'='*70}")
        logger.info(f"📋 CAPTIONS SUMMARY (ALL IMAGES)")
        logger.info(f"{'='*70}")
        
        for i, cap in enumerate(captions, 1):
            status = "✅" if cap.confidence > 0 else "❌"
            logger.info(f"\n{status} Image {i}: {cap.image.source_file} (Page {cap.image.page_number})")
            logger.info(f"   Size: {cap.image.width}x{cap.image.height}")
            logger.info(f"   Caption Preview: {cap.caption[:150]}...")
            logger.info(f"   Time: {cap.processing_time:.2f}s")
        
        logger.info(f"\n{'='*70}\n")
        
        return captions
    
    def switch_model(self, model_name: str) -> Dict[str, Any]:
        """
        Switch to a different vision model.
        
        Args:
            model_name: New model name
            
        Returns:
            Status dictionary
        """
        if model_name not in self.VISION_MODELS:
            return {
                "success": False,
                "message": f"Unknown model: {model_name}",
                "available_models": list(self.VISION_MODELS.keys())
            }
        
        old_model = self.model_name
        self.model_name = model_name
        
        logger.info(f"Vision model switched: {old_model} -> {model_name}")
        
        return {
            "success": True,
            "previous_model": old_model,
            "current_model": model_name,
            "model_info": self.VISION_MODELS[model_name]
        }
    
    @classmethod
    def get_available_models(cls) -> Dict[str, Dict]:
        """Get all available vision models."""
        return cls.VISION_MODELS.copy()
    
    def get_current_model_info(self) -> Dict[str, Any]:
        """Get info about current model."""
        return {
            "model": self.model_name,
            "info": self.VISION_MODELS.get(self.model_name, {}),
            "base_url": self.HUGGINGFACE_BASE_URL
        }
