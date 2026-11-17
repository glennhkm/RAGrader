"""Unit and HTTP middleware tests for optional API bearer token authentication."""

import os
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.auth import check_api_auth, extract_bearer_token


class ApiAuthTest(unittest.TestCase):
    def _build_client(self):
        test_app = FastAPI()

        @test_app.middleware("http")
        async def _auth_middleware(request, call_next):
            denied = check_api_auth(request)
            if denied is not None:
                return denied
            return await call_next(request)

        @test_app.get("/")
        def root():
            return {"status": "healthy"}

        @test_app.get("/health")
        def health():
            return {"status": "healthy"}

        @test_app.post("/assign/answer")
        def grade():
            return {"success": True}

        return TestClient(test_app)

    def test_extract_bearer_token_handles_case_and_whitespace(self):
        self.assertEqual("secret-123", extract_bearer_token({"Authorization": "Bearer secret-123"}))
        self.assertEqual("secret-123", extract_bearer_token({"authorization": "bearer   secret-123  "}))
        self.assertEqual("secret-123", extract_bearer_token({"X-API-Key": "secret-123"}))
        self.assertIsNone(extract_bearer_token({}))
        self.assertIsNone(extract_bearer_token({"Authorization": "Basic abc"}))

    def test_open_mode_when_api_auth_token_unset(self):
        client = self._build_client()
        with patch.dict(os.environ, {"API_AUTH_TOKEN": ""}, clear=False):
            resp = client.post("/assign/answer")
        self.assertEqual(200, resp.status_code)

    def test_protected_endpoint_rejects_missing_or_wrong_token(self):
        client = self._build_client()
        with patch.dict(os.environ, {"API_AUTH_TOKEN": "top-secret-token"}, clear=False):
            missing = client.post("/assign/answer")
            wrong = client.post(
                "/assign/answer",
                headers={"Authorization": "Bearer wrong-token"},
            )
            valid = client.post(
                "/assign/answer",
                headers={"Authorization": "Bearer top-secret-token"},
            )
            health = client.get("/health")
            root = client.get("/")

        self.assertEqual(401, missing.status_code)
        self.assertEqual("Bearer", missing.headers.get("www-authenticate"))
        self.assertEqual(401, wrong.status_code)
        self.assertEqual(200, valid.status_code)
        self.assertEqual(200, health.status_code)
        self.assertEqual(200, root.status_code)


if __name__ == "__main__":
    unittest.main()

