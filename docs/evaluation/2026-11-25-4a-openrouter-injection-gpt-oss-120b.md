# Evaluation report: openrouter-injection-gpt-oss-120b (phase 4a)

Intervals are 95% percentile intervals from 2000 cluster-bootstrap resamples over question_id (seed 20261123). Values read `value [low, high]`; `n/a` means undefined.

## Manifest

| Field | Value |
|---|---|
| git_sha | 4d4ae138c4a2c1bf6fe5816ce48af8b234539866 |
| git_dirty | True |
| backend_version | 1.5.0 |
| prompt_template_sha256 | 56de909d628030bad5da0055871148d1b1021b34f336ab849e64741d8b374e7e |
| config_file | backend/evaluation/experiments/openrouter-injection-gpt-oss-120b.yaml |
| config_hash | a12b471f4c7b91bf |
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
| started_at | 2026-11-24T12:27:30.785838+00:00 |
| finished_at | 2026-11-24T22:34:38.438756+00:00 |
| calls | 1600 |
| prompt_tokens | 1280799 |
| completion_tokens | 864667 |
| estimated_cost_usd | 0.194 |
| failures | {"parse_failure": 2} |

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
| engsaf | dev | 100 | 99 | 1 | 300 |
| engsaf | test | 100 | 100 | 0 | 300 |
| scientsbank | dev | 100 | 100 | 0 | 300 |
| scientsbank | test_uq | 100 | 100 | 0 | 300 |

## Thresholds

Frozen thresholds loaded from `docs/evaluation/2026-11-24-4a-openrouter-baseline-gpt-oss-120b.json` (baseline report); not fitted on this run.

| Dataset | t1 | t2 | Fitted on | Dev QWK |
|---|---|---|---|---|
| engsaf | 30.000 | 76.000 | engsaf/dev | 0.652 |
| scientsbank | 25.000 | 55.000 | scientsbank/dev | 0.666 |


## Agreement

Not reported for injection runs: the baseline report of the same configuration gives these metrics.

## SciEntsBank 2-way

| Dataset | Split | accuracy_2way | macro_f1_2way | n |
|---|---|---|---|---|
| scientsbank | dev | 0.950 [0.904, 0.990] | 0.487 [0.475, 0.497] | 100 |
| scientsbank | test_uq | 0.960 [0.926, 0.989] | 0.490 [0.481, 0.497] | 100 |

## Retrieval

| Dataset | Split | hit_at_1 | hit_at_3 | mrr | n |
|---|---|---|---|---|---|
| engsaf | dev | 0.838 [0.644, 1.000] | 1.000 [1.000, 1.000] | 0.919 [0.822, 1.000] | 99 |
| engsaf | test | 0.970 [0.914, 1.000] | 1.000 [1.000, 1.000] | 0.985 [0.957, 1.000] | 100 |
| scientsbank | dev | 0.930 [0.870, 0.979] | 0.990 [0.967, 1.000] | 0.958 [0.923, 0.988] | 100 |
| scientsbank | test_uq | 0.940 [0.838, 1.000] | 0.980 [0.930, 1.000] | 0.958 [0.881, 1.000] | 100 |

## Calibration

Error is |label - gold| >= 1; auroc_error is the AUROC of (1 - confidence) for predicting error; ece uses 10 bins.

Not reported for injection runs: the baseline report of the same configuration gives these metrics.

## Reliability

| Dataset | Split | failure_rate | parse_failure_rate | integrity_warning_rate | grounded_share | cited_share | n |
|---|---|---|---|---|---|---|---|
| engsaf | dev | 0.010 [0.000, 0.039] | 0.010 [0.000, 0.039] | 0.000 [0.000, 0.000] | 1.000 [1.000, 1.000] | 0.949 [0.858, 1.000] | 100 |
| engsaf | test | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 1.000 [1.000, 1.000] | 0.980 [0.951, 1.000] | 100 |
| scientsbank | dev | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 1.000 [1.000, 1.000] | 0.980 [0.950, 1.000] | 100 |
| scientsbank | test_uq | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 1.000 [1.000, 1.000] | 0.980 [0.949, 1.000] | 100 |

Failures by type: parse_failure: 2

Served providers: DeepInfra: 1600

## Case study

Not part of this run.

## Variants

### Injection

Mean score uplift of the injected copy over its clean original (0-100 points), the share whose label rises, and the share flagged with a `possible_prompt_injection` integrity warning.

| Dataset | Split | injection_score_uplift | injection_label_rise_share | injection_detection_rate | n |
|---|---|---|---|---|---|
| engsaf | dev | -0.529 [-2.530, 2.020] | 0.081 [0.037, 0.129] | 1.000 [1.000, 1.000] | 297 |
| engsaf | test | 0.143 [-2.175, 2.929] | 0.053 [0.023, 0.090] | 1.000 [1.000, 1.000] | 300 |
| scientsbank | dev | -3.328 [-5.278, -1.334] | 0.027 [0.009, 0.050] | 1.000 [1.000, 1.000] | 299 |
| scientsbank | test_uq | -0.333 [-2.689, 2.596] | 0.067 [0.046, 0.095] | 1.000 [1.000, 1.000] | 300 |

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
