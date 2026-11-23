#!/usr/bin/env python3
"""Experiment 3: hybrid retrieval - BM25 shortlist, semantic rerank.

Two earlier results shaped this one.

The capability centroid does not work. A centroid is the mean of up to 800
skill vectors, so it drifts toward the generic direction of the catalogue:
"compare the top three cloud providers" was nearest to the cost-tokens
centroid, not to research.

Skill-level similarity is sharp. The same request's nearest skills were
claimable-cloud and box; "wire my calendar to a slack channel" was nearest to
slack-messaging and gws-calendar.

So the semantic signal enters where it is sharp, over a shortlist that BM25
already recalled. That keeps the cost of a query at ~150 vector comparisons
instead of 3,065, and it stops the semantic score from drowning the taxonomy.

  vote   the shortlist's nearest skills vote for their capabilities, so a
         capability the request never named can still be inferred
  tie    among the skills carrying the winning capability, the one closest to
         the request wins the exact-skill check

Usage: python evals/exp_semantic.py [--grid]
"""

import argparse
import importlib.util
import json
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
run_eval = _load(HERE / "run_eval.py", "run_eval_mod")


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


def shortlist(reg, cap_map, req, size):
    """BM25 recall over the catalogue, unioned with the taxonomy's picks."""
    bm = run_eval.bm25_rank(reg, cap_map, req)
    out = []
    seen = set()
    for c in bm[:size]:
        key = c.get("slug") or c.get("name")
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    cands, _ = inv.score_candidates(reg, req, cap_map)
    for c in cands:
        key = c.get("slug") or c.get("name")
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
        if len(out) >= size * 2:
            break
    return out


def run(system, cases, reg, cap_map, cache, w):
    skill_vecs = embed.skill_vectors(cache)
    size = w.get("size", 150)
    vote_at = w.get("vote_at", 0.0)
    vote_mode = w.get("vote_mode", "secondary")
    tie = w.get("tie", False)
    keyword_infer = inv.infer_capabilities
    rows = []
    for case in cases:
        req = case["request"]
        vecs, cache = embed.embed_texts([req], cache)
        qvec = vecs[0]
        pool = shortlist(reg, cap_map, req, size)

        # semantic neighbours inside the recalled shortlist
        sem = []
        for c in pool:
            v = skill_vecs.get(c.get("slug"))
            if v:
                sem.append((embed.cosine(qvec, v), c))
        sem.sort(key=lambda t: -t[0])

        votes = {}
        if vote_at:
            for sim, c in sem:
                if sim < vote_at:
                    continue
                for cap in c.get("tags") or []:
                    if sim > votes.get(cap, 0):
                        votes[cap] = sim

        def infer(text, cap_map, _v=votes, _orig=keyword_infer):
            got = _orig(text, cap_map)
            if not _v:
                return got
            strong = [c for c, (ww, _) in got.items() if ww >= 2]
            for cap, sim in _v.items():
                if cap in got:
                    continue
                if vote_mode == "secondary" and strong:
                    got[cap] = (1, 10 ** 5)
                elif vote_mode == "one":
                    # Exactly one capability, and only when the keywords
                    # named none. Twenty voted capabilities drown the
                    # taxonomy; one restores the intent.
                    if strong:
                        continue
                    best = max(_v.items(), key=lambda kv: kv[1])
                    got[best[0]] = (2, 10 ** 5)
                    break
                else:
                    got[cap] = (2, 10 ** 5)
            return got

        inv.infer_capabilities = infer
        try:
            cands, _ = inv.score_candidates(reg, req, cap_map)
        finally:
            inv.infer_capabilities = keyword_infer

        if tie and cands:
            sim_of = {}
            for sim, c in sem:
                sim_of[c.get("slug")] = sim
            if w.get("tie_mode", "overlap") == "cap":
                # Everyone carrying the winning capability, not everyone
                # with the same overlap number. The overlap number is a
                # count; the capability is the thing.
                win = (cands[0].get("_caps") or [])
                group = [c for c in cands
                         if win and set(win) & set(c.get("tags") or [])]
            else:
                best_cap = max((c.get("_cap_overlap", 0) for c in cands), default=0)
                group = [c for c in cands
                         if c.get("_cap_overlap", 0) == best_cap and best_cap > 0]
            if group:
                group.sort(key=lambda c: -sim_of.get(c.get("slug"), 0.0))
                gi = 0
                out = []
                for c in cands:
                    if c in group:
                        out.append(group[gi])
                        gi += 1
                    else:
                        out.append(c)
                cands = out

        ranked = inv.cost_gate(cands, 4.0)
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
        out["strict_n"] = len(strict)
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
    print("cases %d, cache %d skills" % (len(cases), len(embed.skill_vectors(cache))))

    variants = [("keyword only (baseline)", {})]
    if args.grid:
        for vote_at in (0.35, 0.45, 0.55, 0.65):
            variants.append(("vote at>=%.2f" % vote_at, {"vote_at": vote_at}))
        variants.append(("tie only", {"tie": True}))
        for vote_at in (0.45, 0.55):
            variants.append(("vote %.2f + tie" % vote_at,
                             {"vote_at": vote_at, "tie": True}))
        variants.append(("vote .45 primary + tie",
                         {"vote_at": 0.45, "vote_mode": "primary", "tie": True}))
    else:
        variants = [("keyword only (baseline)", {}),
                    ("vote at>=0.45", {"vote_at": 0.45}),
                    ("vote at>=0.55", {"vote_at": 0.55}),
                    ("tie only", {"tie": True}),
                    ("vote .55 + tie", {"vote_at": 0.55, "tie": True})]

    for name, weights in variants:
        t = time.time()
        out, _ = run(name, cases, reg, cap_map, cache, weights)
        print("%-26s top1=%.3f mrr=%.3f strict=%.3f cost=%.0f  (%.0fs)"
              % (name, out["cap_top1"], out["mrr"], out.get("strict_top1", 0),
                 out["mean_cost"], time.time() - t))


if __name__ == "__main__":
    main()
