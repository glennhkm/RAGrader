"""Unit tests verifying metadata propagation on ingest and filter forwarding on grading."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from langchain_core.documents import Document

from src.grading.grader import EssayGrader
from src.rag.pipeline import RAGPipeline
from src.rag.retriever import Retriever


class PipelineScopingTest(unittest.TestCase):
    def test_retriever_forwards_metadata_filter(self):
        mock_vs = MagicMock()
        mock_vs.similarity_search.return_value = [
            Document(page_content="Evidence text", metadata={"source": "w1.pdf", "page": 1})
        ]
        retriever = Retriever(vectorstore=mock_vs, top_k=5, enable_reranking=False, rerank_top_k=3)
        where = {"module": {"$in": ["week-1", "week-2"]}}

        docs = retriever.retrieve("What is TCP?", course_id="cs101", metadata_filter=where)

        self.assertEqual(1, len(docs))
        mock_vs.similarity_search.assert_called_once_with(
            query="What is TCP?",
            k=3,
            filter=where,
            course_id="cs101",
        )

    def test_retriever_with_scores_forwards_metadata_filter(self):
        mock_vs = MagicMock()
        mock_vs.similarity_search.return_value = [
            Document(page_content="Evidence text", metadata={"source": "w1.pdf", "page": 1})
        ]
        retriever = Retriever(vectorstore=mock_vs, top_k=5, enable_reranking=False, rerank_top_k=3)
        where = {"module": {"$eq": "week-1"}}

        docs_with_scores = retriever.retrieve_with_scores(
            "What is TCP?",
            course_id="cs101",
            metadata_filter=where,
        )

        self.assertEqual(1, len(docs_with_scores))
        mock_vs.similarity_search.assert_called_once_with(
            query="What is TCP?",
            k=3,
            filter=where,
            course_id="cs101",
        )

    def test_pipeline_grade_essay_forwards_metadata_filter_and_handles_empty_scope(self):
        pipeline = RAGPipeline.__new__(RAGPipeline)
        pipeline.retriever = MagicMock()
        pipeline.retriever.retrieve.return_value = []
        pipeline.prompt_builder = MagicMock()
        pipeline.llm = MagicMock()

        where = {"module": {"$eq": "week-1"}}
        result = pipeline.grade_essay(
            question="What is TCP?",
            essay="Reliable stream.",
            rubric={},
            course_id="net-101",
            metadata_filter=where,
        )

        pipeline.retriever.retrieve.assert_called_once_with(
            "What is TCP?\n\nReliable stream.",
            course_id="net-101",
            metadata_filter=where,
        )
        self.assertFalse(result["success"])
        self.assertEqual("No relevant materials retrieved", result["error"])
        self.assertEqual([], result["retrieved_documents"])

    def test_grade_essay_from_document_forwards_namespace_and_filter(self):
        pipeline = RAGPipeline.__new__(RAGPipeline)
        pipeline.extract_answer_from_document = MagicMock(return_value={
            "success": True,
            "extracted_text": "TCP is a reliable transport protocol.",
            "images_found": 0,
            "image_captions": [],
            "pages_processed": 1,
            "error": None,
        })
        pipeline.grade_essay = MagicMock(return_value={"score": 80, "feedback": "Good."})
        where = {"source": {"$eq": "week1.pdf"}}

        result = pipeline.grade_essay_from_document(
            question="What is TCP?",
            document_path=Path("answer.docx"),
            rubric={},
            course_id="net-101",
            metadata_filter=where,
        )

        pipeline.grade_essay.assert_called_once_with(
            question="What is TCP?",
            essay="TCP is a reliable transport protocol.",
            rubric={},
            course_id="net-101",
            metadata_filter=where,
            language=None,
        )
        self.assertEqual(80, result["score"])
        self.assertEqual(1, result["extraction_info"]["pages_processed"])

    def test_grader_attaches_module_and_tags_and_passes_filter(self):
        with tempfile.TemporaryDirectory() as tempdir:
            sample = Path(tempdir) / "week1.txt"
            sample.write_text("TCP provides reliable ordered byte delivery.", encoding="utf-8")

            with patch("src.grading.grader.RAGPipeline") as mock_pipeline_cls:
                mock_pipeline = mock_pipeline_cls.return_value
                mock_pipeline.vectorstore.get_count.return_value = 1
                mock_pipeline.grade_essay.return_value = {
                    "success": True,
                    "score": 90,
                    "feedback": "Accurate.",
                    "citations": [],
                    "confidence": 0.9,
                }

                config = {
                    "document_processing": {"chunk_size": 500, "chunk_overlap": 50, "separators": ["\n\n", "\n", " "]},
                    "llm": {"provider": "provider_chain", "model_name": "test"},
                    "multimodal": {"enable_image_extraction": False, "enable_vision_captioning": False},
                }
                grader = EssayGrader(config)

                ingest_res = grader.ingest_course_materials(
                    [sample],
                    course_id="net-101",
                    module="week-1",
                    tags={"topic": "transport"},
                )
                self.assertTrue(ingest_res["success"])
                added_docs = mock_pipeline.vectorstore.add_documents.call_args[0][0]
                self.assertEqual("week-1", added_docs[0].metadata["module"])
                self.assertEqual("transport", added_docs[0].metadata["tag_topic"])

                where = {"module": {"$eq": "week-1"}}
                grader.grade_essay(
                    question="What does TCP do?",
                    essay="Reliable delivery.",
                    rubric={},
                    course_id="net-101",
                    metadata_filter=where,
                )
                mock_pipeline.grade_essay.assert_called_once_with(
                    question="What does TCP do?",
                    essay="Reliable delivery.",
                    rubric={},
                    course_id="net-101",
                    metadata_filter=where,
                    language=None,
                )


if __name__ == "__main__":
    unittest.main()
