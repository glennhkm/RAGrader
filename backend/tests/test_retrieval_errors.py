"""An infrastructure failure must never look like a graded answer or missing materials."""

import unittest
from unittest.mock import MagicMock

from langchain_core.documents import Document

from src.rag.pipeline import RAGPipeline
from src.vectorstore.chroma_store import VectorStore


class StoreSearchErrorTest(unittest.TestCase):
    def _store(self, method):
        store = VectorStore.__new__(VectorStore)
        chroma = MagicMock()
        getattr(chroma, method).side_effect = RuntimeError("Error code: 429 rate limit")
        store._get_vectorstore = lambda course_id=None: chroma
        return store

    def test_search_errors_propagate_instead_of_empty_results(self):
        for method in ("similarity_search", "similarity_search_with_score"):
            with self.subTest(method=method), self.assertRaisesRegex(RuntimeError, "429"):
                getattr(self._store(method), method)("q", course_id="7")


class PipelineErrorTest(unittest.TestCase):
    def _pipeline(self):
        p = RAGPipeline.__new__(RAGPipeline)
        p.retriever, p.llm, p.prompt_builder = MagicMock(), MagicMock(), MagicMock()
        return p

    def test_retrieval_outage_is_a_failed_grade(self):
        p = self._pipeline()
        p.retriever.retrieve.side_effect = RuntimeError("Error code: 429 rate limit")
        result = p.grade_essay("q", "e", {}, course_id="7")
        self.assertIs(False, result["success"])
        self.assertIn("429", result["error"])
        self.assertNotIn("No relevant materials", result["error"])

    def test_llm_outage_is_a_failed_grade(self):
        p = self._pipeline()
        p.retriever.retrieve.return_value = [Document(page_content="x", metadata={})]
        p.llm.generate.side_effect = RuntimeError("All LLM providers failed")
        self.assertIs(False, p.grade_essay("q", "e", {})["success"])

    def test_empty_retrieval_is_still_no_materials(self):
        p = self._pipeline()
        p.retriever.retrieve.return_value = []
        self.assertEqual("No relevant materials retrieved", p.grade_essay("q", "e", {})["error"])


if __name__ == "__main__":
    unittest.main()
