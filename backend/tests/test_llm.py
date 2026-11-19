"""Tests for LLMWrapper client unification and lean dependency requirements."""

import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.rag.llm import LLMWrapper
from src.utils.config import load_settings


BACKEND_DIR = Path(__file__).resolve().parents[1]


class LLMWrapperAndDepsTest(unittest.TestCase):
    def test_single_groq_provider_uses_provider_chain_without_langchain_groq(self):
        settings = load_settings(env={"GROQ_API_KEY": "gsk_test_key"}).llm
        wrapper = LLMWrapper(provider="groq", model_name="custom/any-model-id", settings=settings)

        self.assertTrue(getattr(wrapper, "_use_provider_chain", False))
        self.assertEqual("custom/any-model-id", wrapper.model_name)
        self.assertEqual(["groq"], [ep.name for ep in wrapper.provider_endpoints])
        self.assertFalse(hasattr(wrapper, "_init_groq"))
        self.assertFalse(hasattr(wrapper, "_use_openai_client"))
        self.assertIsNone(wrapper.get_llm_instance())

    def test_wrapper_model_applies_unless_endpoint_model_is_overridden(self):
        settings = load_settings(env={
            "GROQ_API_KEY": "g0",
            "OPENROUTER_API_KEY": "o0",
            "OPENROUTER_MODEL": "meta-llama/llama-3.3-70b-instruct",
        }).llm
        wrapper = LLMWrapper(provider="provider_chain", model_name="switched/model", settings=settings)
        models = {ep.name: ep.model for ep in wrapper.provider_endpoints}
        self.assertEqual("switched/model", models["groq"])
        self.assertEqual("meta-llama/llama-3.3-70b-instruct", models["openrouter"])

    def test_generate_uses_settings_keys_headers_and_timeouts_not_environment(self):
        settings = load_settings(env={
            "LLM_PROVIDER_ORDER": "openrouter,custom_1",
            "OPENROUTER_API_KEY": "or-key",
            "LLM_CUSTOM_1_BASE_URL": "http://ollama:11434/v1",
            "LLM_REQUEST_TIMEOUT": "12",
            "LLM_TOTAL_TIMEOUT": "30",
        }).llm
        created = []

        class _FakeCompletions:
            def __init__(self, fail):
                self.fail = fail

            def create(self, **kwargs):
                if self.fail:
                    raise RuntimeError("upstream exploded")
                message = SimpleNamespace(content="  graded  ")
                return SimpleNamespace(choices=[SimpleNamespace(message=message)])

        def _fake_openai(**kwargs):
            created.append(kwargs)
            fail = kwargs["base_url"].startswith("https://openrouter.ai")
            return SimpleNamespace(chat=SimpleNamespace(completions=_FakeCompletions(fail)))

        with patch.dict(os.environ, {}, clear=True), patch("src.rag.llm.OpenAI", side_effect=_fake_openai):
            wrapper = LLMWrapper(model_name="m", settings=settings)
            self.assertEqual("graded", wrapper.generate("prompt"))

        openrouter_call, custom_call = created
        self.assertEqual("or-key", openrouter_call["api_key"])
        self.assertEqual("http://localhost", openrouter_call["default_headers"]["HTTP-Referer"])
        self.assertEqual(12.0, openrouter_call["timeout"])
        self.assertEqual("http://ollama:11434/v1", custom_call["base_url"])
        self.assertEqual("not-needed", custom_call["api_key"])
        self.assertIsNone(custom_call["default_headers"])
        self.assertEqual("custom_1", wrapper.get_provider_info()["last_provider"])
        self.assertNotIn("or-key", repr(wrapper.get_provider_info()))

    def test_huggingface_provider_reads_token_from_settings(self):
        with self.assertRaises(ValueError):
            LLMWrapper(provider="huggingface", settings=load_settings(env={}).llm)
        wrapper = LLMWrapper(
            provider="huggingface",
            settings=load_settings(env={"HUGGINGFACE_API_TOKEN": "hf_x"}).llm,
        )
        self.assertEqual("https://router.huggingface.co/v1/", str(wrapper.client.base_url))

    def test_requirements_excludes_unused_packages(self):
        req_text = (BACKEND_DIR / "requirements.txt").read_text(encoding="utf-8")
        packages = {
            line.strip().split(">=")[0].split("==")[0].split("<")[0].lower()
            for line in req_text.splitlines()
            if line.strip() and not line.strip().startswith("#")
        }
        for unused in (
            "nltk",
            "tiktoken",
            "pandas",
            "numpy",
            "langchain-groq",
            "pinecone",
            "pydantic-settings",
        ):
            self.assertNotIn(unused, packages)

        opt_text = (BACKEND_DIR / "requirements-optional.txt").read_text(encoding="utf-8")
        self.assertIn("pinecone", opt_text.lower())


if __name__ == "__main__":
    unittest.main()
