"""Tests for the central typed settings layer (src/utils/config.py)."""

import os
import tempfile
import unittest
from pathlib import Path

from src.utils.config import (
    ConfigError,
    get_settings,
    load_settings,
    override_settings,
    reset_settings,
)


class SettingsDefaultsTest(unittest.TestCase):
    """An empty environment must reproduce the pre-Cycle 2 runtime behavior."""

    def setUp(self):
        self.settings = load_settings(env={})

    def test_llm_defaults_match_legacy_behavior(self):
        llm = self.settings.llm
        self.assertEqual("provider_chain", llm.provider)
        self.assertEqual("openai/gpt-oss-120b", llm.model)
        self.assertEqual(0.3, llm.temperature)
        self.assertEqual(2048, llm.max_new_tokens)
        self.assertEqual(60.0, llm.request_timeout)
        self.assertEqual(110.0, llm.total_timeout)
        self.assertEqual(("groq", "openrouter"), llm.provider_order)
        # No keys configured -> no usable endpoints, but loading must not fail.
        self.assertEqual((), llm.endpoints)

    def test_embedding_reranker_vision_prompt_defaults(self):
        s = self.settings
        self.assertEqual("huggingface", s.embeddings.provider)
        self.assertEqual("BAAI/bge-m3", s.embeddings.model)
        self.assertEqual("cpu", s.embeddings.device)  # legacy "cloud" normalized
        self.assertFalse(s.reranker.enabled)
        self.assertEqual("pinecone", s.reranker.type)  # legacy "bge" alias
        self.assertEqual("bge-reranker-v2-m3", s.reranker.model)
        self.assertEqual(5, s.reranker.top_k)
        self.assertEqual(3, s.reranker.rerank_top_k)
        self.assertEqual("cohere", s.reranker.api_style)
        self.assertFalse(s.vision.enable_image_extraction)
        self.assertFalse(s.vision.enable_vision_captioning)
        self.assertEqual("https://router.huggingface.co/v1", s.vision.base_url)
        self.assertEqual("Qwen/Qwen2.5-VL-7B-Instruct", s.vision.model)
        self.assertEqual("auto", s.prompt.language)

    def test_vectorstore_telemetry_defaults_off_and_follows_env(self):
        self.assertFalse(load_settings(env={}).vectorstore.anonymized_telemetry)
        self.assertTrue(load_settings(env={"ANONYMIZED_TELEMETRY": "true"}).vectorstore.anonymized_telemetry)
        self.assertFalse(load_settings(env={"ANONYMIZED_TELEMETRY": "False"}).vectorstore.anonymized_telemetry)

    def test_lock_api_logging_defaults(self):
        s = self.settings
        self.assertFalse(s.locks.enabled)
        self.assertEqual("redis://redis:6379/0", s.locks.redis_url)
        self.assertEqual("airag:lock", s.locks.prefix)
        self.assertEqual(900, s.locks.ttl_seconds)
        self.assertEqual(120, s.locks.wait_seconds)
        self.assertEqual("", s.api.auth_token)
        self.assertEqual(50, s.api.max_upload_size_mb)
        self.assertEqual("0.0.0.0", s.api.host)
        self.assertEqual(8000, s.api.port)
        self.assertTrue(s.api.instance_id)
        self.assertEqual("INFO", s.logging.level)
        self.assertTrue(s.logging.to_file)

    def test_raw_config_is_the_resolved_yaml(self):
        raw = self.settings.raw
        self.assertEqual(500, raw["document_processing"]["chunk_size"])
        self.assertEqual("BAAI/bge-m3", raw["embeddings"]["model_name"])
        self.assertEqual("persistent", raw["vectorstore"]["client_mode"])


class SettingsParsingTest(unittest.TestCase):
    def test_numbered_keys_expand_in_provider_order(self):
        s = load_settings(env={
            "LLM_PROVIDER_ORDER": "openrouter,groq",
            "GROQ_API_KEY": "g0",
            "GROQ_API_KEY_2": "g2",
            "OPENROUTER_API_KEY_1": "o1",
            "GROQ_MODEL": "llama-3.3-70b-versatile",
            "OPENROUTER_SITE_URL": "https://lms.example",
        })
        names = [ep.name for ep in s.llm.endpoints]
        self.assertEqual(["openrouter1", "groq", "groq2"], names)
        groq = s.llm.endpoints[1]
        self.assertEqual("https://api.groq.com/openai/v1", groq.base_url)
        self.assertEqual("g0", groq.api_key)
        self.assertEqual("llama-3.3-70b-versatile", groq.model)
        openrouter = s.llm.endpoints[0]
        self.assertEqual("https://openrouter.ai/api/v1", openrouter.base_url)
        self.assertEqual("openai/gpt-oss-120b", openrouter.model)
        self.assertEqual("https://lms.example", openrouter.extra_headers["HTTP-Referer"])

    def test_key_max_index_limits_numbered_keys(self):
        s = load_settings(env={"GROQ_API_KEY_3": "g3", "GROQ_KEY_MAX_INDEX": "2"})
        self.assertEqual((), s.llm.endpoints)

    def test_custom_endpoint_resolves_with_optional_key(self):
        s = load_settings(env={
            "LLM_PROVIDER_ORDER": "custom_1,groq",
            "LLM_CUSTOM_1_BASE_URL": "http://ollama:11434/v1",
            "LLM_CUSTOM_1_MODEL": "qwen2.5:14b-instruct",
            "GROQ_API_KEY": "g0",
        })
        custom, groq = s.llm.endpoints
        self.assertEqual("custom_1", custom.name)
        self.assertEqual("http://ollama:11434/v1", custom.base_url)
        self.assertEqual("", custom.api_key)
        self.assertEqual("qwen2.5:14b-instruct", custom.model)
        self.assertEqual("groq", groq.name)

    def test_custom_endpoint_without_base_url_is_rejected(self):
        with self.assertRaises(ConfigError) as ctx:
            load_settings(env={"LLM_PROVIDER_ORDER": "custom_2"})
        self.assertIn("LLM_CUSTOM_2_BASE_URL", str(ctx.exception))

    def test_unknown_chain_entries_are_skipped_like_before(self):
        s = load_settings(env={"LLM_PROVIDER_ORDER": "mystery,groq", "GROQ_API_KEY": "g0"})
        self.assertEqual(("mystery", "groq"), s.llm.provider_order)
        self.assertEqual(["groq"], [ep.name for ep in s.llm.endpoints])

    def test_chain_helper_returns_presets_in_requested_order(self):
        s = load_settings(env={"GROQ_API_KEY": "g0", "OPENROUTER_API_KEY": "o0"})
        self.assertEqual(["openrouter", "groq"], [ep.name for ep in s.llm.chain(["openrouter", "groq"])])
        hf = load_settings(env={"HUGGINGFACE_API_TOKEN": "hf_x"}).llm.chain(["huggingface"])
        self.assertEqual("https://router.huggingface.co/v1", hf[0].base_url)
        self.assertEqual("hf_x", hf[0].api_key)

    def test_provider_aliases_and_openai_compatible(self):
        self.assertEqual("provider_chain", load_settings(env={"LLM_PROVIDER": "auto"}).llm.provider)
        s = load_settings(env={
            "LLM_PROVIDER": "OpenAI_Compatible",
            "LLM_BASE_URL": "http://vllm:8000/v1",
            "LLM_MODEL": "any/custom-model-id",
        })
        self.assertEqual("openai_compatible", s.llm.provider)
        self.assertEqual("http://vllm:8000/v1", s.llm.base_url)
        self.assertEqual("any/custom-model-id", s.llm.model)

    def test_unknown_provider_is_rejected_with_variable_name(self):
        with self.assertRaises(ConfigError) as ctx:
            load_settings(env={"LLM_PROVIDER": "skynet"})
        self.assertIn("LLM_PROVIDER", str(ctx.exception))

    def test_invalid_number_names_the_variable(self):
        with self.assertRaises(ConfigError) as ctx:
            load_settings(env={"LLM_REQUEST_TIMEOUT": "abc"})
        self.assertIn("LLM_REQUEST_TIMEOUT", str(ctx.exception))

    def test_lower_bounds_are_clamped_like_before(self):
        s = load_settings(env={
            "LLM_REQUEST_TIMEOUT": "0",
            "LLM_TOTAL_TIMEOUT": "5",
            "DISTRIBUTED_LOCK_TTL_SECONDS": "10",
            "DISTRIBUTED_LOCK_WAIT_SECONDS": "0",
            "MAX_UPLOAD_SIZE_MB": "0",
        })
        self.assertEqual(1.0, s.llm.request_timeout)
        self.assertEqual(5.0, s.llm.total_timeout)
        self.assertEqual(60, s.locks.ttl_seconds)
        self.assertEqual(1, s.locks.wait_seconds)
        self.assertEqual(1, s.api.max_upload_size_mb)
        # The total deadline is never shorter than one request.
        s2 = load_settings(env={"LLM_REQUEST_TIMEOUT": "90", "LLM_TOTAL_TIMEOUT": "30"})
        self.assertEqual(90.0, s2.llm.total_timeout)

    def test_booleans_and_choices(self):
        s = load_settings(env={
            "DISTRIBUTED_LOCK_ENABLED": "Yes",
            "ENABLE_RERANKING": "on",
            "RERANKER_TYPE": "http_rerank",
            "RERANKER_API_STYLE": "TEI",
            "EMBEDDING_PROVIDER": "local",
            "EMBEDDING_DEVICE": "cuda",
            "PROMPT_LANGUAGE": "ID",
            "LOG_TO_FILE": "0",
            "API_AUTH_TOKEN": "  secret  ",
        })
        self.assertTrue(s.locks.enabled)
        self.assertTrue(s.reranker.enabled)
        self.assertEqual("http_rerank", s.reranker.type)
        self.assertEqual("tei", s.reranker.api_style)
        self.assertEqual("local", s.embeddings.provider)
        self.assertEqual("cuda", s.embeddings.device)
        self.assertEqual("id", s.prompt.language)
        self.assertFalse(s.logging.to_file)
        self.assertEqual("secret", s.api.auth_token)
        with self.assertRaises(ConfigError):
            load_settings(env={"DISTRIBUTED_LOCK_ENABLED": "maybe"})
        with self.assertRaises(ConfigError):
            load_settings(env={"PROMPT_LANGUAGE": "fr"})

    def test_client_settings_for_cli(self):
        self.assertEqual("http://127.0.0.1:8000", load_settings(env={}).client.api_url)
        s = load_settings(env={"RAG_API_URL": "https://grader.example/", "API_AUTH_TOKEN": "srv"})
        self.assertEqual("https://grader.example", s.client.api_url)
        self.assertEqual("srv", s.client.api_token)
        self.assertEqual("cli", load_settings(env={"RAG_API_TOKEN": "cli", "API_AUTH_TOKEN": "srv"}).client.api_token)

    def test_vision_key_falls_back_to_huggingface_token(self):
        s = load_settings(env={"HUGGINGFACE_API_TOKEN": "hf_x"})
        self.assertEqual("hf_x", s.vision.api_key)
        self.assertEqual("hf_x", s.embeddings.huggingface_token)
        s2 = load_settings(env={"HUGGINGFACE_API_TOKEN": "hf_x", "VISION_API_KEY": "v_y"})
        self.assertEqual("v_y", s2.vision.api_key)

    def test_yaml_file_values_apply_when_env_is_unset(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            path.write_text(
                'llm:\n  provider: "${LLM_PROVIDER:openai_compatible}"\n'
                '  model_name: "${LLM_MODEL:local-model}"\n'
                '  temperature: 0.1\n  max_new_tokens: 512\n',
                encoding="utf-8",
            )
            s = load_settings(env={}, config_path=path)
            self.assertEqual("openai_compatible", s.llm.provider)
            self.assertEqual("local-model", s.llm.model)
            self.assertEqual(0.1, s.llm.temperature)
            self.assertEqual(512, s.llm.max_new_tokens)
            s_env = load_settings(env={"LLM_MODEL": "from-env"}, config_path=path)
            self.assertEqual("from-env", s_env.llm.model)


class SettingsSecretsAndCacheTest(unittest.TestCase):
    def tearDown(self):
        reset_settings()

    def test_repr_masks_secrets(self):
        s = load_settings(env={
            "GROQ_API_KEY": "gsk_super_secret",
            "HUGGINGFACE_API_TOKEN": "hf_super_secret",
            "API_AUTH_TOKEN": "bearer_super_secret",
            "PINECONE_API_KEY": "pc_super_secret",
            "LLM_API_KEY": "llm_super_secret",
        })
        text = repr(s)
        for secret in ("gsk_super_secret", "hf_super_secret", "bearer_super_secret",
                       "pc_super_secret", "llm_super_secret"):
            self.assertNotIn(secret, text)
        self.assertIn("***", text)

    def test_settings_are_immutable(self):
        s = load_settings(env={})
        with self.assertRaises(Exception):
            s.llm.model = "other"  # type: ignore[misc]

    def test_override_settings_isolates_and_restores(self):
        previous = os.environ.get("LLM_MODEL")
        with override_settings(LLM_MODEL="override-model") as s:
            self.assertEqual("override-model", s.llm.model)
            self.assertEqual("override-model", get_settings().llm.model)
        self.assertEqual(previous, os.environ.get("LLM_MODEL"))
        self.assertNotEqual("override-model", get_settings().llm.model)

    def test_override_settings_can_unset_variables(self):
        os.environ["API_AUTH_TOKEN"] = "temporary"
        try:
            with override_settings(API_AUTH_TOKEN=None) as s:
                self.assertEqual("", s.api.auth_token)
            self.assertEqual("temporary", os.environ["API_AUTH_TOKEN"])
        finally:
            os.environ.pop("API_AUTH_TOKEN", None)

    def test_get_settings_is_cached_until_reset(self):
        first = get_settings()
        self.assertIs(first, get_settings())
        reset_settings()
        self.assertIsNot(first, get_settings())


if __name__ == "__main__":
    unittest.main()
