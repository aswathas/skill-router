# Evaluation results

Case counts: 293 authored, 5 historical. Registry: 1120 local, 318 plugin, 2780 marketplace. Capabilities: 78.

## Headline

| system | cap top-1 | cap top-3 | MRR | strict top-1 | on-topic | mean tokens | median tokens |
|---|---|---|---|---|---|---|---|
| random | 0.013 | 0.054 | 0.030 | 0.000 | 0.040 | 2420 | 1585 |
| name_only | 0.198 | 0.332 | 0.292 | 0.127 | 0.248 | 703 | 336 |
| bm25 | 0.477 | 0.624 | 0.570 | 0.397 | 0.564 | 1898 | 1215 |
| keyword_substring | 0.614 | 0.708 | 0.678 | 0.206 | 0.460 | 592 | 214 |
| no_ledger | 0.849 | 0.889 | 0.876 | 0.413 | 0.799 | 2782 | 1539 |
| no_cost_gate | 0.849 | 0.893 | 0.877 | 0.397 | 0.792 | 3096 | 1608 |
| full_budget | 0.829 | 0.859 | 0.847 | 0.365 | 0.711 | 1402 | 1011 |
| full | 0.849 | 0.893 | 0.878 | 0.397 | 0.795 | 2862 | 1550 |

## Lexically isolated subset

Cases where the request shares no exact keyword string with the expected capability.

| system | n | top-1 | top-3 |
|---|---|---|---|
| random | 66 | 0.030 | 0.076 |
| name_only | 66 | 0.182 | 0.288 |
| bm25 | 66 | 0.273 | 0.348 |
| keyword_substring | 66 | 0.273 | 0.379 |
| no_ledger | 66 | 0.364 | 0.530 |
| no_cost_gate | 66 | 0.364 | 0.545 |
| full_budget | 66 | 0.288 | 0.424 |
| full | 66 | 0.364 | 0.545 |

## Strict subset (one unambiguous skill per case)

| system | n | strict top-1 | strict MRR |
|---|---|---|---|
| random | 63 | 0.000 | 0.000 |
| name_only | 63 | 0.127 | 0.165 |
| bm25 | 63 | 0.397 | 0.446 |
| keyword_substring | 63 | 0.206 | 0.275 |
| no_ledger | 63 | 0.413 | 0.524 |
| no_cost_gate | 63 | 0.397 | 0.530 |
| full_budget | 63 | 0.365 | 0.440 |
| full | 63 | 0.397 | 0.518 |

## Head-to-head against the pre-fix matcher

| outcome | cases |
|---|---|
| shipped router right, pre-fix wrong | 80 |
| pre-fix right, shipped router wrong | 10 |
| both right | 173 |
| both wrong | 35 |

Mean cost of the chosen skill on the cases only the shipped router gets right: shipped router 2727 tokens, pre-fix matcher 249 tokens.


## Per-capability top-1 (full router)

| capability | n | accuracy |
|---|---|---|
| integrations-docs | 3 | 0.000 |
| analytics | 3 | 0.333 |
| ci-delivery | 3 | 0.333 |
| content-cms | 3 | 0.333 |
| design-inspect | 3 | 0.333 |
| code-review | 7 | 0.429 |
| browser | 4 | 0.500 |
| cli-tooling | 4 | 0.500 |
| design-critique | 2 | 0.500 |
| verification | 2 | 0.500 |
| architecture | 5 | 0.600 |
| concurrency | 3 | 0.667 |
| image-generation | 6 | 0.667 |
| integrations-drive | 3 | 0.667 |
| video-audio | 3 | 0.667 |
| debugging | 7 | 0.714 |
| auth | 4 | 0.750 |
| design-direction | 4 | 0.750 |
| memory | 4 | 0.750 |
| observability | 4 | 0.750 |
| writing | 4 | 0.750 |
| research | 9 | 0.778 |
| orchestration | 5 | 0.800 |
| app-automation | 6 | 0.833 |
| planning | 7 | 0.857 |
| refactoring | 8 | 0.875 |
| 3d-graphics | 2 | 1.000 |
| agent-process | 5 | 1.000 |
| api | 5 | 1.000 |
| cloud-ops | 3 | 1.000 |
| code-quality | 2 | 1.000 |
| code-search | 3 | 1.000 |
| cost-tokens | 8 | 1.000 |
| data | 6 | 1.000 |
| database | 4 | 1.000 |
| deployment | 5 | 1.000 |
| design-accessibility | 3 | 1.000 |
| design-copy | 2 | 1.000 |
| design-motion | 4 | 1.000 |
| design-system | 5 | 1.000 |
| devtooling | 4 | 1.000 |
| diagrams | 4 | 1.000 |
| docs-authoring | 7 | 1.000 |
| documentation | 5 | 1.000 |
| documents | 2 | 1.000 |
| ecommerce | 3 | 1.000 |
| email-marketing | 2 | 1.000 |
| file-management | 2 | 1.000 |
| forms | 3 | 1.000 |
| frontend-web | 4 | 1.000 |
| harness-audit | 4 | 1.000 |
| infra-provisioning | 3 | 1.000 |
| integrations-calendar | 3 | 1.000 |
| integrations-gmail | 2 | 1.000 |
| integrations-sheets | 3 | 1.000 |
| integrations-tasks | 3 | 1.000 |
| knowledge-management | 5 | 1.000 |
| marketplace | 2 | 1.000 |
| mcp-builder | 5 | 1.000 |
| payments | 3 | 1.000 |
| performance | 5 | 1.000 |
| problem-solving | 4 | 1.000 |
| research-discovery | 2 | 1.000 |
| response-style | 3 | 1.000 |
| search-observability | 4 | 1.000 |
| security-ops | 4 | 1.000 |
| seo | 3 | 1.000 |
| skill-authoring | 4 | 1.000 |
| social-linkedin | 1 | 1.000 |
| social-media | 2 | 1.000 |
| testing | 8 | 1.000 |
| ui-implementation | 6 | 1.000 |
| version-control | 5 | 1.000 |
