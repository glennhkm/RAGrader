"""Document and student content never reaches logs at INFO level or above.

Captions are generated for course materials and for students' answer
documents alike, so caption text and uploaded answer paths are only logged
at DEBUG (an explicit opt-in), while INFO keeps operational metadata.
"""

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from langchain_core.documents import Document
from loguru import logger

from src.ingestion.image_extractor import ExtractedImage
from src.ingestion.preprocessor import DocumentPreprocessor
from src.ingestion.vision_captioner import ImageCaption, VisionCaptioner
from src.rag.pipeline import RAGPipeline
from src.utils.config import load_settings

SECRET_CAPTION = "Student Jane Doe drew the SYN-ACK diagram"
STUDENT_PATH = Path("/srv/uploads/jane_doe_student_answer.pdf")


class _CapturingLogs:
    """Collect formatted log messages per level while the context is active."""

    def __enter__(self):
        self.records = []
        self._sink_id = logger.add(
            lambda message: self.records.append(message.record), level="DEBUG", format="{message}"
        )
        return self

    def __exit__(self, *exc):
        logger.remove(self._sink_id)

    def text(self, min_level: str) -> str:
        threshold = logger.level(min_level).no
        return "\n".join(r["message"] for r in self.records if r["level"].no >= threshold)


def _image():
    return ExtractedImage(image_data=b"\x89img", image_format="png", source_file=STUDENT_PATH.name,
                          page_number=2, image_index=0, width=10, height=10, image_hash="h")


class _FakeVisionClient:
    def __init__(self):
        outer = self
        self.chat = SimpleNamespace(completions=SimpleNamespace(
            create=lambda **_: SimpleNamespace(choices=[SimpleNamespace(
                message=SimpleNamespace(content=SECRET_CAPTION))])))

    def __call__(self, **kwargs):
        return self


class LogHygieneTest(unittest.TestCase):
    def test_vision_captioner_logs_caption_text_only_at_debug(self):
        settings = load_settings(env={"VISION_BASE_URL": "http://vision.local/v1", "VISION_MODEL": "vlm"})
        captioner = VisionCaptioner(settings=settings.vision, prompt_settings=settings.prompt,
                                    client_factory=_FakeVisionClient())
        with _CapturingLogs() as logs:
            caption = captioner.caption_image(_image())
        self.assertIn(SECRET_CAPTION, caption.caption)
        self.assertNotIn(SECRET_CAPTION, logs.text("INFO"))
        self.assertNotIn(STUDENT_PATH.name, logs.text("INFO"))
        self.assertIn("page=2", logs.text("INFO"))
        self.assertIn(SECRET_CAPTION, logs.text("DEBUG"))

    def test_preprocessor_logs_caption_documents_only_at_debug(self):
        preprocessor = DocumentPreprocessor(include_image_captions=True)
        caption = ImageCaption(image=_image(), caption=SECRET_CAPTION, model_used="vlm")
        with _CapturingLogs() as logs:
            docs = preprocessor.create_image_caption_documents([caption])
        self.assertEqual(1, len(docs))
        self.assertNotIn(SECRET_CAPTION, logs.text("INFO"))
        self.assertNotIn(STUDENT_PATH.name, logs.text("INFO"))
        self.assertIn("1 image caption document", logs.text("INFO"))
        self.assertIn(SECRET_CAPTION, logs.text("DEBUG"))

    def test_answer_document_path_is_not_logged_at_info(self):
        class _Loader:
            def __init__(self, *args, **kwargs):
                pass

            def load_document(self, path):
                return {"documents": [Document(page_content="answer", metadata={"page": 1})],
                        "images": [], "captions": []}

        pipeline = RAGPipeline.__new__(RAGPipeline)
        with _CapturingLogs() as logs, patch("src.rag.pipeline.DocumentLoader", _Loader), \
                patch.object(RAGPipeline, "grade_essay", return_value={"score": 1}):
            pipeline.grade_essay_from_document(question="Q", document_path=STUDENT_PATH, rubric={})
        self.assertNotIn("jane_doe", logs.text("INFO"))
        self.assertIn(".pdf", logs.text("INFO"))


if __name__ == "__main__":
    unittest.main()
