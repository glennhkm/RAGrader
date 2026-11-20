"""Tests for embedding providers and the vector-collection embedding identity guard."""

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from threading import RLock
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

import chromadb
from fastapi.testclient import TestClient
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from src.api.runtime import AppRuntime
from src.utils.config import LOCAL_FASTEMBED_EMBEDDING_MODEL, load_settings
from src.vectorstore import embeddings as embeddings_module
from src.vectorstore.chroma_store import VectorStore
from src.vectorstore.embeddings import (
    EmbeddingGenerator,
    EmbeddingMismatchError,
    LocalEmbeddings,
    OpenAICompatibleEmbeddings,
)


class _FakeEmbeddingsClient:
    """Fake OpenAI client that returns embeddings out of order, like real APIs may."""

    def __init__(self, dimension=3):
        self.dimension = dimension
        self.init_kwargs = None
        self.requests = []
        factory = self

        class _Embeddings:
            def create(self, model, input):
                factory.requests.append({"model": model, "input": list(input)})
                data = [
                    SimpleNamespace(index=i, embedding=[float(len(text))] * factory.dimension)
                    for i, text in enumerate(input)
                ]
                return SimpleNamespace(data=list(reversed(data)))

        self.embeddings = _Embeddings()

    def __call__(self, **kwargs):
        self.init_kwargs = kwargs
        return self


class OpenAICompatibleEmbeddingsTest(unittest.TestCase):
    def test_batches_preserve_input_order(self):
        client = _FakeEmbeddingsClient()
        emb = OpenAICompatibleEmbeddings(
            model="nomic-embed-text", base_url="http://ollama:11434/v1",
            batch_size=2, client_factory=client,
        )
        vectors = emb.embed_documents(["a", "bb", "ccc", ""])

        self.assertEqual([[1.0] * 3, [2.0] * 3, [3.0] * 3, [1.0] * 3], vectors)
        self.assertEqual([["a", "bb"], ["ccc", " "]], [r["input"] for r in client.requests])
        self.assertEqual("nomic-embed-text", client.requests[0]["model"])
        self.assertEqual("not-needed", client.init_kwargs["api_key"])
        self.assertEqual("http://ollama:11434/v1", client.init_kwargs["base_url"])
        self.assertEqual([4.0] * 3, emb.embed_query("dddd"))

    def test_requires_base_url(self):
        with self.assertRaises(ValueError) as ctx:
            OpenAICompatibleEmbeddings(model="m", base_url="", client_factory=_FakeEmbeddingsClient())
        self.assertIn("EMBEDDING_BASE_URL", str(ctx.exception))


class EmbeddingGeneratorTest(unittest.TestCase):
    def test_huggingface_token_only_required_when_selected(self):
        with self.assertRaises(ValueError) as ctx:
            EmbeddingGenerator(settings=load_settings(env={}).embeddings)
        self.assertIn("HUGGINGFACE_API_TOKEN", str(ctx.exception))

        settings = load_settings(env={
            "EMBEDDING_PROVIDER": "openai_compatible",
            "EMBEDDING_BASE_URL": "http://tei:8080/v1",
            "EMBEDDING_MODEL": "BAAI/bge-m3",
        }).embeddings
        generator = EmbeddingGenerator(settings=settings, client_factory=_FakeEmbeddingsClient(dimension=8))
        self.assertEqual("openai_compatible", generator.provider)
        self.assertEqual(
            {"embedding_provider": "openai_compatible", "embedding_model": "BAAI/bge-m3",
             "embedding_dimension": 8},
            generator.identity(),
        )
        self.assertEqual("openai_compatible", generator.get_model_info()["provider"])

    def test_switch_model_keeps_state_when_new_model_fails(self):
        settings = load_settings(env={
            "EMBEDDING_PROVIDER": "openai_compatible",
            "EMBEDDING_BASE_URL": "http://tei:8080/v1",
        }).embeddings
        generator = EmbeddingGenerator(model_name="model-a", settings=settings,
                                       client_factory=_FakeEmbeddingsClient())
        original = generator.get_embeddings_instance()
        with patch.object(generator, "_build", side_effect=RuntimeError("boom")):
            self.assertFalse(generator.switch_model("model-b"))
        self.assertEqual("model-a", generator.model_name)
        self.assertIs(original, generator.get_embeddings_instance())
        self.assertTrue(generator.switch_model("model-b"))
        self.assertEqual("model-b", generator.model_name)


class LocalEmbeddingsTest(unittest.TestCase):
    def setUp(self):
        embeddings_module._LOCAL_MODEL_CACHE.clear()

    def tearDown(self):
        embeddings_module._LOCAL_MODEL_CACHE.clear()

    def test_fastembed_backend_is_loaded_once_and_used(self):
        created = []

        class _TextEmbedding:
            def __init__(self, model_name, **kwargs):
                created.append((model_name, kwargs))

            def embed(self, texts, batch_size):
                return [[0.5, float(len(text))] for text in texts]

        fake_module = ModuleType("fastembed")
        fake_module.TextEmbedding = _TextEmbedding
        settings = load_settings(env={
            "EMBEDDING_PROVIDER": "local",
            "EMBEDDING_MODEL": "intfloat/multilingual-e5-large",
            "EMBEDDING_DEVICE": "cuda",
        }).embeddings
        with patch.dict(sys.modules, {"fastembed": fake_module}):
            first = EmbeddingGenerator(settings=settings)
            second = EmbeddingGenerator(settings=settings)
            self.assertEqual([[0.5, 2.0]], first.embed_documents(["ab"]))
            self.assertEqual([0.5, 3.0], second.embed_query("abc"))
        self.assertEqual([("intfloat/multilingual-e5-large", {"cuda": True})], created)
        self.assertEqual("cuda", first.get_model_info()["device"])

    def test_sentence_transformers_backend(self):
        class _SentenceTransformer:
            def __init__(self, model, device):
                self.model, self.device = model, device

            def encode(self, texts, batch_size, normalize_embeddings, convert_to_numpy):
                assert normalize_embeddings is True
                return [[1.0, 0.0] for _ in texts]

        fake_module = ModuleType("sentence_transformers")
        fake_module.SentenceTransformer = _SentenceTransformer
        with patch.dict(sys.modules, {"sentence_transformers": fake_module}):
            emb = LocalEmbeddings(model="BAAI/bge-m3", backend="sentence_transformers")
            self.assertEqual([[1.0, 0.0], [1.0, 0.0]], emb.embed_documents(["x", "y"]))
            self.assertEqual([], emb.embed_documents([]))

    def test_unsupported_fastembed_model_error_names_alternatives(self):
        class _RejectingTextEmbedding:
            def __init__(self, model_name, **kwargs):
                raise ValueError(f"Model {model_name} is not supported in TextEmbedding")

        fake_module = ModuleType("fastembed")
        fake_module.TextEmbedding = _RejectingTextEmbedding
        with patch.dict(sys.modules, {"fastembed": fake_module}):
            with self.assertRaises(ValueError) as ctx:
                LocalEmbeddings(model="BAAI/bge-m3", backend="fastembed")
        message = str(ctx.exception)
        self.assertIn("EMBEDDING_MODEL", message)
        self.assertIn("sentence_transformers", message)
        self.assertIn(LOCAL_FASTEMBED_EMBEDDING_MODEL, message)

    def test_fastembed_on_mps_warns_and_runs_on_cpu(self):
        from loguru import logger

        created = []

        class _TextEmbedding:
            def __init__(self, model_name, **kwargs):
                created.append(kwargs)

            def embed(self, texts, batch_size):
                return [[1.0] for _ in texts]

        fake_module = ModuleType("fastembed")
        fake_module.TextEmbedding = _TextEmbedding
        records = []
        sink = logger.add(lambda m: records.append(m.record), level="WARNING")
        try:
            with patch.dict(sys.modules, {"fastembed": fake_module}):
                LocalEmbeddings(model="mps-test-model", backend="fastembed", device="mps")
        finally:
            logger.remove(sink)
        self.assertEqual([{}], created)
        self.assertTrue(any("mps" in r["message"].lower() for r in records))

    def test_missing_optional_package_has_actionable_error(self):
        with patch.dict(sys.modules, {"fastembed": None}):
            with self.assertRaises(ImportError) as ctx:
                LocalEmbeddings(model="m", backend="fastembed")
        self.assertIn("requirements-local.txt", str(ctx.exception))


class _HashEmbeddings(Embeddings):
    def __init__(self, dimension):
        self.dimension = dimension

    def embed_documents(self, texts):
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text):
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return [byte / 255.0 for byte in digest[: self.dimension]]


def _store(tempdir, provider="huggingface", dimension=8, model="BAAI/bge-m3"):
    generator = MagicMock()
    generator.get_embeddings_instance.return_value = _HashEmbeddings(dimension)
    generator.identity.return_value = {
        "embedding_provider": provider,
        "embedding_model": model,
        "embedding_dimension": dimension,
    }
    with patch("src.vectorstore.chroma_store.EmbeddingGenerator", return_value=generator):
        return VectorStore(persist_directory=tempdir, embedding_model=model, client_mode="persistent")


class CollectionIdentityGuardTest(unittest.TestCase):
    def _doc(self, text="TCP is reliable."):
        return Document(page_content=text, metadata={"source": "w1.pdf", "page": 1})

    def test_new_collection_records_identity_and_reopens_with_same_setup(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store(tmp)
            store.add_documents([self._doc()], course_id="12")
            collection = store.client.get_collection(store._get_collection_name("12"))
            self.assertEqual("huggingface", collection.metadata["embedding_provider"])
            self.assertEqual(8, collection.metadata["embedding_dimension"])

            reopened = _store(tmp)
            self.assertEqual(1, len(reopened.similarity_search("TCP", k=1, course_id="12")))

    def test_switching_provider_on_existing_collection_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            _store(tmp, provider="huggingface").add_documents([self._doc()], course_id="12")
            other = _store(tmp, provider="openai_compatible")
            with self.assertRaises(EmbeddingMismatchError) as ctx:
                other.similarity_search("TCP", k=1, course_id="12")
            self.assertIn("embedding_provider", str(ctx.exception))
            with self.assertRaises(EmbeddingMismatchError):
                other.add_documents([self._doc()], course_id="12")

    def test_legacy_collection_without_identity_is_adopted(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store(tmp, dimension=8)
            name = store._get_collection_name("7")
            legacy = store.client.create_collection(name)  # pre-Cycle 2: no metadata
            legacy.add(ids=["a"], embeddings=[[0.1] * 8], documents=["old chunk"],
                       metadatas=[{"source": "old.pdf"}])

            self.assertEqual(1, len(store.similarity_search("old", k=1, course_id="7")))
            adopted = store.client.get_collection(name)
            self.assertEqual("BAAI/bge-m3", adopted.metadata["embedding_model"])
            self.assertEqual(1, adopted.count())

    def test_legacy_collection_with_other_dimension_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store(tmp, dimension=8)
            legacy = store.client.create_collection(store._get_collection_name("7"))
            legacy.add(ids=["a"], embeddings=[[0.1] * 4], documents=["old chunk"])
            with self.assertRaises(EmbeddingMismatchError) as ctx:
                store.similarity_search("old", k=1, course_id="7")
            self.assertIn("4-dimensional", str(ctx.exception))


class MissingCollectionRegressionTest(unittest.TestCase):
    """chromadb 0.6.x raises InvalidCollectionException (not NotFoundError) for missing collections."""

    def test_operations_on_a_course_without_materials_do_not_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _store(tmp)
            self.assertEqual(0, store.get_count("999"))
            self.assertFalse(store.delete_document_by_source("none.pdf", course_id="999"))
            store.clear(course_id="999")  # must be a no-op, not an error


class EmbeddingMismatchHttpTest(unittest.TestCase):
    def test_api_maps_mismatch_to_409(self):
        from src.api.app import create_app

        grader = MagicMock()
        grader.grade_essay.side_effect = EmbeddingMismatchError("collection built with another model")
        grader.ingest_course_materials.side_effect = EmbeddingMismatchError("collection built with another model")
        locks = MagicMock()
        locks.read.side_effect = lambda resource: RLock()
        locks.write.side_effect = lambda resource: RLock()
        runtime = AppRuntime(grader=grader, operation_locks=locks, settings=load_settings(env={}))

        with tempfile.TemporaryDirectory() as data_dir, \
                patch("src.utils.DATA_DIR", Path(data_dir)), \
                TestClient(create_app(runtime=runtime)) as client:
            v1 = client.post("/v1/namespaces/cs-101/grade", json={"question": "Q", "essay": "A"})
            moodle = client.post("/assign/answer", json={"course_id": 3, "question": "Q", "essay": "A"})
            upload = client.post("/course/materials/upload", data={"course_id": "3"},
                                 files={"file": ("w1.txt", b"TCP", "text/plain")})

        for response in (v1, moodle, upload):
            self.assertEqual(409, response.status_code, response.text)
            self.assertIn("another model", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
