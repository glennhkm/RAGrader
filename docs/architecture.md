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
- **FastAPI Replicas (`src/api/app.py`, `src/api/moodle_routes.py`)**: Stateless API workers handling request validation (`request_utils.py`), optional Bearer token authentication (`auth.py`), document ingestion, and grading orchestration (`src/grading/grader.py`, `src/rag/pipeline.py`).
- **ChromaDB Server (`chroma`)**: Shared HTTP vector store (`CHROMA_CLIENT_MODE=http`) isolating course collections by `course_id`.
- **Redis (`redis`)**: Coordinates per-course distributed read/write locks (`src/api/locking.py`) so concurrent grading requests run in parallel while upload/delete/clear mutations remain mutually exclusive per course.

## HTTP API Contract

When `API_AUTH_TOKEN` is set in `backend/.env`, all endpoints below except `GET /` and `GET /health` require `Authorization: Bearer <API_AUTH_TOKEN>`.

| Method & Path | Caller | Purpose |
| :--- | :--- | :--- |
| `GET /health` | HAProxy, Docker, Admins | Readiness check (Chroma heartbeat + Redis ping) |
| `GET /moodle/status` | `local_assign_ai_rag` | Check RAG service, LLM, and vectorstore readiness |
| `GET /collections/{course_id}` | `local_assign_ai_rag`, Admins | Inspect document count for a course collection |
| `DELETE /collections/{course_id}` | Admins | Delete an entire course collection |
| `POST /course/materials/upload` | `mod_airagmaterial`, `mod_airagassign`, `local_assign_ai_rag` | Upload & vectorize `.pdf`, `.pptx`, `.docx`, `.txt` into course collection |
| `DELETE /course/materials/file` | `mod_airagmaterial`, `mod_airagassign` | Remove vector chunks for a deleted/replaced file |
| `POST /course/materials/clear` | `mod_airagmaterial`, `local_assign_ai_rag` | Clear all vectors for a course |
| `GET /course/materials/status/{course_id}` | Monitoring / Clients | Course material vectorization status |
| `POST /assign/answer` | `mod_airagassign`, `local_assign_ai_rag` | Grade a student answer with `course_id`, `question`, `essay`, `rubric`, `maximum_grade`, `assignment_id` |

