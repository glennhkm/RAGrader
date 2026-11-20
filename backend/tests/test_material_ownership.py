"""Owner-scoped (material_id) vectors, against a real Chroma persistent client."""

import tempfile
import unittest
from unittest.mock import MagicMock

import chromadb
from chromadb.config import Settings as ChromaSettings
from langchain_core.documents import Document

from src.grading.grader import EssayGrader
from src.vectorstore.chroma_store import VectorStore
from src.vectorstore.filters import build_chroma_where_filter

_OFFLINE = ChromaSettings(anonymized_telemetry=False)
_COLLECTION = "course_204_baai_bge_m3"


def _store(client):
    store = VectorStore.__new__(VectorStore)
    store.client = client
    store.base_collection_name = "course_materials"
    store.current_embedding_model = "BAAI/bge-m3"
    store._vectorstores = {}
    return store


def _add(collection, ids, source, material_id=None):
    metadata = {"source": source}
    if material_id:
        metadata["material_id"] = material_id
    collection.add(
        ids=ids,
        embeddings=[[0.1, 0.2, 0.3]] * len(ids),
        documents=["text"] * len(ids),
        metadatas=[dict(metadata) for _ in ids],
    )


class MaterialOwnershipTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.client = chromadb.PersistentClient(path=self.dir.name, settings=_OFFLINE)
        self.collection = self.client.get_or_create_collection(_COLLECTION)
        self.store = _store(self.client)

    def tearDown(self):
        self.dir.cleanup()

    def _ids(self):
        return set(self.collection.get()["ids"])

    def test_same_filename_two_materials_are_isolated(self):
        _add(self.collection, ["a1", "a2"], "notes.txt", "airagmaterial:1")
        _add(self.collection, ["b1", "b2", "b3"], "notes.txt", "airagmaterial:2")

        self.assertTrue(self.store.delete_document_by_source(
            "notes.txt", "204", material_id="airagmaterial:1"))

        self.assertEqual({"b1", "b2", "b3"}, self._ids())

    def test_legacy_delete_only_touches_unowned_chunks(self):
        _add(self.collection, ["old"], "notes.txt")
        _add(self.collection, ["own"], "notes.txt", "airagmaterial:1")

        self.assertTrue(self.store.delete_document_by_source("notes.txt", "204"))

        self.assertEqual({"own"}, self._ids())

    def test_owned_delete_also_removes_legacy_chunks(self):
        _add(self.collection, ["old"], "notes.txt")
        _add(self.collection, ["own"], "notes.txt", "airagmaterial:1")
        _add(self.collection, ["other"], "notes.txt", "airagmaterial:2")

        self.store.delete_document_by_source("notes.txt", "204", material_id="airagmaterial:1")

        self.assertEqual({"other"}, self._ids())

    def test_owned_upload_replaces_legacy_chunks_of_same_source(self):
        _add(self.collection, ["old"], "notes.txt")
        grader = EssayGrader.__new__(EssayGrader)
        grader.enable_vision_captioning = False
        grader.document_loader = MagicMock()
        grader.document_loader.load_multiple_documents.return_value = {
            "documents": [Document(page_content="x", metadata={"source": "notes.txt"})],
            "images": [], "captions": [], "files_processed": ["notes.txt"], "errors": [],
        }
        chunk = Document(page_content="chunk", metadata={"source": "notes.txt"})
        grader.preprocessor = MagicMock()
        grader.preprocessor.process_multimodal_content.return_value = [chunk]
        grader.rag_pipeline = MagicMock()
        grader.rag_pipeline.vectorstore = self.store

        def add_documents(chunks, course_id=None):
            for index, item in enumerate(chunks):
                self.collection.add(
                    ids=[f"new{index}"], embeddings=[[0.1, 0.2, 0.3]],
                    documents=[item.page_content], metadatas=[item.metadata],
                )
        self.store.add_documents = add_documents
        self.store.get_count = lambda course_id=None: self.collection.count()

        from pathlib import Path
        result = grader.ingest_course_materials(
            [Path("notes.txt")], course_id="204", material_id="airagmaterial:1")

        self.assertTrue(result["success"], result)
        got = self.collection.get()
        self.assertEqual(["new0"], got["ids"])
        self.assertEqual("airagmaterial:1", got["metadatas"][0]["material_id"])

    def test_store_error_in_replace_before_add_fails_ingest_without_duplicating(self):
        _add(self.collection, ["old"], "notes.txt", "airagmaterial:1")
        grader = EssayGrader.__new__(EssayGrader)
        grader.enable_vision_captioning = False
        grader.document_loader = MagicMock()
        grader.document_loader.load_multiple_documents.return_value = {
            "documents": [Document(page_content="x", metadata={"source": "notes.txt"})],
            "images": [], "captions": [], "files_processed": ["notes.txt"], "errors": [],
        }
        grader.preprocessor = MagicMock()
        grader.preprocessor.process_multimodal_content.return_value = [
            Document(page_content="chunk", metadata={"source": "notes.txt"})]
        grader.rag_pipeline = MagicMock()
        grader.rag_pipeline.vectorstore = self.store
        added = []
        self.store.add_documents = lambda chunks, course_id=None: added.extend(chunks)

        def broken_get_collection(name):
            raise RuntimeError("chroma unavailable")

        self.store.client = MagicMock()
        self.store.client.get_collection.side_effect = broken_get_collection

        from pathlib import Path
        result = grader.ingest_course_materials(
            [Path("notes.txt")], course_id="204", material_id="airagmaterial:1")

        self.assertFalse(result["success"])
        self.assertIn("chroma unavailable", result["message"])
        self.assertEqual([], added)
        self.assertEqual({"old"}, self._ids())

    def test_where_filter_material_ids(self):
        ids = ["airagmaterial:1", "airagassign:5"]
        self.assertEqual({"material_id": {"$in": ids}}, build_chroma_where_filter(material_ids=ids))
        self.assertEqual(
            {"material_id": {"$eq": "airagmaterial:1"}},
            build_chroma_where_filter(material_ids=["airagmaterial:1"]),
        )


if __name__ == "__main__":
    unittest.main()
