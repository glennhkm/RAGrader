"""Contract smoke tests for every endpoint called by the Moodle plugins."""

import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from threading import RLock
from unittest.mock import call, patch

from fastapi import HTTPException, UploadFile

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

    def get_retriever_config(self):
        return {"reranker_type": "bm25", "requested_reranker_type": "local_cross_encoder",
                "reranker_fallback": True, "reranker_error": "model not supported"}


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
            "integrity_warnings": ["possible_prompt_injection:grade_request"],
        }

    def ingest_course_materials(self, paths, course_id=None, material_id=None):
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

    def delete_course_material_file(self, course_id, filename, material_id=None):
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
        self.lock_mock = self.lock_patch.start()
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
        self.assertEqual(["possible_prompt_injection:grade_request"], response.integrity_warnings)
        self.lock_mock.assert_called_once_with(12)

    def test_grading_contract_forwards_source_filter(self):
        with patch.object(self.fake_grader, "grade_essay", wraps=self.fake_grader.grade_essay) as spy:
            response = moodle_grade_assignment(
                MoodleAssignRequest(**{
                    "course_id": 12,
                    "question": "Question",
                    "essay": "Student answer",
                    "rubric": {},
                    "maximum_grade": 100,
                    "assignment_id": 45,
                    "source_filter": ["week1.pdf", "week2.pptx"],
                })
            )
        self.assertTrue(response.success)
        self.assertEqual(
            {"source": {"$in": ["week1.pdf", "week2.pptx"]}},
            spy.call_args.kwargs["metadata_filter"],
        )

    def _grade(self, **extra):
        return moodle_grade_assignment(
            MoodleAssignRequest(**{
                "course_id": 12, "question": "Question", "essay": "Student answer",
                "assignment_id": 45, **extra,
            })
        )

    def test_grading_material_ids_are_anded_with_source_filter(self):
        with patch.object(self.fake_grader, "grade_essay", wraps=self.fake_grader.grade_essay) as spy:
            self._grade(source_filter=["week1.pdf"], material_ids=["airagmaterial:1", "airagassign:5"])
        self.assertEqual(
            {"$and": [
                {"source": {"$eq": "week1.pdf"}},
                {"material_id": {"$in": ["airagmaterial:1", "airagassign:5"]}},
            ]},
            spy.call_args.kwargs["metadata_filter"],
        )

    def test_grading_without_new_fields_keeps_filter_unchanged(self):
        with patch.object(self.fake_grader, "grade_essay", wraps=self.fake_grader.grade_essay) as spy:
            self._grade()
            self.assertIsNone(spy.call_args.kwargs["metadata_filter"])
            self._grade(source_filter=["a.pdf"], module_filter=["w1"])
            self.assertEqual(
                {"$and": [{"module": {"$eq": "w1"}}, {"source": {"$eq": "a.pdf"}}]},
                spy.call_args.kwargs["metadata_filter"],
            )

    def test_grading_rejects_empty_or_invalid_material_ids(self):
        for ids in ([], ["  "], ["../x"]):
            with self.subTest(ids=ids):
                with self.assertRaises(HTTPException) as ctx:
                    self._grade(material_ids=ids)
                self.assertEqual(400, ctx.exception.status_code)

    def test_upload_and_delete_reject_invalid_material_id(self):
        upload = UploadFile(filename="a.txt", file=BytesIO(b"x"))
        with self.assertRaises(HTTPException) as ctx:
            upload_course_material(file=upload, course_id=12, course_name="", material_id="../x")
        self.assertEqual(400, ctx.exception.status_code)
        with self.assertRaises(HTTPException) as ctx:
            delete_course_material_file(course_id=12, filename="a.txt", material_id="../x")
        self.assertEqual(400, ctx.exception.status_code)

    def test_owned_upload_uses_material_subdirectory_and_forwards_id(self):
        upload = UploadFile(filename="a.txt", file=BytesIO(b"x"))
        with patch.object(self.fake_grader, "ingest_course_materials",
                          wraps=self.fake_grader.ingest_course_materials) as spy:
            upload_course_material(file=upload, course_id=12, course_name="",
                                   material_id="airagmaterial:7")
        path = spy.call_args.args[0][0]
        self.assertEqual(Path(self.tempdir.name) / "uploads" / "course_12" / "airagmaterial_7" / "a.txt", path)
        self.assertEqual("airagmaterial:7", spy.call_args.kwargs["material_id"])

    def test_delete_forwards_valid_material_id_and_legacy_delete_passes_none(self):
        with patch.object(self.fake_grader, "delete_course_material_file",
                          return_value=True) as spy:
            delete_course_material_file(course_id=12, filename="a.txt",
                                        material_id=" airagassign:9 ")
            delete_course_material_file(course_id=12, filename="a.txt", material_id=None)
        self.assertEqual(call("12", "a.txt", material_id="airagassign:9"), spy.call_args_list[0])
        self.assertEqual(call("12", "a.txt"), spy.call_args_list[1])

    def test_delete_store_failure_returns_500_not_success_false(self):
        with patch.object(self.fake_grader, "delete_course_material_file",
                          side_effect=RuntimeError("chroma unavailable")):
            with self.assertRaises(HTTPException) as ctx:
                delete_course_material_file(course_id=12, filename="a.txt",
                                            material_id="airagmaterial:7")
        self.assertEqual(500, ctx.exception.status_code)

    def test_upload_surfaces_ingest_store_failure_as_500(self):
        failed = {"success": False, "message": "Error: chroma unavailable"}
        with patch.object(self.fake_grader, "ingest_course_materials", return_value=failed):
            with self.assertRaises(HTTPException) as ctx:
                upload_course_material(file=UploadFile(filename="a.txt", file=BytesIO(b"x")),
                                       course_id=12, course_name="",
                                       material_id="airagmaterial:7")
        self.assertEqual(500, ctx.exception.status_code)

    def test_grading_rejects_explicit_filter_that_scopes_nothing(self):
        for filters in ({"source_filter": []}, {"source_filter": ["  "]}, {"module_filter": [""]}):
            with self.subTest(filters=filters):
                with patch.object(self.fake_grader, "grade_essay") as spy:
                    with self.assertRaises(HTTPException) as ctx:
                        moodle_grade_assignment(
                            MoodleAssignRequest(**{
                                "course_id": 12,
                                "question": "Question",
                                "essay": "Student answer",
                                "assignment_id": 45,
                                **filters,
                            })
                        )
                self.assertEqual(400, ctx.exception.status_code)
                spy.assert_not_called()

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
        self.assertEqual(
            [call(12, write=True)] * 4,
            self.lock_mock.call_args_list,
        )

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

    def test_deleting_a_collection_also_removes_its_uploaded_files(self):
        # DELETE /collections/{id} must not leave student/course files behind on
        # disk (same retention behavior as POST /course/materials/clear).
        course_dir = Path(self.tempdir.name) / "uploads" / "course_12"
        other_dir = Path(self.tempdir.name) / "uploads" / "course_13"
        for directory in (course_dir, other_dir):
            directory.mkdir(parents=True)
            (directory / "material.pdf").write_bytes(b"pdf")

        response = clear_course_collection(12)

        self.assertTrue(response["success"])
        self.assertFalse(course_dir.exists())
        self.assertTrue((other_dir / "material.pdf").exists())

    def test_status_lists_owned_uploads_in_material_subdirectories(self):
        course_dir = Path(self.tempdir.name) / "uploads" / "course_12"
        (course_dir / "airagmaterial_3").mkdir(parents=True)
        (course_dir / "airagmaterial_4").mkdir()
        (course_dir / "legacy.pdf").write_bytes(b"x")
        (course_dir / "airagmaterial_3" / "notes.txt").write_bytes(b"x")
        (course_dir / "airagmaterial_4" / "notes.txt").write_bytes(b"x")
        (course_dir / "airagmaterial_4" / "zeta.txt").write_bytes(b"x")

        status = get_course_materials_status(12)

        self.assertEqual(["legacy.pdf", "notes.txt", "zeta.txt"], status["uploaded_files"])
        self.assertEqual(3, status["files_count"])

    def test_status_reports_reranker_fallback(self):
        status = moodle_server_status()
        self.assertTrue(status.ready)
        self.assertTrue(status.retrieval["reranker_fallback"])
        self.assertEqual("local_cross_encoder", status.retrieval["requested_reranker_type"])

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
