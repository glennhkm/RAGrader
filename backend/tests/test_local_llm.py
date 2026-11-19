"""Tests for the optional in-process llama.cpp LLM backend."""

import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

from src.rag import local_llm
from src.rag.llm import LLMWrapper
from src.utils.config import ConfigError, load_settings


class _FakeLlama:
    instances = []

    def __init__(self, model_path, n_ctx, n_gpu_layers, verbose):
        self.kwargs = {"model_path": model_path, "n_ctx": n_ctx, "n_gpu_layers": n_gpu_layers}
        self.requests = []
        _FakeLlama.instances.append(self)

    def create_chat_completion(self, messages, temperature, max_tokens):
        self.requests.append({"messages": messages, "temperature": temperature, "max_tokens": max_tokens})
        return {"choices": [{"message": {"content": '  {"score": 80}  '}}]}


class LocalLlamaCppTest(unittest.TestCase):
    def setUp(self):
        local_llm._MODEL_CACHE.clear()
        _FakeLlama.instances.clear()
        self.tmp = tempfile.TemporaryDirectory()
        self.model_path = Path(self.tmp.name) / "grader.gguf"
        self.model_path.write_bytes(b"GGUF")
        self.fake_module = ModuleType("llama_cpp")
        self.fake_module.Llama = _FakeLlama

    def tearDown(self):
        local_llm._MODEL_CACHE.clear()
        self.tmp.cleanup()

    def _settings(self, **env):
        base = {"LLM_PROVIDER": "local", "LLM_LOCAL_MODEL_PATH": str(self.model_path)}
        base.update(env)
        return load_settings(env=base).llm

    def test_wrapper_generates_through_local_model_loaded_once(self):
        settings = self._settings(LLM_LOCAL_N_CTX="8192", LLM_LOCAL_N_GPU_LAYERS="20",
                                  LLM_TEMPERATURE="0.2", LLM_MAX_NEW_TOKENS="700")
        with patch.dict(sys.modules, {"llama_cpp": self.fake_module}):
            first = LLMWrapper(settings=settings)
            LLMWrapper(settings=settings)
            self.assertEqual('{"score": 80}', first.generate("grade"))

        self.assertEqual(1, len(_FakeLlama.instances))
        model = _FakeLlama.instances[0]
        self.assertEqual({"model_path": str(self.model_path), "n_ctx": 8192, "n_gpu_layers": 20}, model.kwargs)
        self.assertEqual(0.2, model.requests[0]["temperature"])
        self.assertEqual(700, model.requests[0]["max_tokens"])
        self.assertEqual("local", first.get_provider_info()["last_provider"])

    def test_missing_model_path_or_file_is_a_config_error(self):
        with self.assertRaises(ConfigError) as ctx:
            LLMWrapper(settings=load_settings(env={"LLM_PROVIDER": "local"}).llm)
        self.assertIn("LLM_LOCAL_MODEL_PATH", str(ctx.exception))
        with self.assertRaises(ConfigError):
            LLMWrapper(settings=self._settings(LLM_LOCAL_MODEL_PATH="/nonexistent/model.gguf"))

    def test_missing_package_has_actionable_error(self):
        with patch.dict(sys.modules, {"llama_cpp": None}):
            with self.assertRaises(ConfigError) as ctx:
                LLMWrapper(settings=self._settings())
        self.assertIn("requirements-local.txt", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
