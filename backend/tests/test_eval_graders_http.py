import json
import re
import tempfile
import unittest
from pathlib import Path

import httpx

from src.evaluation.graders.base import GradeRequest, TransientGraderError
from src.evaluation.graders.http import HttpGrader, http_namespace
from src.evaluation.materials import MaterialDoc
from src.evaluation.schema import EvalItem

NS_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _item():
    return EvalItem.__new__(EvalItem)


def _ok(**extra):
    body = {
        "success": True, "score": 80.0, "confidence": 0.9, "feedback": "good feedback!!",
        "citations": [{"text": "t", "source": "a.txt", "page": None}],
        "integrity_warnings": ["ungrounded_citations_removed:2"],
        "retrieved_documents": [{"content": "c", "source": "a.txt"},
                                {"content": "d", "source": "b.txt"}],
        "error": None,
    }
    body.update(extra)
    return body


class Recorder:
    def __init__(self, grade_response=None, listed=None):
        self.requests = []
        self.grade_response = grade_response or httpx.Response(200, json=_ok())
        self.listed = listed or []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, json={"success": True, "namespace": "n",
                                             "collection_name": "", "uploaded_files": self.listed})
        if request.url.path.endswith("/grade"):
            return self.grade_response
        return httpx.Response(200, json={"success": True})


def _grader(rec):
    client = httpx.Client(transport=httpx.MockTransport(rec))
    return HttpGrader("http://api.test", "tok", http_client=client)


REQ = GradeRequest(question="Q?", answer="A.", language="en")


class HttpNamespaceTest(unittest.TestCase):
    def test_matches_v1_pattern_and_hides_dataset(self):
        ns = http_namespace("a" * 64, "private-dataset-name")
        self.assertRegex(ns, NS_PATTERN)
        self.assertTrue(ns.startswith("eval-" + "a" * 12 + "-"))
        self.assertNotIn("private", ns)
        self.assertEqual(ns, http_namespace("a" * 64, "private-dataset-name"))
        self.assertNotEqual(ns, http_namespace("a" * 64, "other"))


class PrepareTest(unittest.TestCase):
    def test_uploads_missing_files_only(self):
        rec = Recorder(listed=["a.txt"])
        g = _grader(rec)
        docs = [MaterialDoc("a.txt", "A"), MaterialDoc("b.txt", "B")]
        with tempfile.TemporaryDirectory() as d:
            g.prepare_namespace("ns1", docs, Path(d))
        posts = [r for r in rec.requests if r.method == "POST"]
        self.assertEqual(1, len(posts))
        self.assertIn(b"b.txt", posts[0].content)
        self.assertEqual("/v1/namespaces/ns1/materials", posts[0].url.path)


class GradeTest(unittest.TestCase):
    def test_success_mapping_and_payload(self):
        rec = Recorder()
        raw = _grader(rec).grade("ns1", _item(), REQ)
        self.assertTrue(raw.success)
        self.assertEqual(80.0, raw.score)
        self.assertEqual(0.9, raw.confidence)
        self.assertEqual(1, raw.citations_kept)
        self.assertEqual(2, raw.citations_dropped)
        self.assertEqual(["a.txt", "b.txt"], raw.retrieved_sources)
        self.assertIsNone(raw.provider)
        self.assertTrue(raw.tokens_estimated)
        self.assertEqual(len(raw.feedback) // 4, raw.completion_tokens)
        req = rec.requests[0]
        payload = json.loads(req.content)
        self.assertEqual({"question": "Q?", "essay": "A.", "rubric": {},
                          "maximum_grade": 100, "language": "en"}, payload)
        self.assertEqual(len(json.dumps(payload)) // 4, raw.prompt_tokens)
        self.assertEqual("Bearer tok", req.headers["Authorization"])

    def test_parse_failure(self):
        rec = Recorder(httpx.Response(200, json=_ok(error="Failed to parse LLM response")))
        raw = _grader(rec).grade("ns1", _item(), REQ)
        self.assertFalse(raw.success)
        self.assertEqual("parse_failure", raw.error_type)
        self.assertIsNone(raw.score)

    def test_no_materials_and_provider_error(self):
        rec = Recorder(httpx.Response(200, json=_ok(
            success=False, error="No relevant materials found")))
        self.assertEqual("no_materials", _grader(rec).grade("n", _item(), REQ).error_type)
        rec = Recorder(httpx.Response(200, json=_ok(success=False, error="boom")))
        self.assertEqual("provider_error", _grader(rec).grade("n", _item(), REQ).error_type)

    def test_transient_statuses(self):
        for code in (429, 500, 503):
            with self.subTest(code=code):
                rec = Recorder(httpx.Response(code, headers={"Retry-After": "7"}, text="x"))
                with self.assertRaises(TransientGraderError) as cm:
                    _grader(rec).grade("n", _item(), REQ)
                self.assertEqual(7.0, cm.exception.retry_after)

    def test_retry_after_missing_or_non_numeric(self):
        for headers in ({}, {"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}):
            rec = Recorder(httpx.Response(429, headers=headers, text="x"))
            with self.assertRaises(TransientGraderError) as cm:
                _grader(rec).grade("n", _item(), REQ)
            self.assertIsNone(cm.exception.retry_after)

    def test_other_4xx_is_http_error(self):
        rec = Recorder(httpx.Response(404, json={"detail": "nope"}))
        raw = _grader(rec).grade("n", _item(), REQ)
        self.assertFalse(raw.success)
        self.assertEqual("http_error", raw.error_type)

    def test_transport_errors_are_transient(self):
        for exc in (httpx.ReadTimeout("slow"), httpx.ConnectError("down")):
            def handler(request, exc=exc):
                raise exc
            g = HttpGrader("http://api.test", "t",
                           http_client=httpx.Client(transport=httpx.MockTransport(handler)))
            with self.assertRaises(TransientGraderError):
                g.grade("n", _item(), REQ)


if __name__ == "__main__":
    unittest.main()
