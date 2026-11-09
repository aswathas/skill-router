# Taxonomy ablation

The shipped router, the same benchmark, the same cost gate. The only thing that changes is the taxonomy: v1 is the taxonomy as it was before the error-analysis repair, v2 is the repaired one.

| taxonomy | cap top-1 | cap top-3 | MRR | strict top-1 | on-topic | mean cost |
|---|---|---|---|---|---|---|
| v1 original | 0.661 | 0.725 | 0.714 | 0.381 | 0.805 | 2,587 |
| v2 repaired | 0.849 | 0.893 | 0.878 | 0.397 | 0.799 | 2,881 |

Paired: the repaired taxonomy is right where the original is wrong on 58 cases, wrong where it is right on 2, McNemar p = 3.2e-15, MRR difference +0.164 with a 95% paired bootstrap interval of [0.126, 0.204].
