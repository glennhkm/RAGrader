"""Tests for the side-effect-free FastAPI app factory and lifespan-managed runtime."""

import importlib
import sys
import unittest
from threading import RLock
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import runtime as runtime_module
from src.api.runtime import AppRuntime, get_runtime, set_runtime
from src.utils.config import load_settings, override_settings


def _fake_runtime(document_count: int = 3) -> AppRuntime:
    vectorstore = MagicMock()
    vectorstore.heartbeat.return_value = True
    pipeline = SimpleNamespace(
        vectorstore=vectorstore,
        current_embedding_model="BAAI/bge-m3",
        get_vectorstore_info=lambda course_id=None: {
            "collection_name": f"ns_{course_id}",
            "document_count": document_count,
        },
    )
    grader = SimpleNamespace(rag_pipeline=pipeline)
    locks = MagicMock()
    locks.enabled = False
    locks.ping.return_value = True
    locks.read.side_effect = lambda resource: RLock()
    locks.write.side_effect = lambda resource: RLock()
    return AppRuntime(grader=grader, operation_locks=locks, settings=load_settings(env={}))


class AppImportTest(unittest.TestCase):
    def tearDown(self):
        set_runtime(None)

    def test_importing_app_module_builds_nothing(self):
        boom = RuntimeError("must not be constructed at import time")
        had_app = "src.api.app" in sys.modules
        previous = sys.modules.pop("src.api.app", None)
        try:
            with (
                patch("src.grading.grader.EssayGrader.__init__", side_effect=boom),
                patch("src.api.locking.OperationLockManager.__init__", side_effect=boom),
                patch("src.vectorstore.chroma_store.VectorStore.__init__", side_effect=boom),
                patch("src.api.runtime.build_runtime", side_effect=boom),
            ):
                app_module = importlib.import_module("src.api.app")
            self.assertIsInstance(app_module.app, FastAPI)
            with self.assertRaises(RuntimeError):
                get_runtime()
        finally:
            sys.modules.pop("src.api.app", None)
            if had_app and previous is not None:
                sys.modules["src.api.app"] = previous


class AppFactoryTest(unittest.TestCase):
    def tearDown(self):
        set_runtime(None)

    def test_injected_runtime_serves_health_and_auth_protected_v1_routes(self):
        from src.api.app import create_app

        app = create_app(runtime=_fake_runtime())
        with override_settings(API_AUTH_TOKEN="cycle2-secret"), TestClient(app) as client:
            health = client.get("/health")
            unauth = client.get("/v1/namespaces/cs-101/materials")
            wrong = client.get("/v1/namespaces/cs-101/materials",
                               headers={"Authorization": "Bearer wrong"})
            authed = client.get("/v1/namespaces/cs-101/materials",
                                headers={"Authorization": "Bearer cycle2-secret"})
            moodle = client.get("/collections/7", headers={"Authorization": "Bearer cycle2-secret"})

        self.assertEqual(200, health.status_code)
        self.assertIn("X-Request-ID", health.headers)
        self.assertIn("X-API-Instance", health.headers)
        self.assertEqual(401, unauth.status_code)
        self.assertEqual(401, wrong.status_code)
        self.assertEqual(200, authed.status_code)
        self.assertEqual("cs-101", authed.json()["namespace"])
        self.assertEqual(200, moodle.status_code)
        self.assertEqual(3, moodle.json()["document_count"])
        # The runtime belongs to the app lifecycle and is cleared on shutdown.
        with self.assertRaises(RuntimeError):
            get_runtime()

    def test_lifespan_builds_runtime_once_and_clears_it_on_shutdown(self):
        from src.api.app import create_app

        fake = _fake_runtime()
        with (
            patch("src.api.app.build_runtime", return_value=fake) as build,
            patch("src.api.app.setup_logging") as setup_logging,
            patch("src.api.app.ensure_directories") as ensure_directories,
        ):
            app = create_app()
            build.assert_not_called()
            with TestClient(app) as client:
                self.assertIs(fake, get_runtime())
                self.assertEqual(200, client.get("/health").status_code)
                self.assertEqual(200, client.get("/health").status_code)
            build.assert_called_once()
            setup_logging.assert_called_once()
            ensure_directories.assert_called_once()
        with self.assertRaises(RuntimeError):
            get_runtime()

    def test_startup_failure_is_fatal(self):
        from src.api.app import create_app

        with (
            patch("src.api.app.build_runtime", side_effect=RuntimeError("redis unavailable")),
            patch("src.api.app.setup_logging"),
            patch("src.api.app.ensure_directories"),
        ):
            with self.assertRaises(RuntimeError):
                with TestClient(create_app()):
                    pass

    def test_health_is_503_when_runtime_is_not_initialized(self):
        from src.api.app import create_app

        client = TestClient(create_app())  # no context manager -> lifespan never runs
        response = client.get("/health")
        self.assertEqual(503, response.status_code)
        self.assertEqual(200, client.get("/").status_code)

    def test_health_is_503_when_shared_state_is_down(self):
        from src.api.app import create_app

        fake = _fake_runtime()
        fake.operation_locks.ping.side_effect = ConnectionError("redis down")
        with TestClient(create_app(runtime=fake)) as client:
            self.assertEqual(503, client.get("/health").status_code)


class BuildRuntimeTest(unittest.TestCase):
    def test_build_runtime_wires_grader_and_locks_from_settings(self):
        settings = load_settings(env={"LLM_PROVIDER": "groq", "LLM_MODEL": "custom/model"})
        with (
            patch.object(runtime_module, "EssayGrader") as grader_cls,
            patch.object(runtime_module, "OperationLockManager") as locks_cls,
        ):
            runtime = runtime_module.build_runtime(settings)

        config = grader_cls.call_args.args[0]
        self.assertEqual("groq", grader_cls.call_args.kwargs["provider"])
        self.assertEqual("custom/model", grader_cls.call_args.kwargs["model_name"])
        self.assertIsInstance(config, dict)
        # The grader mutates its config (e.g. embedding switch); it must get a copy.
        config["embeddings"]["model_name"] = "mutated"
        self.assertEqual("BAAI/bge-m3", settings.raw["embeddings"]["model_name"])
        locks_cls.assert_called_once_with(settings.locks)
        self.assertIs(settings, runtime.settings)


    def test_injected_settings_reach_every_component_without_environment(self):
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            settings = load_settings(env={
                "LLM_PROVIDER": "openai_compatible",
                "LLM_BASE_URL": "http://llm.invalid/v1",
                "LLM_MODEL": "injected-llm",
                "EMBEDDING_PROVIDER": "openai_compatible",
                "EMBEDDING_BASE_URL": "http://emb.invalid/v1",
                "EMBEDDING_MODEL": "injected-embed",
                "CHROMA_CLIENT_MODE": "persistent",
                "CHROMA_PERSIST_DIRECTORY": tmp,
                "ENABLE_RERANKING": "true",
                "RERANKER_TYPE": "bm25",
                "PROMPT_LANGUAGE": "en",
            })
            # The process environment says something else: it must not be consulted.
            with patch.dict(os.environ, {"LLM_PROVIDER": "groq", "EMBEDDING_PROVIDER": "huggingface",
                                         "PROMPT_LANGUAGE": "id"}, clear=True):
                runtime = runtime_module.build_runtime(settings)

        pipeline = runtime.grader.rag_pipeline
        self.assertIs(settings, runtime.grader.settings)
        self.assertEqual("openai_compatible", pipeline.llm.provider)
        self.assertEqual("http://llm.invalid/v1", pipeline.llm.provider_endpoints[0].base_url)
        self.assertEqual("openai_compatible", pipeline.vectorstore.embedding_generator.provider)
        self.assertEqual("injected-embed", pipeline.vectorstore.embedding_generator.model_name)
        self.assertEqual("bm25", pipeline.retriever.reranker_type)
        self.assertEqual("en", pipeline.prompt_builder.default_language)
        self.assertIs(settings, runtime.grader.document_loader.multimodal_loader._settings)


if __name__ == "__main__":
    unittest.main()
