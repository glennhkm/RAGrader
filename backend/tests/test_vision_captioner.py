"""Tests for the configurable OpenAI-compatible vision captioner."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from src.ingestion.image_extractor import ExtractedImage
from src.ingestion.vision_captioner import VisionCaptioner
from src.utils.config import load_settings


def _image(fmt="jpeg"):
    return ExtractedImage(image_data=b"\x89fakeimage", image_format=fmt, source_file="w1.pdf",
                          page_number=3, image_index=0, width=640, height=480, image_hash="h")


class _FakeVisionClient:
    def __init__(self, failures=0, content="A diagram of the TCP handshake."):
        self.failures = failures
        self.content = content
        self.init_kwargs = None
        self.requests = []
        outer = self

        class _Completions:
            def create(self, **request):
                outer.requests.append(request)
                if outer.failures > 0:
                    outer.failures -= 1
                    raise RuntimeError("temporarily unavailable")
                message = SimpleNamespace(content=outer.content)
                return SimpleNamespace(choices=[SimpleNamespace(message=message)])

        self.chat = SimpleNamespace(completions=_Completions())

    def __call__(self, **kwargs):
        self.init_kwargs = kwargs
        return self


def _settings(**env):
    s = load_settings(env=env)
    return s.vision, s.prompt


class VisionCaptionerTest(unittest.TestCase):
    def test_defaults_to_huggingface_router_and_requires_token(self):
        vision, prompt = _settings()
        with self.assertRaises(ValueError) as ctx:
            VisionCaptioner(settings=vision, prompt_settings=prompt, client_factory=_FakeVisionClient())
        self.assertIn("HUGGINGFACE_API_TOKEN", str(ctx.exception))

        client = _FakeVisionClient()
        vision, prompt = _settings(HUGGINGFACE_API_TOKEN="hf_x")
        captioner = VisionCaptioner(settings=vision, prompt_settings=prompt, client_factory=client)
        self.assertEqual("https://router.huggingface.co/v1", client.init_kwargs["base_url"])
        self.assertEqual("hf_x", client.init_kwargs["api_key"])
        self.assertEqual("Qwen/Qwen2.5-VL-7B-Instruct", captioner.model_name)
        self.assertIn("Jelaskan gambar", captioner.prompt_template)  # auto keeps Indonesian

    def test_custom_endpoint_model_language_and_payload(self):
        client = _FakeVisionClient()
        vision, prompt = _settings(VISION_BASE_URL="http://ollama:11434/v1/", VISION_MODEL="llava:13b",
                                   PROMPT_LANGUAGE="en")
        captioner = VisionCaptioner(settings=vision, prompt_settings=prompt, client_factory=client)

        caption = captioner.caption_image(_image("jpeg"))

        self.assertEqual("http://ollama:11434/v1", client.init_kwargs["base_url"])
        self.assertEqual("not-needed", client.init_kwargs["api_key"])
        request = client.requests[0]
        self.assertEqual("llava:13b", request["model"])
        content = request["messages"][0]["content"]
        self.assertTrue(content[0]["image_url"]["url"].startswith("data:image/jpeg;base64,"))
        self.assertIn("Describe this educational image", content[1]["text"])
        self.assertEqual("llava:13b", caption.model_used)
        self.assertEqual(1.0, caption.confidence)
        self.assertIn("TCP handshake", caption.caption)

    def test_retries_then_succeeds(self):
        client = _FakeVisionClient(failures=2)
        vision, prompt = _settings(VISION_BASE_URL="http://vllm:8000/v1")
        captioner = VisionCaptioner(settings=vision, prompt_settings=prompt, client_factory=client,
                                    max_retries=3, retry_delay=0.01)
        with patch("src.ingestion.vision_captioner.time.sleep"):
            caption = captioner.caption_image(_image())
        self.assertEqual(3, len(client.requests))
        self.assertEqual(1.0, caption.confidence)

    def test_exhausted_retries_return_placeholder_caption(self):
        client = _FakeVisionClient(failures=5)
        vision, prompt = _settings(VISION_BASE_URL="http://vllm:8000/v1")
        captioner = VisionCaptioner(settings=vision, prompt_settings=prompt, client_factory=client,
                                    max_retries=2, retry_delay=0.01)
        with patch("src.ingestion.vision_captioner.time.sleep"):
            caption = captioner.caption_image(_image())
        self.assertEqual(0.0, caption.confidence)
        self.assertIn("w1.pdf", caption.caption)

    def test_switch_model_accepts_any_model(self):
        vision, prompt = _settings(VISION_BASE_URL="http://x/v1")
        captioner = VisionCaptioner(settings=vision, prompt_settings=prompt, client_factory=_FakeVisionClient())
        result = captioner.switch_model("my-org/custom-vlm")
        self.assertTrue(result["success"])
        self.assertEqual("my-org/custom-vlm", captioner.model_name)


if __name__ == "__main__":
    unittest.main()
