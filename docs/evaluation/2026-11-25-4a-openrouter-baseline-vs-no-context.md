# Comparison

- A: `openrouter-baseline-gpt-oss-120b-2c2c3cd3c719c4d6`
- B: `openrouter-no-context-gpt-oss-120b-11bc137abb06e3ac`

| Dataset | Split | Metric | Difference (B - A) [95% CI] | Verdict | Paired items |
|---|---|---|---|---|---|
| engsaf | dev | qwk | -0.081 [-0.155, -0.008] | worsens | 593 |
| engsaf | dev | mae_score | 0.040 [0.018, 0.063] | worsens | 593 |
| engsaf | dev | spearman | -0.089 [-0.170, -0.026] | worsens | 593 |
| engsaf | test | qwk | -0.295 [-0.401, -0.182] | worsens | 994 |
| engsaf | test | mae_score | 0.115 [0.077, 0.147] | worsens | 994 |
| engsaf | test | spearman | -0.262 [-0.358, -0.156] | worsens | 994 |
| scientsbank | dev | qwk | -0.157 [-0.226, -0.089] | worsens | 568 |
| scientsbank | dev | mae_score | 0.096 [0.067, 0.125] | worsens | 568 |
| scientsbank | dev | spearman | -0.151 [-0.219, -0.088] | worsens | 568 |
| scientsbank | test_ua | qwk | -0.214 [-0.302, -0.126] | worsens | 405 |
| scientsbank | test_ua | mae_score | 0.134 [0.106, 0.163] | worsens | 405 |
| scientsbank | test_ua | spearman | -0.219 [-0.304, -0.145] | worsens | 405 |
| scientsbank | test_uq | qwk | -0.137 [-0.258, -0.049] | worsens | 598 |
| scientsbank | test_uq | mae_score | 0.067 [0.039, 0.098] | worsens | 598 |
| scientsbank | test_uq | spearman | -0.094 [-0.223, -0.017] | worsens | 598 |

Items per side (pairs are dropped when either side failed):

| Dataset | Split | A results | A failures | B results | B failures | Paired | Pairs dropped | Unmatched |
|---|---|---|---|---|---|---|---|---|
| engsaf | dev | 599 | 3 | 599 | 4 | 593 | 6 | 0 |
| engsaf | test | 997 | 1 | 997 | 2 | 994 | 3 | 0 |
| scientsbank | dev | 568 | 0 | 568 | 0 | 568 | 0 | 0 |
| scientsbank | test_ua | 405 | 0 | 405 | 0 | 405 | 0 | 0 |
| scientsbank | test_uq | 598 | 0 | 598 | 0 | 598 | 0 | 0 |

