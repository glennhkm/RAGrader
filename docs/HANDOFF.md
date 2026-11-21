# RAGrader Handoff: State after v1.0.1 and the Plan for Cycle 4

> **For the next coding agent:** read this file completely before you change anything. Then read, in this order:
> [`docs/PRD.md`](PRD.md) (§2.2, §3.2, §8), [`CHANGELOG.md`](../CHANGELOG.md), [`docs/architecture.md`](architecture.md), and the most recent plan in [`docs/superpowers/plans/`](superpowers/plans/).
> Last updated **2026-11-22**, on laptop A (the laptop that produced Cycle 3 and v1.0.1). Work continues on laptop B, where the real grading data is kept.

---

## 0. TL;DR

- Releases **`v1.0.0`** (2026-11-20) and **`v1.0.1`** (2026-11-22) are published on GitHub, with 4 plugin ZIPs and `SHA256SUMS`. CI is green on `main` = `992f0de`.
- **`main` was force-replaced on 2026-11-20.** The old prototype history is kept as tag `legacy/v1.1.0-prototype` (`e52235e`). A local `main` on laptop B that predates this **must be reset** (see §1), not merged.
- The three roadmap cycles in the PRD are done. A security and maintenance release (v1.0.1) followed.
- **Next up is Cycle 4, "Grading Quality & Trust":** prove with numbers that AI grades can be trusted, then improve them. Brainstorming has started but no design has been approved yet (see §8). The labelled data needed for it is on laptop B.
- **Never commit real student data.** The repository is public. Put it under any `private-data/` folder, which is git-ignored (see §8.6).

---

## 1. Syncing laptop B (do this first)

```bash
git fetch --all --tags --prune
git switch main
git reset --hard origin/main      # main was rewritten on 2026-11-20; do NOT merge the old main
git log --oneline -1              # expect 992f0de (or newer) "docs: date the v1.0.1 release"
```

- **Old local branches.** Any local branch that was based on the *old* `main` (pre-`v1.0.0`) has unrelated history. To keep its work, cherry-pick its commits onto a new branch from the new `main`. Do not merge or rebase it wholesale.
- **Branches already merged into `main`** can be deleted on GitHub: `feat/cycle1-core-generalization`, `feat/cycle2-model-freedom-config`, `feat/cycle3-moodle-hardening-release`, `fix/cycle1-scope-hardening`, `fix/cycle2-review-followups` and `fix/v1.0.1-hardening`.
- **Python environment.** Recreate it with **Python 3.12**. The Docker image and CI use 3.12, and 3.10 is end of life.

```bash
cd backend
uv venv -p 3.12 .venv            # or: python3.12 -m venv .venv
. .venv/bin/activate
uv pip install -r requirements.txt   # or pip install -r requirements.txt
python tests/run_offline.py -v       # expect: Ran 221 tests ... OK (skipped=1)
```

---

## 2. Release snapshot

| Item | Value |
|---|---|
| `main` | `992f0de` |
| Tags | `legacy/v1.1.0-prototype` (`e52235e`, archived prototype), `v1.0.0` (`4d43f51`), `v1.0.1` (`992f0de`) |
| Releases | https://github.com/glennhkm/RAGrader/releases/tag/v1.0.0 and https://github.com/glennhkm/RAGrader/releases/tag/v1.0.1 |
| GitHub license detection | MIT. It was `NOASSERTION` before v1.0.1 because the LICENSE files were empty. |

| Component | Version | Moodle `$plugin->version` | Requires |
|---|---|---|---|
| backend (FastAPI) | **1.4.1** (`backend/src/__init__.py`) | - | Python 3.12 |
| `mod_airagmaterial` | **1.2.1** | `2026112101` | Moodle 4.5 (`2024100700`) |
| `mod_airagassign` | **1.2.1** | `2026112101` | Moodle 4.5; depends on `mod_airagmaterial >= 2026112100` |
| `local_assign_ai_rag` | 1.1.3 | `2026112100` | Moodle 4.5 |
| `aiprovider_rag` | 1.1.1 | `2026071901` | Moodle 4.5 |

**CI** ([`.github/workflows/ci.yml`](../.github/workflows/ci.yml)) has 21 jobs:

- `moodle-plugins` (lint and ZIP build), `release-notes`, `backend-tests` (Python 3.12, network blocked) and `image-local-extras`.
- `integration`: the full Docker Compose stack with 2 replicas, Redis, Chroma and a stub AI.
- 16 `moodle-plugin-ci` legs: 4 plugins × Moodle **4.5 LTS (PHP 8.1), 5.1, 5.2 and 5.3 LTS (PHP 8.3)**, on PostgreSQL 17.

**Release** ([`.github/workflows/release.yml`](../.github/workflows/release.yml)):

- Pushing tag `vX.Y.Z` builds the ZIPs and publishes the release.
- The tag must be reachable from `main`, and `CHANGELOG.md` must contain a **dated** `## [X.Y.Z] - YYYY-MM-DD` section, not "Unreleased".
- `workflow_dispatch` with `dry_run: true` (the default) and an optional `ref` builds the ZIPs without publishing.

---

## 3. What was built on laptop A (chronological)

### 3.1 Cycle 1 and 2 follow-ups ("small notes")

These ran on new branches, as you required (`fix/cycle1-scope-hardening`, `fix/cycle2-review-followups`):

- Deleting a course collection also deletes its uploaded files.
- Document image captions are labelled in the answer's language.
- Caption text and answer file paths are kept out of INFO logs.
- Chroma telemetry is off by default.
- Local-mode defaults work, and a reranker fallback is reported loudly.
- The CLI gained tag-scoped grading and a lightweight install.
- The PRD was synced, and backend bumped to 1.3.0.

### 3.2 Cycle 2 audit and Cycle 3

All findings from the Cycle 2 audit were fixed, then Cycle 3 ran as 11 tasks. Plan: [`docs/superpowers/plans/2026-11-20-cycle3-moodle-hardening-release.md`](superpowers/plans/2026-11-20-cycle3-moodle-hardening-release.md). Commits run from `4af4934` to `4d43f51`.

**Owner-scoped vectors** (backend 1.4.0)

- Ingestion takes an optional `material_id` matching `^[a-z_]+:[0-9]+$`, such as `airagmaterial:12` or `airagassign:7`. It is stamped on every chunk.
- Deletes with a `material_id` remove that owner's chunks plus *unowned legacy* chunks of the same source. Deletes without one remove only unowned chunks.
- `/assign/answer` takes `material_ids`, AND-ed with `source_filter`. An explicitly empty list returns HTTP 400.
- A vector store failure during delete now returns **HTTP 500**, not 200 with `success:false`.

**`mod_airagmaterial`**

- RAG calls go through an injectable `\mod_airagmaterial\local\rag_client` and `http_factory`, using `\core\http_client`. Tests mock it via `\core\di`.
- After upgrade, re-vectorization is queued.
- Backup and restore was fixed: `prepare_activity_structure` was missing, and the material files were never annotated.

**`mod_airagassign`**

- `lib.php` was split into tested local services: `material_scope`, `grading_service` and `rubric_builder`.
- Reference ("manual") files are tracked in table `airagassign_manualfiles`, with statuses pending, queued, processing, completed, failed and deleting. The adhoc task `vectorize_manualfile` processes them.
- Grading is refused while any linked material is not fully vectorized.
- **Security:** the reference file now requires `mod/airagassign:grade` to download.

**Privacy and tests**

- Privacy API providers exist in all 4 plugins. Deleting a whole context also anonymises teacher references.
- Every plugin has data generators and PHPUnit tests, run through `moodle-plugin-ci` in CI.
- Full-stack integration tests live in `backend/integration_tests/` (`stub_ai.py`, `test_full_stack.py`). They fail instead of skipping when `CI` or `RAG_IT_EXPECT_REPLICAS` is set.

**Release process**

- `CHANGELOG.md` (Keep a Changelog format), `scripts/release-notes.sh` and the tag-driven release workflow.
- `main` was replaced, and `v1.0.0` was tagged.

### 3.3 v1.0.1: security and maintenance (commits `370f4c3` to `992f0de`)

**Licensing**

- `LICENSE` and `backend/LICENSE` contain the MIT text. They were 0 bytes in v1.0.0.
- A test (`test_deploy_config.py`) guards this.

**Runtimes**

- Python 3.12 in the Dockerfile and CI. A test guards the base image.
- The Moodle CI matrix now covers only branches with security support. The activity modules require 4.5 again; Moodle 4.4 support from Cycle 3 Task 9 was dropped because 4.4 is end of life.

**Grading integrity** ([`backend/src/rag/grading_guard.py`](../backend/src/rag/grading_guard.py), wired in `pipeline.grade_essay`)

1. `fence_answer`: the answer is wrapped in `student_answer` tags inside both prompt templates, and tags inside the answer are neutralised. The templates' first instruction says the answer is data, not instructions. The Indonesian template snapshot (`tests/fixtures/prompt_template_id.txt`) was updated on purpose.
2. `detect_injection`: high-precision regexes for English and Indonesian. Signal labels are `override_instructions`, `grade_request`, `role_markup`, `grading_json` and `fence_tag`.
3. `ground_citations`: a citation is kept only if its text occurs in one retrieved chunk.
   - Matching is a normalised substring match, or at least 60% word-trigram coverage for small drift. Parts separated by `...` must all be in the same chunk.
   - `source` and `page` are taken from the chunk's metadata, and the model's page is dropped if the chunk has none.
4. `apply_integrity_checks`: any warning caps confidence at **0.3**, which is `SUSPECT_CONFIDENCE_CAP`. That is below the CLI's default review threshold of 0.6. An unparseable LLM response gets confidence **0.0** (it was 0.5).
5. **New response field:** `integrity_warnings: List[str]` in `/v1/namespaces/{ns}/grade`, `/assign/answer` and legacy `/grade`, plus a new `integrity_warnings` CSV column in the CLI. Rows with warnings are flagged for review.

**Integration stub:** it now quotes chunks verbatim, like an honest model. The full-stack test also covers an injected answer.

---

## 4. Code map (where things live)

```
backend/src/
  utils/config.py        the ONLY module that reads env; typed Settings (get_settings())
  api/app.py             create_app() + lifespan runtime; legacy routes (/grade, /status ...)
  api/v1_routes.py       generic /v1/namespaces/{ns}/... API (materials, grade, collections)
  api/moodle_routes.py   Moodle adapter: /assign/answer, /course/materials/*, /moodle/status
  api/request_utils.py   normalize_grade() (percent -> Moodle scale, criterion caps, confidence 0..1)
  api/locking.py         Redis RW locks per namespace/course
  rag/pipeline.py        RAGPipeline.grade_essay(): retrieve -> prompt -> LLM -> parse -> integrity checks
  rag/prompts.py         en/id templates (same JSON schema), language detection
  rag/prompt_builder.py  build_prompt (fences answer), parse_llm_response (first "{" .. last "}" + json.loads)
  rag/grading_guard.py   v1.0.1 integrity checks
  rag/llm.py             provider_chain / openai_compatible / local (llama.cpp); LLM_TEMPERATURE default 0.3
  rag/retriever.py, reranker.py   retrieval + rerankers (none/bm25/local_cross_encoder/http_rerank/llm_rerank/pinecone)
  vectorstore/           Chroma 0.6.3 store, embeddings (collection name includes the embedding model)
  cli.py                 /v1 CLI incl. grade-csv batch grading (review_threshold default 0.6)
backend/tests/           offline unit tests (run via tests/run_offline.py, which blocks network)
backend/integration_tests/  compose stack tests + stub_ai.py
moodle-plugins/mod_airagmaterial, mod_airagassign, local_assign_ai_rag, aiprovider_rag
examples/week1_to_week4_quiz/  sample materials, rubric.json, 4 unlabeled answers, run_demo.sh
docs/                    PRD, architecture, deployment, moodle-setup, superpowers/plans (cycle plans)
```

Key data for Cycle 4 is in `mod_airagassign`'s `db/install.xml`:

- `airagassign_submissions`: `ai_grade` (AI suggestion), `grade` (final grade), `confidence`, `ai_response` (full JSON), `status` (`submitted`, `grading`, `grading_failed`, `ai_suggested`, `graded`), `graded_by` and `teacher_note`.
- `airagassign_answers` (per question): `ai_score`, `ai_feedback` and `ai_response`.

Every submission a teacher confirms or overrides in `grade_review.php` is therefore an "AI vs teacher" pair.

---

## 5. Conventions and process (keep these)

**Branches**

- Never commit straight to `main`. Use one new branch per cycle or fix set, such as `feat/cycle4-...` or `fix/...`.
- Push the branch so CI can prove it. Merge to `main` (fast-forward) and tag only with the owner's explicit approval.

**Commits**

- Use Conventional Commits (`feat(moodle): ...`, `fix(grading): ...`, `ci(...)`, `docs: ...`), one topic per commit, with a body that explains *why*.
- End each message with the agent's attribution trailer, if your agent uses one.

**Versions**

- The repo is released as a whole (`vX.Y.Z`), and each component keeps its own version.
- Every plugin change bumps `$plugin->version` (`YYYYMMDDXX`) and `release`. Every backend change bumps `backend/src/__init__.py`.
- Add an entry under `## [Unreleased]` in `CHANGELOG.md` as you go. Date the section before tagging.

**Compatibility**

- Moodle routes and fields stay backward compatible: add optional fields only.
- When the plugins need new backend behaviour, the upgrade notes must say "upgrade the backend first".

**Tests**

- Backend: `cd backend && python tests/run_offline.py -v`. Unit tests must not touch the network.
- Moodle PHPUnit runs **in CI** through `moodle-plugin-ci`. There is no local Moodle checkout on laptop A any more.
- The integration stack (`docker compose -f docker-compose.yml -f docker-compose.ci.yml up`) needs `backend/.env` and data directories owned by uid 10001. Don't overwrite a real `.env`.

**Moodle CI matrix:** follow https://moodledev.io/general/releases and drop branches when their security support ends.

| Branch | Security support ends |
|---|---|
| 4.5 LTS | 2027-10 |
| 5.1 | 2027-04 |
| 5.2 | 2027-10 |
| 5.3 LTS | 2029-10 |

**Workflow used so far**

- Each cycle went brainstorm, then a design/spec, then a written plan in `docs/superpowers/plans/YYYY-MM-DD-<topic>.md`, then task-by-task implementation with review, then CI, then release.
- Specs go to `docs/superpowers/specs/`.

---

## 6. Decisions already made (do not reopen without a reason)

**Release decisions**

- Replace `main` with the open-source line, and archive the prototype as `legacy/v1.1.0-prototype`.
- Repo release `v1.0.0`, with components keeping their own versions.

**Cycle 3 rulings**

- R1: tests mock HTTP through `http_factory` and `\core\di`.
- R3: Chroma is published on `127.0.0.1:18001` only in the CI override.
- R5: the `airagmaterial` generator keeps the real default status `queued`.
- R6: CI posts failing log tails as public annotations, because job logs need a sign-in.
- R12: three small form-save helpers stay in `mod_airagassign/lib.php`.
- R13: no student ids in `mtrace` output.
- R17: `graded_by` is a text label, not personal data.
- R18 and R23: a privacy deletion of a whole context also anonymises teacher references.
- R19: `graderid` becomes 0 when a teacher's data is deleted, so auto-approve falls back to manual review.
- R22: release dry runs accept any ref and never publish.

**v1.0.1 decisions**

- Backend 1.4.1 is a patch bump: the field is additive and the change is a security fix.
- The confidence cap is 0.3, and the trigram coverage threshold is 0.6.
- Citation source and page come from the chunk, and the model's page is dropped when the chunk has none.
- Activity modules require 4.5. Sites on 4.4 stay on the 1.0.0 modules.

---

## 7. Known gaps and debt (not done yet)

| # | Gap | Where | Size |
|---|---|---|---|
| G1 | **R24:** a restored AI RAG Material stays `pending` and is not queued for vectorization, so the teacher must re-vectorize it. | `mod_airagmaterial` restore steps | small |
| G2 | **R28:** `mod_airagassign` backup does not annotate the `intro` file area, so files embedded in the description are lost on restore. | `backup/moodle2/backup_airagassign_stepslib.php` | small |
| G3 | Plugins do not store or show `integrity_warnings`. Teachers only see the low confidence, not the reason. This needs a DB column (upgrade step) plus UI in `grade_review.php` and `view_result.php`. | `mod_airagassign`, `local_assign_ai_rag` | medium |
| G4 | `local_assign_ai_rag` still uses raw `curl` and grades course-wide, without material scoping or `material_ids`. | `local_assign_ai_rag` | medium |
| G5 | No structured output: there is no `response_format`/JSON-schema mode and no retry or repair. A malformed JSON response gives score 0 with confidence 0.0. | `rag/llm.py`, `prompt_builder.parse_llm_response` | medium |
| G6 | Grading is not deterministic (temperature 0.3, no seed). | `config.py`, `llm.py` | small |
| G7 | Confidence is still the model's self-report, only capped. It is not calibrated. | pipeline | Cycle 4 core |
| G8 | Dependencies: `chromadb==0.6.3` (latest 1.x needs a data migration plan, and the `posthog<6` pin belongs to 0.6), `openai<2` (latest 3.x), langchain 0.3 (the `Chroma` wrapper is deprecated; move to `langchain-chroma`), and GitHub Actions on Node 20 (deprecation warnings). | `backend/requirements.txt`, workflows | Cycle 5 |
| G9 | Moodle codechecker is informational only. It must be clean before listing in the Moodle Plugins Directory. | plugins | Cycle 5 |
| G10 | Operations: one shared bearer token (no per-client tokens or rate limiting), no metrics endpoint, no backup guide for Chroma and Redis, and no data-governance or DPA guide for sending essays to cloud LLMs. | backend, docs | Cycle 5+ |

**For the owner (manual):**

- Enable branch protection on `main` (require CI, block force-push).
- Delete the merged branches listed in §1.
- Smoke-install the v1.0.1 ZIPs on a real Moodle 4.5 or 5.x and grade one submission.

---

## 8. Next: Cycle 4, "Grading Quality & Trust" (detailed)

### 8.1 Why

Every test proves plumbing: scoping, API, privacy and CI. **Nothing yet measures whether AI grades match teachers.** Three of the PRD §3.2 KPIs depend on that measurement:

- Citation Groundedness ≥ 95%.
- Low-Confidence Flag Accuracy: overrides are more frequent below the threshold.
- Teacher agreement, which is implied by "trustworthy grades".

Cycle 4 makes trust measurable, then improves it against those numbers.

### 8.2 Where the brainstorming stopped

- The agent restated the theme and asked the owner one question: **who must be convinced that the grades can be trusted** (for example thesis examiners, the campus, or the open-source community), **and what real teacher-graded data exists?**
- The owner answered that **the data is on laptop B** and asked to continue there.
- **Still open, and to settle with the owner before any design:**
  1. **Audience and rigour.** A thesis or research evaluation (statistics, confidence intervals, a written method) or a product feature (a dashboard plus thresholds)?
  2. **The data itself.** Format (Moodle DB export, CSV or spreadsheet), size (number of answers, questions and graders), language mix (en/id), whether rubric scores per criterion exist, whether the matching course materials are available, and whether there are several graders per answer.
  3. **Which LLM(s) to evaluate**, and the budget for running the evaluation repeatedly (cloud or local model).
  4. **Where results live:** a report in the repo, a CI gate, or both.

**Inspect the data on laptop B first** (structure only, never commit it). Then ask these questions one at a time. Then present 2–3 approaches, and only then write the spec in `docs/superpowers/specs/YYYY-MM-DD-cycle4-grading-quality-design.md` and the plan.

### 8.3 Proposed workstreams

This is the agent's proposal and has not been approved yet.

**A. Evaluation harness** (first: everything else is measured with it)

- **Dataset format.** A versioned JSONL or CSV schema: `item_id`, `question`, `answer`, `rubric`, `max_grade`, `teacher_score` (and per-criterion scores if available), `language`, the materials reference (namespace or files), and optionally `split` (dev or test).
- **Two kinds of data:**
  - a small **public synthetic** set committed to the repo (built from `examples/week1_to_week4_quiz`, plus labelled answers written for testing);
  - the **private real** set, loaded from a `private-data/` path.
- **Runner.** A CLI subcommand or `backend/eval/` module that ingests materials into an isolated namespace, grades every item through the real pipeline, and writes per-item results and a summary (JSON plus Markdown).
- **Metrics:**
  - agreement: MAE and RMSE on the 0–100 scale, Quadratic Weighted Kappa on banded grades, Spearman rank correlation, and exact or adjacent agreement per band;
  - groundedness: the share of citations kept by `ground_citations`, and the share of grades with at least one grounded citation;
  - calibration: AUROC or AUPRC of confidence for predicting "|AI − teacher| > tolerance", ECE or reliability bins, and the override-rate gap above and below the threshold;
  - consistency: the spread of scores when the same answer is graded N times;
  - robustness: an adversarial set of injection attempts (en/id). Measure the score uplift versus the clean answer and the detection rate.
- **Reproducibility.** Record the model, provider, temperature, seed, prompt-template hash, embedding model and git SHA in every report. Use a fixed random seed for sampling.
- **CI.** Run a smoke evaluation on the public set with a recorded or stub LLM so the harness itself is tested. Real-model evaluations run manually or on a schedule with secrets, and never print private data.

**B. Deterministic and structured output** (G5, G6)

- Use temperature 0 (or a configurable grading temperature) and pass a `seed` where the provider supports it.
- Use `response_format` with a JSON schema when the provider supports it, otherwise fall back to the current extraction.
- Add one repair or retry attempt on invalid JSON.
- Validate with a Pydantic model: a missing criterion or score out of range triggers a warning and reduced confidence.

**C. Calibrated confidence** (G7)

- Replace the model's self-report with a score derived from measurable signals:
  - self-consistency (score variance over k samples, or two prompts);
  - citation groundedness ratio;
  - rubric coverage (all criteria scored);
  - retrieval strength (rerank or similarity scores);
  - integrity warnings;
  - parse repairs.
- Fit a simple calibrator (logistic or isotonic) on the dev split of the labelled data, and evaluate it on the test split. Keep the 0.3 integrity cap.
- Report the chosen review threshold with its expected override rate.
- The k-sample cost needs a config switch, for example `GRADING_CONSISTENCY_SAMPLES`.

**D. Moodle: close the loop**

- **G3:** store and show `integrity_warnings` (DB upgrade step, the review page, and privacy metadata).
- **Export.** Teachers or admins can export anonymised "AI vs teacher" pairs (`ai_grade`, `grade`, `confidence`, per-question scores and language) from `mod_airagassign` as CSV, with the evaluation dataset schema. This needs a capability check, contains no student identity, and must be documented in the privacy provider. It turns every deployment into a source of evaluation data.
- **G1 and G2:** quick fixes.

**E. Optional, if time allows:** `local_assign_ai_rag` modernisation (G4): `\core\http_client` and material scoping.

### 8.4 Suggested order and done criteria

1. **A (harness) and the public synthetic set.**
   - Done when one command produces a reproducible report.
   - The harness is unit-tested and runs in CI on the public set.
2. **Baseline run** on the real data (laptop B).
   - Done when baseline numbers are recorded in a report: model, date and git SHA, with no private content.
3. **B, then a re-run.**
   - Done when parse failures drop to about 0.
   - Consistency improves, and the agreement metrics do not regress.
4. **C, then a re-run.**
   - Done when confidence separates good from bad grades (the AUROC target is set from the baseline).
   - A documented threshold is chosen.
5. **D (G3, export, G1, G2)**, with PHPUnit across the CI matrix.
6. **Release.** Release v1.1.0, with backend 1.5.0 (new evaluation features and response semantics) and plugin minors. Add the CHANGELOG entry and PRD updates: §3.2 measured values, and a new Cycle 4 row in §8.

### 8.5 Anti-goals

Avoid these:

- Tuning prompts on the test split.
- Reporting metrics without the model and settings.
- Making grading slower by default without a switch.
- Breaking the existing Moodle and `/v1` contracts. Only add optional fields.

### 8.6 Data protection (mandatory)

- Real student answers and grades are personal data, and the repository is **public**.
- Keep them under a `private-data/` directory (git-ignored anywhere in the tree) or outside the repo.
- Before every commit, check that `git status` lists no data files.
- Reports committed to the repo may contain only aggregates and synthetic examples.
- If an export from Moodle includes names, emails or user ids, strip them before use.

---

## 9. Environment notes from laptop A

- `python3.12-venv` (ensurepip) was missing, so the test venv was created with `uv venv -p 3.12`.
- The `gh` CLI was not on PATH in the last session. CI status was read from the public GitHub REST API. Use `gh` on laptop B if it is installed.
- The local Moodle PHPUnit database (`ragrader_moodle_phpunit`, role `ragrader_test`) was dropped on laptop A. Moodle tests run in CI only.
- `backend/.env` is git-ignored. Copy from `.env.example` or `.env.dev.example`, and never commit real tokens.
