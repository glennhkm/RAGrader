"""Characterization tests for PromptBuilder.

These lock in the current grading prompt and response parsing behavior before
Cycle 2 adds language-aware templates, so any change to the Indonesian prompt
or to the parser contract is deliberate and visible in review.
"""

import json
import unittest
from pathlib import Path

from langchain_core.documents import Document

from src.rag.prompt_builder import PromptBuilder


FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


class PromptBuilderTemplateTest(unittest.TestCase):
    def test_indonesian_template_matches_snapshot(self):
        snapshot = (FIXTURES_DIR / "prompt_template_id.txt").read_text(encoding="utf-8")
        self.assertEqual(snapshot, PromptBuilder().template)

    def test_build_prompt_includes_all_inputs_and_records_last_prompt(self):
        builder = PromptBuilder()
        rubric = {"Akurasi": {"description": "Benar secara konsep", "max_score": 60}}
        docs = [
            Document(page_content="TCP menjamin pengiriman andal.", metadata={"source": "w1.pdf", "page": 2}),
            Document(page_content="Tanpa metadata halaman.", metadata={}),
        ]

        prompt = builder.build_prompt(
            question="Apa fungsi TCP?",
            essay="TCP menjamin data sampai berurutan.",
            rubric=rubric,
            retrieved_docs=docs,
        )

        self.assertIn("Apa fungsi TCP?", prompt)
        self.assertIn("TCP menjamin data sampai berurutan.", prompt)
        self.assertIn(json.dumps(rubric, indent=2), prompt)
        self.assertIn("[Dokumen 1] (Sumber: w1.pdf, Halaman: 2)\nTCP menjamin pengiriman andal.", prompt)
        self.assertIn("[Dokumen 2] (Sumber: Tidak Diketahui, Halaman: N/A)", prompt)
        # Literal JSON braces in the template must survive str.format().
        self.assertIn('"criterion_scores": {', prompt)
        self.assertTrue(prompt.rstrip().endswith("Respons:"))
        self.assertEqual(prompt, builder.last_prompt)

    def test_empty_rubric_is_rendered_as_empty_json_object(self):
        prompt = PromptBuilder().build_prompt(
            question="Q", essay="A", rubric={}, retrieved_docs=[]
        )
        self.assertIn("RUBRIK PENILAIAN:\n{}\n", prompt)

    def test_format_context_without_documents(self):
        self.assertEqual(
            "Tidak ada materi kuliah yang relevan ditemukan.",
            PromptBuilder()._format_context([]),
        )


class PromptBuilderParserTest(unittest.TestCase):
    def setUp(self):
        self.builder = PromptBuilder()
        self.payload = {
            "score": 85,
            "feedback": "Jawaban tepat.",
            "criterion_scores": {"Akurasi": {"score": 50, "feedback": "Baik", "evidence": "TCP andal"}},
            "citations": [{"text": "TCP andal", "source": "w1.pdf", "page": 2}],
            "confidence": 0.9,
        }

    def test_parses_plain_json(self):
        self.assertEqual(self.payload, self.builder.parse_llm_response(json.dumps(self.payload)))

    def test_parses_json_wrapped_in_prose_and_markdown_fence(self):
        response = "Berikut hasilnya:\n```json\n" + json.dumps(self.payload) + "\n```\nSemoga membantu."
        self.assertEqual(self.payload, self.builder.parse_llm_response(response))

    def test_malformed_json_returns_fallback(self):
        result = self.builder.parse_llm_response('{"score": 80, "feedback": ')
        self.assertEqual(0, result["score"])
        self.assertEqual(0.5, result["confidence"])
        self.assertEqual({}, result["criterion_scores"])
        self.assertEqual([], result["citations"])
        self.assertIn("error", result)

    def test_response_without_json_returns_fallback_with_raw_text(self):
        result = self.builder.parse_llm_response("Saya tidak bisa menilai jawaban ini.")
        self.assertEqual("Saya tidak bisa menilai jawaban ini.", result["feedback"])
        self.assertIn("error", result)


if __name__ == "__main__":
    unittest.main()
