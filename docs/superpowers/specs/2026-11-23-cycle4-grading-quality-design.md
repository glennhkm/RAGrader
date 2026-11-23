# Cycle 4 Design: Grading Quality & Trust

- **Status:** draft for owner approval
- **Date:** 2026-11-23
- **Scope:** backend `src/evaluation/` (new), grading pipeline (`src/rag/`), `/v1` and `/assign/answer` (optional fields only), `mod_airagassign` (phase 4e), `docs/evaluation/` (new)

This document can be read without the conversation that produced it. Decisions the owner made are marked **[owner]**. Calls the agent made, which the owner may still override, are marked **[agent]**.

---

## 1. Intent

Every test so far proves plumbing: scoping, API, privacy and CI. Nothing measures whether RAGrader's grades agree with human graders, or whether its `confidence` means anything. Cycle 4 does two things:

1. Builds a fresh, rigorous evaluation that produces numbers that can be defended.
2. Improves grading quality and trustworthiness, one measured change at a time.

The owner decides later which results to use as evidence that RAGrader can be trusted **[owner]**, so the evaluation must hold up to publication-grade scrutiny **[owner]**.

The owner's thesis prototype is **not** a target **[owner]**. Its numbers may appear only in an appendix, together with the methodological caveats in §3.4.

## 2. Goals, non-goals, anti-goals

### Goals
- **G-A:** a reproducible evaluation harness. One command yields a report that records the model, settings, prompt hash, data snapshot and git SHA.
- **G-B:** honest baseline numbers for the released pipeline (v1.0.1) on three LLMs.
- **G-C:** measured improvements to grading:
  - structured output, determinism, and the retrieval query mode (4b);
  - labelled examples and ordinal fusion (4c);
  - calibrated confidence and a documented review threshold (4d).

  Each is accepted only if the harness shows it helps on the test split.
- **G-D:** close the loop in Moodle (4e):
  - store and show `integrity_warnings`;
  - export anonymised "AI vs teacher" pairs in the evaluation dataset schema;
  - fix gaps G1 and G2 from `docs/HANDOFF.md` §7.

### Non-goals
- Fine-tuning or training models.
- Supporting LMSs other than Moodle.
- Evaluating feedback *quality* against EngSAF feedback. That feedback is LLM-generated, so it is not a human gold standard.
- Local or on-premise model benchmarks. There is no GPU available; the harness supports them, but no runs are planned.
- Indonesian-language statistical claims. Indonesian is covered by a qualitative case study only **[owner]**.

### Anti-goals (these would make Cycle 4 a failure even if it "works")
- Tuning prompts, thresholds, calibrators or fusion parameters on the test split.
- Reporting a metric without its model, settings, data snapshot and confidence interval.
- Calling a difference an improvement when its paired confidence interval includes 0.
- Any dataset row from EngSAF or the private case study reaching the public repository.
- Making default grading slower or more expensive without an explicit setting.
- Breaking the `/v1` or Moodle contracts. Only optional fields may be added.

## 3. Constraints and facts

### 3.1 Data

| Dataset | Use | Size | Labels | License or terms |
|---|---|---|---|---|
| **EngSAF** (Aggarwal et al., AIED 2025) | main English dataset | train file only: 3,662 answers, 107 questions | 0 incorrect / 1 partial / 2 correct | Obtained on request for an open-source thesis project. **Redistribution prohibited; citation required.** Never committed. |
| **SciEntsBank** (SemEval-2013 Task 7, HF `nkazi/SciEntsBank`) | second English dataset, official unseen-question test | train 4,969 / test_ua 540 / test_uq 733 | 5-way: 0 correct, 1 contradictory, 2 partially_correct_incomplete, 3 irrelevant, 4 non_domain | CC BY 4.0. Downloaded by script from a pinned HF revision and verified by checksum. |
| **Private Indonesian case study** (a university computer networks course) | Indonesian qualitative case study | 32 answers, 4 questions, 8 pseudonymous students | teacher score 0–25 per answer | Real student data. Always private and never committed. |

**Data quality facts**, verified 2026-11-23:
- EngSAF contains 12 empty answers and 81 groups of exact-duplicate answers within a question (238 rows; 2 groups have conflicting labels). One question has two reference answers. Answers per question range from 1 to 314.
- A copy of SciEntsBank circulated in the thesis repository as "beetle.csv" with wrong label names. Cycle 4 uses only the official HF source.
- None of the datasets has course materials, only reference answers (see §6.3).

### 3.2 Compute and budget
- **No GPU** on either laptop, so all runs use cloud LLMs.
- **Budget:** one paid OpenRouter key dedicated to evaluation, with a credit limit, about US$10–30 in total **[owner]**. gpt-oss-120b costs about US$0.0003 per grading call (thesis measurement, about 2,000 input and 300 output tokens).
- **Embeddings:** `BAAI/bge-m3` via HuggingFace for all runs, held constant **[owner]**.

### 3.3 Repo conventions (from `docs/HANDOFF.md` §5)
- One branch per phase (`feat/cycle4a-...` and so on). No commits to `main`; merge and tag only with the owner's approval.
- Conventional Commits.
- Version bumps plus a `CHANGELOG.md` `[Unreleased]` entry for every change.
- Only `src/utils/config.py` reads the environment (an AST test enforces this).
- Unit tests run with network blocked (`tests/run_offline.py`).
- No `pandas`, `numpy` or `scikit-learn` in the core requirements. They were removed on purpose in Cycle 1.

### 3.4 Lessons from the thesis evaluation (what this design must avoid)
- **Label leakage in GradeRAG.**
  - The "knowledge" context contained scoring notes built from dataset feedback for the same question. For 115 of the 300 benchmark items, the item's own feedback (which states whether it is correct) was in its context.
  - The example pool also contained exact duplicates of the graded answer with the same label.
- **Selection bias.** The 300-item benchmark was sampled only from items that had succeeded in an earlier run, and it was class-balanced rather than naturally distributed.
- **Confidence intervals too narrow.** The bootstrap resampled items, ignoring clustering by question (up to 36 items per question).
- **Overstated claims.** Fusion changed 30 predictions (17 better, 13 worse), which is not significant. Fusion parameters were not selected on held-out data.
- **Unequal comparison.** The LLM-only baseline had no reference answer, while the RAG variants did. Its "RAG helps" result therefore largely means "the reference answer helps".

## 4. Owner decisions (brainstorm Q1–Q9, 2026-11-23)

1. **Models:** three models with a small paid budget **[owner]**. The agent's plan **[agent]**:
   - `openai/gpt-oss-120b`: strong open-weight model, full experiment matrix.
   - a small open model of about 8B, such as `meta-llama/llama-3.1-8b-instruct`: shows the method does not depend on model size.
   - one mid-priced commercial model: shows where open models stand.

   Exact model ids are pinned in phase 4a after checking OpenRouter prices. To fit the budget, only gpt-oss-120b runs every configuration. The other two run the baseline and the final best configuration (§8.3).
2. **Rigour:** publication-grade **[owner]**.
   - Frozen dev and test splits.
   - The test split is never used for any choice.
   - Bootstrap clustered by question.
   - Every report has a full manifest.
3. **Score to label** **[owner]**:
   - The product's 0–100 score maps to ordinal labels with two thresholds fitted on dev (maximising QWK), then frozen.
   - Continuous metrics are also reported: MAE on the 0–1 scale and Spearman correlation.
   - SciEntsBank maps to 3-way ordinal: correct → 2, partially_correct_incomplete → 1, and contradictory, irrelevant and non_domain → 0. It also gets the official 2-way metrics (correct vs not: accuracy and macro-F1) for comparison with the SemEval literature.
4. **Indonesian:** the private case study is reported qualitatively and per question, without statistical claims **[owner]**. The harness and the Moodle export (4e) let more real data be added later without code changes.
5. **What is public** **[owner]**:
   - Public: scripts, schemas, aggregate reports, a small synthetic smoke set, and per-item SciEntsBank predictions (CC BY, with attribution).
   - Private: EngSAF and the case-study data and per-item outputs, which stay in git-ignored `private-data/`.
   - Every report cites EngSAF (AIED 2025) and SemEval-2013 Task 7.
6. **Where results live** **[agent]:**
   - `docs/evaluation/` holds the aggregate Markdown and JSON reports.
   - CI runs a smoke evaluation with a stub LLM.
7. **Phasing:** 4a → 4b → 4c → 4d → 4e. Each phase is its own branch and can be merged on its own. No deadline **[owner]**.
8. **Labelled examples in Moodle** **[owner]**:
   - opt-in per assignment, off by default, with a warning that other students' graded answers are sent to the AI provider;
   - examples carry no identity (answer text, teacher score and feedback only);
   - only grades the teacher confirmed are used;
   - the privacy provider and docs are updated;
   - `/v1` gets an optional `examples` field.
9. **Keys:** one dedicated paid OpenRouter key with a credit limit, which the owner adds to `backend/.env`. Embeddings use `BAAI/bge-m3` **[owner]**.

## 5. Approaches considered

| | Approach | Trade-off |
|---|---|---|
| A | **In-process.** The harness calls `RAGPipeline` directly with a temporary Chroma store. | Fast to iterate and testable offline, but it does not exercise the API layer (auth, locks, request validation, HTTP ingestion). |
| B | **Black-box over HTTP.** The harness is a client of a running `/v1` stack. | Tests exactly the shipped server, but every iteration needs the stack, and every experiment needs its API field before it can be measured. |
| **C** | **Hybrid (chosen [owner]).** A transport-agnostic harness core with a `Grader` interface and three implementations: `inprocess` (development and experiments), `http` (certification runs against the Docker stack; official report numbers) and `stub` (CI). | Small extra cost (one interface). It gives fast iteration and evidence about the product as released, and one test confirms that `inprocess` and `http` agree. |

## 6. Design

### 6.1 Components

The harness lives in `backend/src/evaluation/`, a package inside the backend, run as `python -m src.evaluation <command>` **[agent]**.

```
src/evaluation/
  __main__.py      CLI: prepare | run | report | compare (argparse, like src/cli.py)
  schema.py        EvalItem, EvalResult, RunManifest dataclasses + JSONL (de)serialisation
  datasets/        one adapter per dataset -> EvalItem
    engsaf.py        reads private-data CSV; cleaning rules (§6.2)
    scientsbank.py   downloads pinned HF revision (stdlib urllib/httpx), sha256 check, label mapping
    jk_case.py       reads private case-study CSV + reference PDF path
    synthetic.py     tiny public smoke set from examples/week1_to_week4_quiz (+ hand-written gold labels)
  splits.py        deterministic, seeded per-question split + frozen split files (§6.2)
  materials.py     builds per-dataset "materials" (reference documents) and ingests them via the grader
  graders/
    base.py          Grader protocol: prepare_namespace(dataset, documents), grade(item, config) -> raw result
    inprocess.py     builds RAGPipeline from Settings; temp Chroma dir per run
    http.py          reuses src.cli's API client; /v1 materials + grade
    stub.py          deterministic fake for CI and unit tests
  runner.py        concurrency, JSONL checkpoint, resume by (item_id, config_hash), rate-limit backoff, cost/token log
  metrics.py       pure-Python QWK, accuracy, macro-F1, adjacent acc., MAE, Spearman, AUROC, ECE, retrieval Hit@k/MRR
  stats.py         cluster (per-question) bootstrap CIs, paired differences, seeded
  thresholds.py    fit/freeze score->label thresholds on dev
  report.py        Markdown + JSON report with manifest; privacy guard (§6.7)
backend/evaluation/experiments/*.yaml   committed experiment configs (one file = one configuration)
docs/evaluation/                         committed aggregate reports
private-data/evaluation/                 git-ignored per-item outputs for private datasets
```

How the parts work:
- **Configuration.** A configuration YAML names the grader mode, the model, the settings overrides (temperature, response format, query mode, examples, fusion) and the datasets and splits.
- **Config hash.** The configuration hash covers the configuration, the prompt-template hash and the data snapshot hash. A run is identified by it, and resuming never mixes configurations.
- **Settings.** The `inprocess` and `stub` graders get their settings through `Settings` built in code, without reading the environment. API keys reach the process only through `src/utils/config.py` as today.

### 6.2 Items, cleaning and splits

**`EvalItem`** fields:
- `item_id`, `dataset`, `question_id` (the cluster unit), `question`, `answer`, `language`;
- `reference_text`, or `reference_document` (a file path, for the case-study PDF);
- `gold_label` (ordinal int), `label_scale` (the number of ordinal classes), `gold_score` (0–1, when the source has a continuous score) and `gold_label_raw` (the source label, such as the SciEntsBank 5-way class);
- `split`.

**Cleaning** (EngSAF), applied before splitting and counted in the report:
- drop empty answers;
- collapse exact duplicates within a question (normalised whitespace and case) into one item when the labels agree, and drop the group when they conflict;
- for the question with two reference answers, use the first and record it.

**Splits:**
- **EngSAF.** Questions are shuffled with seed 20261123 and assigned to dev or test so that about 40% of *items* fall in dev. A question is never split across dev and test.
- **SciEntsBank.**
  - The official train split is dev.
  - Official `test_uq` (unseen questions) and `test_ua` (unseen answers to seen questions) are test, each reported separately.
  - `test_ud` is not used; it is a different domain and too large for the budget.
- **Case study.** One split, `case`.

**Frozen split files.** Item ids per split, plus a sha256 over the cleaned items, are written by `prepare`.
- SciEntsBank split files are committed under `backend/evaluation/splits/`.
- EngSAF and case-study split files hold only hashed ids and live in `private-data/evaluation/splits/`. Only their checksums are committed.

**Dev caps** **[agent]**. Dev is used to fit thresholds, calibrators and fusion parameters, and every configuration needs a dev run. Dev is therefore capped at about 600 items per dataset, sampled per question like the test sample below.

**Example banks (for 4c)** **[agent]**.
- In Moodle, examples are earlier teacher-graded answers *to the same question*. With question-disjoint splits, test questions have no such answers in dev.
- So each question's items (in dev and test) are split once, with a seed, into a **bank** (about one third, at most 9 items) and an **evaluation subset**. Bank items are never graded in any configuration.
- All configurations, including the baseline, are reported on the evaluation subset, so comparisons stay paired.
- For SciEntsBank `test_ua`, whose questions appear in train, examples may also come from the train split of the same question.

**Budget sampling.** If a test split exceeds the run budget, a fixed sample is drawn *per question*: the same fraction from each question, preserving the natural label distribution. It is frozen like the split.
- Planned cap: about 1,000 EngSAF test items.
- SciEntsBank test_uq (733) and test_ua (540) are used in full.

### 6.3 Materials (the reference answer as course material)

RAGrader grades against course materials, but these datasets only have reference answers. The design makes the reference answers the materials and states this limitation in every report:

- **Per dataset,** one namespace holds one document per question: "Question: …\nReference answer: …". It contains all questions of that dataset (dev and test), so retrieval must find the right one among about 100–200, as in a real course.
- **Retrieval gold** is the item's own question document. Hit@k and MRR are reported.
- **Case study:** the teacher's real answer-key PDF is ingested through the normal product path (PDF parser and chunking).
- **Grading request** **[agent]**.
  - An empty rubric (`{}`), which is the product's "no rubric" mode, so the score is the model's overall percentage.
  - `maximum_grade=100`.
  - An explicit `language` per dataset: `en` for EngSAF and SciEntsBank, `id` for the case study.
- **Case-study labels** **[agent]**. The predicted score × 25 goes through the teacher's own conversion (≤ 8 → 0, 9–17 → 1, ≥ 18 → 2), so no thresholds are fitted on 32 items. MAE is also reported in points on the 0–25 scale.
- **Two diagnostic bounds**, eval-only and implemented in the `inprocess` grader:
  - **oracle:** the gold reference document is the only context, giving the upper bound for retrieval;
  - **no_context:** no materials at all, giving the lower bound.

  The fair "LLM-only" comparison is **oracle**, not no_context, because the gold reference is supplied without retrieval (§3.4).

### 6.4 Metrics and statistics
- **Agreement**, on the ordinal labels after the frozen thresholds:
  - primary: QWK;
  - secondary: accuracy, macro-F1, adjacent accuracy and MAE (label units).
- **Continuous agreement:** MAE on the 0–1 scale and Spearman's ρ between the score and the gold (label normalised, or `gold_score`).
- **SciEntsBank 2-way:** accuracy and macro-F1 for "correct vs not". For this, the product score is thresholded at the dev-fitted upper threshold.
- **Reliability:**
  - parse-failure rate and integrity-warning rate;
  - groundedness: the share of returned citations kept by `ground_citations`, and the share of grades with at least one grounded citation;
  - retrieval Hit@1, Hit@3 and MRR.
- **Calibration** (phase 4d, and also reported for the baseline):
  - error is defined as |predicted label − gold| ≥ 1;
  - AUROC of (1 − confidence) for predicting error;
  - ECE over 10 bins;
  - deferral rate and accuracy on the accepted items at the chosen review threshold.
- **Consistency:** a fixed 100-item dev subset graded 3 times. Report the mean per-item score standard deviation and the label agreement between repeats.
- **Robustness to injection:**
  - A public adversarial set: for 100 dev and 100 test items with gold label 0, append fixed English or Indonesian injection templates (`backend/evaluation/adversarial_templates.yaml`).
  - Report the mean score uplift versus the clean answer, the share that crosses into a higher label, and the detection rate of `integrity_warnings`.
- **Statistics:**
  - 95% percentile confidence intervals from 2,000 **cluster-bootstrap** resamples over `question_id`, with a fixed seed.
  - Comparisons between configurations are **paired** on identical items, and the paired-difference CI is reported.
  - Wording rule: "improves" only when the paired CI excludes 0; otherwise "no detectable difference".
- **Implementation:** pure Python. Unit tests check the metrics against reference values computed once with scikit-learn and SciPy and stored as constants in the tests. Those libraries are not dependencies.

### 6.5 Report and manifest
- Each `report` writes `docs/evaluation/<date>-<phase>-<name>.md` and `.json`.
- **The manifest records:**
  - git SHA (and dirty flag), backend version and prompt-template sha256 (both languages);
  - configuration file and hash;
  - model id, provider, temperature, seed, response format and embedding model;
  - dataset snapshot and split hashes, item counts after cleaning, and threshold values;
  - run start and end, calls, tokens and estimated cost;
  - failures by type.
- **Required report sections:**
  - limitations: reference answers as materials, EngSAF feedback not human-written, case-study size;
  - dataset citations: EngSAF (AIED 2025), SemEval-2013 Task 7 and SciEntsBank.

### 6.6 Phase content

**4a: Harness and baseline**

No change to grading behaviour.
- Everything in §6.1–6.5, plus the CI smoke job (stub grader on the synthetic set, run in `backend-tests`).
- An `inprocess` vs `http` agreement check: the same 50 SciEntsBank items with the stub LLM and identical results; one real-model run on 50 items is reported.
- **Baseline runs on gpt-oss-120b:**
  - `baseline` (v1.0.1 defaults);
  - `oracle` and `no_context`;
  - consistency and injection sets.
- **Baseline runs on the other two models:** `baseline` only.

**4b: Structured, deterministic grading**

New settings (read in `config.py`, defaults shown):
- `GRADING_RESPONSE_FORMAT=auto|json_schema|json_object|none` (default `auto`). `auto` uses JSON-schema structured output when the provider or model supports it, and falls back otherwise.
- `GRADING_REPAIR_ATTEMPTS=1`: at most one repair call, and only after a parse or validation failure, so the extra cost applies only to failures.
- `GRADING_TEMPERATURE` and `GRADING_SEED`. If the harness shows `0` and a seed improve consistency without hurting agreement, they become the grading defaults and the change is recorded in the CHANGELOG.
- `RETRIEVAL_QUERY_MODE=question_answer|question` (default stays `question_answer` unless the harness shows `question` is better on test).

Responses are validated with a Pydantic model: score range, known criteria, and citation shape. A validation failure triggers repair, then the current fallback.

**4c: Labelled examples and fusion**

- **API.** An optional `examples: [{answer, score, feedback?}]` field (at most `GRADING_MAX_EXAMPLES`) on `/v1/namespaces/{ns}/grade` and `/assign/answer`. Examples go into a fenced prompt section and are labelled as teacher-graded references. They are untrusted input, and injection checks apply to them too.
- **Harness example selection, anti-leakage by construction:**
  - same-question examples come only from that question's **bank** (§6.2), and cross-question examples come only from dev banks;
  - the graded item and its duplicates are never in the pool, and evaluation-subset items are never used as examples;
  - example feedback is either the teacher's feedback (case study, Moodle) or omitted. EngSAF's LLM-generated feedback is not used, and no feedback of a graded item is ever in context.
- **Variants on dev:**
  - same-question examples only (the realistic Moodle case);
  - k ∈ {3, 6, 9};
  - balanced vs top-similarity.
- **Ordinal evidence fusion:**
  - an optional `GRADING_ENSEMBLE=none|fusion` setting (off by default, because it costs two calls);
  - re-implemented from its published description (similarity-weighted label support plus two predictions);
  - all parameters (τ, same-question boost, weights, rounding) fitted on dev only and frozen into a versioned parameter file;
  - kept only if the paired test CI beats the best single-call configuration.

**4d: Calibrated confidence**

- **Signals:**
  - the model's self-reported confidence;
  - integrity warnings and parse repairs;
  - the grounded-citation ratio and rubric coverage;
  - retrieval strength (top similarity or rerank score);
  - optionally, self-consistency (score spread over n samples, behind `GRADING_CONSISTENCY_SAMPLES`, default 1, which means off).
- **Calibrator:**
  - a logistic or isotonic model fitted on dev and shipped as a versioned JSON parameter file;
  - `confidence` becomes the calibrated probability that the grade is within one label of the teacher;
  - without a parameter file, the current behaviour is kept;
  - the 0.3 integrity cap stays.
- **Documented review threshold** per model family, with its expected accuracy on the accepted grades and the expected deferral rate on test.
- **Version bump.** The meaning of `confidence` changes, so the backend moves to a minor version: 1.5.0 or later.

**4e: Moodle loop**

`mod_airagassign`:
- **Integrity warnings:** a DB upgrade step adds a field for `integrity_warnings`. They are shown in `grade_review.php` and `view_result.php`, and declared in the privacy metadata.
- **Example opt-in:** an assignment setting, off by default, with a warning text. Examples come from teacher-confirmed submissions of the same assignment and question, without identity, and are sent in `examples`.
- **Export:**
  - a teacher or admin action, behind a new capability, exports anonymised AI-vs-teacher pairs as CSV in the `EvalItem` schema;
  - no user ids, names or emails; `question_id` and pseudonymous item ids are generated per export;
  - declared in the privacy provider.
- **G1:** a restored material is queued for vectorization.
- **G2:** the intro file area is annotated in the backup.
- PHPUnit covers the full CI matrix.

### 6.7 Privacy guard
- The dataset registry marks each dataset `public` (SciEntsBank, synthetic) or `private` (EngSAF, case study).
- For private datasets, `run` and `report` refuse to write per-item outputs anywhere except under a `private-data/` path. Aggregate reports may never contain answer, question or reference text for them.
- Reports are built only from aggregate structures (counts, metrics and confidence intervals), so per-item text has no code path into a report **[agent]**.
- **Canary test:** a unit test feeds private-marked items whose text contains unique canary strings and asserts that no canary appears in any report output, and that per-item files land only under `private-data/`.

### 6.8 Testing
- **Unit tests (offline):**
  - metrics against stored reference values;
  - cluster bootstrap determinism;
  - split determinism and the no-question-in-both-splits property;
  - cleaning rules;
  - label mappings;
  - runner resume and backoff (stub grader and a fake clock);
  - the privacy guard;
  - example-pool anti-leakage properties;
  - fusion and calibrator maths;
  - response validation and repair.
- **CI:** an end-to-end smoke evaluation with the stub grader on the synthetic set. Its report is diffed against a stored expected summary.
- **Integration (compose):** the `http` grader against the stub-AI stack on the synthetic set.
- **Moodle (4e):** PHPUnit for the upgrade step, the export (anonymisation), the opt-in examples payload and the privacy provider.

## 7. Done criteria per phase

| Phase | Done when |
|---|---|
| 4a | `prepare`, `run` and `report` reproduce the baseline report from a clean checkout, given the data and key. CI smoke passes. The `inprocess` vs `http` stub check is identical. Baseline reports for 3 models are committed (aggregates only). |
| 4b | Parse-failure rate is ≤ 0.5% on gpt-oss-120b test. Consistency improves (paired CI). No agreement metric gets worse with a paired CI excluding 0. Defaults change only where this holds. |
| 4c | The anti-leakage tests pass. Example and fusion results are reported with paired CIs against 4b's best. The features ship off by default. Fusion ships only if it wins. |
| 4d | The calibrated confidence beats self-reported confidence on test AUROC (paired CI). The review threshold and its expected deferral and accuracy are documented. |
| 4e | PHPUnit passes on the CI matrix. The export round-trips into the harness as a dataset. Privacy metadata is complete. G1 and G2 are fixed. |

## 8. Left to the builder (the implementation plan)

1. Exact OpenRouter model ids and prices for the small and commercial models (pinned in 4a).
2. The OpenRouter structured-output capability detection for `GRADING_RESPONSE_FORMAT=auto`.
3. **Run matrix and budget:** for each configuration, a cost estimate from tokens per call × items. Abort if the projected total exceeds the configured cap (`--max-cost-usd`).
4. The pinned HF revision and checksums for SciEntsBank, and the download method (the HF datasets-server or parquet files over HTTPS, without the `datasets` library).
5. The YAML loader. Use PyYAML, which the tests already use. If it is not a core runtime dependency, add it to the evaluation extras (`requirements-eval.txt`).
6. Thresholds, ECE binning and AUROC tie handling, as conventional choices documented in `metrics.py`.
7. The DB field type and name for `integrity_warnings` and the export capability name in `mod_airagassign`.

## 9. Risks

| Risk | Mitigation |
|---|---|
| OpenRouter provider routing changes a model's behaviour mid-run | Pin the provider order in the request, record the served provider per call, and report a per-provider breakdown when more than one served the run. |
| Budget overrun | `--max-cost-usd` guard, a cost estimate before every run, and the full matrix only on the cheapest strong model. |
| Small dev splits make fitted thresholds or calibrators unstable | Report bootstrap CIs on dev-fitted parameters. Prefer low-capacity calibrators (logistic). |
| Reference-answer-as-material overstates real-course performance | State it in every report. The case study uses a real answer-key PDF. Real course materials can be added later through the Moodle export. |
| Leakage re-introduced by a later change | Anti-leakage properties are unit-tested, not just documented. |
