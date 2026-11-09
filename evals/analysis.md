# Statistical analysis

Cases: 298 (293 authored, 5 historical).

## 1. Is the improvement distinguishable from zero?

McNemar exact test on capability top-1 (discordant pairs only), plus a paired bootstrap over MRR. p-values are Holm-corrected across the six baselines.

The first interval resamples cases; the second resamples capabilities, which is the honest unit because cases are clustered by the capability they expect.

| baseline | full only right | baseline only right | MRR diff | 95% CI (cases) | 95% CI (clusters) | McNemar p (raw) | p (Holm) |
|---|---|---|---|---|---|---|---|
| random | 250 | 0 | +0.856 | [0.820, 0.891] | [0.815, 0.896] | 1.1e-75 | 7.7e-75 |
| name_only | 198 | 4 | +0.585 | [0.536, 0.633] | [0.527, 0.641] | 2.1e-53 | 1.3e-52 |
| bm25 | 119 | 7 | +0.308 | [0.259, 0.356] | [0.241, 0.374] | 2.1e-27 | 1.1e-26 |
| keyword_substring | 80 | 10 | +0.200 | [0.155, 0.247] | [0.133, 0.270] | 1.1e-14 | 4.2e-14 |
| full_budget | 8 | 2 | +0.030 | [0.013, 0.050] | [0.012, 0.051] | 0.11 | 0.33 |
| no_ledger | 0 | 0 | +0.002 | [-0.001, 0.004] | [-0.001, 0.004] | 1 | 1 |
| no_cost_gate | 0 | 0 | +0.000 | [-0.001, 0.001] | [-0.001, 0.001] | 1 | 1 |

## 2. Intervals on the headline numbers

| quantity | n | point | 95% CI (Wilson) |
|---|---|---|---|
| full_cap_top1 | 298 | 0.849 | [0.804, 0.885] |
| baseline_cap_top1 | 298 | 0.614 | [0.558, 0.668] |
| full_on_topic | 298 | 0.799 | [0.749, 0.840] |
| baseline_on_topic | 298 | 0.460 | [0.404, 0.516] |
| full_strict_top1 | 63 | 0.397 | [0.285, 0.520] |
| baseline_strict_top1 | 63 | 0.206 | [0.125, 0.322] |

## 3. Oracle ceiling and headroom

- Cases with at least one skill carrying the expected capability: **297 / 298** (0.997).
- Expected skill present in the registry: 1 cases absent.
- Mean providers per capability: 49.8, worst case 839 skills.
- Ranking headroom: shipped router 0.849, pre-fix matcher 0.614, perfect ranker 1.000.

## 4. A split the design was not tuned on

Cases are split by a stable hash of the case id. The taxonomy and the router rules were designed while every case was visible, so this is a leakage-aware check, not a clean held-out evaluation.

| split | n | full top-1 | baseline top-1 | full strict | baseline strict |
|---|---|---|---|---|---|
| dev | 147 | 0.959 | 0.673 | 0.387 | 0.226 |
| test | 151 | 0.742 | 0.556 | 0.406 | 0.188 |

Significance inside each half. The taxonomy repair was driven by the dev half alone, so the test half is the honest number.

| split | n | full top-1 | baseline top-1 | full only right | baseline only right | MRR diff | 95% CI | McNemar p |
|---|---|---|---|---|---|---|---|---|
| dev | 147 | 0.959 | 0.673 | 44 | 2 | +0.227 | [0.163, 0.293] | 3.1e-11 |
| test | 151 | 0.742 | 0.556 | 36 | 8 | +0.173 | [0.109, 0.239] | 2.5e-05 |

## 5. The accuracy-cost frontier

| token budget | cap top-1 | strict top-1 | mean cost | median cost |
|---|---|---|---|---|
| 500 | 0.805 | 0.206 | 1,396 | 360 |
| 1000 | 0.826 | 0.254 | 1,149 | 734 |
| 2000 | 0.829 | 0.365 | 1,402 | 1,011 |
| 4000 | 0.846 | 0.397 | 1,891 | 1,391 |
| 8000 | 0.849 | 0.381 | 2,268 | 1,518 |
| none | 0.849 | 0.397 | 2,881 | 1,550 |

## 6. Error analysis

Every capability-level failure of the shipped router, categorised.

| category | count |
|---|---|
| inference error: the request never named the capability | 42 |
| ranking error: right capability was inferred but not ranked | 2 |
| ranking error: right capability was in the top three | 1 |
| **total failures** | **45** |

Which capabilities account for the failures, and is the failure an inference miss (the request never named the capability) or a ranking miss (it did, and the ranker still missed it)?

| capability | cases | failures | inference misses | ranking misses |
|---|---|---|---|---|
| code-review | 7 | 4 | 4 | 0 |
| architecture | 6 | 3 | 3 | 0 |
| integrations-docs | 3 | 3 | 3 | 0 |
| research | 9 | 2 | 2 | 0 |
| debugging | 7 | 2 | 2 | 0 |
| design-inspect | 3 | 2 | 2 | 0 |
| image-generation | 6 | 2 | 2 | 0 |
| analytics | 3 | 2 | 2 | 0 |
| content-cms | 3 | 2 | 0 | 2 |
| browser | 4 | 2 | 2 | 0 |
| cli-tooling | 4 | 2 | 2 | 0 |
| ci-delivery | 3 | 2 | 2 | 0 |
| app-automation | 6 | 1 | 1 | 0 |
| planning | 7 | 1 | 1 | 0 |
| writing | 4 | 1 | 1 | 0 |
| design-direction | 4 | 1 | 1 | 0 |
| video-audio | 3 | 1 | 1 | 0 |
| auth | 4 | 1 | 1 | 0 |
| concurrency | 3 | 1 | 1 | 0 |
| observability | 4 | 1 | 1 | 0 |

Strict-subset failures:

| category | count |
|---|---|
| right capability, sibling skill chosen | 27 |
| wrong capability | 11 |

**inference error: the request never named the capability**

- `wire my calendar to a slack channel so meetings announce themselves` -> chose `meeting-insights-analyzer` (expected capability `app-automation`)
- `compare the top three cloud providers for a small team and tell me whi` -> chose `cloudlayer-automation` (expected capability `research`)
- `what are the realistic risks of migrating off postgres` -> chose `Neon Automation` (expected capability `research`)

**ranking error: right capability was inferred but not ranked**

- `migrate the blog posts into the headless cms` -> chose `viral-linkedin-post` (expected capability `content-cms`)
- `write the article in the content pipeline format` -> chose `internal-comms` (expected capability `content-cms`)

**ranking error: right capability was in the top three**

- `find the file in my drive folder` -> chose `file-organizer` (expected capability `integrations-drive`)

## 7. The lexically isolated subset

A case is lexically isolated when its request shares no exact keyword string with the expected capability's keyword lists. Which cases qualify depends on the lists used to define it, so both are measured. Every system is scored on the same subset.

### Isolated by the shipped taxonomy keyword lists (66 cases)

| system | top-1 | top-3 |
|---|---|---|
| full | 0.364 | 0.545 |
| keyword_substring | 0.273 | 0.379 |
| bm25 | 0.273 | 0.348 |
| no_ledger | 0.364 | 0.530 |
| no_cost_gate | 0.364 | 0.545 |
| full_budget | 0.288 | 0.424 |
| name_only | 0.182 | 0.288 |
| random | 0.015 | 0.015 |

### Isolated by the pre repair taxonomy keyword lists (126 cases)

| system | top-1 | top-3 |
|---|---|---|
| full | 0.659 | 0.762 |
| keyword_substring | 0.444 | 0.540 |
| bm25 | 0.349 | 0.468 |
| no_ledger | 0.659 | 0.754 |
| no_cost_gate | 0.659 | 0.762 |
| full_budget | 0.627 | 0.698 |
| name_only | 0.159 | 0.254 |
| random | 0.008 | 0.040 |

## 8. Robustness to a missing keyword

The strongest matching keyword is deleted from the request and the request is routed again.

- Cases with a matched keyword: 232
- Expected capability still inferred: 43 (0.185)
- Same skill still chosen: 79 (0.341)

