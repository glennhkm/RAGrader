"""Full-stack integration tests against a running RAGrader stack.

Run against the compose stack (HAProxy -> API replicas -> Chroma + Redis) with the
CI override, or any API reachable at RAG_IT_URL. Not part of ``tests/``: the unit
runner never depends on this module, and it skips cleanly when the API is down.

Environment:
    RAG_IT_URL               API base URL (default http://127.0.0.1:8000)
    RAG_IT_TOKEN             Bearer token (default empty)
    RAG_IT_CHROMA_PORT       Published Chroma port for the mismatch seed (default 18001)
    RAG_IT_EXPECT_REPLICAS   Set to 2 in CI to make the balancing test assert

Tests never print answer text beyond the fixtures defined below.
"""

import os
import random
import time
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional

import httpx

BASE_URL = os.environ.get("RAG_IT_URL", "http://127.0.0.1:8000").rstrip("/")
TOKEN = os.environ.get("RAG_IT_TOKEN", "")
CHROMA_PORT = int(os.environ.get("RAG_IT_CHROMA_PORT", "18001"))
EXPECT_REPLICAS = int(os.environ.get("RAG_IT_EXPECT_REPLICAS", "0") or 0)
EMBEDDING_MODEL = "stub-embed"
MATERIALS = Path(__file__).resolve().parents[2] / "examples" / "week1_to_week4_quiz" / "materials"
HEADERS = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}

TLS_QUESTION = "How do TLS and HTTPS protect data in transit?"
TLS_ANSWER = "TLS encrypts traffic with session keys agreed during the handshake and HTTPS runs HTTP over TLS."


def setUpModule() -> None:
    try:
        httpx.get(f"{BASE_URL}/health", timeout=5).raise_for_status()
    except Exception as exc:  # noqa: BLE001 - any failure means the stack is not up
        raise unittest.SkipTest(f"API not reachable at {BASE_URL}: {type(exc).__name__}")


def unique_course_id() -> int:
    """A course id unlikely to collide with other runs (Chroma data may persist)."""
    return random.randint(900_000_000, 999_999_999)


def collection_name(course_id: int) -> str:
    from src.vectorstore.filters import build_collection_name

    return build_collection_name("materials", EMBEDDING_MODEL, str(course_id))


class StackTestCase(unittest.TestCase):
    client: httpx.Client

    @classmethod
    def setUpClass(cls) -> None:
        cls.client = httpx.Client(base_url=BASE_URL, headers=HEADERS, timeout=120)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.close()

    def upload_v1(self, namespace: str, path: Path, module: str) -> httpx.Response:
        return self.client.post(
            f"/v1/namespaces/{namespace}/materials",
            files={"file": (path.name, path.read_bytes(), "text/plain")},
            data={"module": module},
        )

    def grade_v1(self, namespace: str, material_filter: Optional[Dict] = None) -> httpx.Response:
        body: Dict = {"question": TLS_QUESTION, "essay": TLS_ANSWER, "maximum_grade": 100}
        if material_filter is not None:
            body["material_filter"] = material_filter
        return self.client.post(f"/v1/namespaces/{namespace}/grade", json=body)

    def upload_course(self, course_id: int, filename: str, content: str, material_id: str) -> httpx.Response:
        return self.client.post(
            "/course/materials/upload",
            files={"file": (filename, content.encode("utf-8"), "text/plain")},
            data={"course_id": str(course_id), "material_id": material_id},
        )

    def grade_course(self, course_id: int, **extra) -> httpx.Response:
        body = {
            "course_id": course_id,
            "question": "Describe the orchard and the submarine.",
            "essay": "The orchard grows apples while the submarine dives deep.",
            "maximum_grade": 100,
            **extra,
        }
        return self.client.post("/assign/answer", json=body)

    def cleanup_course(self, course_id: int) -> None:
        self.client.delete(f"/collections/{course_id}")

    def cleanup_namespace(self, namespace: str) -> None:
        self.client.delete(f"/v1/namespaces/{namespace}")


class HealthAndAuthTests(StackTestCase):
    def test_health_is_open_and_routes_need_token(self) -> None:
        with httpx.Client(base_url=BASE_URL, timeout=30) as anonymous:
            self.assertEqual(anonymous.get("/health").status_code, 200)
            self.assertEqual(anonymous.get("/").status_code, 200)
            if TOKEN:
                denied = anonymous.get("/v1/namespaces/auth-probe/materials")
                self.assertEqual(denied.status_code, 401)
                wrong = anonymous.get(
                    "/v1/namespaces/auth-probe/materials",
                    headers={"Authorization": "Bearer definitely-wrong"},
                )
                self.assertEqual(wrong.status_code, 401)
                self.assertNotEqual(
                    self.client.get("/v1/namespaces/auth-probe/materials").status_code, 401
                )


class ScopeTests(StackTestCase):
    def test_v1_week1_to_3_scope_never_cites_week4(self) -> None:
        namespace = f"it-scope-{uuid.uuid4().hex[:10]}"
        self.addCleanup(self.cleanup_namespace, namespace)
        for week in (1, 2, 3, 4):
            response = self.upload_v1(namespace, MATERIALS / f"week-{week}.txt", f"week-{week}")
            self.assertEqual(response.status_code, 200, response.status_code)

        # Control: without a scope, the TLS question reaches the Week 4 material.
        unscoped = self.grade_v1(namespace)
        self.assertEqual(unscoped.status_code, 200)
        unscoped_sources = {d["source"] for d in unscoped.json()["retrieved_documents"]}
        self.assertIn("week-4.txt", unscoped_sources)

        scoped = self.grade_v1(namespace, {"modules": ["week-1", "week-2", "week-3"]})
        self.assertEqual(scoped.status_code, 200)
        data = scoped.json()
        self.assertTrue(data["success"])
        self.assertTrue(data["retrieved_documents"])
        retrieved = {d["source"] for d in data["retrieved_documents"]}
        cited = {c["source"] for c in data["citations"]}
        self.assertNotIn("week-4.txt", retrieved)
        self.assertNotIn("week-4.txt", cited)
        self.assertTrue(retrieved <= {"week-1.txt", "week-2.txt", "week-3.txt"}, retrieved)

    def test_same_filename_materials_are_isolated_end_to_end(self) -> None:
        course = unique_course_id()
        self.addCleanup(self.cleanup_course, course)
        owner_a, owner_b = "airagmaterial:101", "airagmaterial:102"
        self.assertEqual(
            self.upload_course(course, "notes.txt", "alpha orchard apples harvest alpha trees.", owner_a).status_code, 200
        )
        self.assertEqual(
            self.upload_course(course, "notes.txt", "bravo submarine ocean dive bravo depth.", owner_b).status_code, 200
        )

        only_a = self.grade_course(course, material_ids=[owner_a])
        self.assertEqual(only_a.status_code, 200)
        docs = only_a.json()["retrieved_documents"]
        self.assertTrue(docs)
        for doc in docs:
            self.assertIn("alpha", doc["content"])
            self.assertNotIn("bravo", doc["content"])

        # Deleting one owner's file leaves the same-named file of the other owner.
        deleted = self.client.request(
            "DELETE",
            "/course/materials/file",
            data={"course_id": str(course), "filename": "notes.txt", "material_id": owner_a},
        )
        self.assertEqual(deleted.status_code, 200)
        self.assertTrue(deleted.json()["success"])

        gone = self.grade_course(course, material_ids=[owner_a])
        self.assertEqual(gone.status_code, 200)
        self.assertFalse(gone.json()["success"])

        remaining = self.grade_course(course, material_ids=[owner_b])
        self.assertEqual(remaining.status_code, 200)
        self.assertTrue(remaining.json()["success"])
        for doc in remaining.json()["retrieved_documents"]:
            self.assertIn("bravo", doc["content"])

        # An explicit empty owner list must never widen to the whole course.
        self.assertEqual(self.grade_course(course, material_ids=[]).status_code, 400)


class ConcurrencyTests(StackTestCase):
    def test_concurrent_grading_during_upload_has_no_5xx(self) -> None:
        namespace = f"it-conc-{uuid.uuid4().hex[:10]}"
        self.addCleanup(self.cleanup_namespace, namespace)
        for week in (1, 2):
            self.assertEqual(self.upload_v1(namespace, MATERIALS / f"week-{week}.txt", f"week-{week}").status_code, 200)

        def grade(_index: int) -> int:
            with httpx.Client(base_url=BASE_URL, headers=HEADERS, timeout=120) as client:
                return client.post(
                    f"/v1/namespaces/{namespace}/grade",
                    json={"question": TLS_QUESTION, "essay": TLS_ANSWER, "maximum_grade": 100},
                ).status_code

        def upload() -> int:
            time.sleep(0.2)  # let some grades start first
            with httpx.Client(base_url=BASE_URL, headers=HEADERS, timeout=120) as client:
                path = MATERIALS / "week-3.txt"
                return client.post(
                    f"/v1/namespaces/{namespace}/materials",
                    files={"file": (path.name, path.read_bytes(), "text/plain")},
                    data={"module": "week-3"},
                ).status_code

        with ThreadPoolExecutor(max_workers=16) as pool:
            upload_future = pool.submit(upload)
            grade_futures = [pool.submit(grade, i) for i in range(40)]
            statuses = [f.result() for f in grade_futures] + [upload_future.result()]

        server_errors = [s for s in statuses if s >= 500]
        self.assertEqual(server_errors, [], f"{len(server_errors)}/{len(statuses)} responses were 5xx: {sorted(set(server_errors))}")
        self.assertEqual(upload_future.result(), 200)


class BalancingTests(StackTestCase):
    def test_requests_are_balanced_across_replicas(self) -> None:
        def probe(_index: int) -> Optional[str]:
            with httpx.Client(base_url=BASE_URL, timeout=30) as client:  # new connection each time
                return client.get("/health").headers.get("X-API-Instance")

        seen: List[str] = []
        with ThreadPoolExecutor(max_workers=10) as pool:
            seen.extend(pool.map(probe, range(20)))
            # Give HAProxy more chances if it has not rotated yet.
            for _ in range(8):
                if len({s for s in seen if s}) >= 2:
                    break
                seen.extend(pool.map(probe, range(10)))

        instances = {s for s in seen if s}
        self.assertTrue(instances, "no X-API-Instance header returned")
        if EXPECT_REPLICAS and len(instances) < EXPECT_REPLICAS:
            self.fail(f"expected {EXPECT_REPLICAS} replicas, saw {len(instances)}: {sorted(instances)}")
        if len(instances) < 2:
            self.skipTest("single API instance (set RAG_IT_EXPECT_REPLICAS=2 to require balancing)")
        self.assertGreaterEqual(len(instances), 2)


class EmbeddingMismatchTests(StackTestCase):
    def test_embedding_mismatch_returns_409(self) -> None:
        import chromadb

        course = unique_course_id()
        name = collection_name(course)
        chroma = chromadb.HttpClient(
            host="127.0.0.1",
            port=CHROMA_PORT,
            settings=chromadb.config.Settings(anonymized_telemetry=False),
        )
        collection = chroma.create_collection(
            name=name,
            metadata={
                "embedding_provider": "some-other-provider",
                "embedding_model": "some-other-model",
                "embedding_dimension": 1536,
            },
        )
        # An empty collection short-circuits grading before the identity check.
        collection.add(ids=["seed"], documents=["seed"], embeddings=[[0.1] * 64])

        def drop() -> None:
            try:
                chroma.delete_collection(name)
            except Exception:  # noqa: BLE001
                pass

        self.addCleanup(drop)
        response = self.grade_course(course)
        self.assertEqual(response.status_code, 409, response.status_code)


if __name__ == "__main__":
    unittest.main()
