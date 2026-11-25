# Evaluation report: openrouter-consistency-gpt-oss-120b (phase 4a)

Intervals are 95% percentile intervals from 2000 cluster-bootstrap resamples over question_id (seed 20261123). Values read `value [low, high]`; `n/a` means undefined.

## Manifest

| Field | Value |
|---|---|
| git_sha | 4d4ae138c4a2c1bf6fe5816ce48af8b234539866 |
| git_dirty | True |
| backend_version | 1.5.0 |
| prompt_template_sha256 | 56de909d628030bad5da0055871148d1b1021b34f336ab849e64741d8b374e7e |
| config_file | backend/evaluation/experiments/openrouter-consistency-gpt-oss-120b.yaml |
| config_hash | 64e089892f8d097d |
| model | openai/gpt-oss-120b |
| provider | openai_compatible |
| temperature | n/a |
| seed | n/a |
| response_format | n/a |
| embedding_model | baai/bge-m3 |
| effective_settings | {"chunk_overlap": 50, "chunk_size": 500, "context_mode": "rag", "embedding_model": "baai/bge-m3", "embedding_provider": "openai_compatible", "grader": "inprocess", "llm_max_new_tokens": 2048, "llm_model": "openai/gpt-oss-120b", "llm_provider": "openai_compatible", "llm_temperature": 0.3, "rerank_top_k": 3, "reranker_model": "bge-reranker-v2-m3", "reranker_type": "pinecone", "reranking_enabled": false, "retrieval_top_k": 5} |
| dataset_snapshots | {"engsaf": "f8c4be30cb95985e297bb986f636ec818bfcf2ea0de776ec13cd4f64d6dcde85", "scientsbank": "84bb4b50c2e2d85cc75f84dedf8f55ca34c02eb93ab158015795e1a3488350ac"} |
| split_hashes | {"engsaf": "4a21c97d2b4420f7ab7cfaec31216e31485b0bfbd271f3b2f71e0cef95c8dd7d", "scientsbank": "a77acdb33372b92f7e1f0f34d27039250a3c017c3cc193ede306df6995d93900"} |
| item_counts | {"engsaf": {"dev": 599, "dev_bank": 280, "test": 997, "test_bank": 356}, "scientsbank": {"dev": 568, "dev_bank": 1215, "test_ua": 405, "test_ua_bank": 135, "test_uq": 598, "test_uq_bank": 135}} |
| thresholds | {"engsaf": {"fitted_on": "engsaf/dev", "qwk_dev": 0.6518085428102749, "t1": 30.0, "t2": 76.0}, "scientsbank": {"fitted_on": "scientsbank/dev", "qwk_dev": 0.6664141472111904, "t1": 25.0, "t2": 55.0}} |
| thresholds_source | docs/evaluation/2026-11-24-4a-openrouter-baseline-gpt-oss-120b.json |
| started_at | 2026-11-24T12:05:43.114953+00:00 |
| finished_at | 2026-11-24T12:27:27.403214+00:00 |
| calls | 300 |
| prompt_tokens | 237687 |
| completion_tokens | 156067 |
| estimated_cost_usd | 0.035 |
| failures | {"parse_failure": 1} |

## Data and cleaning counts

Items after cleaning (split files):

| Dataset | Split | Items |
|---|---|---|
| engsaf | dev | 599 |
| engsaf | dev_bank | 280 |
| engsaf | test | 997 |
| engsaf | test_bank | 356 |
| scientsbank | dev | 568 |
| scientsbank | dev_bank | 1215 |
| scientsbank | test_ua | 405 |
| scientsbank | test_ua_bank | 135 |
| scientsbank | test_uq | 598 |
| scientsbank | test_uq_bank | 135 |

Results in this run:

| Dataset | Split | Results | Scored | Failed | Variant results |
|---|---|---|---|---|---|
| engsaf | dev | 48 | 48 | 0 | 96 |
| scientsbank | dev | 52 | 52 | 0 | 104 |

## Thresholds

Frozen thresholds loaded from `docs/evaluation/2026-11-24-4a-openrouter-baseline-gpt-oss-120b.json` (baseline report); not fitted on this run.

| Dataset | t1 | t2 | Fitted on | Dev QWK |
|---|---|---|---|---|
| engsaf | 30.000 | 76.000 | engsaf/dev | 0.652 |
| scientsbank | 25.000 | 55.000 | scientsbank/dev | 0.666 |


## Agreement

| Dataset | Split | qwk | accuracy | macro_f1 | adjacent_accuracy | mae_label | mae_score | spearman | n |
|---|---|---|---|---|---|---|---|---|---|
| engsaf | dev | 0.695 [0.428, 0.848] | 0.688 [0.513, 0.816] | 0.673 [0.451, 0.801] | 0.979 [0.930, 1.000] | 0.333 [0.186, 0.533] | 0.194 [0.128, 0.277] | 0.673 [0.357, 0.852] | 48 |
| scientsbank | dev | 0.696 [0.425, 0.889] | 0.712 [0.574, 0.837] | 0.612 [0.470, 0.751] | 0.923 [0.807, 1.000] | 0.365 [0.176, 0.593] | 0.218 [0.132, 0.313] | 0.690 [0.461, 0.850] | 52 |

## SciEntsBank 2-way

| Dataset | Split | accuracy_2way | macro_f1_2way | n |
|---|---|---|---|---|
| scientsbank | dev | 0.808 [0.673, 0.925] | 0.800 [0.655, 0.922] | 52 |

## Retrieval

| Dataset | Split | hit_at_1 | hit_at_3 | mrr | n |
|---|---|---|---|---|---|
| engsaf | dev | 0.896 [0.762, 1.000] | 1.000 [1.000, 1.000] | 0.948 [0.881, 1.000] | 48 |
| scientsbank | dev | 0.981 [0.940, 1.000] | 1.000 [1.000, 1.000] | 0.990 [0.970, 1.000] | 52 |

## Calibration

Error is |label - gold| >= 1; auroc_error is the AUROC of (1 - confidence) for predicting error; ece uses 10 bins.

| Dataset | Split | auroc_error | ece | n |
|---|---|---|---|---|
| engsaf | dev | 0.530 [0.348, 0.743] | 0.288 [0.165, 0.448] | 48 |
| scientsbank | dev | 0.696 [0.539, 0.842] | 0.212 [0.091, 0.342] | 52 |

## Reliability

| Dataset | Split | failure_rate | parse_failure_rate | integrity_warning_rate | grounded_share | cited_share | n |
|---|---|---|---|---|---|---|---|
| engsaf | dev | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 1.000 [1.000, 1.000] | 0.958 [0.870, 1.000] | 48 |
| scientsbank | dev | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 1.000 [1.000, 1.000] | 0.981 [0.940, 1.000] | 52 |

Failures by type: parse_failure: 1

Served providers: DeepInfra: 300

## Case study

Not part of this run.

## Variants

### Consistency

Mean per-item score standard deviation over repeats (0-100 points) and the share of items whose repeats all get the same label.

| Dataset | Split | consistency_score_std | consistency_label_agreement | n |
|---|---|---|---|---|
| engsaf | dev | 2.828 [1.187, 4.197] | 0.854 [0.754, 0.974] | 48 |
| scientsbank | dev | 3.208 [2.338, 4.121] | 0.885 [0.774, 0.967] | 52 |

## Limitations

- Materials are the datasets' reference answers, not real course materials; real-course retrieval may be harder.
- EngSAF feedback is LLM-generated and is not used as a gold standard; only its labels are.
- The Indonesian case study has 32 answers from 4 questions and is reported qualitatively, without statistical claims.
- The no_context bound uses a single placeholder document ('No course materials are available'), because the product refuses to grade with zero retrieved documents.
- Provider routing is outside the configuration file; the served provider per call is recorded and reported.
- The oracle and no_context bounds exclude the case study, whose reference is a PDF.

## Citations

- Aggarwal, D., Sil, P., Raman, B., Bhattacharyya, P. (2025). "I Understand Why I Got This Grade": Automatic Short Answer Grading (ASAG) with Feedback. In: Artificial Intelligence in Education. AIED 2025. Lecture Notes in Computer Science, vol 15879. Springer, Cham. https://doi.org/10.1007/978-3-031-98420-4_22
- Dzikovska et al. (2013). SemEval-2013 Task 7: The Joint Student Response Analysis and 8th Recognizing Textual Entailment Challenge. In Proceedings of the Seventh International Workshop on Semantic Evaluation (SemEval 2013), pp. 263–274, ACL.
- Nielsen, Ward, Martin & Palmer (2008). Annotating students' understanding of science concepts (SciEntsBank). LREC 2008. Licensed CC BY 4.0 via HF nkazi/SciEntsBank.
