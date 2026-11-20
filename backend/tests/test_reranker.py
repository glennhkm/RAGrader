"""Tests for reranker implementations, the factory, and Retriever integration."""

import json
import sys
import unittest
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
from langchain_core.documents import Document

from src.rag import reranker as reranker_module
from src.rag.reranker import (
    BGEReranker,
    BM25Reranker,
    HTTPReranker,
    LLMReranker,
    LocalCrossEncoderReranker,
    PineconeReranker,
    create_reranker,
)
from src.rag.retriever import Retriever
from src.utils.config import load_settings


def _docs():
    return [
        Document(page_content="Photosynthesis converts light into chemical energy.", metadata={"source": "bio.pdf"}),
        Document(page_content="TCP uses a three-way handshake: SYN, SYN-ACK, ACK.", metadata={"source": "net.pdf"}),
        Document(page_content="UDP is connectionless and has no handshake.", metadata={"source": "net.pdf"}),
    ]


def _http_client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


class HTTPRerankerTest(unittest.TestCase):
    def test_cohere_style_request_and_response(self):
        seen = {}

        def handler(request):
            seen["url"] = str(request.url)
            seen["auth"] = request.headers.get("authorization")
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json={"results": [
                {"index": 1, "relevance_score": 0.97},
                {"index": 2, "relevance_score": 0.40},
                {"index": 0, "relevance_score": 0.01},
            ]})

        rr = HTTPReranker(base_url="http://vllm:8000/v1", model="BAAI/bge-reranker-v2-m3",
                          api_key="rk", http_client=_http_client(handler))
        ranked = rr.rerank("Explain the TCP handshake", _docs(), top_k=2)

        self.assertEqual("http://vllm:8000/v1/rerank", seen["url"])
        self.assertEqual("Bearer rk", seen["auth"])
        self.assertEqual("BAAI/bge-reranker-v2-m3", seen["body"]["model"])
        self.assertEqual(3, len(seen["body"]["documents"]))
        self.assertEqual(3, seen["body"]["top_n"])
        self.assertEqual(["net.pdf", "net.pdf"], [d.metadata["source"] for d, _ in ranked])
        self.assertAlmostEqual(0.97, ranked[0][1])
        self.assertIn("TCP", ranked[0][0].page_content)

    def test_tei_style_without_key_and_full_rerank_url(self):
        seen = {}

        def handler(request):
            seen["url"] = str(request.url)
            seen["auth"] = request.headers.get("authorization")
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json=[{"index": 2, "score": 3.1}, {"index": 1, "score": 9.5}])

        rr = HTTPReranker(base_url="http://tei:8080/rerank", api_style="tei",
                          http_client=_http_client(handler))
        docs = rr.rerank_documents("handshake", _docs(), top_k=3)

        self.assertEqual("http://tei:8080/rerank", seen["url"])
        self.assertIsNone(seen["auth"])
        self.assertEqual({"query", "texts", "truncate"}, set(seen["body"]))
        # Ranked by score, then the unscored document appended in vector order.
        self.assertEqual([1, 2, 0], [_docs().index(next(x for x in _docs() if x.page_content == d.page_content)) for d in docs])

    def test_out_of_range_and_malformed_results_are_ignored(self):
        def handler(request):
            return httpx.Response(200, json={"results": [
                {"index": 99, "relevance_score": 1.0},
                {"index": "1", "relevance_score": 0.9},
                {"index": True, "relevance_score": 0.8},
                {"index": 2, "relevance_score": 0.5},
                "garbage",
            ]})

        rr = HTTPReranker(base_url="http://x", http_client=_http_client(handler))
        ranked = rr.rerank("q", _docs(), top_k=2)
        self.assertEqual(_docs()[2].page_content, ranked[0][0].page_content)
        self.assertEqual(2, len(ranked))

    def test_server_error_keeps_vector_order(self):
        rr = HTTPReranker(base_url="http://x", http_client=_http_client(lambda r: httpx.Response(500)))
        ranked = rr.rerank("q", _docs(), top_k=2)
        self.assertEqual([d.page_content for d in _docs()[:2]], [d.page_content for d, _ in ranked])
        self.assertEqual([0.0, 0.0], [s for _, s in ranked])

    def test_requires_base_url(self):
        with self.assertRaises(ValueError):
            HTTPReranker(base_url="")


class LLMRerankerTest(unittest.TestCase):
    def _factory(self, content):
        calls = []

        def factory(**kwargs):
            calls.append(kwargs)
            completions = SimpleNamespace(create=lambda **req: SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=content))]))
            return SimpleNamespace(chat=SimpleNamespace(completions=completions))

        return factory, calls

    def test_parses_fenced_json_ranking(self):
        factory, calls = self._factory(
            'Sure!\n```json\n{"ranking": [{"index": 2, "score": 0.6}, {"index": 1, "score": 0.9}]}\n```'
        )
        rr = LLMReranker(base_url="http://ollama:11434/v1", model="qwen2.5:7b", client_factory=factory)
        ranked = rr.rerank("handshake", _docs(), top_k=2)
        self.assertEqual("not-needed", calls[0]["api_key"])
        self.assertEqual([_docs()[1].page_content, _docs()[2].page_content],
                         [d.page_content for d, _ in ranked])

    def test_garbage_output_keeps_vector_order(self):
        factory, _ = self._factory("I cannot rank these.")
        rr = LLMReranker(base_url="http://x/v1", model="m", client_factory=factory)
        ranked = rr.rerank("q", _docs(), top_k=3)
        self.assertEqual([d.page_content for d in _docs()], [d.page_content for d, _ in ranked])


class LocalCrossEncoderTest(unittest.TestCase):
    def setUp(self):
        reranker_module._CROSS_ENCODER_CACHE.clear()

    def tearDown(self):
        reranker_module._CROSS_ENCODER_CACHE.clear()

    def test_fastembed_cross_encoder(self):
        class _TextCrossEncoder:
            def __init__(self, model_name, **kwargs):
                self.model_name = model_name

            def rerank(self, query, documents):
                return [0.1, 0.9, 0.5][: len(documents)]

        cross = ModuleType("fastembed.rerank.cross_encoder")
        cross.TextCrossEncoder = _TextCrossEncoder
        modules = {"fastembed": ModuleType("fastembed"), "fastembed.rerank": ModuleType("fastembed.rerank"),
                   "fastembed.rerank.cross_encoder": cross}
        with patch.dict(sys.modules, modules):
            rr = LocalCrossEncoderReranker(model="Xenova/ms-marco-MiniLM-L-6-v2")
        self.assertEqual("fastembed", rr.backend)
        self.assertEqual(_docs()[1].page_content, rr.rerank("q", _docs(), top_k=1)[0][0].page_content)

    def test_falls_back_to_sentence_transformers(self):
        class _CrossEncoder:
            def __init__(self, model, device):
                self.device = device

            def predict(self, pairs):
                return [len(text) for _, text in pairs]

        st = ModuleType("sentence_transformers")
        st.CrossEncoder = _CrossEncoder
        with patch.dict(sys.modules, {"fastembed": None, "fastembed.rerank": None,
                                      "fastembed.rerank.cross_encoder": None,
                                      "sentence_transformers": st}):
            rr = LocalCrossEncoderReranker(model="BAAI/bge-reranker-v2-m3", device="cuda")
        self.assertEqual("sentence_transformers", rr.backend)
        self.assertEqual("cuda", rr.get_model_info()["device"])

    def test_unsupported_fastembed_model_falls_back_to_sentence_transformers(self):
        class _RejectingCrossEncoder:
            def __init__(self, model_name, **kwargs):
                raise ValueError(f"Model {model_name} is not supported in TextCrossEncoder")

        class _CrossEncoder:
            def __init__(self, model, device):
                self.model = model

            def predict(self, pairs):
                return [1.0 for _ in pairs]

        cross = ModuleType("fastembed.rerank.cross_encoder")
        cross.TextCrossEncoder = _RejectingCrossEncoder
        st = ModuleType("sentence_transformers")
        st.CrossEncoder = _CrossEncoder
        with patch.dict(sys.modules, {"fastembed": ModuleType("fastembed"),
                                      "fastembed.rerank": ModuleType("fastembed.rerank"),
                                      "fastembed.rerank.cross_encoder": cross,
                                      "sentence_transformers": st}):
            rr = LocalCrossEncoderReranker(model="org/custom-reranker")
        self.assertEqual("sentence_transformers", rr.backend)

    def test_model_rejected_everywhere_raises_value_error_naming_each_backend(self):
        class _RejectingCrossEncoder:
            def __init__(self, model_name, **kwargs):
                raise ValueError("not supported")

        cross = ModuleType("fastembed.rerank.cross_encoder")
        cross.TextCrossEncoder = _RejectingCrossEncoder
        with patch.dict(sys.modules, {"fastembed": ModuleType("fastembed"),
                                      "fastembed.rerank": ModuleType("fastembed.rerank"),
                                      "fastembed.rerank.cross_encoder": cross,
                                      "sentence_transformers": None}):
            with self.assertRaises(ValueError) as ctx:
                LocalCrossEncoderReranker(model="bge-reranker-v2-m3")
        message = str(ctx.exception)
        self.assertIn("fastembed", message)
        self.assertIn("sentence_transformers", message)
        self.assertIn("RERANKER_MODEL", message)

    def test_missing_backends_have_actionable_error(self):
        with patch.dict(sys.modules, {"fastembed": None, "fastembed.rerank": None,
                                      "fastembed.rerank.cross_encoder": None,
                                      "sentence_transformers": None}):
            with self.assertRaises(ImportError) as ctx:
                LocalCrossEncoderReranker(model="m")
        self.assertIn("requirements-local.txt", str(ctx.exception))


class BM25AndPineconeTest(unittest.TestCase):
    def test_bm25_ranks_lexical_overlap_first(self):
        ranked = BM25Reranker().rerank("three-way handshake SYN ACK", _docs(), top_k=1)
        self.assertIn("TCP", ranked[0][0].page_content)

    def test_pinecone_with_injected_client_and_legacy_alias(self):
        self.assertIs(PineconeReranker, BGEReranker)
        client = MagicMock()
        client.inference.rerank.return_value = SimpleNamespace(
            data=[SimpleNamespace(index=2, score=0.7), SimpleNamespace(index=0, score=0.2)])
        rr = PineconeReranker(model_name="bge-reranker-v2-m3", client=client)
        ranked = rr.rerank("q", _docs(), top_k=2)
        self.assertEqual(_docs()[2].page_content, ranked[0][0].page_content)
        self.assertEqual(3, client.inference.rerank.call_args.kwargs["top_n"])

    def test_pinecone_requires_key(self):
        with patch.object(reranker_module, "PINECONE_AVAILABLE", True), \
                patch.object(reranker_module, "Pinecone", MagicMock()), \
                patch.object(reranker_module, "get_settings", return_value=load_settings(env={})):
            with self.assertRaises(ValueError):
                PineconeReranker()


class FactoryAndRetrieverTest(unittest.TestCase):
    def test_factory_mapping(self):
        self.assertIsNone(create_reranker(load_settings(env={"ENABLE_RERANKING": "false"}).reranker))
        self.assertIsNone(create_reranker(load_settings(env={
            "ENABLE_RERANKING": "true", "RERANKER_TYPE": "none"}).reranker))
        self.assertIsInstance(create_reranker(load_settings(env={
            "ENABLE_RERANKING": "true", "RERANKER_TYPE": "bm25"}).reranker), BM25Reranker)
        http = create_reranker(load_settings(env={
            "ENABLE_RERANKING": "true", "RERANKER_TYPE": "http_rerank",
            "RERANKER_BASE_URL": "http://tei:8080", "RERANKER_API_STYLE": "tei"}).reranker)
        self.assertIsInstance(http, HTTPReranker)
        self.assertEqual("tei", http.api_style)
        llm = create_reranker(load_settings(env={
            "ENABLE_RERANKING": "true", "RERANKER_TYPE": "llm_rerank",
            "RERANKER_BASE_URL": "http://ollama:11434/v1", "RERANKER_MODEL": "qwen2.5:7b"}).reranker)
        self.assertIsInstance(llm, LLMReranker)
        self.assertEqual("pinecone", load_settings(env={"RERANKER_TYPE": "bge"}).reranker.type)

    def test_retriever_uses_injected_reranker_and_over_fetches(self):
        vs = MagicMock()
        vs.similarity_search.return_value = _docs()
        retriever = Retriever(vectorstore=vs, top_k=10, rerank_top_k=1, enable_reranking=True,
                              reranker=BM25Reranker())
        docs = retriever.retrieve("three-way handshake SYN ACK", course_id="7")
        self.assertEqual(10, vs.similarity_search.call_args.kwargs["k"])
        self.assertEqual(1, len(docs))
        self.assertIn("TCP", docs[0].page_content)
        self.assertEqual("bm25", retriever.get_config()["reranker_type"])

    def test_retriever_falls_back_to_bm25_when_reranker_cannot_start(self):
        settings = load_settings(env={}).reranker  # http_rerank without base URL -> ValueError
        retriever = Retriever(vectorstore=MagicMock(), enable_reranking=True,
                              reranker_type="http_rerank", settings=settings)
        self.assertEqual("bm25", retriever.reranker_type)
        self.assertIsInstance(retriever._reranker, BM25Reranker)

    def test_reranker_fallback_is_logged_as_error_and_reported_in_status(self):
        from loguru import logger

        records = []
        sink = logger.add(lambda m: records.append(m.record), level="ERROR")
        try:
            retriever = Retriever(vectorstore=MagicMock(), enable_reranking=True,
                                  reranker_type="http_rerank", settings=load_settings(env={}).reranker)
        finally:
            logger.remove(sink)
        self.assertTrue(any("http_rerank" in r["message"] for r in records))
        config = retriever.get_config()
        self.assertTrue(config["reranker_fallback"])
        self.assertEqual("http_rerank", config["requested_reranker_type"])
        self.assertIn("RERANKER_BASE_URL", config["reranker_error"])

        healthy = Retriever(vectorstore=MagicMock(), enable_reranking=True, reranker_type="bm25")
        self.assertFalse(healthy.get_config()["reranker_fallback"])
        self.assertIsNone(healthy.get_config()["reranker_error"])

    def test_retriever_type_none_with_reranking_enabled_does_not_over_fetch(self):
        vs = MagicMock()
        vs.similarity_search.return_value = _docs()[:2]
        retriever = Retriever(vectorstore=vs, top_k=20, rerank_top_k=2, enable_reranking=True,
                              reranker_type="none")
        retriever.retrieve("q")
        self.assertEqual(2, vs.similarity_search.call_args.kwargs["k"])

    def test_legacy_bge_type_normalizes_to_pinecone(self):
        retriever = Retriever(vectorstore=MagicMock(), enable_reranking=False, reranker_type="bge")
        self.assertEqual("pinecone", retriever.reranker_type)


if __name__ == "__main__":
    unittest.main()
