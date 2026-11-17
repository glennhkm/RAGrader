"""Contract tests for generic /v1/namespaces/* autograding endpoints."""

import json
import tempfile
import unittest
from pathlib import Path
from threading import RLock
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.v1_routes import router as v1_router


class _FakePipeline:
    current_embedding_model = "BAAI/bge-m3"

    def get_vectorstore_info(self, course_id=None):
        return {"collection_name": f"ns_{course_id}", "document_count": 4}


class _FakeGrader:
    def __init__(self):
        self.rag_pipeline = _FakePipeline()
        self.last_ingest_kwargs = None
        self.last_grade_kwargs = None

    def ingest_course_materials(self, paths, **kwargs):
        self.last_ingest_kwargs = {"paths": paths, **kwargs}
        return {"success": True, "documents_loaded": 1, "chunks_created": 4, "errors": []}

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
        }

    def delete_course_material_file(self, course_id, filename):
        return True

    def clear_vector_store(self, course_id=None):
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
        self.assertEqual("cs-101", self.fake_grader.last_ingest_kwargs["course_id"])
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
        self.assertEqual(17.0, body["score"])
        self.assertEqual(
            {"module": {"$in": ["week-1", "week-2", "week-3"]}},
            self.fake_grader.last_grade_kwargs["metadata_filter"],
        )

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


if __name__ == "__main__":
    unittest.main()
