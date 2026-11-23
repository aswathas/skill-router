#!/usr/bin/env python3
"""Grid over the hybrid retrieval settings, with a significance check.

The headline limit is strict top-1: the fraction of cases where the router
picks the one skill the case expects, not merely a skill of the right
capability. On the 63 strict cases a change of a few points is noise, so every
variant is compared with the baseline by McNemar's exact test on the discordant
pairs.

Usage: python evals/exp_grid.py
"""

import importlib.util
import json
import math
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("exp", HERE / "exp_semantic.py")
exp = importlib.util.module_from_spec(spec)
sys.modules["exp"] = exp
spec.loader.exec_module(exp)


def mcnemar(b, c):
    """Two-sided exact McNemar on discordant pairs. b = baseline only, c = variant only."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    total = 0.0
    for i in range(0, n + 1):
        p = math.comb(n, i)
        if i <= k:
            total += p
    return min(1.0, total / (2 ** n))


def main():
    reg = json.loads((exp.state_dir() / "skills.json").read_text(encoding="utf-8"))
    caps = json.loads((exp.state_dir() / "capabilities.json").read_text(encoding="utf-8"))
    cap_map = caps.get("capabilities", {})
    cache = exp.embed.load_cache()
    cases = exp.load_cases()

    base_out, base_rows = exp.run("baseline", cases, reg, cap_map, cache, {})
    base_strict = [r.get("strict_top1") for r in base_rows if "strict_top1" in r]
    print("baseline top1=%.3f mrr=%.3f strict=%.3f cost=%.0f"
          % (base_out["cap_top1"], base_out["mrr"], base_out["strict_top1"],
             base_out["mean_cost"]))

    variants = []
    for size in (150, 300):
        for vote_at in (0.35, 0.45, 0.55):
            variants.append(("size%d rescue%.2f tie" % (size, vote_at),
                             {"size": size, "vote_at": vote_at,
                              "vote_mode": "one", "tie": True}))
    variants.append(("size300 rescue.45 tie, no rescue",
                     {"size": 300, "vote_at": 0, "tie": True}))
    variants.append(("size300 rescue.45 primary tie",
                     {"size": 300, "vote_at": 0.45, "vote_mode": "primary", "tie": True}))

    for name, w in variants:
        t = time.time()
        out, rows = exp.run(name, cases, reg, cap_map, cache, w)
        strict = [r.get("strict_top1") for r in rows if "strict_top1" in r]
        b = sum(1 for x, y in zip(base_strict, strict) if x and not y)
        c = sum(1 for x, y in zip(base_strict, strict) if y and not x)
        p = mcnemar(b, c)
        print("%-34s top1=%.3f mrr=%.3f strict=%.3f cost=%.0f  "
              "discordant b=%d v=%d p=%.3f  (%.0fs)"
              % (name, out["cap_top1"], out["mrr"], out.get("strict_top1", 0),
                 out["mean_cost"], b, c, p, time.time() - t))


if __name__ == "__main__":
    main()
