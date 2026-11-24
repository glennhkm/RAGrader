# Grading-quality evaluation

This folder holds the committed **aggregate** evaluation reports of RAGrader's grading pipeline (Cycle 4, "Grading Quality & Trust"). Each report is a pair, `<date>-<phase>-<config name>.md` and `.json`. The JSON carries a manifest: git SHA, backend version, prompt-template hash, configuration hash, model, dataset snapshot and split hashes, thresholds, calls, tokens, cost and failures.

The harness that produces them lives in [`backend/src/evaluation`](../../backend/src/evaluation). The method is described in the [Cycle 4 design](../superpowers/specs/2026-11-23-cycle4-grading-quality-design.md).

No reports have been committed yet. The 4a baseline runs are pending (see [HANDOFF §8.0](../HANDOFF.md)).

## Privacy

- **Per-item EngSAF and case-study outputs are never published.** Only aggregate numbers (counts, metrics, confidence intervals and thresholds) leave `private-data/`. No report contains a question, an answer, a reference text or a feedback text of a private dataset.
- Where the private outputs live (git-ignored):

  | Path | Content |
  |------|---------|
  | `private-data/datasets/` | source files (EngSAF CSV, case-study CSV and reference PDF) |
  | `private-data/cache/scientsbank/` | the downloaded SciEntsBank parquet files |
  | `private-data/evaluation/prepared/<dataset>.jsonl` | cleaned, split items (also SciEntsBank, as a cache) |
  | `private-data/evaluation/splits/<dataset>.json` | EngSAF and case-study split files (hashed item ids only) |
  | `private-data/evaluation/runs/<config name>-<config hash>/` | `results.jsonl`, `run_summary.json`, `run_meta.json` and the per-run work dir |

- Committed instead: `backend/evaluation/splits/scientsbank.json` (public; ids in clear) and `backend/evaluation/splits/private_checksums.json` (the sha256 of each private split file).
- `run` refuses an `--out-root` outside `private-data/` when a configuration includes a private dataset.
- Before committing reports, check that no answer text slipped in. The hidden `canaries` helper prints 50 seeded 8-word snippets of the prepared private answers to stdout and writes nothing:

  ```bash
  cd backend
  grep -rIlF -f <(python -m src.evaluation canaries --from-prepared) ../docs/evaluation   # expect no output
  ```

  Use `-F`: the snippets are literal text, not regular expressions.

## Reproducing a report

All commands run from `backend/`.

1. **Install** the service requirements and the evaluation extra (the SciEntsBank parquet reader):

   ```bash
   pip install -r requirements.txt -r requirements-eval.txt
   ```

2. **Keys.** Put the keys in `backend/.env`; they reach the harness only through `src/utils/config.py`, as for the service. For the in-process grader that is `OPENROUTER_API_KEY` (use a dedicated key with a credit limit) and, for the embeddings used by every real run (`EMBEDDING_PROVIDER=huggingface`, `EMBEDDING_MODEL=BAAI/bge-m3`), `HUGGINGFACE_API_TOKEN`. The `http` grader uses `RAG_API_URL` and `RAG_API_TOKEN`. Never commit `.env`.

3. **Prepare** each dataset once. This cleans and splits it, prints the counts and freezes the split file:

   ```bash
   python -m src.evaluation prepare --dataset engsaf        # private-data/datasets/engsaf/engsaf_train.csv
   python -m src.evaluation prepare --dataset scientsbank   # downloads HF nkazi/SciEntsBank at the pinned revision
   python -m src.evaluation prepare --dataset jk_case       # private-data/datasets/jk-usk/jaringan_komputer_usk.csv + reference PDF
   ```

   `--source PATH` and (for `jk_case`) `--reference-pdf PATH` override the defaults. A later `prepare` whose snapshot hash differs from the frozen split file fails with `split file is frozen; snapshot changed`; pass `--refreeze` only when changing the split on purpose, and commit the updated split file or checksum. The synthetic set needs no `prepare`: `run` prepares it from the committed file.

4. **Run** a configuration from `backend/evaluation/experiments/`:

   ```bash
   python -m src.evaluation run --experiment evaluation/experiments/baseline-gpt-oss-120b.yaml
   ```

   It prints the planned calls and the estimated cost and asks `Proceed? [y/N]`; `--yes` skips the question (required when stdin is not a terminal). A run above the configuration's `max_cost_usd` is refused. Results go to `private-data/evaluation/runs/` (override with `--out-root`). An interrupted run resumes when the same command is run again. `run_meta.json` in the run directory records the effective grading settings (model, temperature, embedding provider and model, retrieval `top_k`, reranking, chunk size and overlap; never keys), the prompt-template hash and the first start time. A resume under different effective settings is refused before anything in the run directory changes.

   Optional `max_items_per_split: N` in a configuration grades only the first `N` eval items by `item_id` of each dataset split (used for the 50-item agreement checks); it is part of the configuration hash only when set. `overrides` must stay empty until Cycle 4b, which applies them. The `jk_case` reference PDF is copied beside the prepared items and named in them by file name and sha256, so its snapshot does not depend on the checkout path.

   **Token estimates of the `http` grader.** The `/v1` API returns no token counts, so `http` results estimate prompt tokens as (request characters + retrieved-context characters shown in the response) / 4 and completion tokens as feedback characters / 4 (`tokens_estimated: true`). The response truncates each retrieved chunk and does not include the prompt template, so the estimate is a lower bound and the reported cost of `http` runs is too.

5. **Report** the run:

   ```bash
   python -m src.evaluation report --run-dir ../private-data/evaluation/runs/baseline-gpt-oss-120b-<hash>
   ```

   This writes `docs/evaluation/<YYYY-MM-DD>-4a-baseline-gpt-oss-120b.md` and `.json` (override with `--out <base path>`). Score-to-label thresholds are fitted on the run's own dev results and frozen in the report.

   **Variant runs (consistency, injection)** grade no plain dev set, so they reuse the frozen thresholds of the same model's baseline report:

   ```bash
   python -m src.evaluation report \
     --run-dir ../private-data/evaluation/runs/injection-gpt-oss-120b-<hash> \
     --thresholds-from ../docs/evaluation/<date>-4a-baseline-gpt-oss-120b.json
   ```

   The manifest records the thresholds used and their source. Injection reports omit the Agreement and Calibration tables, which would mix clean and injected answers; the baseline report gives them.

6. **Compare** two runs (paired B - A differences on the items both scored; verdicts follow each metric's direction, so a lower MAE "improves"; the case study gets point differences only, and a second table lists failures per side and dropped pairs):

   ```bash
   python -m src.evaluation compare \
     --run-dir ../private-data/evaluation/runs/baseline-gpt-oss-120b-<hash> \
     --run-dir ../private-data/evaluation/runs/oracle-gpt-oss-120b-<hash> \
     --out ../docs/evaluation/<date>-4a-baseline-vs-oracle.md
   ```

## CI smoke check

CI (`backend-tests`) runs the stub grader on the 30-item public synthetic set and compares the report's metrics with [`backend/evaluation/synthetic/expected_summary.json`](../../backend/evaluation/synthetic/expected_summary.json):

```bash
python -m src.evaluation smoke --check evaluation/synthetic/expected_summary.json
```

It exits 1 with a per-key diff when a metric changes. After an intended change, regenerate the file with `smoke --write evaluation/synthetic/expected_summary.json` and review the diff. **The smoke numbers are not an evaluation:** the synthetic set has no dev split, so its thresholds are fitted on the smoke results themselves, and the bootstrap uses 200 resamples instead of 2,000. It only checks that prepare, run and report fit together and stay deterministic.

## Provider limits and outages

- `requests_per_minute` in a configuration paces the in-process grader's LLM and embedding calls together. It is not part of the configuration hash.
- Rate limits, gateway errors (413 included), timeouts and connection errors are retried with backoff. An item that still fails is stored as `provider_error`.
- After five such items in a row the run stops with `provider_unavailable`. Re-run the same command to continue, adding `--retry-failed` to grade the stored `provider_error` items again. Parse failures are model behaviour and are never retried.

## Grader agreement

**Stub stack, 2026-11-23.**
- Setup: the first 50 SciEntsBank `test_uq` eval items by `item_id`, on the `docker-compose.ci.yml` stack (stub LLM and stub embeddings), graded once through `http` (HAProxy → two API replicas → `/v1`) and once through `inprocess`.
- Result: 50/50 graded on both sides with no failures, and all 50 pairs identical in score, confidence, integrity warnings and retrieved sources.
- Gold reference: retrieved for 49/50 items.

The real-model agreement check, which uses the Way gateway, is recorded with the baseline reports.

## Model access for the 4a runs

The baseline reports use the `way-*` configurations: Way's OpenAI-compatible gateway, called as a single `openai_compatible` endpoint (`LLM_BASE_URL` / `LLM_API_KEY` in `backend/.env`).
- **Models:** `openai/gpt-oss-120b` (the product default) and `openai/gpt-oss-20b`, both on Way's free tier.
- **No fallback:** a single endpoint never falls back to another provider, so every grade comes from the configured model.
- **Key setup:** the key used must have TokenSaver switched off and no RAG collection bound, because both change the prompt the grader sends.
- **Embeddings:** `text-embedding-3-small` through the same gateway, not the product default `BAAI/bge-m3`, because the Hugging Face credits were exhausted. Set `EMBEDDING_PROVIDER=openai_compatible`, `EMBEDDING_MODEL`, `EMBEDDING_BASE_URL` and `EMBEDDING_API_KEY` in the environment of the evaluation process; `run_meta.json` records the provider and model.
- **Known limitation:** Way adds its own service-policy instructions to every request. A one-sentence probe was billed as about 1,500 prompt tokens on both models (2026-11-23), so roughly 1,450 tokens precede the grader's prompt. Their text is not visible to us, and we could not rule out that part of them comes from another gateway setting. The results therefore describe RAGrader through Way, and token counts are inflated by that amount.
- **Old configurations:** the OpenRouter configurations (`baseline-*.yaml` without the `way-` prefix) stay as written but were not run.

## Datasets and citations

Every report cites:

- Aggarwal, D., Sil, P., Raman, B., Bhattacharyya, P. (2025). "I Understand Why I Got This Grade": Automatic Short Answer Grading (ASAG) with Feedback. In: Artificial Intelligence in Education. AIED 2025. Lecture Notes in Computer Science, vol 15879. Springer, Cham. https://doi.org/10.1007/978-3-031-98420-4_22
- Dzikovska et al. (2013). SemEval-2013 Task 7: The Joint Student Response Analysis and 8th Recognizing Textual Entailment Challenge. In Proceedings of the Seventh International Workshop on Semantic Evaluation (SemEval 2013), pp. 263–274, ACL.
- Nielsen, Ward, Martin & Palmer (2008). Annotating students' understanding of science concepts (SciEntsBank). LREC 2008. Licensed CC BY 4.0 via HF nkazi/SciEntsBank.

The Indonesian case study (32 answers to 4 questions from a computer-networks course) is private and reported qualitatively.
