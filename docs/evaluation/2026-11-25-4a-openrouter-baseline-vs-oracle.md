# Comparison

- A: `openrouter-baseline-gpt-oss-120b-2c2c3cd3c719c4d6`
- B: `openrouter-oracle-gpt-oss-120b-8c5ed2af3a80372f`

| Dataset | Split | Metric | Difference (B - A) [95% CI] | Verdict | Paired items |
|---|---|---|---|---|---|
| engsaf | dev | qwk | 0.027 [-0.012, 0.070] | no detectable difference | 592 |
| engsaf | dev | mae_score | -0.007 [-0.018, 0.003] | no detectable difference | 592 |
| engsaf | dev | spearman | 0.013 [-0.025, 0.050] | no detectable difference | 592 |
| engsaf | test | qwk | 0.012 [-0.021, 0.046] | no detectable difference | 994 |
| engsaf | test | mae_score | -0.002 [-0.010, 0.008] | no detectable difference | 994 |
| engsaf | test | spearman | -0.014 [-0.030, 0.007] | no detectable difference | 994 |
| scientsbank | dev | qwk | 0.043 [-0.000, 0.088] | no detectable difference | 567 |
| scientsbank | dev | mae_score | -0.024 [-0.040, -0.008] | improves | 567 |
| scientsbank | dev | spearman | 0.035 [-0.004, 0.076] | no detectable difference | 567 |
| scientsbank | test_ua | qwk | 0.056 [0.005, 0.112] | improves | 404 |
| scientsbank | test_ua | mae_score | -0.025 [-0.042, -0.008] | improves | 404 |
| scientsbank | test_ua | spearman | 0.023 [-0.018, 0.065] | no detectable difference | 404 |
| scientsbank | test_uq | qwk | 0.029 [-0.012, 0.060] | no detectable difference | 598 |
| scientsbank | test_uq | mae_score | -0.021 [-0.037, -0.004] | improves | 598 |
| scientsbank | test_uq | spearman | 0.024 [-0.010, 0.049] | no detectable difference | 598 |

Items per side (pairs are dropped when either side failed):

| Dataset | Split | A results | A failures | B results | B failures | Paired | Pairs dropped | Unmatched |
|---|---|---|---|---|---|---|---|---|
| engsaf | dev | 599 | 3 | 599 | 4 | 592 | 7 | 0 |
| engsaf | test | 997 | 1 | 997 | 2 | 994 | 3 | 0 |
| scientsbank | dev | 568 | 0 | 568 | 1 | 567 | 1 | 0 |
| scientsbank | test_ua | 405 | 0 | 405 | 1 | 404 | 1 | 0 |
| scientsbank | test_uq | 598 | 0 | 598 | 0 | 598 | 0 | 0 |

