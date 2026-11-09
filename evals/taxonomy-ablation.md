# Taxonomy ablation

The shipped router, the same benchmark, the same cost gate. The only thing that changes is the taxonomy: v1 is the taxonomy as it was before the error-analysis repair, v2 is the repaired one.

| taxonomy | cap top-1 | cap top-3 | MRR | strict top-1 | on-topic | mean cost |
|---|---|---|---|---|---|---|
| v1 original | 0.661 | 0.721 | 0.712 | 0.397 | 0.799 | 2,522 |
| v2 repaired | 0.849 | 0.893 | 0.878 | 0.397 | 0.795 | 2,862 |

Paired: the repaired taxonomy is right where the original is wrong on 59 cases, wrong where it is right on 3, McNemar p = 1.7e-14, MRR difference +0.166 with a 95% paired bootstrap interval of [0.128, 0.206].
