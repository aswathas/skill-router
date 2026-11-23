#!/usr/bin/env python3
"""Experiment 4: let the semantic neighbourhood lead when the keywords are silent.

The strict failures decompose into three groups, and only the third is fixable
by a ranker:

  35 of 63  the expected skill is dropped before ranking (score 0)
  27 of 63  the expected skill is not installed on this machine at all
            (unwinnable: the ceiling on strict top-1 here is 36/63 = 0.571)
  23 of 63  the expected skill is inside the semantic top ten

So the layer needs to be able to *lead*, not only to vote. When the keywords
name no capability, the answer should come from the semantic neighbourhood
itself - the skills closest to the request - with the taxonomy as the
tie-break inside it, not the other way round.

Usage: python evals/exp_lead.py
"""

import argparse
import importlib.util
import json
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SCRIPTS = REPO / "skills" / "aswath-capability" / "scripts"


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


embed = _load(SCRIPTS / "embed.py", "embed_mod")
inv = _load(SCRIPTS / "invoke.py", "inv_mod")


def state_dir():
    return embed.state_dir()


def load_cases():
    cases = []
    for name in ("benchmark-a.jsonl", "benchmark-b.jsonl",
                 "benchmark-c.jsonl", "historical.jsonl"):
        p = HERE / name
        if p.is_file():
            for line in p.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    cases.append(json.loads(line))
    return cases


def full_scan(qvec, skill_vecs, limit):
    """The whole catalogue, closest first."""
    scored = []
    for slug, v in skill_vecs.items():
        if v:
            scored.append((embed.cosine(qvec, v), slug))
    scored.sort(reverse=True)
    return scored[:limit]


def run(system, cases, reg, cap_map, cache, w):
    skill_vecs = embed.skill_vectors(cache)
    limit = w.get("limit", 15)
    lead_at = w.get("lead_at", 0.0)
    keyword_infer = inv.infer_capabilities
    rows = []
    for case in cases:
        req = case["request"]
        weights = keyword_infer(req, cap_map)
        strong = [c for c, (ww, _) in weights.items() if ww >= 2]
        weak = {c for c, (ww, _) in weights.items() if ww < 2}

        vecs, cache = embed.embed_texts([req], cache)
        qvec = vecs[0]
        near = full_scan(qvec, skill_vecs, limit)
        by_slug = {}
        for s in inv.all_skills(reg):
            if isinstance(s, dict):
                by_slug[s.get("slug")] = s

        cands, _ = inv.score_candidates(reg, req, cap_map)
        ranked = list(cands)

        if lead_at and not strong:
            # The keywords named no capability. Let the neighbourhood lead,
            # and let the weak keyword capabilities order it.
            pool = []
            for sim, slug in near:
                if sim < lead_at:
                    break
                s = by_slug.get(slug)
                if not s:
                    continue
                item = dict(s)
                item["_match"] = sim
                item["_sem"] = sim
                item["_caps"] = sorted(set(s.get("tags") or []) & weak)
                item["_cap_overlap"] = len(item["_caps"])
                pool.append(item)
            pool.sort(key=lambda c: (-c["_cap_overlap"], -c["_sem"]))
            pool_slugs = {c.get("slug") for c in pool}
            ranked = pool + [c for c in cands if c.get("slug") not in pool_slugs]

        ranked = inv.cost_gate(ranked, 4.0)
        exp_cap = case.get("cap")
        exp_skill = case.get("skill")
        chosen = ranked[0] if ranked else None
        rank = 0
        for i, c in enumerate(ranked, 1):
            if exp_cap and exp_cap in (c.get("tags") or []):
                rank = i
                break
        row = {
            "cap_top1": bool(exp_cap and exp_cap in ((chosen or {}).get("tags") or [])),
            "mrr": (1.0 / rank) if rank else 0.0,
            "cost": (chosen or {}).get("tokens_est") or 0,
            "chosen": (chosen or {}).get("name"),
        }
        if exp_skill:
            row["strict_top1"] = row["chosen"] == exp_skill
            row["strict_rank"] = next(
                (i for i, c in enumerate(ranked, 1) if c.get("name") == exp_skill), 0)
        rows.append(row)
    n = len(rows)
    out = {
        "cap_top1": sum(1 for r in rows if r["cap_top1"]) / n,
        "mrr": sum(r["mrr"] for r in rows) / n,
        "mean_cost": sum(r["cost"] for r in rows) / n,
    }
    strict = [r for r in rows if "strict_top1" in r]
    if strict:
        out["strict_top1"] = sum(1 for r in strict if r["strict_top1"]) / len(strict)
        out["strict_mrr"] = sum((1.0 / r["strict_rank"]) if r["strict_rank"] else 0.0
                                for r in strict) / len(strict)
    return out, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--grid", action="store_true")
    args = ap.parse_args()
    reg = json.loads((state_dir() / "skills.json").read_text(encoding="utf-8"))
    caps = json.loads((state_dir() / "capabilities.json").read_text(encoding="utf-8"))
    cap_map = caps.get("capabilities", {})
    cache = embed.load_cache()
    cases = load_cases()
    variants = [("keyword only", {})]
    if args.grid:
        for limit in (5, 10, 15, 30):
            for lead_at in (0.35, 0.45, 0.55):
                variants.append(("lead lim%d at>=%.2f" % (limit, lead_at),
                                 {"limit": limit, "lead_at": lead_at}))
    else:
        for limit in (5, 10, 15):
            variants.append(("lead lim%d at>=0.40" % limit,
                             {"limit": limit, "lead_at": 0.40}))
    for name, w in variants:
        t = time.time()
        out, _ = run(name, cases, reg, cap_map, cache, w)
        print("%-22s top1=%.3f mrr=%.3f strict=%.3f cost=%.0f  (%.0fs)"
              % (name, out["cap_top1"], out["mrr"], out.get("strict_top1", 0),
                 out["mean_cost"], time.time() - t))


if __name__ == "__main__":
    main()
