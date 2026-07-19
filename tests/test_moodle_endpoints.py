"""Contract smoke tests for every endpoint called by the Moodle plugins."""

import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from threading import RLock
from unittest.mock import patch

from fastapi import UploadFile

from src.api.moodle_models import MoodleAssignRequest
from src.api.moodle_routes import (
    assign_server_status,
    clear_course_collection,
    clear_course_materials,
    delete_course_material_file,
    get_course_collection,
    get_course_materials_status,
    moodle_grade_assignment,
    moodle_server_status,
    router,
    upload_course_material,
)


class _FakeVectorStore:
    def get_count(self, course_id=None):
        return 3


class _FakePipeline:
    current_embedding_model = "test-embedding"
    vectorstore = _FakeVectorStore()

    def get_vectorstore_info(self, course_id=None):
        return {"collection_name": f"course_{course_id or 'default'}", "document_count": 3}

    def get_llm_info(self):
        return {"provider": "test", "model": "test-model"}


class _FakeGrader:
    rag_pipeline = _FakePipeline()

    def grade_essay(self, **kwargs):
        return {
            "success": True,
            "score": 80,
            "feedback": "Feedback",
            "criterion_scores": {},
            "citations": [{"text": "Evidence", "source": "material.pdf", "page": "1"}],
            "confidence": 0.9,
            "retrieved_documents": [],
        }

    def ingest_course_materials(self, paths, course_id=None):
        return {
            "success": True,
            "message": "Processed",
            "documents_loaded": 1,
            "chunks_created": 3,
            "total_documents_in_db": 3,
            "errors": [],
        }

    def update_chunking_config(self, **kwargs):
        return None

    def clear_vector_store(self, course_id=None):
        return None

    def delete_course_material_file(self, course_id, filename):
        return True


class MoodleEndpointTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.fake_grader = _FakeGrader()
        self.grader_patch = patch(
            "src.api.moodle_routes.get_grader", return_value=self.fake_grader
        )
        self.lock_patch = patch(
            "src.api.moodle_routes.get_operation_lock", return_value=RLock()
        )
        self.data_patch = patch("src.utils.DATA_DIR", Path(self.tempdir.name))
        self.grader_patch.start()
        self.lock_patch.start()
        self.data_patch.start()

    def tearDown(self):
        self.data_patch.stop()
        self.lock_patch.stop()
        self.grader_patch.stop()
        self.tempdir.cleanup()

    def test_grading_contract(self):
        response = moodle_grade_assignment(
            MoodleAssignRequest(**{
                "course_id": 12,
                "question": "Question",
                "essay": "Student answer",
                "rubric": {},
                "maximum_grade": 50,
                "assignment_id": 45,
            })
        )
        self.assertTrue(response.success)
        self.assertEqual(40.0, response.score)

    def test_material_upload_supports_all_plugin_formats(self):
        for extension in ("pdf", "pptx", "docx", "txt"):
            with self.subTest(extension=extension):
                response = upload_course_material(
                    file=UploadFile(
                        file=BytesIO(b"test"),
                        filename=f"material.{extension}",
                    ),
                    course_id=12,
                    course_name="Course",
                )
                self.assertTrue(response["success"])
                self.assertEqual(3, response["chunk_count"])

    def test_material_management_and_status_contracts(self):
        responses = [
            moodle_server_status(),
            assign_server_status(),
            get_course_collection(12),
            get_course_materials_status(12),
            delete_course_material_file(12, "material.pdf"),
            clear_course_materials(12),
            clear_course_collection(12),
        ]
        for response in responses:
            success = response.get("success", True) if isinstance(response, dict) else getattr(response, "success", True)
            self.assertTrue(success)

    def test_router_exposes_every_plugin_operation(self):
        available = {
            (method, route.path)
            for route in router.routes
            for method in route.methods
        }
        expected = {
            ("POST", "/assign/answer"),
            ("POST", "/course/materials/upload"),
            ("POST", "/course/materials/clear"),
            ("DELETE", "/course/materials/file"),
            ("GET", "/moodle/status"),
            ("GET", "/assign/status"),
            ("GET", "/collections/{course_id}"),
        }
        self.assertTrue(expected.issubset(available))


if __name__ == "__main__":
    unittest.main()
