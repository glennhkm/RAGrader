# Cycle 3: Moodle Deep Hardening, Full-Stack Tests & v1.0.0 Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Moodle plugins audit-ready (Privacy API, per-activity vector ownership, verified reference-file vectorization, modular testable PHP), prove the whole stack in CI (Moodle PHPUnit + Docker Compose integration), and publish the first public release `v1.0.0` from a clean `main`.

**Architecture:** Every chunk gets an optional owner (`material_id`, e.g. `airagmaterial:12`, `airagassign:5`); owner-scoped calls never touch another owner's chunks and legacy calls only touch unowned chunks. The plugins talk to the API through one injectable Guzzle-based client (`\mod_airagmaterial\local\rag_client`) so PHPUnit can mock HTTP. `mod_airagassign/lib.php` keeps only Moodle callbacks; logic moves to autoloaded `classes/local/` services. CI gains a `moodle-plugin-ci` matrix and a Compose-based integration job against a deterministic AI stub.

**Tech Stack:** Python 3.10 / FastAPI / ChromaDB 0.6.3 (backend), PHP 8.1+ / Moodle 4.5 LTS–5.3 (plugins), `\core\http_client` (Guzzle), Moodle PHPUnit + `\core_privacy\tests\provider_testcase`, `moodlehq/moodle-plugin-ci` 4.5.x, Docker Compose, GitHub Actions, `gh` CLI.

**Spec:** [`docs/PRD.md`](../../PRD.md) §6.1 items 8–10, §6.3, §8 (Cycle 3 row). Builds on Cycle 2 ([`2026-11-19-cycle2-model-freedom-config.md`](2026-11-19-cycle2-model-freedom-config.md)) and the review hardening on `fix/cycle1-scope-hardening` / `fix/cycle2-review-followups`.

**Branch:** `feat/cycle3-moodle-hardening-release` (from `fix/cycle2-review-followups` @ `7a334a2`).

**Maintainer decisions (2026-11-20):** (1) `main` is **replaced**: the old history is archived as tag `legacy/v1.1.0-prototype` and `main` is pointed at the finished Cycle 3 branch. (2) The repository release is **`v1.0.0`**; components keep their own versions.

---

## Done Criteria (PRD §8 Cycle 3, made testable)

1. `mod_airagassign`, `mod_airagmaterial` and `local_assign_ai_rag` ship a Privacy provider; `aiprovider_rag` keeps its `null_provider`; privacy PHPUnit tests pass (export + delete for one user, many users, whole context).
2. A reference (`manualfile`) file that failed or is still pending vectorization makes grading **refuse with a teacher-visible reason**; it never silently yields empty retrieval.
3. Two `mod_airagmaterial` activities in one course with an identical filename never affect each other's retrieval or deletion (backend integration test + PHPUnit payload test).
4. `mod_airagassign/lib.php` contains only Moodle callbacks/APIs and is **≤ 450 lines**; the moved logic is covered by PHPUnit.
5. CI is green for: Python unit tests (offline), PHP lint, `moodle-plugin-ci` (validate, savepoints, phpunit) on Moodle 4.5 / 5.0 / 5.3, Compose integration tests (2 API replicas + Chroma + Redis + HAProxy), API image builds with and without `INSTALL_LOCAL_EXTRAS`, plugin ZIP build.
6. `CHANGELOG.md` exists; pushing tag `v1.0.0` on `main` publishes a GitHub Release with the four plugin ZIPs and `SHA256SUMS`.
7. Old clients keep working: a 1.1.x plugin against backend 1.4.0, and a Cycle 3 plugin against backend 1.3.0 (contract tests).

## Global Constraints

- **Backward compatibility:** existing Moodle routes, payloads and collection names (`course_{id}_{model}`) keep working; every new request field is optional.
- Keep `chromadb==0.6.3`. Unit tests run through `backend/tests/run_offline.py` (no network).
- Moodle `$plugin->requires = 2024100700` (4.5) for all plugins unless Task 9 proves 4.4 for the two activity modules.
- PHP ≥ 8.1. Plugins stay GPL-3.0-or-later; backend/scripts/docs stay MIT.
- New `version.php` values use `YYYYMMDDXX` ≥ `2026112100`. Target component versions: backend **1.4.0**, `mod_airagmaterial` **1.2.0**, `mod_airagassign` **1.2.0**, `local_assign_ai_rag` **1.1.3**, `aiprovider_rag` unchanged **1.1.1**.
- Never log student identity, essay text or caption text at `INFO`+ (backend) and never `mtrace()` it (Moodle tasks).
- RAG HTTP calls go through `rag_client` only; the API URL is admin-configured (`moodle/site:config`), so the client is built with `ignoresecurity => true` (internal/private hosts are the normal deployment) — documented in the class docblock.
- After every task: `cd backend && python tests/run_offline.py`, `make lint-php`, `./scripts/build-plugins.sh`; Moodle PHPUnit runs in CI (`moodle-plugin-ci phpunit`) — locally only if a Moodle checkout is available.
- One commit per task, Conventional Commits, ending with the project's `Co-Authored-By` trailer. Lang strings are added in **both** `lang/en` and `lang/id`.
- **Other development machine:** before Task 11, merge any new commits from `origin/feat/cycle1-core-generalization` and `origin/feat/cycle2-model-freedom-config` into this branch.

## Review Focus

1. **Upgrade with the RAG server down:** upgrading `mod_airagmaterial` must only *queue* re-vectorization (no HTTP inside `upgrade.php`); materials then fail visibly and grading is refused until re-vectorized. → test in Task 5.
2. **Mixed versions:** a 1.1.x plugin calling backend 1.4.0 (no `material_id`) must not delete owned chunks; a Cycle 3 plugin calling backend 1.3.0 must still be scoped by `source_filter`. → tests in Task 4 and Task 6.
3. **Reference file replaced while its task is queued:** the task must vectorize the *current* file and not mark a stale content hash as vectorized. → test in Task 6.
4. **Assignment or material deleted while its adhoc task is queued:** the task must exit cleanly without HTTP calls or errors. → tests in Task 5 and Task 6.
5. **Privacy deletion of one student:** removes only that student's submissions/answers/pending rows; other students and teacher-owned config stay intact; teacher-only fields (`graded_by`, `usermodified`) are anonymised to `0`, not deleted. → test in Task 7.

---

## File Structure

| Path | Responsibility |
| :--- | :--- |
| `backend/src/vectorstore/chroma_store.py`, `filters.py` | Owner-aware delete (`material_id`), `material_ids` where-clause |
| `backend/src/grading/grader.py`, `src/api/moodle_routes.py`, `moodle_models.py` | `material_id` on ingest/delete, `material_ids` on `/assign/answer` |
| `backend/integration_tests/` (new) | `stub_ai.py` (deterministic OpenAI-compatible chat + embeddings), `test_full_stack.py` |
| `backend/docker-compose.ci.yml` (new) | Compose override: stub service, auth token, stub endpoints |
| `moodle-plugins/mod_airagmaterial/classes/local/rag_client.php` (new) | The only HTTP client for the RAG API (both activity modules) |
| `moodle-plugins/mod_airagassign/classes/local/{rubric_builder,material_scope,grading_service}.php` (new) | Logic moved out of `lib.php` |
| `moodle-plugins/mod_airagassign/classes/task/vectorize_manualfile.php` (new) | Background reference-file vectorization with status |
| `moodle-plugins/*/classes/privacy/provider.php` (new ×3) | Privacy API |
| `moodle-plugins/{mod_airagassign,mod_airagmaterial}/tests/` (new) | Generators + PHPUnit |
| `.github/workflows/ci.yml`, `.github/workflows/release.yml` (new) | Moodle/integration CI; tag-driven release |
| `CHANGELOG.md`, `scripts/release-notes.sh` (new) | Release notes source and extractor |

---

### Task 1: Moodle PHPUnit Harness in CI (generators + smoke tests)

**Files:**
- Create: `moodle-plugins/mod_airagmaterial/tests/generator/lib.php`, `moodle-plugins/mod_airagassign/tests/generator/lib.php`, `moodle-plugins/mod_airagmaterial/tests/generator_test.php`, `moodle-plugins/mod_airagassign/tests/generator_test.php`
- Modify: `.github/workflows/ci.yml` (new job `moodle-plugin-ci`)

**Interfaces:**
- Produces: `mod_airagmaterial_generator::create_instance($record = null, array $options = null)` (defaults `vectorize_status='pending'`); `mod_airagmaterial_generator::create_file(stdClass $material, string $filename, string $content): stored_file` (file area `mod_airagmaterial` / `materials`, itemid 0, as read by `airagmaterial_get_uploaded_files()`); `mod_airagassign` reference files live in `mod_airagassign` / `manualfile`; `mod_airagassign_generator::create_instance(...)` (defaults `assignmode='essay'`, `rubricmode='custom'`, `maximumgrade=100`) and `create_submission(stdClass $assign, int $userid, string $answer, string $status = 'submitted'): stdClass`.

- [ ] **Step 1: Write the smoke tests** (`final class generator_test extends \advanced_testcase`, `@covers` the generator): create a course and an instance via `$this->getDataGenerator()->create_module('airagmaterial', ['course' => $course->id])`; assert the record exists and `vectorize_status === 'pending'`; for `airagassign` also assert `create_submission()` writes one `airagassign_submissions` row plus one `airagassign_answers` row with the answer text.
- [ ] **Step 2: Add the CI job** using `moodlehq/moodle-plugin-ci` `^4.5` with a `postgres:16` service. Matrix (`fail-fast: false`): `{moodle: MOODLE_405_STABLE, php: 8.1}`, `{MOODLE_500_STABLE, 8.3}`, `{MOODLE_503_STABLE, 8.3}` × `plugin: [mod_airagmaterial, mod_airagassign, local_assign_ai_rag, aiprovider_rag]`. Install with `moodle-plugin-ci install --plugin ./moodle-plugins/${{ matrix.plugin }} --db-host=127.0.0.1` and `EXTRA_PLUGINS_DIR` holding the dependency (`mod_airagmaterial` for `mod_airagassign`; `aiprovider_rag` for `local_assign_ai_rag`). Blocking steps: `phplint`, `validate`, `savepoints`, `phpunit --fail-on-warning`. Informational (`continue-on-error: true`): `codechecker --max-warnings 0`, `phpdoc` (full style clean-up is out of scope).
- [ ] **Step 3: Push the branch and confirm** all 12 matrix legs are green.
- [ ] **Step 4: Commit** `test(moodle): add plugin data generators and moodle-plugin-ci PHPUnit matrix`.

### Task 2: Injectable RAG HTTP Client (`\mod_airagmaterial\local\rag_client`)

**Files:**
- Create: `moodle-plugins/mod_airagmaterial/classes/local/rag_client.php`, `moodle-plugins/mod_airagmaterial/tests/local/rag_client_test.php`
- Modify: `moodle-plugins/mod_airagmaterial/lib.php` (replace the raw `curl_*` in `airagmaterial_send_file_to_rag()` and `airagmaterial_delete_file_vectors()`)

**Interfaces:**
- Produces:
  ```php
  final class rag_client {
      public function __construct(string $serverurl, string $apikey = '', ?\GuzzleHttp\ClientInterface $http = null, int $timeout = 300);
      public static function for_component(string $component): self; // reads {component}/serverurl, {component}/apikey; default URL http://127.0.0.1:8000
      public function upload_material(int $courseid, string $filepath, string $filename, ?string $materialid = null): array; // POST /course/materials/upload
      public function delete_file(int $courseid, string $filename, ?string $materialid = null): array; // DELETE /course/materials/file (form body)
      public function grade(array $payload, string $requestid): array; // POST /assign/answer, header X-Request-ID
  }
  ```
  Every method returns `['success' => bool, 'error' => ?string, 'status' => int, 'data' => array]` and never throws for HTTP/network errors. The default `$http` is `new \core\http_client(['ignoresecurity' => true, 'timeout' => $timeout, 'connect_timeout' => 30])`. The bearer header is sent only when `$apikey !== ''`.

- [ ] **Step 1: Write failing tests** with `new \GuzzleHttp\Client(['handler' => \GuzzleHttp\HandlerStack::create($mock)])` and `Middleware::history`:
  - `test_upload_sends_multipart_with_material_id`: the request is `POST {url}/course/materials/upload`; the multipart body contains `course_id=7`, `material_id=airagmaterial:3` and the filename; the `Authorization: Bearer k` header is present.
  - `test_material_id_is_omitted_when_null`: no `material_id` part (old backends stay happy).
  - `test_http_error_returns_failure_with_status`: a 503 response → `success=false`, `status=503`, `error` contains the server `detail`.
  - `test_connection_error_never_throws`: `ConnectException` → `success=false`, `status=0`.
  - `test_no_auth_header_without_api_key`.
- [ ] **Step 2: Run** `moodle-plugin-ci phpunit` (CI) → FAIL (class missing).
- [ ] **Step 3: Implement** `rag_client`; switch the two `mod_airagmaterial` functions to `rag_client::for_component('mod_airagmaterial')` (behavior otherwise unchanged).
- [ ] **Step 4: Run** → PASS; `make lint-php` clean.
- [ ] **Step 5: Commit** `refactor(moodle): route mod_airagmaterial RAG calls through an injectable client`.

### Task 3: Modularize `mod_airagassign/lib.php`

**Files:**
- Create: `moodle-plugins/mod_airagassign/classes/local/rubric_builder.php`, `material_scope.php`, `grading_service.php`; tests `moodle-plugins/mod_airagassign/tests/local/{rubric_builder,material_scope,grading_service}_test.php`
- Modify: `moodle-plugins/mod_airagassign/lib.php`, `classes/task/grade_submission.php`, `classes/task/grade_all_submissions.php`, and every page that calls the moved functions (`grep -rn "airagassign_" moodle-plugins/mod_airagassign --include=*.php`)

**Interfaces:**
- Consumes: `\mod_airagmaterial\local\rag_client` (Task 2).
- Produces:
  - `rubric_builder::build(int $assignid): array` and `rubric_builder::build_moodle(stdClass $assign): array` (today's `airagassign_build_rubric` / `airagassign_build_moodle_rubric`), `rubric_builder::sync_moodle(stdClass $data): void`.
  - `material_scope::linked_filenames(int $assignid, int $contextid): array`, `material_scope::unready_materials(int $assignid): array`, `material_scope::describe_unready(array $materials, \context $context): string`.
  - `grading_service::__construct(?rag_client $client = null)`, `grading_service::grade_submission(stdClass $assign, stdClass $submission, \context_module $context): array`, `grading_service::record_failure(int $submissionid, string $error, string $requestid = ''): void`, `grading_service::normalize_confidence($value): float`.
  - `lib.php` keeps the Moodle API (`airagassign_supports`, `*_add/update/delete_instance`, grade-item functions, `airagassign_pluginfile`, view/post actions, `airagassign_get_uploaded_files`). Moved functions are deleted (they are plugin-internal; no deprecation shims).

- [ ] **Step 1: Write characterization tests** against the *current* functions:
  - `rubric_builder_test`: custom criteria (`Accuracy` 50, `Clarity` 20) → the exact array shape today's `airagassign_build_rubric()` returns; a Moodle-rubric assignment without a definition → `[]`.
  - `material_scope_test`: two linked materials (one `completed` with a vectorized file `w1.pdf`, one `queued`) → `unready_materials()` lists only the queued one; `linked_filenames()` returns `['w1.pdf']`; `describe_unready()` is `"Week 2 (Queued for vectorization)"`.
  - `grading_service_test` (mocked client): essay mode posts `source_filter=['w1.pdf']`, stores `ai_grade`, `ai_feedback`, `confidence` and status `ai_suggested`; an HTTP 500 → status `grading_failed` with `grading_error` set; any unready material → no HTTP request and the `linkedmaterials_not_ready` message.
- [ ] **Step 2: Run** → the tests pass against the old functions (they are a safety net).
- [ ] **Step 3: Move the code** into the three classes, point the tests at the new API, and update every caller. HTTP goes through `rag_client::for_component('mod_airagassign')`.
- [ ] **Step 4: Verify** PHPUnit is green and `wc -l moodle-plugins/mod_airagassign/lib.php` ≤ 450.
- [ ] **Step 5: Commit** `refactor(moodle): split mod_airagassign lib.php into tested local services`.

### Task 4: Backend Owner-Scoped Vectors (`material_id`)

**Files:**
- Modify: `backend/src/vectorstore/chroma_store.py`, `backend/src/vectorstore/filters.py`, `backend/src/grading/grader.py`, `backend/src/api/moodle_routes.py`, `backend/src/api/moodle_models.py`, `backend/src/__init__.py` (→ `1.4.0`), `docs/architecture.md`
- Test: `backend/tests/test_material_ownership.py` (new, real `chromadb.PersistentClient` with telemetry off), `backend/tests/test_moodle_endpoints.py`

**Interfaces:**
- Produces:
  - Chunk metadata key `material_id` (string, `^[a-z_]+:[0-9]+$`, validated; invalid → HTTP 400).
  - `VectorStore.delete_document_by_source(source_name, course_id=None, material_id: Optional[str] = None) -> bool` — with `material_id`: deletes chunks of that source owned by it **plus** unowned (legacy) chunks of that source; without: deletes **only unowned** chunks of that source.
  - `EssayGrader.ingest_course_materials(..., material_id: Optional[str] = None)` — stamps `material_id` on every chunk and uses the rule above for replace-before-add.
  - `build_chroma_where_filter(..., material_ids: Optional[Sequence[str]] = None)` → `material_id` `$eq`/`$in` clause.
  - `POST /course/materials/upload` and `DELETE /course/materials/file`: optional form field `material_id`; with it the disk copy lives in `uploads/course_{id}/{slug(material_id)}/`.
  - `MoodleAssignRequest.material_ids: Optional[List[str]] = None`, AND-ed with `source_filter` / `module_filter`; an explicitly empty list → HTTP 400 (existing fail-closed rule).

- [ ] **Step 1: Write failing tests** (`test_material_ownership.py`):
  - `test_same_filename_two_materials_are_isolated`: ingest `notes.txt` as `airagmaterial:1` and as `airagmaterial:2`; deleting with `material_id=airagmaterial:1` leaves material 2's chunks (count unchanged) and removes material 1's.
  - `test_legacy_delete_only_touches_unowned_chunks`: an owned and an unowned `notes.txt`; delete without `material_id` → the owned chunks survive.
  - `test_owned_upload_replaces_legacy_chunks_of_same_source`: an unowned `notes.txt` exists; an upload with `airagmaterial:1` leaves only owned chunks.
  - `test_where_filter_material_ids`: `build_chroma_where_filter(material_ids=["airagmaterial:1","airagassign:5"])` == `{"material_id": {"$in": [...]}}`.
  - Endpoint tests: `/assign/answer` with `material_ids` forwards `{"$and": [source clause, material_id clause]}`; `material_ids: []` → 400; `material_id="../x"` → 400; a request without the new fields produces exactly today's filter (backward-compat guard).
- [ ] **Step 2: Run** `python tests/run_offline.py` → the new tests FAIL.
- [ ] **Step 3: Implement**; unowned detection = `collection.get(where={"source": ...})`, then select ids whose metadata lacks `material_id` (Chroma 0.6.3 cannot filter on a missing key).
- [ ] **Step 4: Run** → PASS; update the `docs/architecture.md` Moodle table and the scoped-retrieval note.
- [ ] **Step 5: Commit** `feat(api): owner-scoped material vectors via optional material_id`.

### Task 5: `mod_airagmaterial` Owner-Scoped Vectorization + Migration

**Files:**
- Modify: `moodle-plugins/mod_airagmaterial/lib.php`, `classes/task/vectorize_material.php`, `db/upgrade.php`, `version.php` (`2026112100` / `1.2.0`), `lang/{en,id}/airagmaterial.php`
- Delete: `moodle-plugins/mod_airagmaterial/classes/local/vector_ownership.php` (owner scoping replaces the shared-filename guard)
- Test: `moodle-plugins/mod_airagmaterial/tests/vectorize_test.php`, `tests/upgrade_test.php`

**Interfaces:**
- Consumes: `rag_client` (Task 2), backend `material_id` (Task 4).
- Produces: `airagmaterial_material_owner(int $materialid): string` → `"airagmaterial:{id}"`; `airagmaterial_queue_owner_migration(): int` (sets every material with files to `queued`, queues one `vectorize_material` task each, returns the count; makes **no HTTP call**).

- [ ] **Step 1: Write failing tests** (mocked client via `\core\di` or an injected `rag_client`):
  - `test_vectorize_sends_material_owner`: each upload carries `material_id=airagmaterial:{id}`.
  - `test_removed_file_is_deleted_with_owner`: a file removed from the material → `delete_file(..., 'airagmaterial:{id}')`.
  - `test_task_for_deleted_material_exits_quietly`: queue the task, delete the material, run the task → no HTTP request, no exception.
  - `test_queue_owner_migration_queues_without_http`: three materials (two with files) → returns 2; both `queued`; two adhoc tasks; zero HTTP requests recorded.
- [ ] **Step 2: Run** (CI) → FAIL.
- [ ] **Step 3: Implement**; the `upgrade.php` savepoint `2026112100` calls `airagmaterial_queue_owner_migration()`; the lang string `upgrade_revectorize_notice` (en/id) explains that materials are re-vectorized after the upgrade and grading waits for them (the Cycle 1 readiness gate).
- [ ] **Step 4: Run** → PASS; `moodle-plugin-ci savepoints` green.
- [ ] **Step 5: Commit** `feat(moodle): owner-scoped material vectors with queued post-upgrade re-vectorization`.

### Task 6: `mod_airagassign` Reference-File Status, Owner Scoping, `material_ids`

**Files:**
- Modify: `moodle-plugins/mod_airagassign/db/install.xml` (+ table `airagassign_manualfiles`: `id`, `assignid` FK, `filename` char(255), `contenthash` char(40), `status` char(20) `pending|queued|processing|completed|failed`, `error_message` text, `timemodified`; unique index `(assignid, filename)`), `db/upgrade.php`, `version.php` (`2026112100` / `1.2.0`, dependency `mod_airagmaterial => 2026112100`), `lib.php` (add/update instance queue the task instead of synchronous vectorization), `classes/local/material_scope.php`, `classes/local/grading_service.php`, `view.php` / `grade.php` (status badge + "Re-vectorize reference file" action with `require_sesskey()` and `mod/airagassign:manage`), `backup/moodle2/restore_airagassign_stepslib.php` (queue after restore), `lang/{en,id}/airagassign.php`
- Create: `moodle-plugins/mod_airagassign/classes/task/vectorize_manualfile.php`
- Test: `moodle-plugins/mod_airagassign/tests/manualfile_test.php`, extend `tests/local/grading_service_test.php`

**Interfaces:**
- Consumes: Tasks 2–5.
- Produces: `airagassign_manualfile_owner(int $assignid): string` → `"airagassign:{id}"`; `material_scope::unready_manualfiles(int $assignid, int $contextid): array` (files whose row is missing, not `completed`, or whose `contenthash` differs from the stored file); `material_scope::owner_ids(int $assignid, int $contextid): array` (completed linked materials + the assignment owner when it has completed manual files); `\mod_airagassign\task\vectorize_manualfile` (custom data `{assignid}`).

- [ ] **Step 1: Write failing tests:**
  - `test_failed_manualfile_blocks_grading_with_reason`: a manual file row `failed` → `grade_submission()` returns `success=false` with the `manualfile_not_ready` string naming the file; no HTTP request.
  - `test_grading_payload_has_material_ids_and_source_filter`: one completed material and one completed manual file → the payload holds `material_ids=['airagmaterial:{m}','airagassign:{a}']` **and** `source_filter` (keeps backend 1.3.0 scoped).
  - `test_stale_task_does_not_mark_new_content`: queue the task, replace the file (new content hash), run → the stored `contenthash` equals the *new* file and the upload used the new content.
  - `test_task_for_deleted_assignment_exits_quietly`.
  - `test_save_queues_instead_of_uploading`: `add_instance` with a manual file → one queued task, zero HTTP requests during the request.
  - `test_upgrade_queues_existing_manualfiles`.
- [ ] **Step 2: Run** (CI) → FAIL.
- [ ] **Step 3: Implement**; the readiness check in `grading_service` runs `unready_materials()` then `unready_manualfiles()`; `linked_filenames()` only includes **completed** manual files.
- [ ] **Step 4: Run** → PASS (PHPUnit, savepoints, backup/restore test: a restored assignment gets `queued` rows).
- [ ] **Step 5: Commit** `feat(moodle): track reference-file vectorization and scope grading by owner`.

### Task 7: Privacy API Providers

**Files:**
- Create: `moodle-plugins/mod_airagassign/classes/privacy/provider.php`, `moodle-plugins/mod_airagmaterial/classes/privacy/provider.php`, `moodle-plugins/local_assign_ai_rag/classes/privacy/provider.php`, tests `moodle-plugins/{mod_airagassign,local_assign_ai_rag}/tests/privacy/provider_test.php`, `moodle-plugins/mod_airagmaterial/tests/privacy/provider_test.php`
- Modify: the `lang/{en,id}` files of the three plugins (`privacy:metadata:*` strings), each `version.php` (`local_assign_ai_rag` `2026112100` / `1.1.3`)

**Interfaces:**
- `mod_airagmaterial`: `\core_privacy\local\metadata\null_provider` (like `mod_resource`: course material, no per-user data); the reason string states that files are sent to the configured RAG server.
- `mod_airagassign`: `metadata\provider`, `request\plugin\provider`, `request\core_userlist_provider`. Metadata: `airagassign_submissions` (`userid`, `grade`, `ai_grade`, `ai_feedback`, `feedback`, `ai_response`, `graded_by`, `teacher_note`, `confidence`, `timecreated`, `timegraded`), `airagassign_answers` (`answertext`, `score`, `ai_score`, `ai_feedback`, `feedback`, `ai_response`), external location `rag_server` (`question`, `answertext`, `rubric` — no user identity is sent). Contexts: module contexts where the user has a submission or is `graded_by`. Export: one record per submission with its answers under `[get_string('submissions','airagassign')]`. Delete for user: delete their submissions + answers; set `graded_by = 0` where they graded.
- `local_assign_ai_rag`: same three interfaces. `local_assign_ai_rag_pending` (`userid`, `message`, `grade`, `rubric_response`, `citations`, `confidence`, `retrieved_docs`, `usermodified`) in the module context of `assignmentid` (= cmid); `local_assign_ai_rag_config` / `_rubric` (`usermodified`) in the module context; `local_assign_ai_rag_materials` (`usermodified`) in the course context; external location `rag_server`. Delete for user: delete their pending rows; anonymise `usermodified` to `0` elsewhere.

- [ ] **Step 1: Write failing tests** extending `\core_privacy\tests\provider_testcase`: `test_get_metadata`, `test_get_contexts_for_userid`, `test_export_user_data` (`writer::with_context($ctx)->get_data([...])` holds the answer text), `test_delete_data_for_user_keeps_other_students` (Review Focus 5), `test_delete_data_for_users`, `test_delete_data_for_all_users_in_context`, `test_teacher_fields_are_anonymised` (`graded_by` / `usermodified` → 0, rows kept); for `mod_airagmaterial` a null-provider test.
- [ ] **Step 2: Run** (CI) → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS (`validate` checks the lang strings).
- [ ] **Step 5: Commit** `feat(moodle): add Privacy API providers to the remaining plugins`.

### Task 8: Full-Stack Compose Integration Tests + Local-Extras Image

**Files:**
- Create: `backend/integration_tests/__init__.py`, `backend/integration_tests/stub_ai.py`, `backend/integration_tests/test_full_stack.py`, `backend/docker-compose.ci.yml`
- Modify: `.github/workflows/ci.yml` (jobs `integration`, `image-local-extras`), `CONTRIBUTING.md` (how to run it locally)

**Interfaces:**
- `stub_ai.py`: FastAPI on port 9000. `POST /v1/embeddings` → deterministic 64-dim hashed bag-of-words vectors; `POST /v1/chat/completions` → JSON grade citing every `*.txt|*.pdf` source named in the prompt, `score=80`, `confidence=0.85` (same contract as the Cycle 2 stand-in).
- `docker-compose.ci.yml`: adds service `stub-ai` (the API image, `command: uvicorn integration_tests.stub_ai:app --host 0.0.0.0 --port 9000`, `./integration_tests` mounted read-only — the image's `.dockerignore` excludes tests), sets on `api` `LLM_PROVIDER=openai_compatible`, `LLM_BASE_URL=http://stub-ai:9000/v1`, `EMBEDDING_PROVIDER=openai_compatible`, `EMBEDDING_BASE_URL=http://stub-ai:9000/v1`, `EMBEDDING_MODEL=stub-embed`, `API_AUTH_TOKEN=ci-token`, `API_REPLICAS=2`.
- `test_full_stack.py` reads `RAG_IT_URL` (default `http://127.0.0.1:8000`) and `RAG_IT_TOKEN`, and skips the module if the URL is unreachable (so the unit runner never depends on it). It is **not** under `tests/`.

- [ ] **Step 1: Write the integration tests:** `test_health_is_open_and_routes_need_token` (401 without a token); `test_v1_week1_to_3_scope_never_cites_week4` (the four example files); `test_same_filename_materials_are_isolated_end_to_end` (Moodle routes with `material_id`); `test_concurrent_grading_during_upload_has_no_5xx` (40 parallel grades + 1 upload, 0 responses ≥ 500 — the PRD < 1% target); `test_requests_are_balanced_across_replicas` (≥ 2 distinct `X-API-Instance` values over 20 requests); `test_embedding_mismatch_returns_409` (pre-create a collection with a different `embedding_provider` through the Chroma HTTP API, then grade → 409).
- [ ] **Step 2: CI job `integration`** (needs `backend-tests`): `cp .env.example .env`, `docker compose -f docker-compose.yml -f docker-compose.ci.yml up -d --build --wait`, `python -m unittest discover -s integration_tests -v`, `if: failure()` → `docker compose logs`, `always()` → `down -v`. **Job `image-local-extras`:** `docker build --build-arg INSTALL_LOCAL_EXTRAS=true`, then `docker run --rm <img> python -c "import fastembed"`.
- [ ] **Step 3: Push and confirm** both jobs are green (local Docker is unavailable on this machine; CI is the source of truth).
- [ ] **Step 4: Commit** `test(integration): full-stack compose tests and local-extras image build in CI`.

### Task 9: Moodle 4.4 Validation (gated)

**Files:** `.github/workflows/ci.yml`; conditionally `moodle-plugins/{mod_airagmaterial,mod_airagassign}/version.php`, `README.md`, `docs/moodle-setup.md`, PRD §2.2

- [ ] **Step 1:** Add the matrix leg `{MOODLE_404_STABLE, php 8.1}` for `mod_airagmaterial` and `mod_airagassign` only, with `continue-on-error: true` and a pre-install step that rewrites `requires` to `2024042200` in the CI workspace copy only (`sed -i`).
- [ ] **Step 2: Decide from the result.** Green → set `$plugin->requires = 2024042200` in both modules, make the leg blocking, and document "4.4+" for the two activity modules (`local_assign_ai_rag` / `aiprovider_rag` stay 4.5+ because of the Core AI subsystem). Red → remove the leg, keep 4.5, and note the failing API in `docs/moodle-setup.md`.
- [ ] **Step 3: Commit** `ci(moodle): validate activity modules on Moodle 4.4` (+ the `requires` change when green).

### Task 10: CHANGELOG and Tag-Driven Release Workflow

**Files:**
- Create: `CHANGELOG.md` ([Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/); sections `[Unreleased]` and `[1.0.0] - YYYY-MM-DD` summarizing Cycles 1–3 with a component-version table), `scripts/release-notes.sh`, `.github/workflows/release.yml`
- Modify: `README.md` (release/installation section), `Makefile` (`release-notes VERSION=…`)

**Interfaces:**
- `scripts/release-notes.sh <version>` prints the body of `## [<version>]` from `CHANGELOG.md` and exits non-zero when the section is missing or empty.
- `release.yml`: `on: push: tags: ['v*']` + `workflow_dispatch` (input `tag`, `dry_run: true` by default); `permissions: contents: write` (this workflow only). Steps: tag matches `^v[0-9]+\.[0-9]+\.[0-9]+$`; tagged commit is reachable from `origin/main`; `release-notes.sh ${TAG#v}`; `./scripts/build-plugins.sh`; `sha256sum dist/*.zip > dist/SHA256SUMS`; unless dry-run: `gh release create "$TAG" dist/*.zip dist/SHA256SUMS --title "$TAG" --notes-file notes.md --verify-tag`.

- [ ] **Step 1: Write a failing check:** a CI step runs `scripts/release-notes.sh 1.0.0` (expect output containing `mod_airagassign` and `1.2.0`) and `scripts/release-notes.sh 9.9.9` (expect non-zero exit).
- [ ] **Step 2: Implement** the script, the CHANGELOG and the workflow; run `workflow_dispatch` with `dry_run=true` on the branch → green and the ZIP artifacts are uploaded.
- [ ] **Step 3: Commit** `ci(release): CHANGELOG and tag-driven GitHub release with plugin ZIPs`.

### Task 11: Replace `main` and Publish `v1.0.0` (maintainer-run)

**Files:** `docs/PRD.md` §8 (status: delivered; `main` replaced; release `v1.0.0`), `CHANGELOG.md` (release date)

The force-push and the tag are irreversible and outward-facing: the agent prepares and verifies; the **maintainer runs** the push commands after an explicit go-ahead in chat.

- [ ] **Step 1:** Merge any new commits from the other machine's branches (Global Constraints), push, and confirm every CI job is green on the final commit.
- [ ] **Step 2: Archive the old history:** `git tag -a legacy/v1.1.0-prototype e52235e -m "Pre-open-source prototype (backend 1.1.0)"` then `git push origin legacy/v1.1.0-prototype`.
- [ ] **Step 3: Replace `main`** (maintainer): `git push --force-with-lease=main:e52235e origin feat/cycle3-moodle-hardening-release:main`; then on GitHub keep `main` as the default branch and enable branch protection (require the CI checks, block force-pushes from now on).
- [ ] **Step 4: Release:** set the date in `CHANGELOG.md` `[1.0.0]`, update PRD §8, commit `docs: release v1.0.0` on `main` (via PR), then `git tag -a v1.0.0 -m "v1.0.0"` and `git push origin v1.0.0` → the release workflow publishes. Verify the release page lists 4 ZIPs + `SHA256SUMS` and that the ZIPs install on a Moodle 4.5 site (manual smoke: install, create material, vectorize, grade one essay).
- [ ] **Step 5:** Tell the other machine to re-base its work: `git fetch && git switch main && git reset --hard origin/main` for clean checkouts, or rebase any local branches onto the new `main`.

---

## Task Dependency Order

```text
1 ─► 2 ─► 3 ─┐
     4 ──────┼─► 5 ─► 6 ─► 7 ─┐
             │                ├─► 9 ─► 10 ─► 11
     8 (needs 4) ─────────────┘
```

Task 4 (backend) and Task 8 (integration) can run in parallel with Tasks 1–3. Task 7 only needs Task 6's final schema.

## Risks & Mitigations

| Risk | Impact | Mitigation |
| :--- | :--- | :--- |
| Post-upgrade re-vectorization load | Many queued tasks right after the upgrade | Tasks are adhoc (cron-paced); the readiness gate refuses grading meanwhile, with a visible reason |
| `moodle-plugin-ci` matrix cost / flakiness | Slow CI | `fail-fast: false`, Postgres only, PHPUnit without Behat |
| Mixed plugin/backend versions during rollout | Wrong scope or deleted vectors | Optional fields; legacy calls touch only unowned chunks; contract tests both ways (Done 7) |
| Force-replacing `main` | The other machine diverges | Archive tag first, `--force-with-lease`, explicit re-base instructions (Task 11 Step 5) |
| Codechecker debt in existing PHP | Red CI | Informational step only; a style clean-up is a later task |

## Out of Scope

- Behat acceptance tests (PHPUnit covers Cycle 3's Done criteria; Behat needs a browser stack and a live AI stub).
- `POST /v1/namespaces/{ns}/grade/batch`, non-Moodle LMS plugins, a Moodle-wide coding-style clean-up, refactoring `mod_form.php` / `local_assign_ai_rag` HTTP code to `rag_client` (`local_assign_ai_rag` only gains Privacy in this cycle).
