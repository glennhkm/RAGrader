"""Tests for LLMWrapper providers and the OpenAI-compatible chain executor."""

import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from src.rag.llm import LLMWrapper
from src.utils.config import load_settings



class _FakeClientFactory:
    """Records OpenAI client construction and chat requests per base URL."""

    def __init__(self, fail_urls=(), errors=None, contents=None):
        self.fail_urls = set(fail_urls)
        self.errors = errors or {}
        self.contents = contents or {}
        self.calls = []
        self.requests = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        base_url = kwargs["base_url"]
        factory = self

        class _Completions:
            def create(self, **request):
                factory.requests.append(request)
                if base_url in factory.errors:
                    raise factory.errors[base_url]
                if base_url in factory.fail_urls:
                    raise RuntimeError(f"{base_url} unavailable")
                message = SimpleNamespace(content=factory.contents.get(base_url, "ok"))
                return SimpleNamespace(choices=[SimpleNamespace(message=message)])

        return SimpleNamespace(chat=SimpleNamespace(completions=_Completions()))


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

    def test_huggingface_provider_runs_through_chain_with_router_url(self):
        with self.assertRaises(ValueError) as ctx:
            LLMWrapper(provider="huggingface", settings=load_settings(env={}).llm)
        self.assertIn("HUGGINGFACE_API_TOKEN", str(ctx.exception))

        fake = _FakeClientFactory()
        wrapper = LLMWrapper(
            provider="huggingface",
            model_name="Qwen/Qwen2.5-72B-Instruct",
            settings=load_settings(env={"HUGGINGFACE_API_TOKEN": "hf_x"}).llm,
            client_factory=fake,
        )
        self.assertEqual("ok", wrapper.generate("prompt"))
        self.assertEqual("https://router.huggingface.co/v1", fake.calls[0]["base_url"])
        self.assertEqual("hf_x", fake.calls[0]["api_key"])
        self.assertEqual("Qwen/Qwen2.5-72B-Instruct", fake.requests[0]["model"])

    def test_openai_compatible_without_key_and_with_arbitrary_model(self):
        fake = _FakeClientFactory()
        settings = load_settings(env={
            "LLM_PROVIDER": "openai_compatible",
            "LLM_BASE_URL": "http://localhost:11434/v1",
            "LLM_MODEL": "my-org/finetuned-grader:q4_K_M",
            "LLM_TEMPERATURE": "0.1",
            "LLM_MAX_NEW_TOKENS": "900",
        }).llm
        wrapper = LLMWrapper(settings=settings, client_factory=fake)

        self.assertEqual("ok", wrapper.generate("grade this"))
        call, request = fake.calls[0], fake.requests[0]
        self.assertEqual("http://localhost:11434/v1", call["base_url"])
        self.assertEqual("not-needed", call["api_key"])
        self.assertEqual(0, call["max_retries"])
        self.assertEqual("my-org/finetuned-grader:q4_K_M", request["model"])
        self.assertEqual(0.1, request["temperature"])
        self.assertEqual(900, request["max_tokens"])
        self.assertEqual([{"role": "user", "content": "grade this"}], request["messages"])
        self.assertEqual("openai_compatible", wrapper.get_provider_info()["last_provider"])

    def test_openai_compatible_requires_base_url(self):
        settings = load_settings(env={"LLM_PROVIDER": "openai_compatible"}).llm
        with self.assertRaises(ValueError) as ctx:
            LLMWrapper(settings=settings)
        self.assertIn("LLM_BASE_URL", str(ctx.exception))

    def test_custom_endpoint_falls_back_to_groq_in_configured_order(self):
        fake = _FakeClientFactory(fail_urls={"http://vllm:8000/v1"})
        settings = load_settings(env={
            "LLM_PROVIDER_ORDER": "custom_1,groq",
            "LLM_CUSTOM_1_BASE_URL": "http://vllm:8000/v1",
            "LLM_CUSTOM_1_API_KEY": "vllm-key",
            "GROQ_API_KEY": "g0",
        }).llm
        wrapper = LLMWrapper(settings=settings, client_factory=fake)

        self.assertEqual("ok", wrapper.generate("prompt"))
        self.assertEqual(["http://vllm:8000/v1", "https://api.groq.com/openai/v1"],
                         [call["base_url"] for call in fake.calls])
        info = wrapper.get_provider_info()
        self.assertEqual("groq", info["last_provider"])
        self.assertEqual("custom_1", info["provider_failures"][0]["provider"])
        self.assertNotIn("vllm-key", repr(info))
        self.assertNotIn("g0", [e.get("api_key") for e in info["endpoints"]])

    def test_rate_limited_endpoint_honors_retry_after_then_next_succeeds(self):
        rate_limited = RuntimeError("429 Too Many Requests")
        rate_limited.status_code = 429
        rate_limited.response = SimpleNamespace(headers={"retry-after": "1.5"})
        fake = _FakeClientFactory(errors={"https://api.groq.com/openai/v1": rate_limited})
        settings = load_settings(env={"GROQ_API_KEY": "g0", "OPENROUTER_API_KEY": "o0"}).llm
        wrapper = LLMWrapper(settings=settings, client_factory=fake)

        with patch("src.rag.llm.time.sleep") as sleep:
            self.assertEqual("ok", wrapper.generate("prompt"))
        sleep.assert_called_once_with(1.5)
        self.assertEqual("rate_limit", wrapper.get_provider_info()["provider_failures"][0]["error_type"])
        self.assertEqual("openrouter", wrapper.get_provider_info()["last_provider"])

    def test_total_deadline_stops_the_chain(self):
        fake = _FakeClientFactory(fail_urls={"https://api.groq.com/openai/v1"})
        settings = load_settings(env={
            "GROQ_API_KEY": "g0", "OPENROUTER_API_KEY": "o0",
            "LLM_REQUEST_TIMEOUT": "10", "LLM_TOTAL_TIMEOUT": "10",
        }).llm
        wrapper = LLMWrapper(settings=settings, client_factory=fake)
        # monotonic: deadline computed at 0 -> first endpoint at 0 -> second at 11 (past deadline)
        with patch("src.rag.llm.time.monotonic", side_effect=[0.0, 0.0, 11.0]):
            with self.assertRaises(RuntimeError) as ctx:
                wrapper.generate("prompt")
        self.assertIn("All LLM providers failed", str(ctx.exception))
        self.assertEqual(1, len(fake.calls))

    def test_empty_completion_is_treated_as_failure(self):
        fake = _FakeClientFactory(contents={"https://api.groq.com/openai/v1": "   "})
        settings = load_settings(env={"GROQ_API_KEY": "g0", "OPENROUTER_API_KEY": "o0"}).llm
        wrapper = LLMWrapper(settings=settings, client_factory=fake)
        self.assertEqual("ok", wrapper.generate("prompt"))
        self.assertEqual("openrouter", wrapper.get_provider_info()["last_provider"])

    def test_defaults_come_from_settings(self):
        settings = load_settings(env={"GROQ_API_KEY": "g0", "LLM_MODEL": "from/settings"}).llm
        wrapper = LLMWrapper(settings=settings)
        self.assertEqual("provider_chain", wrapper.provider)
        self.assertEqual("from/settings", wrapper.model_name)
        self.assertEqual(0.3, wrapper.temperature)
        self.assertEqual(2048, wrapper.max_new_tokens)

    def test_unknown_provider_argument_is_rejected(self):
        with self.assertRaises(ValueError):
            LLMWrapper(provider="skynet", settings=load_settings(env={}).llm)


if __name__ == "__main__":
    unittest.main()
