"""Regression tests for Chroma collection access across client versions."""

import unittest
import tempfile
from unittest.mock import MagicMock, patch

import chromadb

from chromadb.errors import NotFoundError

from chromadb.config import Settings as ChromaSettings

from src.vectorstore.chroma_store import VectorStore

_OFFLINE = ChromaSettings(anonymized_telemetry=False)


class _FakeCollection:
    def __init__(self, count=37, ids=None):
        self._count = count
        self._ids = ids or []
        self.deleted_ids = []

    def count(self):
        return self._count

    def get(self, where=None):
        return {"ids": self._ids}

    def delete(self, ids=None):
        self.deleted_ids.extend(ids or [])


class _FakeClient:
    def __init__(self, collection=None, missing=False):
        self.collection = collection
        self.missing = missing
        self.deleted_collections = []

    def list_collections(self):
        raise AssertionError("Collection operations must not depend on list_collections()")

    def get_collection(self, name):
        if self.missing:
            raise NotFoundError(f"Collection {name} does not exist")
        return self.collection

    def delete_collection(self, name):
        self.deleted_collections.append(name)


def _make_store(client):
    store = VectorStore.__new__(VectorStore)
    store.client = client
    store.base_collection_name = "course_materials"
    store.current_embedding_model = "BAAI/bge-m3"
    store._vectorstores = {}
    return store


class ChromaStoreCompatibilityTest(unittest.TestCase):
    @patch("src.vectorstore.chroma_store.Chroma")
    @patch("src.vectorstore.chroma_store.EmbeddingGenerator")
    @patch("src.vectorstore.chroma_store.chromadb.HttpClient")
    def test_http_mode_uses_shared_chroma_server(
        self, http_client, _embedding_generator, langchain_chroma
    ):
        client = MagicMock()
        http_client.return_value = client

        with tempfile.TemporaryDirectory() as directory:
            store = VectorStore(
                persist_directory=directory,
                client_mode="http",
                host="chroma",
                port=8000,
                ssl=False,
            )

        http_client.assert_called_once()
        kwargs = http_client.call_args.kwargs
        self.assertEqual(("chroma", 8000, False), (kwargs["host"], kwargs["port"], kwargs["ssl"]))
        # Privacy by default: the client never phones home unless opted in.
        self.assertFalse(kwargs["settings"].anonymized_telemetry)
        client.heartbeat.assert_called_once_with()
        self.assertIs(store.client, client)

        store._get_vectorstore("12")
        store._get_vectorstore("12")
        self.assertEqual(2, langchain_chroma.call_count)
        self.assertEqual({}, store._vectorstores)

    @patch("src.vectorstore.chroma_store.EmbeddingGenerator")
    def test_persistent_client_telemetry_is_off_by_default_and_opt_in(self, _embedding_generator):
        with tempfile.TemporaryDirectory() as directory:
            store = VectorStore(persist_directory=directory, client_mode="persistent")
            self.assertFalse(store.client.get_settings().anonymized_telemetry)
        with tempfile.TemporaryDirectory() as directory:
            store = VectorStore(persist_directory=directory, client_mode="persistent",
                                anonymized_telemetry=True)
            self.assertTrue(store.client.get_settings().anonymized_telemetry)

    def test_real_persistent_client_counts_and_deletes_course_chunks(self):
        with tempfile.TemporaryDirectory() as directory:
            client = chromadb.PersistentClient(path=directory, settings=_OFFLINE)
            store = _make_store(client)
            collection = client.get_or_create_collection("course_204_baai_bge_m3")
            collection.add(
                ids=["chunk-1"],
                embeddings=[[0.1, 0.2, 0.3]],
                documents=["Deployment pipeline material"],
                metadatas=[{"source": "material.pptx"}],
            )

            self.assertEqual(1, store.get_count("204"))
            self.assertTrue(store.delete_document_by_source("material.pptx", "204"))
            self.assertEqual(0, store.get_count("204"))

    def test_count_reads_existing_collection_without_listing(self):
        store = _make_store(_FakeClient(_FakeCollection(count=37)))

        self.assertEqual(37, store.get_count("204"))

    def test_count_returns_zero_only_for_missing_collection(self):
        store = _make_store(_FakeClient(missing=True))

        self.assertEqual(0, store.get_count("204"))

    def test_deleting_an_absent_source_is_not_a_warning(self):
        # Every first upload of a file first removes its previous chunks; finding
        # none is the normal path and must not raise WARNING-level noise.
        from loguru import logger

        records = []
        sink = logger.add(lambda m: records.append(m.record), level="WARNING")
        try:
            with tempfile.TemporaryDirectory() as directory:
                client = chromadb.PersistentClient(path=directory, settings=_OFFLINE)
                store = _make_store(client)
                # Collection missing entirely (first upload into a new course).
                self.assertFalse(store.delete_document_by_source("never-uploaded.pdf", "204"))
                client.get_or_create_collection("course_204_baai_bge_m3")
                # Collection present but the file was never uploaded.
                self.assertFalse(store.delete_document_by_source("never-uploaded.pdf", "204"))
        finally:
            logger.remove(sink)
        self.assertEqual([], [r["message"] for r in records])

    def test_reupload_deletes_existing_source_chunks(self):
        collection = _FakeCollection(ids=["chunk-1", "chunk-2"])
        store = _make_store(_FakeClient(collection))

        deleted = store.delete_document_by_source("material.pptx", "204")

        self.assertTrue(deleted)
        self.assertEqual(["chunk-1", "chunk-2"], collection.deleted_ids)

    def test_store_error_during_delete_is_raised_not_reported_as_nothing(self):
        # A Chroma outage must not look like "no chunks to delete" (False): the
        # DELETE route would answer 200 and the plugins would drop their retry.
        collection = _FakeCollection(ids=["chunk-1"])

        def broken_get(**kwargs):
            raise RuntimeError("chroma unavailable")

        collection.get = broken_get
        store = _make_store(_FakeClient(collection))

        with self.assertRaises(RuntimeError):
            store.delete_document_by_source("material.pptx", "204")
        self.assertEqual([], collection.deleted_ids or [])

    def test_clear_deletes_existing_collection(self):
        client = _FakeClient(_FakeCollection())
        store = _make_store(client)

        store.clear("204")

        self.assertEqual(["course_204_baai_bge_m3"], client.deleted_collections)


if __name__ == "__main__":
    unittest.main()
