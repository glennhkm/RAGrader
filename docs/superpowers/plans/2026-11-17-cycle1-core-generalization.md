# Cycle 1: Core Engine Generalization, Scoped RAG & Dependency Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generalize the FastAPI RAG grading backend into a framework-agnostic `/v1/` autograding engine with metadata-scoped retrieval (supporting the "Weeks 1–3 materials → Week 4 quiz" workflow), wire linked-material filtering from `mod_airagassign`, and remove unused Python libraries from `backend/requirements.txt` while keeping all existing Moodle integrations 100% backward compatible.

**Architecture:** We split Cycle 1 into six incremental, testable units: (1) strip dead Python packages (`nltk`, `tiktoken`, `pandas`, `numpy`, `langchain-groq`) and unify Groq/OpenRouter handling onto `openai.OpenAI`; (2) add safe string-namespace collection naming and Chroma `where` metadata filter builders; (3) propagate metadata tags on ingestion and `metadata_filter` through `EssayGrader` → `RAGPipeline` → `Retriever` → `VectorStore`; (4) expose generic `/v1/namespaces/{namespace}/...` REST endpoints plus optional `source_filter`/`module_filter` on `/assign/answer`; (5) update `mod_airagassign` to send linked `airagmaterial_files` + `manualfile` filenames as `source_filter`; and (6) sync `docs/architecture.md` and run full Python + PHP + Docker + ZIP verification.

**Tech Stack:** Python 3.10+, FastAPI, Pydantic v2, ChromaDB (`0.6.3`), Redis distributed read/write locks, `openai` SDK, PHP 8.1+ (Moodle 4.5+ / 5.x plugins), Docker Compose.

**Spec:** [`docs/PRD.md`](../../PRD.md) (Sections 5–8) and [`docs/moodle-setup.md`](../../moodle-setup.md).

## Global Constraints

- Preserve 100% backward compatibility on existing Moodle routes (`/assign/answer`, `/course/materials/*`, `/collections/{course_id}`, `/moodle/status`, `/assign/status`).
- Keep ChromaDB pinned at `chromadb==0.6.3`; collection names must satisfy Chroma's 3–63 character `[a-z0-9_-]` start/end alphanumeric rule and preserve `course_{id}_{sanitized_model}` naming for integer Moodle courses.
- All Chroma metadata values stored per chunk must be scalar primitives (`str`, `int`, `float`, `bool`)—never nested dicts or lists.
- Never log student names, user IDs, or essay text to application logs.
- Every Moodle PHP change must pass `php -l` and `./scripts/build-plugins.sh` (preserving plugin root folder names and install order from `docs/moodle-setup.md`: `mod_airagmaterial` before `mod_airagassign`, `aiprovider_rag` before `local_assign_ai_rag`).
- Always run the full test command `cd backend && python -m unittest discover -s tests -v` (using the repo's Python 3.10+ environment) after every backend task.

---

### Task 1: Remove Unused Python Libraries & Unify `LLMWrapper` Client

**Files:**
- Modify: `backend/requirements.txt`
- Create: `backend/requirements-optional.txt`
- Modify: `backend/src/rag/llm.py:11,110-121,195-220,260-266,368-374`
- Create: `backend/tests/test_llm.py`

**Interfaces:**
- Consumes: `openai.OpenAI` and `LLMWrapper` in `backend/src/rag/llm.py`.
- Produces: Lean `backend/requirements.txt` without `nltk`, `tiktoken`, `pandas`, `numpy`, `langchain-groq`; `LLMWrapper(provider="groq"|"openrouter"|"provider_chain"|"huggingface")` using `openai.OpenAI` without `langchain_groq`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_llm.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
cd backend && python -m unittest tests/test_llm.py -v
```
Expected: FAIL (`AssertionError: True is not false` on `_init_groq` and `nltk` present in `requirements.txt`).

- [ ] **Step 3: Remove legacy `langchain_groq` path in `backend/src/rag/llm.py` and clean `requirements.txt`**

Edit `backend/src/rag/llm.py` to remove `from langchain_groq import ChatGroq`, `_init_groq`, and `_generate_langchain_style`:

```python
# Remove line 11:
# from langchain_groq import ChatGroq

# In generate():
    def generate(self, prompt: str) -> str:
        """
        Generate text from prompt.

        Args:
            prompt: Input prompt

        Returns:
            Generated text
        """
        try:
            if getattr(self, "_use_provider_chain", False):
                return self._generate_with_provider_chain(prompt)
            return self._generate_openai_style(prompt)
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            raise
```

Remove `_init_groq()` (lines 195–220) and `_generate_langchain_style()` (lines 368–374) from `backend/src/rag/llm.py`.

Update `backend/requirements.txt`:

```text
# Web API Server
fastapi>=0.115,<1.0
uvicorn[standard]>=0.30,<1.0
gunicorn>=22,<24
pydantic>=2.7,<3.0
pydantic-settings>=2.3,<3.0
python-multipart>=0.0.9,<1.0
python-dotenv>=1.0,<2.0
PyYAML>=6.0,<7.0
loguru>=0.7,<1.0
redis>=5.0,<6.0

# RAG & AI Subsystem
langchain>=0.3,<0.4
langchain-community>=0.3,<0.4
langchain-core>=0.3,<0.4
langchain-text-splitters>=0.3,<0.4
langchain-huggingface>=0.1,<0.4
huggingface-hub>=0.33.4,<1.0
openai>=1.50,<2.0

# Lexical Reranking (Local Fallback)
rank-bm25>=0.2,<1.0

# Vector Database
chromadb==0.6.3
# Chroma 0.x still uses the positional capture API removed in PostHog 6.
posthog>=2.4,<6.0

# Document Ingestion
pypdf>=4.0,<6.0
PyMuPDF>=1.24,<2.0
python-pptx>=0.6.23,<2.0
python-docx>=1.1,<2.0
Pillow>=10.0,<12.0
```

Create `backend/requirements-optional.txt`:

```text
# Optional cloud reranking (required only when ENABLE_RERANKING=true and RERANKER_TYPE=bge)
pinecone>=5.0,<8.0
```

- [ ] **Step 4: Run test suite to verify it passes**

Run:
```bash
cd backend && python -m unittest discover -s tests -v
```
Expected: PASS (21 tests OK).

- [ ] **Step 5: Commit**

```bash
git add backend/requirements.txt backend/requirements-optional.txt backend/src/rag/llm.py backend/tests/test_llm.py
git commit -m "chore(backend): remove unused packages and unify LLM client on openai SDK"
```

---

### Task 2: Namespace Collection Naming & Chroma Metadata Filter Builder

**Files:**
- Create: `backend/src/vectorstore/filters.py`
- Modify: `backend/src/vectorstore/chroma_store.py:84-96,174-240,308-341`
- Create: `backend/tests/test_scope_filtering.py`

**Interfaces:**
- Produces:
  - `build_collection_name(base_collection_name: str, embedding_model: str, namespace: Optional[str] = None) -> str`
  - `sanitize_chunk_metadata(module: Optional[str] = None, tags: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]`
  - `build_chroma_where_filter(modules: Optional[Sequence[str]] = None, sources: Optional[Sequence[str]] = None, tags: Optional[Mapping[str, Any]] = None) -> Optional[Dict[str, Any]]`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_scope_filtering.py`:

```python
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
    build_collection_name,
    sanitize_chunk_metadata,
)


class _DeterministicFakeEmbeddings(Embeddings):
    def embed_documents(self, texts):
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text):
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return [byte / 255.0 for byte in digest[:16]]


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

    def test_sanitize_chunk_metadata_flattens_scalar_tags(self):
        meta = sanitize_chunk_metadata(
            module="week-1",
            tags={"topic": "OSI Model", "graded": True, "skip_none": None},
        )
        self.assertEqual({"module": "week-1", "tag_topic": "OSI Model", "tag_graded": True}, meta)

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

    def test_real_chroma_filters_week1_to_week3_and_excludes_week4(self):
        with tempfile.TemporaryDirectory() as tempdir:
            with patch(
                "src.vectorstore.chroma_store.EmbeddingGenerator"
            ) as mock_generator_cls:
                fake_embeddings = _DeterministicFakeEmbeddings()
                mock_generator_cls.return_value.get_embeddings_instance.return_value = (
                    fake_embeddings
                )
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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
cd backend && python -m unittest tests/test_scope_filtering.py -v
```
Expected: FAIL (`ModuleNotFoundError: No module named 'src.vectorstore.filters'`).

- [ ] **Step 3: Implement `backend/src/vectorstore/filters.py` and wire `build_collection_name` into `chroma_store.py`**

Create `backend/src/vectorstore/filters.py`:

```python
"""Helpers for ChromaDB collection naming and metadata-scoped filtering."""

import hashlib
import re
from typing import Any, Dict, List, Mapping, Optional, Sequence


_NON_ALNUM_RE = re.compile(r"[^a-z0-9_-]+")
_COLLAPSE_UNDERSCORE_RE = re.compile(r"_+")


def _slugify(value: str) -> str:
    lowered = value.strip().lower().replace("/", "_").replace("-", "_").replace(" ", "_")
    cleaned = _NON_ALNUM_RE.sub("_", lowered)
    return _COLLAPSE_UNDERSCORE_RE.sub("_", cleaned).strip("_-")


def build_collection_name(
    base_collection_name: str,
    embedding_model: str,
    namespace: Optional[str] = None,
) -> str:
    """Build a Chroma-safe (3-63 char) collection name for a namespace + model.

    Preserves the exact ``course_{id}_{sanitized_model}`` naming used by existing
    integer Moodle course IDs while safely bounding arbitrary namespace strings.
    """
    sanitized_model = _slugify(embedding_model) or "default_model"
    if namespace is None or not str(namespace).strip():
        prefix = _slugify(base_collection_name) or "materials"
        candidate = f"{prefix}_{sanitized_model}"
    else:
        raw_ns = str(namespace).strip()
        sanitized_ns = _slugify(raw_ns) or "ns"
        if raw_ns.isdigit():
            candidate = f"course_{sanitized_ns}_{sanitized_model}"
        else:
            candidate = f"ns_{sanitized_ns}_{sanitized_model}"

    if len(candidate) <= 63:
        return candidate

    digest = hashlib.sha1(f"{namespace or ''}:{embedding_model}".encode("utf-8")).hexdigest()[:8]
    model_tail = sanitized_model[:18].strip("_-") or "model"
    ns_head = candidate[: 63 - len(model_tail) - len(digest) - 2].strip("_-") or "ns"
    return f"{ns_head}_{digest}_{model_tail}"[:63].strip("_-")


def sanitize_chunk_metadata(
    module: Optional[str] = None,
    tags: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Normalize optional module/tag metadata into Chroma scalar primitives."""
    metadata: Dict[str, Any] = {}
    if module is not None and str(module).strip():
        metadata["module"] = str(module).strip()

    if tags:
        for key, value in tags.items():
            if value is None:
                continue
            clean_key = _slugify(str(key))
            if not clean_key:
                continue
            prefixed = clean_key if clean_key.startswith("tag_") else f"tag_{clean_key}"
            if isinstance(value, (bool, int, float, str)):
                metadata[prefixed] = value
            else:
                metadata[prefixed] = str(value)
    return metadata


def _build_field_clause(field: str, values: Sequence[str]) -> Optional[Dict[str, Any]]:
    cleaned = [str(v).strip() for v in values if v is not None and str(v).strip()]
    if not cleaned:
        return None
    if len(cleaned) == 1:
        return {field: {"$eq": cleaned[0]}}
    return {field: {"$in": cleaned}}


def build_chroma_where_filter(
    modules: Optional[Sequence[str]] = None,
    sources: Optional[Sequence[str]] = None,
    tags: Optional[Mapping[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Construct a Chroma ``where`` filter dict from optional scope criteria."""
    clauses: List[Dict[str, Any]] = []

    if modules:
        clause = _build_field_clause("module", modules)
        if clause:
            clauses.append(clause)

    if sources:
        clause = _build_field_clause("source", sources)
        if clause:
            clauses.append(clause)

    if tags:
        for key, value in tags.items():
            if value is None:
                continue
            clean_key = _slugify(str(key))
            if not clean_key:
                continue
            field = clean_key if clean_key.startswith("tag_") else f"tag_{clean_key}"
            if isinstance(value, (list, tuple, set)):
                clause = _build_field_clause(field, list(value))
                if clause:
                    clauses.append(clause)
            else:
                clauses.append({field: {"$eq": value if isinstance(value, (bool, int, float)) else str(value)}})

    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}
```

Edit `backend/src/vectorstore/chroma_store.py`:

```python
# Near top imports:
from .filters import build_collection_name

# Replace _get_collection_name:
    def _get_collection_name(self, course_id: Optional[str] = None) -> str:
        """Generate a Chroma-safe collection name from embedding model and namespace."""
        return build_collection_name(
            base_collection_name=self.base_collection_name,
            embedding_model=self.current_embedding_model,
            namespace=course_id,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
cd backend && python -m unittest discover -s tests -v
```
Expected: PASS (25 tests OK, including `test_scope_filtering.py` and existing `test_chroma_store.py`).

- [ ] **Step 5: Commit**

```bash
git add backend/src/vectorstore/filters.py backend/src/vectorstore/chroma_store.py backend/tests/test_scope_filtering.py
git commit -m "feat(vectorstore): add namespace collection naming and metadata scope filter builder"
```

---

### Task 3: Propagate Metadata Tags on Ingestion & Scope Filter in Core Grading Engine

**Files:**
- Modify: `backend/src/rag/retriever.py:172-242`
- Modify: `backend/src/rag/pipeline.py:83-120`
- Modify: `backend/src/grading/grader.py:66-163,244-275`
- Create: `backend/tests/test_pipeline_scoping.py`

**Interfaces:**
- Consumes: `sanitize_chunk_metadata` from `src/vectorstore/filters.py`, `VectorStore.similarity_search(query, k, filter, course_id)`.
- Produces:
  - `EssayGrader.ingest_course_materials(file_paths, course_id=None, ..., module=None, tags=None) -> Dict[str, Any]`
  - `EssayGrader.grade_essay(question, essay, rubric, course_id=None, metadata_filter=None) -> Dict[str, Any]`
  - `RAGPipeline.grade_essay(question, essay, rubric, course_id=None, metadata_filter=None) -> Dict[str, Any]`
  - `Retriever.retrieve(query, course_id=None, metadata_filter=None) -> List[Document]`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_pipeline_scoping.py`:

```python
"""Unit tests verifying metadata propagation on ingest and filter forwarding on grading."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from langchain_core.documents import Document

from src.grading.grader import EssayGrader
from src.rag.retriever import Retriever


class PipelineScopingTest(unittest.TestCase):
    def test_retriever_forwards_metadata_filter(self):
        mock_vs = MagicMock()
        mock_vs.similarity_search.return_value = [
            Document(page_content="Evidence text", metadata={"source": "w1.pdf", "page": 1})
        ]
        retriever = Retriever(vectorstore=mock_vs, top_k=5, enable_reranking=False, rerank_top_k=3)
        where = {"module": {"$in": ["week-1", "week-2"]}}

        docs = retriever.retrieve("What is TCP?", course_id="cs101", metadata_filter=where)

        self.assertEqual(1, len(docs))
        mock_vs.similarity_search.assert_called_once_with(
            query="What is TCP?",
            k=3,
            filter=where,
            course_id="cs101",
        )

    def test_grader_attaches_module_and_tags_and_passes_filter(self):
        with tempfile.TemporaryDirectory() as tempdir:
            sample = Path(tempdir) / "week1.txt"
            sample.write_text("TCP provides reliable ordered byte delivery.", encoding="utf-8")

            with patch("src.grading.grader.RAGPipeline") as mock_pipeline_cls:
                mock_pipeline = mock_pipeline_cls.return_value
                mock_pipeline.vectorstore.get_count.return_value = 1
                mock_pipeline.grade_essay.return_value = {
                    "success": True,
                    "score": 90,
                    "feedback": "Accurate.",
                    "citations": [],
                    "confidence": 0.9,
                }

                config = {
                    "document_processing": {"chunk_size": 500, "chunk_overlap": 50, "separators": ["\n\n", "\n", " "]},
                    "llm": {"provider": "provider_chain", "model_name": "test"},
                    "multimodal": {"enable_image_extraction": False, "enable_vision_captioning": False},
                }
                grader = EssayGrader(config)

                ingest_res = grader.ingest_course_materials(
                    [sample],
                    course_id="net-101",
                    module="week-1",
                    tags={"topic": "transport"},
                )
                self.assertTrue(ingest_res["success"])
                added_docs = mock_pipeline.vectorstore.add_documents.call_args[0][0]
                self.assertEqual("week-1", added_docs[0].metadata["module"])
                self.assertEqual("transport", added_docs[0].metadata["tag_topic"])

                where = {"module": {"$eq": "week-1"}}
                grader.grade_essay(
                    question="What does TCP do?",
                    essay="Reliable delivery.",
                    rubric={},
                    course_id="net-101",
                    metadata_filter=where,
                )
                mock_pipeline.grade_essay.assert_called_once_with(
                    question="What does TCP do?",
                    essay="Reliable delivery.",
                    rubric={},
                    course_id="net-101",
                    metadata_filter=where,
                )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
cd backend && python -m unittest tests/test_pipeline_scoping.py -v
```
Expected: FAIL (`TypeError: Retriever.retrieve() got an unexpected keyword argument 'metadata_filter'`).

- [ ] **Step 3: Update `retriever.py`, `pipeline.py`, and `grader.py`**

In `backend/src/rag/retriever.py`, update `retrieve` and `retrieve_with_scores`:

```python
    def retrieve(
        self,
        query: str,
        course_id: Optional[str] = None,
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> List[Document]:
        """Retrieve relevant documents with optional metadata filter and reranking."""
        k_val = self.top_k if self.enable_reranking else self.rerank_top_k
        results = self.vectorstore.similarity_search(
            query=query,
            k=k_val,
            filter=metadata_filter,
            course_id=course_id,
        )

        if not results:
            logger.warning("No documents retrieved")
            return []

        if self.enable_reranking and len(results) > 1 and self._reranker is not None:
            results = self._reranker.rerank_documents(
                query=query,
                documents=results,
                top_k=self.rerank_top_k,
            )

        return results

    def retrieve_with_scores(
        self,
        query: str,
        course_id: Optional[str] = None,
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> List[tuple[Document, float]]:
        """Retrieve documents with relevance scores and optional metadata filter."""
        k_val = self.top_k if self.enable_reranking else self.rerank_top_k
        results = self.vectorstore.similarity_search(
            query=query,
            k=k_val,
            filter=metadata_filter,
            course_id=course_id,
        )

        if not results:
            logger.warning("No documents retrieved")
            return []

        if self.enable_reranking and len(results) > 1 and self._reranker is not None:
            results_with_scores = self._reranker.rerank(
                query=query,
                documents=results,
                top_k=self.rerank_top_k,
            )
            logger.info(f"Retrieved and reranked {len(results_with_scores)} documents with scores")
            return results_with_scores

        results_with_scores = [(doc, 1.0) for doc in results]
        logger.info(f"Retrieved {len(results_with_scores)} documents")
        return results_with_scores
```

In `backend/src/rag/pipeline.py`, update `grade_essay`:

```python
    def grade_essay(
        self,
        question: str,
        essay: str,
        rubric: Dict[str, Any],
        course_id: Optional[str] = None,
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Grade an essay using RAG pipeline with optional namespace and metadata filter."""
        logger.info("Starting essay grading with question context...")

        try:
            logger.info("Retrieving relevant course materials...")
            query = f"Pertanyaan: {question}\n\nJawaban: {essay}"
            retrieved_docs = self.retriever.retrieve(
                query,
                course_id=course_id,
                metadata_filter=metadata_filter,
            )

            if not retrieved_docs:
                logger.warning("No relevant materials found within scope")
                return {
                    "success": False,
                    "score": 0,
                    "feedback": "Cannot grade: no relevant course materials found in the selected scope.",
                    "citations": [],
                    "confidence": 0.0,
                    "retrieved_documents": [],
                    "error": "No relevant materials retrieved",
                }
```

In `backend/src/grading/grader.py`, import `sanitize_chunk_metadata` from `..vectorstore.filters`, add `module: Optional[str] = None` and `tags: Optional[Dict[str, Any]] = None` to `ingest_course_materials` (applying them to each chunk before `add_documents`), and add `metadata_filter: Optional[Dict[str, Any]] = None` to `grade_essay`:

```python
# In imports:
from ..vectorstore.filters import sanitize_chunk_metadata

# In ingest_course_materials signature:
    def ingest_course_materials(
        self,
        file_paths: List[Path],
        course_id: Optional[str] = None,
        progress_callback: Callable = None,
        enable_vision: bool = None,
        vision_model: str = None,
        module: Optional[str] = None,
        tags: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:

# Before delete_document_by_source / add_documents:
            extra_meta = sanitize_chunk_metadata(module=module, tags=tags)
            if chunks and extra_meta:
                for chunk in chunks:
                    chunk.metadata.update(extra_meta)

# In grade_essay:
    def grade_essay(
        self,
        question: str,
        essay: str,
        rubric: Dict[str, Any],
        course_id: Optional[str] = None,
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Grade a student essay with optional course/namespace and metadata scope filter."""
        return self.rag_pipeline.grade_essay(
            question=question,
            essay=essay,
            rubric=rubric,
            course_id=course_id,
            metadata_filter=metadata_filter,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
cd backend && python -m unittest discover -s tests -v
```
Expected: PASS (27 tests OK).

- [ ] **Step 5: Commit**

```bash
git add backend/src/rag/retriever.py backend/src/rag/pipeline.py backend/src/grading/grader.py backend/tests/test_pipeline_scoping.py
git commit -m "feat(rag): propagate metadata tags on ingestion and scope filters on retrieval"
```

---

### Task 4: Generic `/v1/namespaces/{namespace}/*` API & Moodle Filter Adapter

**Files:**
- Create: `backend/src/api/v1_models.py`
- Create: `backend/src/api/v1_routes.py`
- Modify: `backend/src/api/moodle_models.py:31-35`
- Modify: `backend/src/api/moodle_routes.py:23-31,109-120`
- Modify: `backend/src/api/app.py:31-35,68-71`
- Create: `backend/tests/test_v1_endpoints.py`
- Modify: `backend/tests/test_moodle_endpoints.py`

**Interfaces:**
- Consumes: `EssayGrader.ingest_course_materials`, `EssayGrader.grade_essay`, `build_chroma_where_filter`, `OperationLockManager`, `safe_filename`, `validate_material_filename`, `save_upload`, `normalize_grade`, `optional_page`.
- Produces:
  - `POST /v1/namespaces/{namespace}/materials`
  - `GET /v1/namespaces/{namespace}/materials`
  - `DELETE /v1/namespaces/{namespace}/materials/{filename}`
  - `DELETE /v1/namespaces/{namespace}`
  - `POST /v1/namespaces/{namespace}/grade`
  - `MoodleAssignRequest.source_filter` & `MoodleAssignRequest.module_filter` wired into `/assign/answer`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_v1_endpoints.py`:

```python
"""Contract tests for generic /v1/namespaces/* autograding endpoints."""

import json
import tempfile
import unittest
from pathlib import Path
from threading import RLock
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.v1_routes import router as v1_router


class _FakePipeline:
    current_embedding_model = "BAAI/bge-m3"

    def get_vectorstore_info(self, course_id=None):
        return {"collection_name": f"ns_{course_id}", "document_count": 4}


class _FakeGrader:
    def __init__(self):
        self.rag_pipeline = _FakePipeline()
        self.last_ingest_kwargs = None
        self.last_grade_kwargs = None

    def ingest_course_materials(self, paths, **kwargs):
        self.last_ingest_kwargs = {"paths": paths, **kwargs}
        return {"success": True, "documents_loaded": 1, "chunks_created": 4, "errors": []}

    def grade_essay(self, **kwargs):
        self.last_grade_kwargs = kwargs
        return {
            "success": True,
            "score": 85,
            "feedback": "Grounded answer.",
            "criterion_scores": {},
            "citations": [{"text": "TCP ensures delivery", "source": "week1.pdf", "page": 1}],
            "confidence": 0.91,
            "retrieved_documents": [],
        }

    def delete_course_material_file(self, course_id, filename):
        return True

    def clear_vector_store(self, course_id=None):
        return None


class V1EndpointTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.fake_grader = _FakeGrader()
        app = FastAPI()
        app.include_router(v1_router)
        self.client = TestClient(app)

        self.p1 = patch("src.api.v1_routes.get_grader", return_value=self.fake_grader)
        self.p2 = patch("src.api.v1_routes.get_operation_lock", return_value=RLock())
        self.p3 = patch("src.utils.DATA_DIR", Path(self.tempdir.name))
        self.p1.start()
        self.p2.start()
        self.p3.start()

    def tearDown(self):
        self.p3.stop()
        self.p2.stop()
        self.p1.stop()
        self.tempdir.cleanup()

    def test_upload_with_module_and_tags_then_grade_with_scope_filter(self):
        upload_resp = self.client.post(
            "/v1/namespaces/cs-101/materials",
            data={"module": "week-1", "tags": json.dumps({"topic": "networking"})},
            files={"file": ("week1.txt", b"TCP three-way handshake", "text/plain")},
        )
        self.assertEqual(200, upload_resp.status_code)
        self.assertTrue(upload_resp.json()["success"])
        self.assertEqual("cs-101", self.fake_grader.last_ingest_kwargs["course_id"])
        self.assertEqual("week-1", self.fake_grader.last_ingest_kwargs["module"])
        self.assertEqual({"topic": "networking"}, self.fake_grader.last_ingest_kwargs["tags"])

        grade_resp = self.client.post(
            "/v1/namespaces/cs-101/grade",
            json={
                "question": "Explain TCP handshake",
                "essay": "It uses SYN, SYN-ACK, ACK.",
                "maximum_grade": 20,
                "material_filter": {"modules": ["week-1", "week-2", "week-3"]},
            },
        )
        self.assertEqual(200, grade_resp.status_code)
        body = grade_resp.json()
        self.assertTrue(body["success"])
        self.assertEqual(17.0, body["score"])
        self.assertEqual(
            {"module": {"$in": ["week-1", "week-2", "week-3"]}},
            self.fake_grader.last_grade_kwargs["metadata_filter"],
        )

    def test_list_delete_file_and_clear_namespace(self):
        self.client.post(
            "/v1/namespaces/bio-101/materials",
            files={"file": ("cells.txt", b"Mitochondria", "text/plain")},
        )
        listing = self.client.get("/v1/namespaces/bio-101/materials")
        self.assertEqual(200, listing.status_code)
        self.assertEqual(["cells.txt"], listing.json()["uploaded_files"])

        delete_file = self.client.delete("/v1/namespaces/bio-101/materials/cells.txt")
        self.assertEqual(200, delete_file.status_code)
        self.assertTrue(delete_file.json()["success"])

        clear_ns = self.client.delete("/v1/namespaces/bio-101")
        self.assertEqual(200, clear_ns.status_code)
        self.assertTrue(clear_ns.json()["success"])


if __name__ == "__main__":
    unittest.main()
```

Also add a test method to `backend/tests/test_moodle_endpoints.py` verifying `source_filter` passes through `/assign/answer`:

```python
    def test_grading_contract_forwards_source_filter(self):
        with patch.object(self.fake_grader, "grade_essay", wraps=self.fake_grader.grade_essay) as spy:
            response = moodle_grade_assignment(
                MoodleAssignRequest(**{
                    "course_id": 12,
                    "question": "Question",
                    "essay": "Student answer",
                    "rubric": {},
                    "maximum_grade": 100,
                    "assignment_id": 45,
                    "source_filter": ["week1.pdf", "week2.pptx"],
                })
            )
        self.assertTrue(response.success)
        self.assertEqual(
            {"source": {"$in": ["week1.pdf", "week2.pptx"]}},
            spy.call_args.kwargs["metadata_filter"],
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd backend && python -m unittest tests/test_v1_endpoints.py tests/test_moodle_endpoints.py -v
```
Expected: FAIL (`ModuleNotFoundError: No module named 'src.api.v1_routes'`).

- [ ] **Step 3: Implement `v1_models.py`, `v1_routes.py`, update `moodle_models.py`, `moodle_routes.py`, and wire `v1_router` in `app.py`**

Create `backend/src/api/v1_models.py`:

```python
"""Pydantic models for generic /v1/ namespace-scoped autograding endpoints."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class V1MaterialFilter(BaseModel):
    """Optional retrieval scope filter (e.g., Weeks 1-3 modules or specific filenames)."""

    modules: List[str] = Field(default_factory=list, description="Restrict retrieval to these module/week tags")
    sources: List[str] = Field(default_factory=list, description="Restrict retrieval to these filenames")
    tags: Dict[str, Any] = Field(default_factory=dict, description="Additional scalar tag filters")


class V1GradeRequest(BaseModel):
    """Generic autograding request supporting optional rubric and material scope filtering."""

    question: str = Field(..., min_length=1, description="Quiz/assignment question prompt")
    essay: str = Field(..., min_length=1, description="Student answer text")
    rubric: Dict[str, Any] = Field(default_factory=dict, description="Optional rubric criteria dictionary")
    maximum_grade: float = Field(default=100.0, gt=0, le=10000, description="Maximum grade scale")
    material_filter: Optional[V1MaterialFilter] = Field(
        default=None,
        description="Optional scope filter limiting retrieval to selected modules, filenames, or tags",
    )


class V1CriterionScore(BaseModel):
    score: float
    feedback: str = ""
    evidence: Optional[str] = None


class V1Citation(BaseModel):
    text: str
    source: str = "Unknown"
    page: Optional[int] = None


class V1RetrievedDoc(BaseModel):
    content: str
    source: str = "Unknown"
    page: Any = None


class V1GradeResponse(BaseModel):
    success: bool = True
    namespace: str
    score: float = 0.0
    feedback: str = ""
    criterion_scores: Dict[str, V1CriterionScore] = Field(default_factory=dict)
    citations: List[V1Citation] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    retrieved_documents: List[V1RetrievedDoc] = Field(default_factory=list)
    error: Optional[str] = None


class V1UploadResponse(BaseModel):
    success: bool
    message: str
    namespace: str
    filename: str
    module: Optional[str] = None
    tags: Dict[str, Any] = Field(default_factory=dict)
    chunk_count: int = 0
    documents_loaded: int = 0


class V1NamespaceInfoResponse(BaseModel):
    success: bool
    namespace: str
    collection_name: str
    document_count: int = 0
    uploaded_files: List[str] = Field(default_factory=list)
    embedding_model: str = ""


class V1DeleteResponse(BaseModel):
    success: bool
    message: str
    namespace: str
    filename: Optional[str] = None
```

Create `backend/src/api/v1_routes.py`:

```python
"""Generic LMS-agnostic /v1/ endpoints for namespace-isolated RAG autograding."""

import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, File, Form, HTTPException, Path as PathParam, UploadFile
from loguru import logger

from ..vectorstore.filters import build_chroma_where_filter
from .locking import LockAcquisitionError
from .request_utils import normalize_grade, optional_page, safe_filename, save_upload, validate_material_filename
from .v1_models import (
    V1Citation,
    V1CriterionScore,
    V1DeleteResponse,
    V1GradeRequest,
    V1GradeResponse,
    V1NamespaceInfoResponse,
    V1RetrievedDoc,
    V1UploadResponse,
)

router = APIRouter(prefix="/v1", tags=["Generic Autograder API v1"])
NAMESPACE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def get_grader():
    from .app import grader
    return grader


def get_operation_lock(namespace: str, write: bool = False):
    from .app import operation_locks
    resource = f"namespace:{namespace}"
    return operation_locks.write(resource) if write else operation_locks.read(resource)


def _validate_namespace(namespace: str) -> str:
    cleaned = (namespace or "").strip()
    if not NAMESPACE_PATTERN.fullmatch(cleaned):
        raise HTTPException(
            status_code=400,
            detail="Invalid namespace. Use 1-128 alphanumeric, '.', '_', or '-' characters.",
        )
    return cleaned


def _namespace_upload_dir(data_dir: Path, namespace: str) -> Path:
    digest = hashlib.sha1(namespace.encode("utf-8")).hexdigest()[:8]
    safe_prefix = re.sub(r"[^A-Za-z0-9_-]", "_", namespace)[:40].strip("_") or "ns"
    return data_dir / "uploads" / f"ns_{safe_prefix}_{digest}"


def _parse_tags_json(raw_tags: str) -> Dict[str, Any]:
    if not raw_tags or not raw_tags.strip():
        return {}
    try:
        parsed = json.loads(raw_tags)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid tags JSON: {exc.msg}") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="tags must be a JSON object")
    return parsed


@router.post("/namespaces/{namespace}/materials", response_model=V1UploadResponse)
def upload_namespace_material(
    namespace: str = PathParam(...),
    file: UploadFile = File(...),
    module: Optional[str] = Form(default=None),
    tags: str = Form(default=""),
):
    """Upload and index a material file into an isolated namespace with optional module/tags."""
    ns = _validate_namespace(namespace)
    filename = validate_material_filename(file.filename)
    parsed_tags = _parse_tags_json(tags)

    try:
        grader = get_grader()
        with get_operation_lock(ns, write=True):
            from ..utils import DATA_DIR

            upload_dir = _namespace_upload_dir(DATA_DIR, ns)
            upload_dir.mkdir(parents=True, exist_ok=True)
            file_path = upload_dir / filename
            save_upload(file, file_path)

            result = grader.ingest_course_materials(
                [file_path],
                course_id=ns,
                module=module,
                tags=parsed_tags,
            )

        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("message", "Ingestion failed"))

        return V1UploadResponse(
            success=True,
            message=f"Successfully indexed {filename}",
            namespace=ns,
            filename=filename,
            module=module,
            tags=parsed_tags,
            chunk_count=int(result.get("chunks_created", 0)),
            documents_loaded=int(result.get("documents_loaded", 0)),
        )
    except LockAcquisitionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/namespaces/{namespace}/materials", response_model=V1NamespaceInfoResponse)
def get_namespace_materials(namespace: str = PathParam(...)):
    """Inspect indexed chunk count and uploaded filenames for a namespace."""
    ns = _validate_namespace(namespace)
    try:
        grader = get_grader()
        with get_operation_lock(ns, write=False):
            vs_info = grader.rag_pipeline.get_vectorstore_info(ns)
            from ..utils import DATA_DIR

            upload_dir = _namespace_upload_dir(DATA_DIR, ns)
            files = sorted(f.name for f in upload_dir.iterdir() if f.is_file()) if upload_dir.exists() else []

        return V1NamespaceInfoResponse(
            success=True,
            namespace=ns,
            collection_name=vs_info.get("collection_name", ""),
            document_count=int(vs_info.get("document_count", 0)),
            uploaded_files=files,
            embedding_model=getattr(grader.rag_pipeline, "current_embedding_model", ""),
        )
    except LockAcquisitionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.delete("/namespaces/{namespace}/materials/{filename}", response_model=V1DeleteResponse)
def delete_namespace_material_file(
    namespace: str = PathParam(...),
    filename: str = PathParam(...),
):
    """Remove a single uploaded file and its vector chunks from a namespace."""
    ns = _validate_namespace(namespace)
    clean_name = safe_filename(filename)
    try:
        grader = get_grader()
        with get_operation_lock(ns, write=True):
            deleted = grader.delete_course_material_file(ns, clean_name)
            from ..utils import DATA_DIR

            file_path = _namespace_upload_dir(DATA_DIR, ns) / clean_name
            if file_path.exists():
                file_path.unlink()

        return V1DeleteResponse(
            success=bool(deleted),
            message=f"Deleted '{clean_name}'" if deleted else f"No vectors found for '{clean_name}'",
            namespace=ns,
            filename=clean_name,
        )
    except LockAcquisitionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.delete("/namespaces/{namespace}", response_model=V1DeleteResponse)
def clear_namespace(namespace: str = PathParam(...)):
    """Delete all vectors and uploaded files for a namespace."""
    ns = _validate_namespace(namespace)
    try:
        grader = get_grader()
        with get_operation_lock(ns, write=True):
            grader.clear_vector_store(ns)
            from ..utils import DATA_DIR

            upload_dir = _namespace_upload_dir(DATA_DIR, ns)
            if upload_dir.exists():
                shutil.rmtree(upload_dir)

        return V1DeleteResponse(
            success=True,
            message=f"Cleared namespace '{ns}'",
            namespace=ns,
        )
    except LockAcquisitionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/namespaces/{namespace}/grade", response_model=V1GradeResponse)
def grade_in_namespace(
    request: V1GradeRequest,
    namespace: str = PathParam(...),
):
    """Grade one student answer against scoped materials in a namespace."""
    ns = _validate_namespace(namespace)
    if not request.question.strip() or not request.essay.strip():
        raise HTTPException(status_code=400, detail="Question and essay must be non-empty")

    where_filter = None
    if request.material_filter is not None:
        where_filter = build_chroma_where_filter(
            modules=request.material_filter.modules,
            sources=request.material_filter.sources,
            tags=request.material_filter.tags,
        )

    try:
        grader = get_grader()
        rubric = request.rubric if request.rubric else {"criteria": {}}
        with get_operation_lock(ns, write=False):
            result = grader.grade_essay(
                question=request.question,
                essay=request.essay,
                rubric=rubric,
                course_id=ns,
                metadata_filter=where_filter,
            )

        if not result.get("success", True) and result.get("error"):
            return V1GradeResponse(
                success=False,
                namespace=ns,
                score=0.0,
                feedback=str(result.get("feedback", "Grading failed")),
                error=str(result.get("error")),
            )

        scaled_score, normalized_criteria, confidence = normalize_grade(
            result=result,
            rubric=rubric,
            maximum_grade=request.maximum_grade,
        )
        logger.info(f"v1 grading complete namespace={ns} score={scaled_score:.1f}/{request.maximum_grade}")

        return V1GradeResponse(
            success=True,
            namespace=ns,
            score=scaled_score,
            feedback=str(result.get("feedback", "")),
            criterion_scores={name: V1CriterionScore(**data) for name, data in normalized_criteria.items()},
            citations=[
                V1Citation(
                    text=str(c.get("text", "")),
                    source=str(c.get("source", "Unknown")),
                    page=optional_page(c.get("page")),
                )
                for c in (result.get("citations") or [])
                if isinstance(c, dict)
            ],
            confidence=confidence,
            retrieved_documents=[
                V1RetrievedDoc(
                    content=str(d.get("content", "")),
                    source=str(d.get("source", "Unknown")),
                    page=d.get("page"),
                )
                for d in (result.get("retrieved_documents") or [])
                if isinstance(d, dict)
            ],
        )
    except LockAcquisitionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
```

Update `backend/src/api/moodle_models.py` (`MoodleAssignRequest`):

```python
    # Additional metadata
    cmi_id: int = Field(default=0, description="Course module ID")
    lang: str = Field(default="en", description="Language code")
    moodle_site_id: str = Field(default="", description="Moodle site identifier")
    source_filter: Optional[List[str]] = Field(
        default=None,
        description="Optional list of linked material filenames to scope retrieval",
    )
    module_filter: Optional[List[str]] = Field(
        default=None,
        description="Optional list of module/week tags to scope retrieval",
    )
```

Update `backend/src/api/moodle_routes.py`:

```python
from ..vectorstore.filters import build_chroma_where_filter

# Inside moodle_grade_assignment():
        rubric = request.rubric if request.rubric else {"criteria": {}}
        metadata_filter = build_chroma_where_filter(
            modules=request.module_filter,
            sources=request.source_filter,
        )
        with get_operation_lock(request.course_id):
            result = grader.grade_essay(
                question=request.question,
                essay=request.essay,
                rubric=rubric,
                course_id=str(request.course_id),
                metadata_filter=metadata_filter,
            )
```

Update `backend/src/api/app.py`:

```python
from .moodle_routes import router as moodle_router
from .v1_routes import router as v1_router
...
app.include_router(moodle_router)
app.include_router(v1_router)
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
cd backend && python -m unittest discover -s tests -v
```
Expected: PASS (30 tests OK).

- [ ] **Step 5: Commit**

```bash
git add backend/src/api/v1_models.py backend/src/api/v1_routes.py backend/src/api/moodle_models.py backend/src/api/moodle_routes.py backend/src/api/app.py backend/tests/test_v1_endpoints.py backend/tests/test_moodle_endpoints.py
git commit -m "feat(api): add generic /v1/namespaces endpoints and Moodle source_filter support"
```

---

### Task 5: Pass Linked Material Filenames as `source_filter` from `mod_airagassign`

**Files:**
- Modify: `moodle-plugins/mod_airagassign/lib.php:669-691,727-765,820-837`

**Interfaces:**
- Consumes: `{airagassign_materials}`, `{airagmaterial_files}`, `airagassign_get_uploaded_files($contextid)` in `moodle-plugins/mod_airagassign/lib.php`, `/assign/answer` accepting optional `source_filter`.
- Produces: `airagassign_get_linked_material_filenames(int $assignid, int $contextid): array` and `source_filter` in grading payloads when linked/manual files exist.

- [ ] **Step 1: Add `airagassign_get_linked_material_filenames` helper and wire `source_filter` in `lib.php`**

Inspect `moodle-plugins/mod_airagassign/lib.php` around lines 660–840, then add the helper and pass `'source_filter'` when non-empty:

```php
/**
 * Collect linked airagmaterial filenames and manual reference filenames for scoped RAG retrieval.
 *
 * @param int $assignid Assignment instance ID
 * @param int $contextid Module context ID
 * @return array List of unique material basenames
 */
function airagassign_get_linked_material_filenames(int $assignid, int $contextid): array {
    global $DB;

    $filenames = [];
    $sql = "SELECT DISTINCT af.filename
              FROM {airagassign_materials} aam
              JOIN {airagmaterial_files} af ON af.materialid = aam.materialid
             WHERE aam.assignid = :assignid
               AND af.status = 'completed'";
    $records = $DB->get_records_sql($sql, ['assignid' => $assignid]);
    foreach ($records as $record) {
        if (!empty($record->filename)) {
            $filenames[$record->filename] = true;
        }
    }

    foreach (airagassign_get_uploaded_files($contextid) as $file) {
        $name = $file->get_filename();
        if ($name !== '' && $name !== '.') {
            $filenames[$name] = true;
        }
    }

    return array_keys($filenames);
}
```

Pass `$sourcefilter = airagassign_get_linked_material_filenames((int)$assign->id, (int)$context->id);` into `airagassign_grade_quiz_submission($assign, $submission, $rubric, $serverurl, $sourcefilter)` and `airagassign_grade_essay_submission($assign, $submission, $rubric, $serverurl, $sourcefilter)`:

```php
        $payload = [
            'course_id' => $assign->course,
            'question' => $question->questiontext, // or $assign->essayprompt in essay mode
            'essay' => $answer->answertext,
            'rubric' => $rubric,
            'maximum_grade' => $gradeperquestion, // or (float)$assign->maximumgrade in essay mode
            'assignment_id' => $assign->id,
        ];
        if (!empty($sourcefilter)) {
            $payload['source_filter'] = array_values($sourcefilter);
        }
        $result = airagassign_call_rag_api($serverurl, $payload);
```

- [ ] **Step 2: Run PHP syntax lint and ZIP build**

Run:
```bash
make lint-php
./scripts/build-plugins.sh
```
Expected: All PHP files report `No syntax errors detected`, and all 4 ZIP packages build cleanly into `dist/`.

- [ ] **Step 3: Commit**

```bash
git add moodle-plugins/mod_airagassign/lib.php
git commit -m "feat(moodle): pass linked airagmaterial filenames as source_filter to /assign/answer"
```

---

### Task 6: Update Architecture Docs & Run End-to-End Cycle 1 Verification

**Files:**
- Modify: `docs/architecture.md`

**Interfaces:**
- Documents `/v1/namespaces/{namespace}/*` endpoints alongside existing Moodle adapter routes and verifies `docs/moodle-setup.md` install order remains accurate.

- [ ] **Step 1: Update `docs/architecture.md` with the `/v1/` API table**

Add a `Generic Autograder API (/v1)` table in `docs/architecture.md` documenting:
- `POST /v1/namespaces/{namespace}/materials` (multipart `file`, optional `module`, optional `tags` JSON)
- `GET /v1/namespaces/{namespace}/materials`
- `DELETE /v1/namespaces/{namespace}/materials/{filename}`
- `DELETE /v1/namespaces/{namespace}`
- `POST /v1/namespaces/{namespace}/grade` (`question`, `essay`, optional `rubric`, `maximum_grade`, optional `material_filter`)

And note that `mod_airagassign` now sends `source_filter` to `/assign/answer` when linked `mod_airagmaterial` files or `manualfile` exist.

- [ ] **Step 2: Run full Cycle 1 verification suite**

Run:
```bash
cd backend && python -m unittest discover -s tests -v
python -m compileall -q backend/src
make lint-php
./scripts/build-plugins.sh
(cd backend && cp .env.example .env && docker compose config --quiet && rm -f .env)
```
Expected:
- All 30+ backend unit tests PASS.
- `compileall` exits `0`.
- `make lint-php` exits `0`.
- `./scripts/build-plugins.sh` outputs all 4 ZIP archives (`airagassign.zip`, `airagmaterial.zip`, `local_assign_ai_rag.zip`, `aiprovider_rag.zip`).
- `docker compose config --quiet` exits `0`.

- [ ] **Step 3: Commit**

```bash
git add docs/architecture.md
git commit -m "docs: document generic /v1/ namespace API and scoped material filtering"
```

