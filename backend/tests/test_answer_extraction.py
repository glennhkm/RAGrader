"""Answer extraction from student documents keeps one language end to end."""

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from langchain_core.documents import Document

from src.rag.pipeline import RAGPipeline
from src.rag.prompts import format_image_captions
from src.utils.config import override_settings

EN_TEXT = "The handshake is used because it is the way that TCP opens a connection."
ID_TEXT = "Jabat tangan ini digunakan karena merupakan cara yang dipakai untuk membuka koneksi."


def _fake_loader(text):
    class _Loader:
        def __init__(self, *args, **kwargs):
            pass

        def load_document(self, path):
            return {
                "documents": [Document(page_content=text, metadata={"page": 1})],
                "images": [object()],
                "captions": [SimpleNamespace(caption="A diagram of the handshake.")],
            }

    return _Loader


class FormatImageCaptionsTest(unittest.TestCase):
    def test_labels_follow_language_and_empty_input_adds_nothing(self):
        self.assertEqual("", format_image_captions([], "en"))
        en = format_image_captions(["a", "b"], "en")
        self.assertIn("--- Image Descriptions in the Document ---", en)
        self.assertIn("[Image 1]: a", en)
        self.assertIn("[Image 2]: b", en)
        idn = format_image_captions(["a"], "id")
        self.assertIn("--- Deskripsi Gambar dalam Dokumen ---", idn)
        self.assertIn("[Gambar 1]: a", idn)

    def test_unknown_language_uses_fallback_labels(self):
        self.assertIn("[Gambar 1]: a", format_image_captions(["a"], "fr"))


class ExtractAnswerFromDocumentTest(unittest.TestCase):
    def _extract(self, text, **kwargs):
        with patch("src.rag.pipeline.DocumentLoader", _fake_loader(text)):
            return RAGPipeline.extract_answer_from_document(Path("answer.pdf"), enable_vision=True, **kwargs)

    def test_english_answer_gets_english_caption_labels(self):
        with override_settings(PROMPT_LANGUAGE="auto"):
            result = self._extract(EN_TEXT)
        self.assertTrue(result["success"])
        self.assertEqual("en", result["language"])
        self.assertIn("[Image 1]: A diagram of the handshake.", result["extracted_text"])
        self.assertNotIn("Gambar", result["extracted_text"])

    def test_indonesian_answer_keeps_indonesian_caption_labels(self):
        with override_settings(PROMPT_LANGUAGE="auto"):
            result = self._extract(ID_TEXT)
        self.assertEqual("id", result["language"])
        self.assertIn("--- Deskripsi Gambar dalam Dokumen ---", result["extracted_text"])
        self.assertIn("[Gambar 1]: A diagram of the handshake.", result["extracted_text"])

    def test_explicit_language_and_configured_language_take_precedence(self):
        with override_settings(PROMPT_LANGUAGE="auto"):
            self.assertEqual("id", self._extract(EN_TEXT, language="id")["language"])
        with override_settings(PROMPT_LANGUAGE="en"):
            self.assertEqual("en", self._extract(ID_TEXT)["language"])

    def test_captions_can_be_excluded(self):
        result = self._extract(EN_TEXT, include_image_captions=False)
        self.assertEqual(EN_TEXT, result["extracted_text"])
        self.assertEqual([], result["image_captions"])


class GradeEssayFromDocumentLanguageTest(unittest.TestCase):
    def test_language_is_forwarded_to_extraction(self):
        pipeline = RAGPipeline.__new__(RAGPipeline)
        with patch.object(RAGPipeline, "extract_answer_from_document", return_value={
            "success": True, "extracted_text": EN_TEXT, "images_found": 0,
            "image_captions": [], "pages_processed": 1, "error": None, "language": "en",
        }) as extract, patch.object(RAGPipeline, "grade_essay", return_value={"score": 1}):
            pipeline.grade_essay_from_document(
                question="Q", document_path=Path("a.pdf"), rubric={}, language="en",
            )
        self.assertEqual("en", extract.call_args.kwargs["language"])


if __name__ == "__main__":
    unittest.main()
