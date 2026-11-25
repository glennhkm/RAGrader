# Evaluation report: openrouter-oracle-gpt-oss-120b (phase 4a)

Intervals are 95% percentile intervals from 2000 cluster-bootstrap resamples over question_id (seed 20261123). Values read `value [low, high]`; `n/a` means undefined.

## Manifest

| Field | Value |
|---|---|
| git_sha | 4d4ae138c4a2c1bf6fe5816ce48af8b234539866 |
| git_dirty | True |
| backend_version | 1.5.0 |
| prompt_template_sha256 | 56de909d628030bad5da0055871148d1b1021b34f336ab849e64741d8b374e7e |
| config_file | backend/evaluation/experiments/openrouter-oracle-gpt-oss-120b.yaml |
| config_hash | 8c5ed2af3a80372f |
| model | openai/gpt-oss-120b |
| provider | openai_compatible |
| temperature | n/a |
| seed | n/a |
| response_format | n/a |
| embedding_model | baai/bge-m3 |
| effective_settings | {"chunk_overlap": 50, "chunk_size": 500, "context_mode": "oracle", "embedding_model": "baai/bge-m3", "embedding_provider": "openai_compatible", "grader": "inprocess", "llm_max_new_tokens": 2048, "llm_model": "openai/gpt-oss-120b", "llm_provider": "openai_compatible", "llm_temperature": 0.3, "rerank_top_k": 3, "reranker_model": "bge-reranker-v2-m3", "reranker_type": "pinecone", "reranking_enabled": false, "retrieval_top_k": 5} |
| dataset_snapshots | {"engsaf": "f8c4be30cb95985e297bb986f636ec818bfcf2ea0de776ec13cd4f64d6dcde85", "scientsbank": "84bb4b50c2e2d85cc75f84dedf8f55ca34c02eb93ab158015795e1a3488350ac"} |
| split_hashes | {"engsaf": "4a21c97d2b4420f7ab7cfaec31216e31485b0bfbd271f3b2f71e0cef95c8dd7d", "scientsbank": "a77acdb33372b92f7e1f0f34d27039250a3c017c3cc193ede306df6995d93900"} |
| item_counts | {"engsaf": {"dev": 599, "dev_bank": 280, "test": 997, "test_bank": 356}, "scientsbank": {"dev": 568, "dev_bank": 1215, "test_ua": 405, "test_ua_bank": 135, "test_uq": 598, "test_uq_bank": 135}} |
| thresholds | {"engsaf": {"fitted_on": "engsaf/dev", "qwk_dev": 0.6772188841201716, "t1": 30.0, "t2": 79.0}, "scientsbank": {"fitted_on": "scientsbank/dev", "qwk_dev": 0.7105908530822697, "t1": 30.0, "t2": 67.0}} |
| thresholds_source | n/a |
| started_at | 2026-11-24T18:02:30.575749+00:00 |
| finished_at | 2026-11-24T22:38:58.636250+00:00 |
| calls | 3167 |
| prompt_tokens | 1996880 |
| completion_tokens | 1633389 |
| estimated_cost_usd | 0.352 |
| failures | {"parse_failure": 8} |

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
| engsaf | dev | 599 | 595 | 4 | 0 |
| engsaf | test | 997 | 995 | 2 | 0 |
| scientsbank | dev | 568 | 567 | 1 | 0 |
| scientsbank | test_uq | 598 | 598 | 0 | 0 |
| scientsbank | test_ua | 405 | 404 | 1 | 0 |

## Thresholds

| Dataset | t1 | t2 | Fitted on | Dev QWK |
|---|---|---|---|---|
| engsaf | 30.000 | 79.000 | engsaf/dev | 0.677 |
| scientsbank | 30.000 | 67.000 | scientsbank/dev | 0.711 |


## Agreement

| Dataset | Split | qwk | accuracy | macro_f1 | adjacent_accuracy | mae_label | mae_score | spearman | n |
|---|---|---|---|---|---|---|---|---|---|
| engsaf | dev | 0.677 [0.603, 0.759] | 0.692 [0.640, 0.763] | 0.687 [0.639, 0.735] | 0.970 [0.949, 0.984] | 0.338 [0.270, 0.394] | 0.195 [0.162, 0.224] | 0.679 [0.603, 0.749] | 595 |
| engsaf | test | 0.690 [0.616, 0.757] | 0.692 [0.633, 0.753] | 0.692 [0.635, 0.742] | 0.975 [0.963, 0.986] | 0.333 [0.273, 0.389] | 0.188 [0.161, 0.214] | 0.712 [0.646, 0.772] | 995 |
| scientsbank | dev | 0.711 [0.655, 0.761] | 0.691 [0.646, 0.736] | 0.650 [0.608, 0.691] | 0.952 [0.933, 0.968] | 0.356 [0.307, 0.408] | 0.208 [0.187, 0.230] | 0.708 [0.655, 0.755] | 567 |
| scientsbank | test_uq | 0.754 [0.623, 0.837] | 0.714 [0.611, 0.813] | 0.679 [0.607, 0.744] | 0.970 [0.948, 0.987] | 0.316 [0.217, 0.427] | 0.189 [0.135, 0.238] | 0.770 [0.660, 0.839] | 598 |
| scientsbank | test_ua | 0.772 [0.710, 0.827] | 0.748 [0.702, 0.793] | 0.699 [0.649, 0.750] | 0.963 [0.941, 0.980] | 0.290 [0.232, 0.347] | 0.181 [0.156, 0.205] | 0.765 [0.713, 0.812] | 404 |

## SciEntsBank 2-way

| Dataset | Split | accuracy_2way | macro_f1_2way | n |
|---|---|---|---|---|
| scientsbank | dev | 0.788 [0.750, 0.824] | 0.781 [0.740, 0.820] | 567 |
| scientsbank | test_uq | 0.839 [0.774, 0.897] | 0.834 [0.745, 0.896] | 598 |
| scientsbank | test_ua | 0.842 [0.802, 0.879] | 0.838 [0.797, 0.876] | 404 |

## Retrieval

Not applicable to this run.

## Calibration

Error is |label - gold| >= 1; auroc_error is the AUROC of (1 - confidence) for predicting error; ece uses 10 bins.

| Dataset | Split | auroc_error | ece | n |
|---|---|---|---|---|
| engsaf | dev | 0.643 [0.557, 0.738] | 0.243 [0.183, 0.293] | 595 |
| engsaf | test | 0.666 [0.597, 0.727] | 0.241 [0.188, 0.294] | 995 |
| scientsbank | dev | 0.622 [0.569, 0.679] | 0.256 [0.216, 0.301] | 567 |
| scientsbank | test_uq | 0.665 [0.549, 0.766] | 0.244 [0.151, 0.341] | 598 |
| scientsbank | test_ua | 0.640 [0.577, 0.704] | 0.189 [0.149, 0.234] | 404 |

## Reliability

| Dataset | Split | failure_rate | parse_failure_rate | integrity_warning_rate | grounded_share | cited_share | n |
|---|---|---|---|---|---|---|---|
| engsaf | dev | 0.007 [0.002, 0.013] | 0.007 [0.002, 0.013] | 0.002 [0.000, 0.006] | 0.999 [0.995, 1.000] | 0.995 [0.988, 1.000] | 599 |
| engsaf | test | 0.002 [0.000, 0.004] | 0.002 [0.000, 0.004] | 0.001 [0.000, 0.004] | 0.999 [0.997, 1.000] | 0.998 [0.996, 1.000] | 997 |
| scientsbank | dev | 0.002 [0.000, 0.006] | 0.002 [0.000, 0.006] | 0.000 [0.000, 0.000] | 1.000 [1.000, 1.000] | 0.998 [0.994, 1.000] | 568 |
| scientsbank | test_uq | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] | 598 |
| scientsbank | test_ua | 0.002 [0.000, 0.007] | 0.002 [0.000, 0.007] | 0.000 [0.000, 0.000] | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] | 405 |

Failures by type: parse_failure: 8

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
