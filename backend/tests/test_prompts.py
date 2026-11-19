"""Tests for language-aware grading prompts and language resolution."""

import json
import tempfile
import unittest
from pathlib import Path
from threading import RLock
from unittest.mock import MagicMock, patch

from langchain_core.documents import Document

from src.api.moodle_models import MoodleAssignRequest
from src.api.moodle_routes import moodle_grade_assignment
from src.rag.pipeline import RAGPipeline
from src.rag.prompt_builder import PromptBuilder
from src.rag.prompts import PROMPT_TEMPLATES, detect_language, normalize_language, resolve_language


EN_Q = "Explain how the TCP three-way handshake establishes a connection."
EN_A = "The client sends a SYN, the server answers with SYN-ACK, and the client confirms with an ACK."
ID_Q = "Jelaskan bagaimana proses three-way handshake pada TCP untuk membangun koneksi."
ID_A = "Klien mengirim SYN, lalu server membalas dengan SYN-ACK, dan klien mengonfirmasi dengan ACK."


class LanguageDetectionTest(unittest.TestCase):
    def test_detects_english_and_indonesian(self):
        self.assertEqual("en", detect_language(EN_Q, EN_A))
        self.assertEqual("id", detect_language(ID_Q, ID_A))

    def test_inconclusive_input_falls_back_to_indonesian(self):
        # Short or marker-free text keeps the historical (Indonesian) behavior.
        self.assertEqual("id", detect_language("TCP?", "SYN ACK"))
        self.assertEqual("id", detect_language("", None))

    def test_normalize_and_resolve(self):
        self.assertEqual("en", normalize_language("en_us"))
        self.assertEqual("id", normalize_language("ID"))
        self.assertEqual("auto", normalize_language("Auto"))
        self.assertIsNone(normalize_language("fr"))
        self.assertEqual("en", resolve_language("en", "id", ID_Q, ID_A))      # request override wins
        self.assertEqual("id", resolve_language(None, "id", EN_Q, EN_A))      # configured default
        self.assertEqual("en", resolve_language(None, "auto", EN_Q, EN_A))    # detection
        self.assertEqual("en", resolve_language("fr", "auto", EN_Q, EN_A))    # unknown -> default


class PromptBuilderLanguageTest(unittest.TestCase):
    def setUp(self):
        self.docs = [Document(page_content="TCP uses SYN, SYN-ACK, ACK.", metadata={"source": "w1.pdf", "page": 4})]
        self.rubric = {"Accuracy": {"description": "Correct steps", "max_score": 10}}

    def test_auto_builds_english_prompt_for_english_answers(self):
        builder = PromptBuilder(language="auto")
        prompt = builder.build_prompt(EN_Q, EN_A, self.rubric, self.docs)
        self.assertTrue(prompt.startswith("You are an expert essay grader."))
        self.assertIn("[Document 1] (Source: w1.pdf, Page: 4)", prompt)
        self.assertEqual("en", builder.last_language)

    def test_auto_builds_indonesian_prompt_for_indonesian_answers(self):
        builder = PromptBuilder(language="auto")
        prompt = builder.build_prompt(ID_Q, ID_A, self.rubric, self.docs)
        self.assertTrue(prompt.startswith("Anda adalah seorang penilai esai ahli."))
        self.assertIn("[Dokumen 1] (Sumber: w1.pdf, Halaman: 4)", prompt)
        self.assertEqual("id", builder.last_language)

    def test_explicit_language_overrides_default(self):
        builder = PromptBuilder(language="id")
        prompt = builder.build_prompt(ID_Q, ID_A, self.rubric, self.docs, language="en")
        self.assertIn("GRADING RUBRIC:", prompt)
        self.assertEqual("en", builder.last_language)

    def test_both_templates_request_the_same_json_schema(self):
        keys = ('"score"', '"feedback"', '"criterion_scores"', '"evidence"', '"citations"',
                '"text"', '"source"', '"page"', '"confidence"')
        for lang, template in PROMPT_TEMPLATES.items():
            rendered = template.format(question="q", rubric="{}", context="c", essay="e")
            for key in keys:
                self.assertIn(key, rendered, f"{lang} template misses {key}")
        payload = {"score": 70, "feedback": "ok", "criterion_scores": {}, "citations": [], "confidence": 0.7}
        self.assertEqual(payload, PromptBuilder().parse_llm_response(json.dumps(payload)))

    def test_english_empty_context_message(self):
        self.assertEqual("No relevant course material was found.", PromptBuilder()._format_context([], "en"))


class PipelineLanguageTest(unittest.TestCase):
    def test_pipeline_forwards_language_and_reports_it(self):
        pipeline = RAGPipeline.__new__(RAGPipeline)
        pipeline.retriever = MagicMock()
        pipeline.retriever.retrieve.return_value = [Document(page_content="SYN", metadata={})]
        pipeline.prompt_builder = PromptBuilder(language="auto")
        pipeline.llm = MagicMock()
        pipeline.llm.generate.return_value = '{"score": 90, "feedback": "Good", "confidence": 0.9}'

        result = pipeline.grade_essay(question=ID_Q, essay=ID_A, rubric={}, language="en")

        self.assertEqual("en", result["language"])
        self.assertTrue(pipeline.llm.generate.call_args.args[0].startswith("You are an expert"))
        self.assertEqual("Unknown", result["retrieved_documents"][0]["source"])
        self.assertEqual(f"{ID_Q}\n\n{ID_A}", pipeline.retriever.retrieve.call_args.args[0])


class MoodleLanguageCompatTest(unittest.TestCase):
    def setUp(self):
        self.grader = MagicMock()
        self.grader.grade_essay.return_value = {"success": True, "score": 80, "feedback": "Baik",
                                                "confidence": 0.8, "language": "id"}
        self.patches = [
            patch("src.api.moodle_routes.get_grader", return_value=self.grader),
            patch("src.api.moodle_routes.get_operation_lock", return_value=RLock()),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_moodle_request_without_lang_does_not_force_english(self):
        response = moodle_grade_assignment(MoodleAssignRequest(course_id=3, question=ID_Q, essay=ID_A))
        self.assertIsNone(self.grader.grade_essay.call_args.kwargs["language"])
        self.assertEqual("id", response.language)

    def test_moodle_explicit_lang_is_honored(self):
        moodle_grade_assignment(MoodleAssignRequest(course_id=3, question=ID_Q, essay=ID_A, lang="en_us"))
        self.assertEqual("en", self.grader.grade_essay.call_args.kwargs["language"])
        moodle_grade_assignment(MoodleAssignRequest(course_id=3, question=EN_Q, essay=EN_A, lang="id"))
        self.assertEqual("id", self.grader.grade_essay.call_args.kwargs["language"])



class V1LanguageTest(unittest.TestCase):
    def test_v1_language_field_is_forwarded_and_validated(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from src.api.v1_routes import router

        grader = MagicMock()
        grader.grade_essay.return_value = {"success": True, "score": 75, "feedback": "Good",
                                           "confidence": 0.7, "language": "en"}
        app = FastAPI()
        app.include_router(router)
        with patch("src.api.v1_routes.get_grader", return_value=grader), \
                patch("src.api.v1_routes.get_operation_lock", return_value=RLock()):
            client = TestClient(app)
            ok = client.post("/v1/namespaces/cs-101/grade",
                             json={"question": ID_Q, "essay": ID_A, "language": "en"})
            default = client.post("/v1/namespaces/cs-101/grade", json={"question": EN_Q, "essay": EN_A})
            bad = client.post("/v1/namespaces/cs-101/grade",
                              json={"question": EN_Q, "essay": EN_A, "language": "fr"})

        self.assertEqual(200, ok.status_code)
        self.assertEqual("en", ok.json()["language"])
        self.assertEqual("en", grader.grade_essay.call_args_list[0].kwargs["language"])
        self.assertIsNone(grader.grade_essay.call_args_list[1].kwargs["language"])
        self.assertEqual(422, bad.status_code)


if __name__ == "__main__":
    unittest.main()
