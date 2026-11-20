# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/).
The repository is released as a whole (tags `vX.Y.Z`); each component keeps its own version,
listed in the table below.

## [Unreleased]

## [1.0.0] - 2026-11-20

First public release. It summarizes three development cycles.

### Component versions

| Component | Version | Moodle plugin version | Requires |
|-----------|---------|-----------------------|----------|
| backend (FastAPI service) | 1.4.0 | - | Python 3.10+ |
| mod_airagmaterial | 1.2.0 | 2026112100 | Moodle 4.4+ |
| mod_airagassign | 1.2.0 | 2026112100 | Moodle 4.4+ |
| local_assign_ai_rag | 1.1.3 | 2026112100 | Moodle 4.5+ |
| aiprovider_rag | 1.1.1 | unchanged | Moodle 4.5+ |

### Added

- Cycle 1 - generic engine: namespaced `/v1` API (`/v1/namespaces/...`) independent of Moodle, metadata tags (`module`, `tag_*`) on ingested chunks, and scoped retrieval with Chroma `where` filters; Moodle grading scoped to linked materials via `source_filter`; scope filters that select nothing are rejected.
- Cycle 2 - model and platform freedom: central typed settings layer and side-effect-free `create_app()` with lifespan; any OpenAI-compatible LLM endpoint and custom provider fallback chains; OpenAI-compatible and local embeddings (with a collection guard), HTTP/LLM/local cross-encoder rerankers, optional in-process llama.cpp provider and configurable vision captioning; `PROMPT_LANGUAGE=auto|en|id`; quickstart dev compose, sample Week 1-4 kit, `/v1` CLI with CSV batch grading and tag-scoped grading, and a lightweight CLI install.
- Cycle 3 - Moodle hardening: Privacy API providers for all plugins; owner-scoped vectors via optional `material_id` (backend 1.4.0) replacing the shared-filename guard; tracked vectorization of reference files; `mod_airagassign` `lib.php` split into tested local services; injectable RAG client in `mod_airagmaterial`; plugin data generators and PHPUnit via moodle-plugin-ci; full-stack Docker Compose integration tests in CI; Moodle 4.4 support for the activity modules; tag-driven GitHub release with plugin ZIPs and SHA256SUMS.

### Changed

- Document image captions are labelled in the answer's language; caption text and answer paths are kept out of INFO logs.

### Fixed

- Moodle-rubric grading crashed (undefined `get_method()`).
- Reference-file vector deletes never sent the filename (`&amp;` separators).
- Backup/restore and duplication of AI RAG Assignments and AI RAG Materials failed (`prepare_activity_structure` was missing); restoring a course now also re-links assignments to their restored materials.
- Deleting a file that has no vectors was reported as a failure.
- A vector store failure while deleting a material file was reported as HTTP 200 `{"success": false}` (indistinguishable from "nothing to delete"), so the plugins dropped the retry; `DELETE /course/materials/file` now returns 500, and a re-upload whose old vectors cannot be removed fails instead of adding duplicates.
- Grading was run while linked materials were only partially vectorized; it is now refused until vectorization finishes.
- `DELETE /collections` now also removes the uploaded files of the collection.
- Chroma telemetry is off by default.
- Privacy context deletion in `local_assign_ai_rag` now also anonymises teacher references (config, rubric and course material rows).

### Security

- The reference (model answer) file of an AI RAG Assignment could be downloaded by any user with course access, including students; it now requires `mod/airagassign:grade`.

### Upgrade notes

- Upgrade the backend to 1.4.0 BEFORE upgrading the Moodle plugins. The Cycle 3 plugins require backend 1.4.0: an older backend ignores `material_id`, so plugin deletes would remove other activities' vectors of the same filename, and materials vectorized there would be stored unowned and then not be found by owner-scoped grading after a later backend upgrade.
- After upgrading, all AI RAG Materials and reference files are re-vectorized in the background (Moodle cron). Grading of affected assignments is refused until that finishes; retry gradings that failed during the upgrade once cron has finished re-vectorization.
- Legacy vectors of files that were removed before the upgrade may remain in the course collection. AI RAG Assignment grading is owner-scoped and ignores them, but `local_assign_ai_rag` grades against the whole course collection and can still retrieve them; if that matters, clear the course collection and then re-vectorize the course's materials.
- The AI RAG Material and AI RAG Assignment activity modules now call the RAG server through Moodle's HTTP client, which honours `$CFG->proxyhost`. If a proxy is configured, add the RAG server host to `$CFG->proxybypass`.

[Unreleased]: https://github.com/glennhkm/RAGrader/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/glennhkm/RAGrader/releases/tag/v1.0.0
