# Evaluation report: openrouter-baseline-gpt-oss-120b (phase 4a)

Intervals are 95% percentile intervals from 2000 cluster-bootstrap resamples over question_id (seed 20261123). Values read `value [low, high]`; `n/a` means undefined.

## Manifest

| Field | Value |
|---|---|
| git_sha | 4d4ae138c4a2c1bf6fe5816ce48af8b234539866 |
| git_dirty | True |
| backend_version | 1.5.0 |
| prompt_template_sha256 | 56de909d628030bad5da0055871148d1b1021b34f336ab849e64741d8b374e7e |
| config_file | backend/evaluation/experiments/openrouter-baseline-gpt-oss-120b.yaml |
| config_hash | 2c2c3cd3c719c4d6 |
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
| thresholds_source | n/a |
| started_at | 2026-11-24T07:07:25.745186+00:00 |
| finished_at | 2026-11-24T11:57:31.448890+00:00 |
| calls | 3167 |
| prompt_tokens | 2504568 |
| completion_tokens | 1723991 |
| estimated_cost_usd | 0.386 |
| failures | {"parse_failure": 4} |

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
| engsaf | dev | 599 | 596 | 3 | 0 |
| engsaf | test | 997 | 996 | 1 | 0 |
| scientsbank | dev | 568 | 568 | 0 | 0 |
| scientsbank | test_uq | 598 | 598 | 0 | 0 |
| scientsbank | test_ua | 405 | 405 | 0 | 0 |

## Thresholds

| Dataset | t1 | t2 | Fitted on | Dev QWK |
|---|---|---|---|---|
| engsaf | 30.000 | 76.000 | engsaf/dev | 0.652 |
| scientsbank | 25.000 | 55.000 | scientsbank/dev | 0.666 |


## Agreement

| Dataset | Split | qwk | accuracy | macro_f1 | adjacent_accuracy | mae_label | mae_score | spearman | n |
|---|---|---|---|---|---|---|---|---|---|
| engsaf | dev | 0.652 [0.574, 0.732] | 0.688 [0.631, 0.752] | 0.685 [0.630, 0.733] | 0.961 [0.934, 0.982] | 0.351 [0.288, 0.414] | 0.202 [0.169, 0.231] | 0.668 [0.598, 0.741] | 596 |
| engsaf | test | 0.679 [0.582, 0.765] | 0.675 [0.609, 0.743] | 0.676 [0.611, 0.732] | 0.974 [0.964, 0.984] | 0.351 [0.278, 0.421] | 0.189 [0.162, 0.217] | 0.726 [0.662, 0.782] | 996 |
| scientsbank | dev | 0.666 [0.598, 0.730] | 0.655 [0.603, 0.707] | 0.585 [0.540, 0.632] | 0.935 [0.908, 0.958] | 0.410 [0.348, 0.472] | 0.232 [0.206, 0.258] | 0.673 [0.611, 0.731] | 568 |
| scientsbank | test_uq | 0.726 [0.619, 0.799] | 0.686 [0.583, 0.784] | 0.637 [0.571, 0.693] | 0.962 [0.946, 0.978] | 0.353 [0.255, 0.456] | 0.210 [0.152, 0.263] | 0.746 [0.646, 0.820] | 598 |
| scientsbank | test_ua | 0.714 [0.642, 0.775] | 0.716 [0.669, 0.760] | 0.649 [0.597, 0.698] | 0.938 [0.911, 0.963] | 0.346 [0.286, 0.410] | 0.207 [0.181, 0.235] | 0.740 [0.685, 0.790] | 405 |

## SciEntsBank 2-way

| Dataset | Split | accuracy_2way | macro_f1_2way | n |
|---|---|---|---|---|
| scientsbank | dev | 0.771 [0.725, 0.817] | 0.765 [0.716, 0.814] | 568 |
| scientsbank | test_uq | 0.801 [0.733, 0.858] | 0.795 [0.703, 0.858] | 598 |
| scientsbank | test_ua | 0.810 [0.770, 0.847] | 0.807 [0.767, 0.845] | 405 |

## Retrieval

| Dataset | Split | hit_at_1 | hit_at_3 | mrr | n |
|---|---|---|---|---|---|
| engsaf | dev | 0.916 [0.782, 1.000] | 1.000 [1.000, 1.000] | 0.958 [0.890, 1.000] | 596 |
| engsaf | test | 0.971 [0.924, 0.998] | 1.000 [1.000, 1.000] | 0.984 [0.956, 0.999] | 996 |
| scientsbank | dev | 0.944 [0.908, 0.975] | 0.993 [0.980, 1.000] | 0.966 [0.944, 0.986] | 568 |
| scientsbank | test_uq | 0.935 [0.811, 1.000] | 0.948 [0.825, 1.000] | 0.941 [0.818, 1.000] | 598 |
| scientsbank | test_ua | 0.946 [0.909, 0.978] | 0.995 [0.985, 1.000] | 0.967 [0.944, 0.987] | 405 |

## Calibration

Error is |label - gold| >= 1; auroc_error is the AUROC of (1 - confidence) for predicting error; ece uses 10 bins.

| Dataset | Split | auroc_error | ece | n |
|---|---|---|---|---|
| engsaf | dev | 0.652 [0.576, 0.733] | 0.221 [0.174, 0.277] | 596 |
| engsaf | test | 0.655 [0.598, 0.705] | 0.262 [0.207, 0.317] | 996 |
| scientsbank | dev | 0.645 [0.595, 0.698] | 0.285 [0.235, 0.334] | 568 |
| scientsbank | test_uq | 0.654 [0.529, 0.769] | 0.263 [0.177, 0.364] | 598 |
| scientsbank | test_ua | 0.682 [0.630, 0.736] | 0.225 [0.185, 0.270] | 405 |

## Reliability

| Dataset | Split | failure_rate | parse_failure_rate | integrity_warning_rate | grounded_share | cited_share | n |
|---|---|---|---|---|---|---|---|
| engsaf | dev | 0.005 [0.000, 0.009] | 0.005 [0.000, 0.009] | 0.000 [0.000, 0.000] | 1.000 [1.000, 1.000] | 0.961 [0.881, 1.000] | 599 |
| engsaf | test | 0.001 [0.000, 0.004] | 0.001 [0.000, 0.004] | 0.001 [0.000, 0.003] | 0.999 [0.998, 1.000] | 0.994 [0.989, 0.999] | 997 |
| scientsbank | dev | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 1.000 [1.000, 1.000] | 0.996 [0.991, 1.000] | 568 |
| scientsbank | test_uq | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 1.000 [1.000, 1.000] | 0.990 [0.978, 1.000] | 598 |
| scientsbank | test_ua | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 1.000 [1.000, 1.000] | 0.993 [0.983, 1.000] | 405 |

Failures by type: parse_failure: 4

Served providers: DeepInfra: 3167

## Case study

Not part of this run.

## Variants

No variant set in this run.

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
