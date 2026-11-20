"""Tests for namespace collection naming and Chroma metadata scope filtering."""

import hashlib
import tempfile
import unittest
from unittest.mock import patch

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from src.vectorstore.chroma_store import VectorStore
from src.vectorstore.filters import (
    build_chroma_where_filter,
    build_explicit_scope_filter,
    EmptyScopeFilterError,
    build_collection_name,
    sanitize_chunk_metadata,
)


class _DeterministicFakeEmbeddings(Embeddings):
    def embed_documents(self, texts):
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text):
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return [byte / 255.0 for byte in digest[:16]]


_FAKE_IDENTITY = {
    "embedding_provider": "fake",
    "embedding_model": "BAAI/bge-m3",
    "embedding_dimension": 16,
}


class ScopeFilteringTest(unittest.TestCase):
    def test_collection_name_preserves_moodle_format_and_bounds_arbitrary_namespaces(self):
        self.assertEqual(
            "course_204_baai_bge_m3",
            build_collection_name("course_materials", "BAAI/bge-m3", "204"),
        )
        long_ns = "University/CS-101 Fall 2026 Section A Really Long Identifier!!"
        col_name = build_collection_name("course_materials", "BAAI/bge-m3", long_ns)
        self.assertLessEqual(len(col_name), 63)
        self.assertGreaterEqual(len(col_name), 3)
        self.assertRegex(col_name, r"^[a-z0-9][a-z0-9_-]*[a-z0-9]$")

        # Punctuation and casing variants must never collapse to the same collection.
        variants = ["cs-101", "cs_101", "cs.101", "CS-101"]
        variant_cols = [
            build_collection_name("course_materials", "BAAI/bge-m3", ns)
            for ns in variants
        ]
        self.assertEqual(len(variants), len(set(variant_cols)))
        for col in variant_cols:
            self.assertLessEqual(len(col), 63)
            self.assertGreaterEqual(len(col), 3)
            self.assertRegex(col, r"^[a-z0-9][a-z0-9_-]*[a-z0-9]$")

        # Numeric v1 namespace key must not collide with Moodle numeric course_id.
        moodle_col = build_collection_name("course_materials", "BAAI/bge-m3", "12")
        v1_col = build_collection_name("course_materials", "BAAI/bge-m3", "v1:12")
        self.assertEqual("course_12_baai_bge_m3", moodle_col)
        self.assertNotEqual(moodle_col, v1_col)
        self.assertTrue(v1_col.startswith("ns_"))

        # Non-ASCII digits must not take the Moodle integer course_ branch.
        arabic_digits_col = build_collection_name("course_materials", "BAAI/bge-m3", "\u0661\u0662")
        self.assertTrue(arabic_digits_col.startswith("ns_"))
        self.assertRegex(arabic_digits_col, r"^[a-z0-9][a-z0-9_-]*[a-z0-9]$")

    def test_sanitize_chunk_metadata_flattens_scalar_tags(self):
        meta = sanitize_chunk_metadata(
            module="week-1",
            tags={
                "topic": "  OSI Model  ",
                "graded": True,
                "flag_false": False,
                "zero_int": 0,
                "blank": "   ",
                "skip_none": None,
            },
        )
        self.assertEqual(
            {
                "module": "week-1",
                "tag_topic": "OSI Model",
                "tag_graded": True,
                "tag_flag_false": False,
                "tag_zero_int": 0,
            },
            meta,
        )

    def test_build_chroma_where_filter_combinations(self):
        self.assertIsNone(build_chroma_where_filter())
        self.assertEqual(
            {"module": {"$eq": "week-1"}},
            build_chroma_where_filter(modules=["week-1"]),
        )
        self.assertEqual(
            {"module": {"$in": ["week-1", "week-2", "week-3"]}},
            build_chroma_where_filter(modules=["week-1", "week-2", "week-3"]),
        )
        self.assertEqual(
            {
                "$and": [
                    {"module": {"$in": ["week-1", "week-2"]}},
                    {"source": {"$eq": "slides.pdf"}},
                ]
            },
            build_chroma_where_filter(modules=["week-1", "week-2"], sources=["slides.pdf"]),
        )
        self.assertEqual(
            {
                "$and": [
                    {"tag_week": {"$in": [1, 2]}},
                    {"tag_graded": {"$in": [True, False]}},
                    {"tag_topic": {"$eq": "osi"}},
                ]
            },
            build_chroma_where_filter(
                tags={
                    "week": [1, 2],
                    "graded": [True, False],
                    "topic": "  osi  ",
                    "ignored_blank": "   ",
                }
            ),
        )

    def test_explicit_scope_filter_rejects_filters_that_normalize_to_nothing(self):
        # An explicitly requested scope must never silently widen to the whole
        # collection: blank values, None tags and empty lists are rejected.
        for kwargs in (
            {},
            {"modules": []},
            {"modules": ["  "], "sources": [""]},
            {"tags": {"topic": None, "week": []}},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(EmptyScopeFilterError):
                    build_explicit_scope_filter(**kwargs)

        self.assertEqual(
            {"source": {"$eq": "week-1.txt"}},
            build_explicit_scope_filter(sources=["week-1.txt", " "]),
        )

    def test_real_chroma_filters_week1_to_week3_and_excludes_week4(self):
        with tempfile.TemporaryDirectory() as tempdir:
            with patch(
                "src.vectorstore.chroma_store.EmbeddingGenerator"
            ) as mock_generator_cls:
                fake_embeddings = _DeterministicFakeEmbeddings()
                mock_generator_cls.return_value.get_embeddings_instance.return_value = (
                    fake_embeddings
                )
                mock_generator_cls.return_value.identity.return_value = _FAKE_IDENTITY
                store = VectorStore(
                    persist_directory=tempdir,
                    collection_name="course_materials",
                    embedding_model="BAAI/bge-m3",
                    client_mode="persistent",
                )

                docs = [
                    Document(
                        page_content="Week 1 TCP/IP fundamentals and network layers.",
                        metadata={"source": "week1.pdf", "page": 1, **sanitize_chunk_metadata("week-1")},
                    ),
                    Document(
                        page_content="Week 3 DNS resolution and routing protocols.",
                        metadata={"source": "week3.pdf", "page": 2, **sanitize_chunk_metadata("week-3")},
                    ),
                    Document(
                        page_content="Week 4 TLS handshake and asymmetric cryptography.",
                        metadata={"source": "week4.pdf", "page": 1, **sanitize_chunk_metadata("week-4")},
                    ),
                ]
                store.add_documents(docs, course_id="net-101")

                where = build_chroma_where_filter(modules=["week-1", "week-2", "week-3"])
                scoped = store.similarity_search(
                    "Explain TCP/IP routing and TLS handshake",
                    k=5,
                    filter=where,
                    course_id="net-101",
                )
                sources = {doc.metadata["source"] for doc in scoped}
                self.assertEqual({"week1.pdf", "week3.pdf"}, sources)
                self.assertNotIn("week4.pdf", sources)

    def test_real_chroma_filters_numeric_and_string_tags(self):
        with tempfile.TemporaryDirectory() as tempdir:
            with patch(
                "src.vectorstore.chroma_store.EmbeddingGenerator"
            ) as mock_generator_cls:
                fake_embeddings = _DeterministicFakeEmbeddings()
                mock_generator_cls.return_value.get_embeddings_instance.return_value = (
                    fake_embeddings
                )
                mock_generator_cls.return_value.identity.return_value = _FAKE_IDENTITY
                store = VectorStore(
                    persist_directory=tempdir,
                    collection_name="course_materials",
                    embedding_model="BAAI/bge-m3",
                    client_mode="persistent",
                )

                docs = [
                    Document(
                        page_content="Week 1 OSI physical and data link layers.",
                        metadata={
                            "source": "w1_osi.pdf",
                            "page": 1,
                            **sanitize_chunk_metadata(tags={"week": 1, "topic": "  osi  "}),
                        },
                    ),
                    Document(
                        page_content="Week 2 OSI network layer IP addressing.",
                        metadata={
                            "source": "w2_osi.pdf",
                            "page": 1,
                            **sanitize_chunk_metadata(tags={"week": 2, "topic": "osi"}),
                        },
                    ),
                    Document(
                        page_content="Week 3 OSI transport layer TCP/UDP.",
                        metadata={
                            "source": "w3_osi.pdf",
                            "page": 1,
                            **sanitize_chunk_metadata(tags={"week": 3, "topic": "osi"}),
                        },
                    ),
                    Document(
                        page_content="Week 1 DNS hierarchy and resolution.",
                        metadata={
                            "source": "w1_dns.pdf",
                            "page": 1,
                            **sanitize_chunk_metadata(tags={"week": 1, "topic": "dns"}),
                        },
                    ),
                ]
                store.add_documents(docs, course_id="v1:net-202")

                where = build_chroma_where_filter(tags={"week": [1, 2], "topic": "osi"})
                scoped = store.similarity_search(
                    "Explain OSI layers",
                    k=5,
                    filter=where,
                    course_id="v1:net-202",
                )
                sources = {doc.metadata["source"] for doc in scoped}
                self.assertEqual({"w1_osi.pdf", "w2_osi.pdf"}, sources)


if __name__ == "__main__":
    unittest.main()
