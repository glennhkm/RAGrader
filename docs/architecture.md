# Architecture & API Contract

## System Components

### 1. Moodle Plugins (`moodle-plugins/`)

Two complementary Moodle integration paths are included:

1. **Dedicated RAG Activity Modules (Primary)**
   - **`mod_airagmaterial`** (`moodle-plugins/mod_airagmaterial/`): Course material resource supporting `.pdf`, `.pptx`, `.docx`, and `.txt`. Uploading or updating files schedules an asynchronous Moodle adhoc task (`\mod_airagmaterial\task\vectorize_material`) so large documents are vectorized in the background via Moodle cron without timing out web requests. Deleting files or activities removes corresponding vectors from ChromaDB.
   - **`mod_airagassign`** (`moodle-plugins/mod_airagassign/`): Essay and multi-question short-answer assignment activity. Links to one or more `mod_airagmaterial` instances (plus optional reference/answer-key files), supports simple direct grading or Moodle native rubrics, queues single or bulk AI grading via adhoc tasks (`grade_submission`, `grade_all_submissions`), and enforces human-in-the-loop teacher review (`grade_review.php`) before publishing final grades to the Moodle gradebook.

2. **Standard Moodle `mod_assign` Integration**
   - **`aiprovider_rag`** (`moodle-plugins/aiprovider_rag/`): Registers the RAG provider in Moodle's `\core_ai\provider` subsystem (with a runtime reflection adapter supporting both Moodle 4.5 and 5.0+).
   - **`local_assign_ai_rag`** (`moodle-plugins/local_assign_ai_rag/`): Hooks into standard `mod_assign` settings and submissions to run RAG grading and store AI suggestions, citations, and confidence scores.

### 2. Python Backend (`backend/`)

- **HAProxy (`deploy/haproxy.cfg`)**: Exposes port `8000`, balances traffic (`leastconn`) across 1–4 FastAPI replicas (`API_REPLICAS`), and checks `/health`.
- **FastAPI Replicas (`src/api/app.py`, `src/api/moodle_routes.py`, `src/api/v1_routes.py`)**: Stateless API workers handling request validation (`request_utils.py`), optional Bearer token authentication (`auth.py`), document ingestion, and grading orchestration (`src/grading/grader.py`, `src/rag/pipeline.py`).
- **ChromaDB Server (`chroma`)**: Shared HTTP vector store (`CHROMA_CLIENT_MODE=http`) isolating collections by `course_id` (Moodle routes) or `namespace` (`/v1` routes), with metadata-scoped `where` filtering (`src/vectorstore/filters.py`).
- **Redis (`redis`)**: Coordinates per-course / per-namespace distributed read/write locks (`src/api/locking.py`) so concurrent grading requests run in parallel while upload/delete/clear mutations remain mutually exclusive per course or namespace.
- **CLI (`src/cli.py`)**: `python -m src.cli ingest | grade | grade-csv` — an HTTP client of the `/v1` API for batch/CSV grading.

### 3. Backend Internals

- **Settings layer (`src/utils/config.py`)**: the only module that reads the environment. `load_settings()` builds frozen, typed settings (LLM, embeddings, reranker, vision, prompt, locks, API, logging, CLI client) from the process environment, `backend/.env` and the env-resolved `configs/config.yaml`; invalid values raise `ConfigError` naming the variable at startup, and `repr()` masks secrets. Components receive settings by constructor injection (`get_settings()` is only their default). An AST test fails if `os.getenv`/`os.environ` appears anywhere else in `src/`.
- **App lifecycle (`src/api/app.py`, `src/api/runtime.py`)**: importing `src.api.app` has no side effects. `create_app()` registers a lifespan that sets up logging/directories and builds an `AppRuntime` (grader + lock manager) at startup — failures such as unreachable Chroma/Redis abort startup — and clears it on shutdown. `/health` returns 503 until the runtime is ready. Tests inject a runtime via `create_app(runtime=...)`.
- **Grading pipeline**: `EssayGrader` → `RAGPipeline` → `Retriever` (Chroma similarity search with `where` scope filter, optional reranker) → `PromptBuilder` (language-aware) → `LLMWrapper` → JSON parsing → `normalize_grade` (criterion totals or percentage scaled to `maximum_grade`).
- **Privacy by default**: Chroma clients are created with `anonymized_telemetry` from settings (`ANONYMIZED_TELEMETRY`, default `false`), so no deployment mode (Docker, venv, library use) reports telemetry unless explicitly enabled. Unit tests run through `tests/run_offline.py`, which fails the run on any non-local network access.
- **Embedding identity guard (`src/vectorstore/chroma_store.py`)**: collection names stay `course_{id}_{model}` / `ns_{namespace}_{hash}_{model}` for backward compatibility, and each collection records `embedding_provider`, `embedding_model` and `embedding_dimension` as metadata. Legacy collections without it are adopted after a stored-vector dimension check; a mismatch raises `EmbeddingMismatchError`, returned as **HTTP 409** so vectors from different embedding spaces are never mixed.

### 4. AI Provider Matrix

Every stage accepts any model id; catalogs in code are suggestions only. Optional local runtimes are imported lazily (`requirements-local.txt`).

| Stage | Setting | Modes |
| :--- | :--- | :--- |
| LLM (`src/rag/llm.py`) | `LLM_PROVIDER` | `provider_chain` (default; ordered fallback over `groq`, `openrouter` and `custom_<N>` endpoints with per-request and total deadlines), `openai_compatible` (`LLM_BASE_URL`, optional `LLM_API_KEY`: Ollama, vLLM, LM Studio, llama.cpp server, LiteLLM, OpenAI), `local` (in-process llama.cpp GGUF), presets `groq` / `openrouter` / `huggingface` |
| Embeddings (`src/vectorstore/embeddings.py`) | `EMBEDDING_PROVIDER` | `huggingface` (default, `HUGGINGFACE_API_TOKEN`), `openai_compatible` (`/v1/embeddings`: OpenAI, Ollama, vLLM, TEI, LiteLLM, Infinity, Jina), `local` (fastembed or sentence-transformers) |
| Reranker (`src/rag/reranker.py`) | `ENABLE_RERANKING`, `RERANKER_TYPE` | `none`, `bm25` (local lexical), `local_cross_encoder`, `http_rerank` (`/rerank`, `RERANKER_API_STYLE=cohere` or `tei`), `llm_rerank` (chat model scores passages), `pinecone` (legacy `bge`). Any reranker failure keeps the vector-search order. |
| Vision (`src/ingestion/vision_captioner.py`) | `ENABLE_VISION_CAPTIONING`, `VISION_*` | Any OpenAI-compatible multimodal endpoint; default HuggingFace Router |
| Prompt (`src/rag/prompts.py`) | `PROMPT_LANGUAGE` | `auto` (stopword detection over question + answer; inconclusive → `id`), `en`, `id`; same JSON schema in both templates |

### Grading integrity (`src/rag/grading_guard.py`)

The student answer is untrusted input and the model's citations and confidence are untrusted output. Without extra LLM calls, every grade passes these checks:

1. **Fenced answer:** the answer is wrapped in `student_answer` tags (tags inside the answer are neutralised) and the instructions that follow declare it data, not instructions.
2. **Injection signals:** instruction overrides, grade requests (English and Indonesian), chat role markup, grading JSON and fence tags in the answer are reported as `possible_prompt_injection:<signals>`.
3. **Citation grounding:** a citation is kept only if its text occurs in a retrieved chunk (normalised for case, punctuation and whitespace; `...` elisions and small wording drift allowed). Its `source` and `page` come from that chunk, not from the model. Removed citations are reported as `ungrounded_citations_removed:<n>`.
4. **Confidence cap:** any warning caps `confidence` at `0.3`, below the review thresholds, and the warnings are returned as `integrity_warnings` in every grading response.

## HTTP API Contract

When `API_AUTH_TOKEN` is set in `backend/.env`, all endpoints below except `GET /` and `GET /health` require `Authorization: Bearer <API_AUTH_TOKEN>`.

### Moodle Adapter & System Endpoints

| Method & Path | Caller | Purpose |
| :--- | :--- | :--- |
| `GET /health` | HAProxy, Docker, Admins | Readiness check (Chroma heartbeat + Redis ping) |
| `GET /moodle/status` | `local_assign_ai_rag` | Check RAG service, LLM, and vectorstore readiness |
| `GET /collections/{course_id}` | `local_assign_ai_rag`, Admins | Inspect document count for a course collection |
| `DELETE /collections/{course_id}` | Admins | Delete an entire course collection and its uploaded files |
| `POST /course/materials/upload` | `mod_airagmaterial`, `mod_airagassign`, `local_assign_ai_rag` | Upload & vectorize `.pdf`, `.pptx`, `.docx`, `.txt` into course collection; optional form field `material_id` (`^[a-z_]+:[0-9]+$`, else HTTP 400) stamps every chunk with its owner and keeps the disk copy in `uploads/course_{id}/{slug(material_id)}/` |
| `DELETE /course/materials/file` | `mod_airagmaterial`, `mod_airagassign` | Remove vector chunks for a deleted/replaced file; optional `material_id` removes that owner's chunks plus unowned legacy chunks of the file, without it only unowned chunks are removed |
| `POST /course/materials/clear` | `mod_airagmaterial`, `local_assign_ai_rag` | Clear all vectors for a course |
| `GET /course/materials/status/{course_id}` | Monitoring / Clients | Course material vectorization status |
| `POST /assign/answer` | `mod_airagassign`, `local_assign_ai_rag` | Grade a student answer with `course_id`, `question`, `essay`, `rubric`, `maximum_grade`, `assignment_id`, plus optional `source_filter`, `module_filter`, `material_ids` (owner ids, AND-ed with the other filters) and `lang` (used as the prompt language **only when sent explicitly**); the response includes `language` |

> **Scoped Retrieval in `mod_airagassign`:** When an assignment has linked vectorized `mod_airagmaterial` files or uploaded `manualfile` reference files, `mod_airagassign` automatically populates `source_filter` on `POST /assign/answer` requests (in both essay and quiz modes) so retrieval is restricted to those specific filenames. Grading fails closed: it is refused (and recorded as a retryable `grading_failed`) while **any** linked material is still pending, queued, processing or failed, so no student is graded against only part of the selected knowledge base.
>
> **Owner-scoped vectors (`material_id`):** the same filename may be uploaded by several materials, so chunks can carry a `material_id` metadata key (e.g. `airagmaterial:12`). Deleting or replacing a source only removes that owner's chunks plus legacy chunks without an owner; a delete without `material_id` never touches owned chunks. `material_ids` on `POST /assign/answer` restricts retrieval to those owners. Chroma cannot filter on a missing key, so unowned chunks are found by reading the source's chunks and checking their metadata. Not available on `/v1`. "Unowned" chunks are both pre-upgrade legacy chunks and current `local_assign_ai_rag` uploads (that plugin sends no `material_id`), so an owned upload or delete of a file with the same name in the same course also removes the local plugin's chunks of that filename.

### Generic Autograder API (`/v1`)

LMS-agnostic endpoints for namespace-isolated RAG autograding (`namespace` must match `^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$`).

| Method & Path | Request Body / Params | Purpose |
| :--- | :--- | :--- |
| `POST /v1/namespaces/{namespace}/materials` | Multipart `file`, optional form `module`, `topic`, and `tags` (JSON object) | Upload & vectorize a material file (`.pdf`, `.pptx`, `.docx`, `.txt`) into an isolated namespace with optional module/topic/tag metadata |
| `GET /v1/namespaces/{namespace}/materials` | Path param `namespace` | Inspect `collection_name`, `document_count`, `uploaded_files`, and `embedding_model` for a namespace |
| `DELETE /v1/namespaces/{namespace}/materials/{filename}` | Path params `namespace`, `filename` | Remove a single uploaded file and its vector chunks from a namespace |
| `DELETE /v1/namespaces/{namespace}` | Path param `namespace` | Delete all vectors and uploaded files for a namespace |
| `POST /v1/namespaces/{namespace}/grade` | JSON: `question`, `essay`, optional `rubric`, `maximum_grade` (default `100.0`), optional `material_filter` (`modules`, `sources`, `tags`), optional `language` (`auto`, `en`, `id`) | Grade a student answer against namespace materials, optionally scoped by `material_filter`; the response includes the `language` used |

**Errors:** `400` invalid input, `401` missing/wrong bearer token, `409` embedding configuration does not match the collection (re-ingest or restore the previous embedding setup), `413` upload too large, `503` lock timeout or shared state unavailable.

**Scope filters fail closed:** omitting `material_filter` (or sending `null`) searches every material in the namespace. A `material_filter` that is present but selects nothing (`{}`, empty lists, blank strings, `null` tag values) returns **HTTP 400** instead of silently widening retrieval to the whole namespace. The same rule applies to an explicitly sent but empty `source_filter` / `module_filter` / `material_ids` on `POST /assign/answer`.

