"""Tests for LLMWrapper client unification and lean dependency requirements."""

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from src.rag.llm import LLMWrapper


BACKEND_DIR = Path(__file__).resolve().parents[1]


class LLMWrapperAndDepsTest(unittest.TestCase):
    def test_single_groq_provider_uses_provider_chain_without_langchain_groq(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "gsk_test_key"}, clear=False):
            wrapper = LLMWrapper(provider="groq", model_name="custom/any-model-id")

        self.assertTrue(getattr(wrapper, "_use_provider_chain", False))
        self.assertEqual("custom/any-model-id", wrapper.model_name)
        self.assertEqual(["groq"], [ep.name for ep in wrapper.provider_endpoints])
        self.assertFalse(hasattr(wrapper, "_init_groq"))

    def test_requirements_excludes_unused_packages(self):
        req_text = (BACKEND_DIR / "requirements.txt").read_text(encoding="utf-8")
        packages = {
            line.strip().split(">=")[0].split("==")[0].split("<")[0].lower()
            for line in req_text.splitlines()
            if line.strip() and not line.strip().startswith("#")
        }
        for unused in ("nltk", "tiktoken", "pandas", "numpy", "langchain-groq", "pinecone"):
            self.assertNotIn(unused, packages)

        opt_text = (BACKEND_DIR / "requirements-optional.txt").read_text(encoding="utf-8")
        self.assertIn("pinecone", opt_text.lower())


if __name__ == "__main__":
    unittest.main()
