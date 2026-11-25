# Evaluation report: openrouter-no-context-gpt-oss-120b (phase 4a)

Intervals are 95% percentile intervals from 2000 cluster-bootstrap resamples over question_id (seed 20261123). Values read `value [low, high]`; `n/a` means undefined.

## Manifest

| Field | Value |
|---|---|
| git_sha | 4d4ae138c4a2c1bf6fe5816ce48af8b234539866 |
| git_dirty | True |
| backend_version | 1.5.0 |
| prompt_template_sha256 | 56de909d628030bad5da0055871148d1b1021b34f336ab849e64741d8b374e7e |
| config_file | backend/evaluation/experiments/openrouter-no-context-gpt-oss-120b.yaml |
| config_hash | 11bc137abb06e3ac |
| model | openai/gpt-oss-120b |
| provider | openai_compatible |
| temperature | n/a |
| seed | n/a |
| response_format | n/a |
| embedding_model | baai/bge-m3 |
| effective_settings | {"chunk_overlap": 50, "chunk_size": 500, "context_mode": "no_context", "embedding_model": "baai/bge-m3", "embedding_provider": "openai_compatible", "grader": "inprocess", "llm_max_new_tokens": 2048, "llm_model": "openai/gpt-oss-120b", "llm_provider": "openai_compatible", "llm_temperature": 0.3, "rerank_top_k": 3, "reranker_model": "bge-reranker-v2-m3", "reranker_type": "pinecone", "reranking_enabled": false, "retrieval_top_k": 5} |
| dataset_snapshots | {"engsaf": "f8c4be30cb95985e297bb986f636ec818bfcf2ea0de776ec13cd4f64d6dcde85", "scientsbank": "84bb4b50c2e2d85cc75f84dedf8f55ca34c02eb93ab158015795e1a3488350ac"} |
| split_hashes | {"engsaf": "4a21c97d2b4420f7ab7cfaec31216e31485b0bfbd271f3b2f71e0cef95c8dd7d", "scientsbank": "a77acdb33372b92f7e1f0f34d27039250a3c017c3cc193ede306df6995d93900"} |
| item_counts | {"engsaf": {"dev": 599, "dev_bank": 280, "test": 997, "test_bank": 356}, "scientsbank": {"dev": 568, "dev_bank": 1215, "test_ua": 405, "test_ua_bank": 135, "test_uq": 598, "test_uq_bank": 135}} |
| thresholds | {"engsaf": {"fitted_on": "engsaf/dev", "qwk_dev": 0.5696905077755323, "t1": 30.0, "t2": 50.0}, "scientsbank": {"fitted_on": "scientsbank/dev", "qwk_dev": 0.5097785582730116, "t1": 20.0, "t2": 25.0}} |
| thresholds_source | n/a |
| started_at | 2026-11-24T14:30:03.596804+00:00 |
| finished_at | 2026-11-24T22:37:05.285877+00:00 |
| calls | 3167 |
| prompt_tokens | 1746990 |
| completion_tokens | 1202171 |
| estimated_cost_usd | 0.269 |
| failures | {"parse_failure": 6} |

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
| scientsbank | dev | 568 | 568 | 0 | 0 |
| scientsbank | test_uq | 598 | 598 | 0 | 0 |
| scientsbank | test_ua | 405 | 405 | 0 | 0 |

## Thresholds

| Dataset | t1 | t2 | Fitted on | Dev QWK |
|---|---|---|---|---|
| engsaf | 30.000 | 50.000 | engsaf/dev | 0.570 |
| scientsbank | 20.000 | 25.000 | scientsbank/dev | 0.510 |


## Agreement

| Dataset | Split | qwk | accuracy | macro_f1 | adjacent_accuracy | mae_label | mae_score | spearman | n |
|---|---|---|---|---|---|---|---|---|---|
| engsaf | dev | 0.570 [0.479, 0.664] | 0.629 [0.558, 0.721] | 0.591 [0.540, 0.644] | 0.928 [0.891, 0.952] | 0.444 [0.355, 0.514] | 0.242 [0.209, 0.271] | 0.579 [0.477, 0.659] | 595 |
| engsaf | test | 0.384 [0.259, 0.523] | 0.501 [0.411, 0.589] | 0.480 [0.403, 0.553] | 0.868 [0.819, 0.921] | 0.631 [0.506, 0.748] | 0.304 [0.254, 0.350] | 0.464 [0.358, 0.580] | 995 |
| scientsbank | dev | 0.510 [0.422, 0.587] | 0.544 [0.495, 0.593] | 0.518 [0.472, 0.560] | 0.915 [0.884, 0.943] | 0.540 [0.477, 0.608] | 0.328 [0.300, 0.358] | 0.521 [0.429, 0.601] | 568 |
| scientsbank | test_uq | 0.589 [0.402, 0.728] | 0.607 [0.461, 0.733] | 0.559 [0.441, 0.647] | 0.923 [0.896, 0.946] | 0.470 [0.323, 0.641] | 0.277 [0.199, 0.350] | 0.652 [0.465, 0.785] | 598 |
| scientsbank | test_ua | 0.501 [0.404, 0.590] | 0.556 [0.504, 0.607] | 0.501 [0.454, 0.542] | 0.894 [0.857, 0.928] | 0.551 [0.474, 0.630] | 0.341 [0.308, 0.374] | 0.521 [0.424, 0.607] | 405 |

## SciEntsBank 2-way

| Dataset | Split | accuracy_2way | macro_f1_2way | n |
|---|---|---|---|---|
| scientsbank | dev | 0.718 [0.675, 0.763] | 0.711 [0.666, 0.757] | 568 |
| scientsbank | test_uq | 0.759 [0.660, 0.838] | 0.757 [0.644, 0.837] | 598 |
| scientsbank | test_ua | 0.736 [0.691, 0.780] | 0.734 [0.687, 0.777] | 405 |

## Retrieval

Not applicable to this run.

## Calibration

Error is |label - gold| >= 1; auroc_error is the AUROC of (1 - confidence) for predicting error; ece uses 10 bins.

| Dataset | Split | auroc_error | ece | n |
|---|---|---|---|---|
| engsaf | dev | 0.602 [0.525, 0.661] | 0.220 [0.159, 0.283] | 595 |
| engsaf | test | 0.645 [0.582, 0.693] | 0.235 [0.197, 0.275] | 995 |
| scientsbank | dev | 0.564 [0.514, 0.616] | 0.286 [0.245, 0.334] | 568 |
| scientsbank | test_uq | 0.520 [0.408, 0.627] | 0.311 [0.193, 0.420] | 598 |
| scientsbank | test_ua | 0.565 [0.503, 0.623] | 0.288 [0.240, 0.341] | 405 |

## Reliability

| Dataset | Split | failure_rate | parse_failure_rate | integrity_warning_rate | grounded_share | cited_share | n |
|---|---|---|---|---|---|---|---|
| engsaf | dev | 0.007 [0.000, 0.013] | 0.007 [0.000, 0.013] | 0.000 [0.000, 0.000] | n/a | 0.000 [0.000, 0.000] | 599 |
| engsaf | test | 0.002 [0.000, 0.006] | 0.002 [0.000, 0.006] | 0.000 [0.000, 0.000] | n/a | 0.000 [0.000, 0.000] | 997 |
| scientsbank | dev | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | n/a | 0.000 [0.000, 0.000] | 568 |
| scientsbank | test_uq | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | n/a | 0.000 [0.000, 0.000] | 598 |
| scientsbank | test_ua | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | n/a | 0.000 [0.000, 0.000] | 405 |

Failures by type: parse_failure: 6

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
