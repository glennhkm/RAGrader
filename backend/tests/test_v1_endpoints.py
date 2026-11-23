"""Contract tests for generic /v1/namespaces/* autograding endpoints."""

import json
import tempfile
import unittest
from pathlib import Path
from threading import RLock
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.runtime import AppRuntime
from src.utils.config import load_settings, override_settings
from src.api.v1_routes import router as v1_router


class _FakePipeline:
    current_embedding_model = "BAAI/bge-m3"

    def __init__(self):
        self.last_info_course_id = None

    def get_vectorstore_info(self, course_id=None):
        self.last_info_course_id = course_id
        return {"collection_name": f"ns_{course_id}", "document_count": 4}


class _FakeGrader:
    def __init__(self):
        self.rag_pipeline = _FakePipeline()
        self.last_ingest_kwargs = None
        self.last_grade_kwargs = None
        self.last_delete_args = None
        self.last_clear_course_id = None
        self.ingest_response = {"success": True, "documents_loaded": 1, "chunks_created": 4, "errors": []}

    def ingest_course_materials(self, paths, **kwargs):
        self.last_ingest_kwargs = {"paths": paths, **kwargs}
        return self.ingest_response

    def grade_essay(self, **kwargs):
        self.last_grade_kwargs = kwargs
        return {
            "success": True,
            "score": 85,
            "feedback": "Grounded answer.",
            "criterion_scores": {},
            "citations": [{"text": "TCP ensures delivery", "source": "week1.pdf", "page": 1}],
            "confidence": 0.91,
            "retrieved_documents": [],
            "integrity_warnings": ["ungrounded_citations_removed:1"],
        }

    def delete_course_material_file(self, course_id, filename):
        self.last_delete_args = (course_id, filename)
        return True

    def clear_vector_store(self, course_id=None):
        self.last_clear_course_id = course_id
        return None


class V1EndpointTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.fake_grader = _FakeGrader()
        app = FastAPI()
        app.include_router(v1_router)
        self.client = TestClient(app)

        self.p1 = patch("src.api.v1_routes.get_grader", return_value=self.fake_grader)
        self.p2 = patch("src.api.v1_routes.get_operation_lock", return_value=RLock())
        self.p3 = patch("src.utils.DATA_DIR", Path(self.tempdir.name))
        self.p1.start()
        self.p2.start()
        self.p3.start()

    def tearDown(self):
        self.p3.stop()
        self.p2.stop()
        self.p1.stop()
        self.tempdir.cleanup()

    def test_upload_with_module_and_tags_then_grade_with_scope_filter(self):
        upload_resp = self.client.post(
            "/v1/namespaces/cs-101/materials",
            data={"module": "week-1", "tags": json.dumps({"topic": "networking"})},
            files={"file": ("week1.txt", b"TCP three-way handshake", "text/plain")},
        )
        self.assertEqual(200, upload_resp.status_code)
        self.assertTrue(upload_resp.json()["success"])
        self.assertEqual("cs-101", upload_resp.json()["namespace"])
        self.assertEqual("v1:cs-101", self.fake_grader.last_ingest_kwargs["course_id"])
        self.assertEqual("week-1", self.fake_grader.last_ingest_kwargs["module"])
        self.assertEqual({"topic": "networking"}, self.fake_grader.last_ingest_kwargs["tags"])

        grade_resp = self.client.post(
            "/v1/namespaces/cs-101/grade",
            json={
                "question": "Explain TCP handshake",
                "essay": "It uses SYN, SYN-ACK, ACK.",
                "maximum_grade": 20,
                "material_filter": {"modules": ["week-1", "week-2", "week-3"]},
            },
        )
        self.assertEqual(200, grade_resp.status_code)
        body = grade_resp.json()
        self.assertTrue(body["success"])
        self.assertEqual("cs-101", body["namespace"])
        self.assertEqual(17.0, body["score"])
        self.assertEqual(["ungrounded_citations_removed:1"], body["integrity_warnings"])
        self.assertEqual("v1:cs-101", self.fake_grader.last_grade_kwargs["course_id"])
        self.assertEqual(
            {"module": {"$in": ["week-1", "week-2", "week-3"]}},
            self.fake_grader.last_grade_kwargs["metadata_filter"],
        )

    def test_grade_rejects_material_filter_that_scopes_nothing(self):
        # Sending material_filter means "restrict retrieval"; an empty or blank
        # filter must fail loudly (400) instead of grading against everything.
        for material_filter in ({}, {"modules": []}, {"modules": [" "], "tags": {"topic": None}}):
            with self.subTest(material_filter=material_filter):
                self.fake_grader.last_grade_kwargs = None
                response = self.client.post(
                    "/v1/namespaces/cs-101/grade",
                    json={"question": "Q", "essay": "A", "material_filter": material_filter},
                )
                self.assertEqual(400, response.status_code)
                self.assertIn("material_filter", response.json()["detail"])
                self.assertIsNone(self.fake_grader.last_grade_kwargs)

    def test_grade_without_or_with_null_material_filter_is_unscoped(self):
        for extra in ({}, {"material_filter": None}):
            with self.subTest(extra=extra):
                response = self.client.post(
                    "/v1/namespaces/cs-101/grade",
                    json={"question": "Q", "essay": "A", **extra},
                )
                self.assertEqual(200, response.status_code)
                self.assertIsNone(self.fake_grader.last_grade_kwargs["metadata_filter"])

    def test_grade_response_exposes_parse_failure_error(self):
        original = self.fake_grader.grade_essay

        def with_error(**kwargs):
            out = original(**kwargs)
            out["error"] = "Failed to parse LLM response"
            return out

        self.fake_grader.grade_essay = with_error
        response = self.client.post(
            "/v1/namespaces/cs-101/grade", json={"question": "Q", "essay": "A"})
        self.assertEqual(200, response.status_code)
        self.assertEqual("Failed to parse LLM response", response.json()["error"])

    def test_grade_response_error_is_null_on_clean_success(self):
        response = self.client.post(
            "/v1/namespaces/cs-101/grade", json={"question": "Q", "essay": "A"})
        self.assertIsNone(response.json()["error"])

    def test_list_delete_file_and_clear_namespace(self):
        self.client.post(
            "/v1/namespaces/bio-101/materials",
            files={"file": ("cells.txt", b"Mitochondria", "text/plain")},
        )
        listing = self.client.get("/v1/namespaces/bio-101/materials")
        self.assertEqual(200, listing.status_code)
        self.assertEqual(["cells.txt"], listing.json()["uploaded_files"])

        delete_file = self.client.delete("/v1/namespaces/bio-101/materials/cells.txt")
        self.assertEqual(200, delete_file.status_code)
        self.assertTrue(delete_file.json()["success"])

        clear_ns = self.client.delete("/v1/namespaces/bio-101")
        self.assertEqual(200, clear_ns.status_code)
        self.assertTrue(clear_ns.json()["success"])

    def test_numeric_namespace_uses_v1_storage_key_while_returning_raw_namespace(self):
        upload_resp = self.client.post(
            "/v1/namespaces/12/materials",
            files={"file": ("syllabus.txt", b"Course 12", "text/plain")},
        )
        self.assertEqual(200, upload_resp.status_code)
        self.assertEqual("12", upload_resp.json()["namespace"])
        self.assertEqual("v1:12", self.fake_grader.last_ingest_kwargs["course_id"])

        info_resp = self.client.get("/v1/namespaces/12/materials")
        self.assertEqual(200, info_resp.status_code)
        self.assertEqual("12", info_resp.json()["namespace"])
        self.assertEqual("v1:12", self.fake_grader.rag_pipeline.last_info_course_id)

        grade_resp = self.client.post(
            "/v1/namespaces/12/grade",
            json={"question": "Q", "essay": "A", "maximum_grade": 100},
        )
        self.assertEqual(200, grade_resp.status_code)
        self.assertEqual("12", grade_resp.json()["namespace"])
        self.assertEqual("v1:12", self.fake_grader.last_grade_kwargs["course_id"])

        del_file_resp = self.client.delete("/v1/namespaces/12/materials/syllabus.txt")
        self.assertEqual(200, del_file_resp.status_code)
        self.assertEqual("12", del_file_resp.json()["namespace"])
        self.assertEqual(("v1:12", "syllabus.txt"), self.fake_grader.last_delete_args)

        clear_resp = self.client.delete("/v1/namespaces/12")
        self.assertEqual(200, clear_resp.status_code)
        self.assertEqual("12", clear_resp.json()["namespace"])
        self.assertEqual("v1:12", self.fake_grader.last_clear_course_id)

    def test_failed_ingest_does_not_leave_orphan_file_or_corrupt_existing_file(self):
        self.fake_grader.ingest_response = {
            "success": False,
            "message": "No readable text found",
            "documents_loaded": 0,
            "chunks_created": 0,
        }
        failed_upload = self.client.post(
            "/v1/namespaces/fail-ns/materials",
            files={"file": ("empty.txt", b"broken", "text/plain")},
        )
        self.assertEqual(500, failed_upload.status_code)

        listing = self.client.get("/v1/namespaces/fail-ns/materials")
        self.assertEqual(200, listing.status_code)
        self.assertEqual([], listing.json()["uploaded_files"])

        # Now upload a valid file, then fail a re-upload of the same filename.
        self.fake_grader.ingest_response = {
            "success": True,
            "documents_loaded": 1,
            "chunks_created": 2,
            "errors": [],
        }
        ok_upload = self.client.post(
            "/v1/namespaces/fail-ns/materials",
            files={"file": ("notes.txt", b"valid v1", "text/plain")},
        )
        self.assertEqual(200, ok_upload.status_code)

        from src.api.v1_routes import _namespace_upload_dir

        saved_path = _namespace_upload_dir(Path(self.tempdir.name), "fail-ns") / "notes.txt"
        self.assertEqual(b"valid v1", saved_path.read_bytes())

        self.fake_grader.ingest_response = {"success": False, "message": "Corrupt upload"}
        failed_reupload = self.client.post(
            "/v1/namespaces/fail-ns/materials",
            files={"file": ("notes.txt", b"corrupt v2", "text/plain")},
        )
        self.assertEqual(500, failed_reupload.status_code)
        self.assertEqual(b"valid v1", saved_path.read_bytes())
        listing_after = self.client.get("/v1/namespaces/fail-ns/materials")
        self.assertEqual(["notes.txt"], listing_after.json()["uploaded_files"])

    def test_invalid_namespace_and_malformed_tags_return_400(self):
        for bad_ns in ("-invalid", "bad!ns", "%2e%2e"):
            resp = self.client.get(f"/v1/namespaces/{bad_ns}/materials")
            self.assertEqual(400, resp.status_code)

        bad_json = self.client.post(
            "/v1/namespaces/valid-ns/materials",
            data={"tags": "{not-json"},
            files={"file": ("notes.txt", b"hello", "text/plain")},
        )
        self.assertEqual(400, bad_json.status_code)

        non_obj_json = self.client.post(
            "/v1/namespaces/valid-ns/materials",
            data={"tags": "[1, 2]"},
            files={"file": ("notes.txt", b"hello", "text/plain")},
        )
        self.assertEqual(400, non_obj_json.status_code)

    def test_upload_accepts_top_level_topic_form_field(self):
        upload_resp = self.client.post(
            "/v1/namespaces/cs-202/materials",
            data={"module": "week-2", "topic": "routing"},
            files={"file": ("week2.txt", b"OSPF routing", "text/plain")},
        )
        self.assertEqual(200, upload_resp.status_code)
        body = upload_resp.json()
        self.assertEqual("routing", body["topic"])
        self.assertEqual({"topic": "routing"}, body["tags"])
        self.assertEqual({"topic": "routing"}, self.fake_grader.last_ingest_kwargs["tags"])

        grade_resp = self.client.post(
            "/v1/namespaces/cs-202/grade",
            json={
                "question": "Explain OSPF",
                "essay": "Link-state routing protocol.",
                "material_filter": {"modules": ["week-2"], "tags": {"topic": "routing"}},
            },
        )
        self.assertEqual(200, grade_resp.status_code)
        self.assertEqual(
            {"$and": [{"module": {"$eq": "week-2"}}, {"tag_topic": {"$eq": "routing"}}]},
            self.fake_grader.last_grade_kwargs["metadata_filter"],
        )

    def test_main_app_mounts_v1_routes_behind_api_auth_middleware(self):
        fake_pipeline = _FakePipeline()
        fake_pipeline.vectorstore = MagicMock()
        fake_pipeline.vectorstore.heartbeat.return_value = True
        fake_grader = _FakeGrader()
        fake_grader.rag_pipeline = fake_pipeline

        fake_locks = MagicMock()
        fake_locks.ping.return_value = True
        fake_locks.read.return_value = RLock()
        fake_locks.write.return_value = RLock()

        runtime = AppRuntime(grader=fake_grader, operation_locks=fake_locks,
                             settings=load_settings(env={}))
        with (
            override_settings(API_AUTH_TOKEN="cycle1-secret"),
            TestClient(create_app(runtime=runtime)) as client,
        ):
            health = client.get("/health")
            unauth = client.get("/v1/namespaces/cs-101/materials")
            wrong = client.get(
                "/v1/namespaces/cs-101/materials",
                headers={"Authorization": "Bearer wrong-token"},
            )
            authed = client.get(
                "/v1/namespaces/cs-101/materials",
                headers={"Authorization": "Bearer cycle1-secret"},
            )

        self.assertEqual(200, health.status_code)
        self.assertEqual(401, unauth.status_code)
        self.assertEqual(401, wrong.status_code)
        self.assertEqual(200, authed.status_code)
        self.assertEqual("cs-101", authed.json()["namespace"])

if __name__ == "__main__":
    unittest.main()
