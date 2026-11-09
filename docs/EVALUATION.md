# Evaluation

Everything in this file is produced by the harness and stored in
`evals/`. Nothing here is hand-typed.

| script | what it produces |
|---|---|
| `evals/run_eval.py` | `results.json`, `results.md` — seven systems on 298 cases |
| `evals/analysis.py` | `analysis.json`, `analysis.md` — significance, intervals, headroom, halves, frontier, error analysis, robustness |
| `evals/taxonomy_ablation.py` | `taxonomy-ablation.json`, `taxonomy-ablation.md` — the taxonomy's own contribution |

~~~bash
cd evals
python run_eval.py            # ~4 minutes
python analysis.py            # ~8 minutes
python taxonomy_ablation.py   # ~3 minutes
~~~

## The benchmark

| file | cases | what it is |
|---|---|---|
| `benchmark-a.jsonl` | 60 | authored, paraphrased needs labelled by capability |
| `benchmark-b.jsonl` | 182 | authored, paraphrased needs labelled by capability |
| `benchmark-c.jsonl` | 51 | authored needs that also name **one** unambiguous skill |
| `historical.jsonl` | 5 | request→skill pairs extracted from stored sessions |

**298 cases**: 293 authored, 5 historical. The authored cases cover **61 of the
78 capabilities**. **63** cases carry a single expected skill (the strict
subset). **126** cases share no exact keyword string with the expected
capability (the lexically isolated subset).

### Two guards against circularity

1. **Paraphrase discipline.** Requests are written the way a person would type
   them and avoid the taxonomy's own keyword strings where a paraphrase exists.
2. **A computed lexically isolated subset.** Cases that share no exact keyword
   string with the expected capability's lists are reported separately.

### The dev/test split

Cases are split by a stable hash of the case id. **Every taxonomy change was
made using the dev half alone**, so the test half is a held-out measurement of
the repair. It is not a clean held-out evaluation of the whole system: the
router's rules and the taxonomy's structure were both designed while every
case was visible.

## Systems compared

| system | what it is |
|---|---|
| `random` | uniform sample from the catalogue |
| `name_only` | rank by name-word overlap |
| `bm25` | **Okapi BM25 over skill name + description** — a real retrieval baseline, taxonomy-blind, ledger-blind and cost-blind |
| `keyword_substring` | the **pre-fix** ranking, faithfully reimplemented |
| `no_ledger` | shipped router with the outcome ledger neutralised |
| `no_cost_gate` | shipped router without the Pareto gate |
| `full_budget` | shipped router restricted to skills costing ≤ 2,000 tokens |
| `full` | the shipped router |

## Headline (298 cases)

| system | cap top-1 | cap top-3 | MRR | strict top-1 | on-topic | mean tok | median tok |
|---|---|---|---|---|---|---|---|
| random | 0.013 | 0.054 | 0.030 | 0.000 | 0.040 | 2,420 | 1,585 |
| name-only | 0.198 | 0.332 | 0.292 | 0.127 | 0.248 | 703 | 336 |
| BM25 | 0.477 | 0.624 | 0.570 | **0.397** | 0.564 | 1,898 | 1,215 |
| keyword-substring (pre-fix) | 0.614 | 0.708 | 0.678 | 0.206 | 0.460 | 592 | 214 |
| no-ledger | 0.849 | 0.889 | 0.876 | 0.413 | 0.799 | 2,782 | 1,539 |
| no-cost-gate | 0.849 | 0.893 | 0.877 | 0.397 | 0.792 | 3,096 | 1,608 |
| full-budget (2K) | 0.829 | 0.859 | 0.847 | 0.365 | 0.711 | 1,402 | 1,011 |
| **full (shipped)** | **0.849** | **0.893** | **0.878** | 0.397 | **0.795** | 2,862 | 1,550 |

### The headline is two different stories

- **Which capability does this request belong to?** The taxonomy wins
  decisively: 0.849 against 0.614 for the pre-fix matcher and 0.477 for BM25.
- **Which exact skill should I load?** BM25 **ties** the full router at 0.397.
  The pre-fix matcher is far behind at 0.206.

The taxonomy buys capability coverage, not skill disambiguation. We report the
tie rather than the metric that flatters us.

## Significance

McNemar's exact test on capability top-1 over the discordant pairs, a paired
bootstrap over MRR, and Holm correction across the baselines.

| baseline | full only right | baseline only right | MRR diff | 95% CI (cases) | McNemar p (Holm) |
|---|---|---|---|---|---|
| random | 251 | 2 | +0.848 | [0.809, 0.886] | 2.7e-71 |
| name-only | 198 | 4 | +0.586 | [0.536, 0.633] | 1.1e-52 |
| keyword-substring | 80 | 10 | +0.200 | [0.155, 0.247] | 4.2e-14 |
| full-budget | 8 | 2 | +0.031 | [0.013, 0.050] | 0.33 |
| no-ledger | 0 | 0 | +0.002 | [-0.001, 0.004] | 1 |
| no-cost-gate | 0 | 0 | +0.001 | [0.000, 0.001] | 1 |

Cases are clustered by expected capability, so the harness also reports a
bootstrap that resamples **capabilities** rather than cases. The conclusion
does not depend on which interval is used.

Wilson intervals on the headline numbers:

| quantity | n | point | 95% CI |
|---|---|---|---|
| full capability top-1 | 298 | 0.849 | [0.804, 0.885] |
| pre-fix capability top-1 | 298 | 0.614 | [0.558, 0.668] |
| full on-topic | 298 | 0.795 | [0.746, 0.837] |
| pre-fix on-topic | 298 | 0.460 | [0.404, 0.516] |
| full strict top-1 | 63 | 0.397 | [0.285, 0.520] |
| pre-fix strict top-1 | 63 | 0.206 | [0.125, 0.322] |

## The taxonomy ablation

The shipped router, the same benchmark, the same cost gate. The only thing
that changes is the taxonomy: the registry is rebuilt from scratch with the
pre-repair keyword lists, so the skills are tagged the way they would have
been tagged before.

| taxonomy | cap top-1 | strict top-1 | MRR | on-topic | mean cost |
|---|---|---|---|---|---|
| v1, before the repair | 0.661 | 0.381 | 0.713 | 0.802 | 2,675 |
| v2, after the repair | **0.849** | 0.397 | **0.878** | 0.795 | 2,862 |

Paired: the repaired taxonomy is right where the original is wrong on **59**
cases and wrong where it is right on **3**. McNemar p = 1.7e-14. The MRR
difference is +0.166 with a 95% paired bootstrap interval of [0.128, 0.206].

Nothing else changed. This is the measurement behind the paper's central
claim that the taxonomy is the load-bearing part.

### Where the repair came from

The error analysis that motivated it: of the 101 capability-level failures,
**98 were cases where the request never named the expected capability at all**
and only three were ranking errors. The failure was in the vocabulary, not in
the ranker.

## The dev/test split

| split | n | full top-1 | pre-fix top-1 | full strict | pre-fix strict |
|---|---|---|---|---|---|
| dev (used for the repair) | 147 | 0.959 | 0.673 | 0.387 | 0.226 |
| test (held out) | 151 | **0.742** | 0.556 | 0.406 | 0.188 |

On the held-out half the difference is still significant: 36 cases favour the
repaired taxonomy, 8 favour the original, p = 2.5e-05.

The gap between the halves, 21 points, is the size of the optimism we cannot
rule out elsewhere. We report it rather than hide it.

## Lexically isolated subset (126 cases)

| system | top-1 | top-3 |
|---|---|---|
| random | 0.024 | 0.040 |
| name-only | 0.095 | 0.167 |
| keyword-substring (pre-fix) | 0.254 | 0.397 |
| no-ledger | 0.222 | 0.357 |
| no-cost-gate | 0.222 | 0.365 |
| full-budget (2K) | 0.167 | 0.333 |
| full (shipped) | 0.222 | 0.365 |

**The shipped router is worse than the pre-fix matcher on this subset.** The
pre-fix matcher's flat inference fires on any substring overlap and lands on
skills carrying a wide spread of tags, which raises the chance the expected
tag is among them. The shipped router is more discriminating: it declines to
route when the evidence does not identify a capability, and gives up some
accidental coverage. Discriminating and well-calibrated are not the same
thing.

## The accuracy-cost frontier

| token budget | cap top-1 | strict top-1 | mean cost | median cost |
|---|---|---|---|---|
| 500 | 0.805 | 0.206 | 1,396 | 360 |
| 1,000 | 0.826 | 0.254 | 1,149 | 734 |
| 2,000 | 0.829 | 0.365 | 1,402 | 1,011 |
| 4,000 | 0.846 | 0.397 | 1,891 | 1,391 |
| 8,000 | 0.849 | 0.381 | 2,250 | 1,507 |
| none | 0.849 | 0.397 | 2,862 | 1,550 |

A 1,000-token budget recovers 60% of the cost for 2.3 points of capability
top-1 — but 14.3 points of strict top-1. **Cost is cheap to recover;
accuracy is not.**

## Error analysis

Of the 45 capability-level failures of the shipped router:

| category | count |
|---|---|
| inference error: the request never named the capability | 42 |
| ranking error: right capability was inferred but not ranked | 2 |
| ranking error: right capability was in the top three | 1 |

Strict-subset failures:

| category | count |
|---|---|
| right capability, sibling skill chosen | 27 |
| wrong capability | 11 |

Capability-level failures are a vocabulary problem. Strict-subset failures are
a disambiguation problem. They need different fixes, and the taxonomy
ablation shows which one is worth doing now.

## Robustness to a missing keyword

Delete the strongest matching keyword from the request and route it again:

- cases with a matched keyword: 232
- expected capability still inferred: 43 (0.185)
- same skill still chosen: 78 (0.336)

The router is keyword-driven, not semantic. A request that says the same thing
in different words is a different request to the router.

## System-level effects

| quantity | before | after |
|---|---|---|
| skills visible to the agent | 1,241 | 36 |
| catalog listing cost (tokens, est.) | 1,867,228 | 62,121 |
| capabilities in the taxonomy | 51 | 78 |
| skills no capability could reach | 845 | 0 |
| skills in the registry | 4,098 | 4,218 |

Raw numbers: `evals/results.json`, `evals/results.md`,
`evals/analysis.json`, `evals/analysis.md`,
`evals/taxonomy-ablation.json`, `evals/system-metrics.json`.
