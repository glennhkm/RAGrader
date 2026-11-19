# Cycle 2: Universal Model Freedom, Config Centralization, Multi-Language Prompt & Quickstart Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove every mandatory cloud dependency from the RAG grading backend so it runs on *any* OpenAI-compatible platform or fully local runtime across all AI stages (LLM, embeddings, reranker, optional vision), centralize configuration into one typed settings layer, make app startup side-effect free (`create_app()` + lifespan), add a language-aware grading prompt (`PROMPT_LANGUAGE=auto|en|id`), and ship a 10-minute quickstart (dev compose, sample "Week 1–3 → Week 4" kit, CLI batch grader) — while keeping every existing Moodle deployment working unchanged.

**Spec:** [`docs/PRD.md`](../../PRD.md) §6.1 items 4–7, §7 (provider matrix), §8 Cycle 2 row. Builds on Cycle 1 ([`2026-11-17-cycle1-core-generalization.md`](2026-11-17-cycle1-core-generalization.md)), merged into `main` at `102ceb8`.

**Branch:** `feat/cycle2-model-freedom-config` (from `main`).

**Tech Stack:** Python 3.10+, FastAPI (lifespan), Pydantic v2, `openai` SDK (chat + embeddings), `httpx` (rerank HTTP + CLI), ChromaDB `0.6.3`, optional `fastembed` / `sentence-transformers` / `llama-cpp-python` (local extras), Docker Compose.

---

## Done Criteria (from PRD §8, made testable)

1. Backend boots and **all unit tests pass with no `HUGGINGFACE_API_TOKEN`, `GROQ_API_KEY`, `OPENROUTER_API_KEY`, or `PINECONE_API_KEY` set** when configured for an OpenAI-compatible endpoint or local mode.
2. Mocked tests cover every provider mode of all three stages (LLM, embedding, reranker) plus vision; no test touches the network.
3. `grep -rn "os.getenv\|os.environ" backend/src` matches only `src/utils/config.py`.
4. `import src.api.app` constructs no grader, vector store, Redis client, or LLM client (verified by test).
5. English question/answer → English feedback prompt; Indonesian → Indonesian; JSON schema identical in both.
6. Quickstart (`docker-compose.dev.yml` + `examples/week1_to_week4_quiz/`) ingests Week 1–3 and grades Week 4 answers end-to-end following the README.
7. Existing Moodle routes, payloads, collection names (`course_{id}_{model}`), and current `.env` files keep working with **zero changes** (backward-compatibility tests).

## Global Constraints

- **Backward compatibility is non-negotiable.** Defaults reproduce today's behavior: `LLM_PROVIDER=provider_chain` (Groq → OpenRouter), `EMBEDDING_PROVIDER=huggingface`, `RERANKER_TYPE=bge` (alias of `pinecone`), Chroma collection naming from `build_collection_name()` unchanged. Every currently documented env var keeps its meaning.
- **No model allow-lists.** Provider classes accept any model string; `PROVIDERS` / `EMBEDDING_MODELS` / `VISION_MODELS` / `RERANKER_MODELS` dicts become documentation hints only.
- **Optional heavy deps are imported lazily** inside the provider that needs them, with an actionable error naming the extra (`pip install -r requirements-local.txt`). Core `requirements.txt` gains only `httpx` (declared because it becomes a direct import).
- **No network in tests.** Use injectable client factories, `httpx.MockTransport`, and fake modules in `sys.modules`.
- **Never log secrets, student identity, or essay text.** Settings `__repr__` must mask API keys.
- Keep `chromadb==0.6.3`. Keep the Cycle 1 rules (scalar chunk metadata, PHP lint, ZIP build) green.
- After every task: `cd backend && python -m unittest discover -s tests -v` and `python -m compileall -q src`.
- One commit per task, Conventional Commits, ending with the project's `Co-Authored-By` trailer.

## Key Design Decisions

| Decision | Choice | Why |
| :--- | :--- | :--- |
| Settings library | Frozen `dataclasses` + small typed env parsers in `src/utils/config.py` | `pydantic-settings` was removed in Cycle 1; dataclasses keep deps lean and are trivially overridable in tests. |
| Settings precedence | process env → `backend/.env` (via `load_dotenv`, never overriding real env) → `configs/config.yaml` defaults → code defaults | Matches today's `${VAR:default}` YAML behavior; YAML stays the documented knob file. |
| Settings access | `get_settings()` (cached) + `reset_settings()` / `override_settings(**kw)` context manager for tests; components take settings **by constructor injection** with `get_settings()` only as default | Removes hidden global reads; makes every provider unit-testable. |
| App lifecycle | `create_app(runtime: AppRuntime \| None = None)`; FastAPI lifespan builds `AppRuntime(grader, operation_locks)` only when not injected; `src/api/runtime.py` holds the active runtime; module-level `app = create_app()` kept for `gunicorn src.api.app:app` | Import becomes side-effect free; existing `get_grader()` / `get_operation_lock()` helpers keep their names and signatures so router tests that patch them stay valid. |
| Embedding/vector safety | Keep collection **name** unchanged; store `{embedding_provider, embedding_model, embedding_dimension}` in Chroma collection metadata on create and verify on every open; mismatch → clear `EmbeddingMismatchError` (HTTP 409 on API) | Changing the naming scheme would orphan every existing Moodle collection; the metadata guard catches provider/dimension switches instead of silently mixing vector spaces. Legacy collections without metadata are adopted (metadata written once). |
| OpenAI-compatible embeddings | Own `OpenAICompatibleEmbeddings(langchain_core.embeddings.Embeddings)` on the `openai` SDK | Avoids adding `langchain-openai`; same SDK as the LLM path. |
| Rerank HTTP contract | `RERANKER_API_STYLE=cohere` (default: `{model, query, documents, top_n}` → `results[].{index, relevance_score}`; Jina/Cohere/vLLM/Infinity/SiliconFlow) or `tei` (`{query, texts}` → `[{index, score}]`) | The two dominant `/rerank` dialects; parser accepts both response shapes defensively. |
| Reranker failure policy | Any reranker error → log + fall back to original vector order (never fail grading) | Same as today's Pinecone behavior. |
| Language detection (`auto`) | Dependency-free stopword-ratio heuristic over question + answer (`id` vs `en`); inconclusive input (fewer than two marker words, or a tie) falls back to `id` | Deterministic, testable, no new package; the `id` fallback keeps today's behavior for short answers (implementation decision in Task 9, overriding the earlier `en` default to honor the backward-compatibility constraint). |
| Moodle `lang` field | Used as an override **only if explicitly sent** (`"lang" in request.model_fields_set`) | `MoodleAssignRequest.lang` defaults to `"en"`; treating the default as an override would silently switch every Indonesian Moodle class to English prompts. |
| CLI transport | `src/cli.py` talks to the `/v1` HTTP API with `httpx` | One grading path (same locks/auth/validation); works against local dev or production. A `/grade/batch` endpoint is **out of scope** for Cycle 2. |
| In-process local LLM | `LLM_PROVIDER=local` via optional `llama-cpp-python` (GGUF path) | PRD §7.2-A; air-gapped single process. Ollama/vLLM users should prefer `openai_compatible`. |

---

### Task 0: Safety Net — Characterization Tests & PRD Baseline Refresh

**Files:**
- Create: `backend/tests/test_prompt_builder.py`
- Modify: `docs/PRD.md` (§2.2 baseline versions, §2.3 gaps: mark Cycle 1 items resolved)

**Why first:** `PromptBuilder` has zero tests and Tasks 9 changes it; lock current behavior before refactoring.

- [x] **Step 1: Write characterization tests** (they must pass against current code):
  - `build_prompt` output contains question, essay, JSON-dumped rubric, and `[Dokumen 1] (Sumber: w1.pdf, Halaman: 2)` context line; `last_prompt` is set.
  - `_format_context([])` returns the "no material" sentence.
  - `parse_llm_response` extracts JSON wrapped in prose / markdown fences; malformed JSON → fallback dict with `error`, `confidence == 0.5`, `score == 0`.
- [x] **Step 2:** Update PRD §2.2 to plugin versions `mod_airagmaterial 2026071902/1.1.2`, `mod_airagassign 2026071906/1.1.6`, `local_assign_ai_rag 2026071902/1.1.2`; mark §2.3 gaps 1, 2, 4 and the §5.3 "Target improvement" as delivered in Cycle 1.
- [x] **Step 3:** Run full suite → PASS. Commit `test(rag): add PromptBuilder characterization tests and refresh PRD baseline`.

---

### Task 1: Central Typed Settings (`src/utils/config.py`)

**Files:**
- Modify: `backend/src/utils/config.py`, `backend/src/utils/__init__.py`
- Create: `backend/tests/test_settings.py`

**Interfaces (produces):**

```python
@dataclass(frozen=True)
class LLMEndpointSettings:      # one OpenAI-compatible endpoint in a chain
    name: str; base_url: str; api_key: str; model: str; extra_headers: Mapping[str, str]

@dataclass(frozen=True)
class LLMSettings:
    provider: str                      # provider_chain | openai_compatible | local | groq | openrouter | huggingface
    model: str; temperature: float; max_new_tokens: int
    request_timeout: float; total_timeout: float
    base_url: str; api_key: str        # openai_compatible
    provider_order: tuple[str, ...]    # groq, openrouter, custom_1..N
    endpoints: tuple[LLMEndpointSettings, ...]  # resolved chain (numbered keys expanded)
    local_model_path: str; local_n_ctx: int; local_n_gpu_layers: int

@dataclass(frozen=True)
class EmbeddingSettings:
    provider: str                      # huggingface | openai_compatible | local
    model: str; base_url: str; api_key: str
    device: str                        # cpu | cuda ("cloud" normalized to "cpu")
    local_backend: str                 # fastembed | sentence_transformers
    batch_size: int; huggingface_token: str

@dataclass(frozen=True)
class RerankerSettings:
    enabled: bool; type: str           # none | bm25 | local_cross_encoder | http_rerank | llm_rerank | pinecone ("bge" → pinecone)
    model: str; base_url: str; api_key: str; api_style: str; device: str
    top_k: int; rerank_top_k: int; timeout: float; pinecone_api_key: str

@dataclass(frozen=True)
class VisionSettings:
    enable_image_extraction: bool; enable_vision_captioning: bool
    base_url: str; api_key: str; model: str

@dataclass(frozen=True)
class PromptSettings:  language: str   # auto | en | id
@dataclass(frozen=True)
class LockSettings:    enabled: bool; redis_url: str; prefix: str; ttl_seconds: int; wait_seconds: int
@dataclass(frozen=True)
class APISettings:     host: str; port: int; auth_token: str; max_upload_size_mb: int; instance_id: str
@dataclass(frozen=True)
class LoggingSettings: level: str; to_file: bool

@dataclass(frozen=True)
class Settings:
    llm: LLMSettings; embeddings: EmbeddingSettings; reranker: RerankerSettings
    vision: VisionSettings; prompt: PromptSettings; locks: LockSettings
    api: APISettings; logging: LoggingSettings
    raw: Mapping[str, Any]             # resolved config.yaml dict (legacy consumers)

def load_settings(env: Mapping[str, str] | None = None, config_path: Path | None = None) -> Settings
def get_settings() -> Settings          # functools.lru_cache
def reset_settings() -> None
@contextmanager
def override_settings(**env: str) -> Iterator[Settings]   # tests: patch env + reset cache
```

**Rules:**
- Env parsing helpers: `_env_bool`, `_env_int(min=…)`, `_env_float(min=…)`, `_env_choice(allowed, default, aliases)`; invalid values raise `ConfigError` naming the variable (fail fast at startup, not mid-request).
- Expand numbered keys exactly like today (`GROQ_API_KEY`, `GROQ_API_KEY_1..GROQ_KEY_MAX_INDEX`; same for OpenRouter) and add custom endpoints `LLM_CUSTOM_<N>_BASE_URL / _API_KEY / _MODEL` referenced in `LLM_PROVIDER_ORDER` as `custom_<N>`.
- OpenRouter endpoints keep `HTTP-Referer` / `X-Title` headers from `OPENROUTER_SITE_URL` / `OPENROUTER_APP_NAME`.
- Secrets: custom `__repr__` on settings dataclasses masks any field named `*api_key*`, `*token*`.
- `load_config()` stays (returns `settings.raw`) for backward compatibility.

- [x] **Step 1: Failing tests** in `test_settings.py`: defaults equal today's behavior with an empty env; numbered Groq/OpenRouter keys expand in `LLM_PROVIDER_ORDER` order; `custom_1` endpoint resolves; `RERANKER_TYPE=bge` → `pinecone`; `EMBEDDING_DEVICE=cloud` → `cpu`; invalid `LLM_REQUEST_TIMEOUT=abc` raises `ConfigError` mentioning the var; `repr(settings)` contains no key value; `override_settings` isolates and resets.
- [x] **Step 2:** Implement; run suite → PASS. Commit `feat(config): add central typed settings layer`.

---

### Task 2: Migrate All Consumers to Settings (zero `os.getenv` outside config)

**Files:** `src/api/auth.py`, `src/api/locking.py`, `src/api/request_utils.py`, `src/api/app.py` (`INSTANCE_ID`), `src/grading/grader.py` (multimodal flags), `src/rag/llm.py` (timeouts, keys — interim, fully reworked in Task 4), `src/vectorstore/embeddings.py`, `src/rag/reranker.py`, `src/ingestion/vision_captioner.py`, `src/utils/config.py` (logging); tests `test_auth.py`, `test_locking.py`, `test_llm.py`, `test_request_utils.py`.

**Rules:** each class gains an optional `settings` constructor argument defaulting to `get_settings().<section>`; module functions (`check_api_auth`, `save_upload`) read `get_settings()` at call time so `override_settings` works. `OperationLockManager(settings: LockSettings | None = None)`.

- [x] **Step 1:** Add test `test_no_getenv_outside_config` (walks `src/**/*.py` with `ast`, asserts no `os.getenv` / `os.environ` access except in `utils/config.py`) — fails now.
- [x] **Step 2:** Migrate consumers; switch existing tests from `patch.dict(os.environ, …)` to `override_settings(...)` where they relied on env reads.
- [x] **Step 3:** Suite → PASS. Commit `refactor(config): route all runtime configuration through settings`.

---

### Task 3: Side-Effect-Free App Factory (`create_app()` + Lifespan)

**Files:**
- Create: `backend/src/api/runtime.py`
- Modify: `backend/src/api/app.py`, `backend/src/api/moodle_routes.py`, `backend/src/api/v1_routes.py`, `backend/run_api.py`
- Create: `backend/tests/test_app_factory.py`; Modify: `backend/tests/test_v1_endpoints.py` (main-app wiring test)

**Interfaces:**

```python
# src/api/runtime.py
@dataclass
class AppRuntime:
    grader: EssayGrader
    operation_locks: OperationLockManager
    settings: Settings

def build_runtime(settings: Settings | None = None) -> AppRuntime
def set_runtime(runtime: AppRuntime | None) -> None
def get_runtime() -> AppRuntime          # raises RuntimeError("API runtime not initialized") if unset

# src/api/app.py
def create_app(runtime: AppRuntime | None = None, settings: Settings | None = None) -> FastAPI
app = create_app()                       # gunicorn entrypoint unchanged; builds nothing at import
```

- Lifespan: `setup_logging()`, `ensure_directories()`, `build_runtime()` (unless injected), `set_runtime()`, and `set_runtime(None)` on shutdown.
- Router helpers keep names: `get_grader()` → `get_runtime().grader`; `get_operation_lock(...)` → `get_runtime().operation_locks`. Legacy routes in `app.py` (`/upload`, `/grade`, `/status`, `/clear`, `/config/chunking`, `/health`) use the same helpers.
- `/health` returns 503 (not 500) if the runtime failed to initialize.

- [x] **Step 1: Failing tests:** (a) importing `src.api.app` with `EssayGrader`, `OperationLockManager`, `VectorStore` patched to raise → import succeeds and none is called; (b) `create_app(runtime=fake)` + `TestClient` serves `/health` and auth-protected `/v1` routes (port the existing wiring test to injection, no `sys.modules` juggling); (c) lifespan calls `build_runtime` exactly once and clears runtime on exit.
- [x] **Step 2:** Implement. **Step 3:** Suite → PASS. Commit `refactor(api): add create_app factory with lifespan-managed runtime`.

---

### Task 4: LLM — Any OpenAI-Compatible Endpoint, Custom Chains, Legacy Presets on One Client

**Files:** Modify `backend/src/rag/llm.py`, `backend/src/rag/pipeline.py` (construct from settings); Modify `backend/tests/test_llm.py`.

**Behavior:**
- `LLMWrapper(settings: LLMSettings | None = None, client_factory: Callable[..., OpenAI] = OpenAI)`; legacy keyword args (`model_name`, `provider`, `temperature`, …) still accepted and override settings (keeps `RAGPipeline.switch_llm` working).
- `openai_compatible`: single endpoint from `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`; empty key allowed (sends placeholder `"not-needed"` because the SDK requires a value) — Ollama `http://host:11434/v1`, vLLM, LM Studio, llama.cpp server, LiteLLM, OpenAI.
- `provider_chain`: ordered `settings.endpoints` (Groq/OpenRouter numbered keys + `custom_N`), existing timeout/deadline/rate-limit/`retry-after` logic preserved.
- `groq` / `openrouter`: chains starting with that preset (today's behavior). `huggingface`: endpoint `https://router.huggingface.co/v1` with `HUGGINGFACE_API_TOKEN` — routed through the same chain executor (removes the separate `_init_huggingface`/`_generate_openai_style` path).
- `local`: delegate to `LocalLlamaCppLLM` (Task 8); `ImportError` → actionable message.
- Error when no usable endpoint names the variables to set for the chosen provider.

- [x] **Step 1: Failing tests** with a fake `client_factory` recording `base_url`, `api_key`, `model`, headers: openai_compatible without key; custom_1 → groq fallback order; first endpoint 429 with `retry-after` then second succeeds; total deadline stops the chain; huggingface preset uses router URL; arbitrary model id passes through untouched; `get_provider_info()` never contains a key.
- [x] **Step 2:** Implement. **Step 3:** Suite → PASS. Commit `feat(llm): support any OpenAI-compatible endpoint and custom provider chains`.

---

### Task 5: Embeddings — Provider Abstraction + Collection Embedding Guard

**Files:**
- Modify: `backend/src/vectorstore/embeddings.py`, `backend/src/vectorstore/chroma_store.py`, `backend/src/api/moodle_routes.py` + `v1_routes.py` (map `EmbeddingMismatchError` → HTTP 409)
- Create: `backend/tests/test_embeddings.py`; Modify: `backend/tests/test_chroma_store.py`

**Interfaces:**

```python
class OpenAICompatibleEmbeddings(Embeddings):   # openai SDK /v1/embeddings, batches of settings.batch_size,
    ...                                          # preserves input order by response `index`
class LocalEmbeddings(Embeddings):              # fastembed.TextEmbedding or sentence_transformers.SentenceTransformer
    ...                                          # lazy import, model cached per process
class EmbeddingGenerator:                       # public API unchanged: get_embeddings_instance(), switch_model(), get_model_info()
    def __init__(self, settings: EmbeddingSettings | None = None, model_name: str | None = None, ...)
    provider: str
    def identity(self) -> dict                  # {"embedding_provider", "embedding_model", "embedding_dimension"(lazy probe)}

class EmbeddingMismatchError(RuntimeError): ...
```

- `huggingface` stays the default and is the **only** mode that requires `HUGGINGFACE_API_TOKEN` (error raised lazily when that provider is selected — never at import).
- Collection guard in `VectorStore._get_vectorstore()`: on first open in the process, read collection metadata; if absent (legacy) write identity; if present and provider/model/dimension differ → `EmbeddingMismatchError` with a message telling the operator to re-ingest or switch back. Dimension probed once via `embed_query("dimension probe")` and cached.
- Local `device`: `cuda` passed to the backend; `fastembed` unsupported model → error suggesting `EMBEDDING_LOCAL_BACKEND=sentence_transformers` (verify the supported-model list against the installed fastembed version during implementation; do not hard-code assumptions in docs).

- [x] **Step 1: Failing tests:** openai_compatible batching + order (fake client); `huggingface` without token raises only when selected; local backend via fake `fastembed` module injected in `sys.modules`; real `chromadb.PersistentClient` guard tests — legacy collection adopted, mismatched provider raises, same identity reopens fine; API route returns 409 on mismatch.
- [x] **Step 2:** Implement. **Step 3:** Suite → PASS. Commit `feat(embeddings): add openai-compatible and local embedding providers with collection guard`.

---

### Task 6: Reranker — Factory With Six Modes

**Files:** Modify `backend/src/rag/reranker.py`, `backend/src/rag/retriever.py`, `backend/src/rag/pipeline.py`; Create `backend/tests/test_reranker.py`.

**Interfaces:**

```python
class BaseReranker(Protocol):
    def rerank(self, query: str, documents: list[Document], top_k: int) -> list[tuple[Document, float]]: ...
    def rerank_documents(self, query: str, documents: list[Document], top_k: int) -> list[Document]: ...
    def get_model_info(self) -> dict: ...

class BM25Reranker            # existing
class PineconeReranker        # existing BGEReranker renamed; BGEReranker / LLMReranker aliases kept
class HTTPReranker            # httpx; api_style cohere|tei; Bearer key optional; timeout from settings
class LLMReranker             # chat-completions JSON {"ranking":[{"index":i,"score":s}]}, reuses LLMWrapper endpoint config of RERANKER_*
class LocalCrossEncoderReranker  # fastembed TextCrossEncoder or sentence_transformers CrossEncoder (lazy)

def create_reranker(settings: RerankerSettings) -> BaseReranker | None   # None when disabled/none
```

- `Retriever` takes `reranker: BaseReranker | None` (factory output) — `reranker_type` string handling moves to `create_reranker`; `set_reranker_type()` keeps working via the factory.
- Every reranker clamps `top_k`, ignores out-of-range indices from remote responses, and on any exception logs and returns the original order (never raises into grading).
- **Note the `llm_rerank` class name:** the module currently exports `LLMReranker = BGEReranker` as a legacy alias; rename the alias target carefully (`PineconeReranker`) and grep for imports before reusing the name.

- [x] **Step 1: Failing tests:** `httpx.MockTransport` for cohere and tei request/response shapes (incl. auth header present only with key); malformed / out-of-range indices ignored; HTTP 500 → original order; llm_rerank parses fenced JSON and falls back on garbage; local cross-encoder with fake module; factory mapping incl. `bge` alias and `ENABLE_RERANKING=false` → `None`.
- [x] **Step 2:** Implement. **Step 3:** Suite → PASS. Commit `feat(rerank): add http, llm, local cross-encoder rerankers behind a factory`.

---

### Task 7: Vision Captioner on Any OpenAI-Compatible Multimodal Endpoint

**Files:** Modify `backend/src/ingestion/vision_captioner.py`, `backend/src/ingestion/document_loader.py`; Create `backend/tests/test_vision_captioner.py`.

- `VisionCaptioner(settings: VisionSettings | None = None, client_factory=OpenAI)`; base URL/key/model from `VISION_BASE_URL` / `VISION_API_KEY` / `VISION_MODEL`, defaulting to the HF Router + `HUGGINGFACE_API_TOKEN` (today's behavior). No model allow-list.
- Caption prompt follows `PROMPT_LANGUAGE` (`en` / `id`; `auto` → `id` for backward compatibility of existing captions) — reuse the template registry from Task 9 if already merged, otherwise a local two-entry dict.
- Remains disabled by default.

- [x] **Step 1:** Failing tests with fake client (base URL/model passthrough, image_url data URI payload, retry then success). **Step 2:** Implement. **Step 3:** Commit `feat(vision): make captioning endpoint configurable`.

---

### Task 8: Optional In-Process Local LLM (`LLM_PROVIDER=local`)

**Files:** Create `backend/src/rag/local_llm.py`; Create `backend/requirements-local.txt`; Modify `backend/src/rag/llm.py`; Create `backend/tests/test_local_llm.py`.

- `LocalLlamaCppLLM(settings)` lazily imports `llama_cpp.Llama`, loads `LLM_LOCAL_MODEL_PATH` (GGUF) once per process with `n_ctx`, `n_gpu_layers`, and exposes `generate(prompt) -> str` via `create_chat_completion`.
- `requirements-local.txt`: `fastembed`, `sentence-transformers` (commented as alternative), `llama-cpp-python` (commented, optional) — pin ranges at implementation time after checking current releases.
- Missing package / missing model file → `ConfigError` with exact remediation.

- [x] **Step 1:** Failing tests with fake `llama_cpp` module. **Step 2:** Implement. **Step 3:** Commit `feat(llm): add optional in-process llama.cpp provider`.

---

### Task 9: Language-Aware Grading Prompt & Neutral Pipeline Strings

**Files:**
- Create: `backend/src/rag/prompts.py` (templates + `detect_language`)
- Modify: `backend/src/rag/prompt_builder.py`, `backend/src/rag/pipeline.py`, `backend/src/grading/grader.py`, `backend/src/api/v1_models.py`, `backend/src/api/v1_routes.py`, `backend/src/api/moodle_routes.py`
- Modify: `backend/tests/test_prompt_builder.py`, `backend/tests/test_pipeline_scoping.py`; Create `backend/tests/test_prompts.py`

**Behavior:**
- `PROMPT_TEMPLATES = {"en": ..., "id": ...}` — same JSON schema/keys in both; the Indonesian template is today's text verbatim (regression-safe).
- `detect_language(*texts) -> "en" | "id"`: lowercase word tokens; ratio of Indonesian vs English stopword hits; tie / too-short → `"id"` (backward compatible).
- Resolution order: per-request `language` (v1: `V1GradeRequest.language: Literal["auto","en","id"] | None`; Moodle: `lang` **only if explicitly sent**, mapped `id*`→`id`, `en*`→`en`, others → auto) → `PROMPT_LANGUAGE` → `auto`.
- `PromptBuilder.build_prompt(..., language=...)`; context lines localized (`[Document 1] (Source: …, Page: …)` / `[Dokumen 1] (Sumber: …, Halaman: …)`).
- Pipeline: retrieval query becomes language-neutral `f"{question}\n\n{essay}"`; source fallback `"Unknown"`; result includes `"language"` used. Grader/pipeline user-facing errors become English (matching the rest of the API); fallback parse error `"Failed to parse structured LLM response"`.
- Update the Cycle 1 pipeline test that asserted the Indonesian query string.

- [x] **Step 1: Failing tests:** detection on EN/ID samples and short/mixed input; v1 explicit `language` wins; Moodle request **without** `lang` + Indonesian text → `id` template (backward-compat guard); Moodle with explicit `lang="en"` → `en`; both templates produce prompts the existing parser handles; Indonesian template unchanged byte-for-byte from Task 0 snapshot.
- [x] **Step 2:** Implement. **Step 3:** Suite → PASS. Commit `feat(prompt): add PROMPT_LANGUAGE auto/en/id and language-neutral retrieval`.

---

### Task 10: Packaging & Images

**Files:** Modify `backend/requirements.txt` (+`httpx`), `backend/requirements-optional.txt`, `backend/Dockerfile`, `backend/.dockerignore` (keep `requirements*.txt` included), `backend/tests/test_llm.py` (dependency assertions → move to `tests/test_dependencies.py`).

- Dockerfile `ARG INSTALL_LOCAL_EXTRAS=false` → installs `requirements-local.txt` when `true`; `ARG INSTALL_OPTIONAL_EXTRAS=false` → `requirements-optional.txt` (Pinecone).
- `test_dependencies.py`: core requirements contain no dead packages (Cycle 1 list) **and** every third-party top-level import in `src/` is either in `requirements.txt`, a documented transitive pin, or lazily imported from an optional extra (AST scan with an explicit allow-map).

- [x] Steps: dependency test → implement → `docker compose config` validated with both build-arg values (local `docker build` not run: Docker daemon unavailable on the dev machine; CI builds the image) → commit `build: add local/optional dependency extras and declare httpx`.

---

### Task 11: 10-Minute Quickstart — Dev Compose, Sample Kit, CLI

**Files:**
- Create: `backend/docker-compose.dev.yml` (single `api` container, `CHROMA_CLIENT_MODE=persistent`, `DISTRIBUTED_LOCK_ENABLED=false`, port `127.0.0.1:8000`, optional `ollama` service under a compose profile `local`)
- Create: `backend/.env.dev.example` (OpenAI-compatible/Ollama defaults, no cloud keys required)
- Create: `examples/week1_to_week4_quiz/` — `materials/week-1.txt … week-4.txt` (original, license-clean networking content), `rubric.json`, `answers.csv` (`student_id,question,answer`), `README.md`, `run_demo.sh`
- Create: `backend/src/cli.py` (`python -m src.cli`), `backend/tests/test_cli.py`

**CLI:**

```text
python -m src.cli ingest     --namespace cs101 --module week-1 [--tag key=value ...] PATH...
python -m src.cli grade      --namespace cs101 --question Q --answer A [--rubric rubric.json] [--max-grade 100] [--module week-1 ...] [--source f.pdf ...]
python -m src.cli grade-csv  --namespace cs101 --input answers.csv --output graded.csv [--rubric ...] [--module ...] [--concurrency 4] [--review-threshold 0.6]
Common: --api-url (env RAG_API_URL, default http://127.0.0.1:8000)  --token (env RAG_API_TOKEN)
```

- `grade-csv` output columns: input columns + `score, max_grade, confidence, needs_review, feedback, citations` (citations as `source#page` list); per-row failures recorded in an `error` column without aborting the batch; exit code 0 if all rows graded, 2 if some failed.
- Bounded concurrency with a thread pool; `X-Request-ID` per row.
- Demo script ingests Weeks 1–3 with `module=week-N`, also ingests Week 4 to prove the filter, then grades with `--module week-1 --module week-2 --module week-3`.

- [ ] **Step 1: Failing tests** with `httpx.MockTransport`: multipart ingest fields, grade payload (`material_filter`), CSV round-trip incl. a failing row and `needs_review`, token header.
- [ ] **Step 2:** Implement. **Step 3:** Manual run: `docker compose -f docker-compose.dev.yml up` + `examples/week1_to_week4_quiz/run_demo.sh` against a local OpenAI-compatible model; record timing in the example README.
- [ ] Commit `feat(cli): add quickstart dev compose, sample Week 1-4 kit, and CSV batch grader`.

---

### Task 12: Docs, Env Templates & Full Verification

**Files:** `README.md` (Quickstart A: dev/local in <10 min; Quickstart B: production), `docs/architecture.md` (provider matrix, settings layer, app lifecycle, collection guard), `docs/deployment.md` (provider env reference + examples for Ollama, vLLM, OpenAI, TEI/Jina rerank), `backend/.env.example` (all new vars, commented, defaults = legacy behavior), `configs/config.yaml` (new placeholders), `docs/PRD.md` §8 status.

- [ ] **Verification (all must pass):**
  ```bash
  cd backend && python -m unittest discover -s tests -v
  python -m compileall -q backend/src
  grep -rn "os.getenv\|os.environ" backend/src   # only src/utils/config.py
  env -u HUGGINGFACE_API_TOKEN -u GROQ_API_KEY -u OPENROUTER_API_KEY -u PINECONE_API_KEY \
      python -m unittest discover -s backend/tests   # Done criterion 1
  make lint-php && ./scripts/build-plugins.sh
  docker compose -f backend/docker-compose.yml config --quiet      # with .env from .env.example in a temp copy
  docker compose -f backend/docker-compose.dev.yml config --quiet
  ```
- [ ] Backward-compat smoke: start the production compose with an unchanged Cycle 1 `.env`; `/health`, `/moodle/status`, `/assign/answer` behave as before and existing collections are readable (guard adopts them).
- [ ] Commit `docs: document provider configuration, settings layer, and quickstart`.

---

## Task Dependency Order

```text
0 ─► 1 ─► 2 ─► 3 ─┬─► 4 ─► 8
                  ├─► 5
                  ├─► 6   (llm_rerank reuses Task 4 client code)
                  ├─► 7   (prompt language reuse optional)
                  └─► 9
4,5,6,7,8,9 ─► 10 ─► 11 ─► 12
```

Tasks 4–7 and 9 touch disjoint modules after Task 3 and can be implemented in parallel worktrees if desired; Task 6 should land after Task 4.

## Risks & Mitigations

| Risk | Impact | Mitigation |
| :--- | :--- | :--- |
| Settings refactor changes a default silently | Existing Moodle deployments degrade | Task 1 "defaults equal today" test + Task 12 smoke with an unchanged `.env` |
| Embedding provider switch on a populated course | Mixed vector spaces / wrong retrieval | Collection identity guard (409 + operator message) instead of silent use |
| `lang="en"` default in `MoodleAssignRequest` | Indonesian classes graded with English prompt | Override only when field explicitly sent; dedicated regression test |
| Optional heavy packages missing at runtime | Startup crash | Lazy import inside provider + actionable `ConfigError`; core image unaffected |
| Rerank API dialect differences | Wrong ordering / crashes | Two explicit `api_style`s, defensive parser, fall back to vector order |
| Small local models emit invalid JSON | Grading fallback with no score | Existing fallback path kept; README recommends ≥7B instruct models and documents `confidence` behavior |
| `create_app` lifespan not run by bare `TestClient(app)` | Tests hit uninitialized runtime | Tests inject runtime via `create_app(runtime=...)`; helper raises a clear `RuntimeError` |

## Out of Scope (Cycle 3 or later)

- `/v1/namespaces/{ns}/grade/batch` endpoint (CLI covers batch use).
- Per-activity `material_id` isolation, Moodle Privacy API, `lib.php` modularization, Moodle PHPUnit/Behat, release automation.
- Additional prompt languages beyond `en` / `id` (template registry makes this a data-only change later).
