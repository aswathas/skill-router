#!/usr/bin/env python3
"""Statistical analysis of the capability-routing evaluation.

run_eval.py answers "how accurate is each system". This module answers the
questions a reviewer asks next:

  * is the improvement statistically distinguishable from zero?
  * how much headroom is left (what does a perfect ranker score)?
  * does the result survive a split the design was not tuned on?
  * what exactly goes wrong when it fails?
  * what does the accuracy-cost frontier look like, point by point?
  * does the router survive its request losing its strongest keyword?

Everything is stdlib only. Run:

    python evals/analysis.py [--state-dir DIR] [--bootstrap N]

Writes evals/analysis.json and evals/analysis.md.
"""

import argparse
import json
import math
import random
import sys
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import run_eval  # noqa: E402

BT = chr(96)


# ---------------------------------------------------------------- statistics

def wilson(successes, n, z=1.959963985):
    """Wilson score interval for a proportion. Behaves at 0 and 1."""
    if n == 0:
        return (0.0, 0.0, 0.0)
    p = successes / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = (z / d) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (p, max(0.0, centre - half), min(1.0, centre + half))


def mcnemar_exact(b, c):
    """Two-sided exact McNemar test. b and c are the discordant counts."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(0, k + 1)) / (2.0 ** n)
    return min(1.0, 2.0 * tail)


def paired_bootstrap(rows_a, rows_b, field, n_boot=10000, seed=20261110):
    """Paired bootstrap over cases for the mean difference a - b."""
    pairs = [(a[field], b[field]) for a, b in zip(rows_a, rows_b)
             if field in a and field in b]
    if not pairs:
        return {"n": 0, "mean_diff": 0.0, "ci_low": 0.0, "ci_high": 0.0}
    diffs = [a - b for a, b in pairs]
    rng = random.Random(seed)
    n = len(diffs)
    means = []
    for _ in range(n_boot):
        s = 0.0
        for _ in range(n):
            s += diffs[rng.randrange(n)]
        means.append(s / n)
    means.sort()
    lo = means[int(0.025 * (n_boot - 1))]
    hi = means[int(0.975 * (n_boot - 1))]
    return {"n": n, "mean_diff": sum(diffs) / n, "ci_low": lo, "ci_high": hi,
            "boot": n_boot}


def cluster_bootstrap(rows_a, rows_b, field, clusters, n_boot=4000, seed=20261110):
    """Bootstrap that resamples CAPABILITIES, not cases.

    Cases are not independent: several cases share an expected capability, and
    the router's behaviour on a capability's cases is correlated. Resampling
    cases therefore understates the uncertainty. This resamples the clusters
    and takes every case in a sampled cluster with it.
    """
    by_cluster = {}
    for a_row, b_row, c in zip(rows_a, rows_b, clusters):
        if field in a_row and field in b_row:
            by_cluster.setdefault(c, []).append((a_row[field], b_row[field]))
    if not by_cluster:
        return {"n": 0, "mean_diff": 0.0, "ci_low": 0.0, "ci_high": 0.0,
                "clusters": 0}
    keys = list(by_cluster)
    rng = random.Random(seed)
    means = []
    for _ in range(n_boot):
        picked = [by_cluster[keys[rng.randrange(len(keys))]] for _ in keys]
        diffs = [x - y for grp in picked for x, y in grp]
        means.append(sum(diffs) / len(diffs))
    means.sort()
    all_diffs = [x - y for grp in by_cluster.values() for x, y in grp]
    return {
        "n": len(all_diffs),
        "mean_diff": sum(all_diffs) / len(all_diffs),
        "ci_low": means[int(0.025 * (n_boot - 1))],
        "ci_high": means[int(0.975 * (n_boot - 1))],
        "clusters": len(keys),
    }


def holm_bonferroni(pvalues):
    """Holm-Bonferroni adjusted p-values, order preserved."""
    items = sorted(pvalues.items(), key=lambda kv: kv[1])
    m = len(items)
    out = {}
    running = 0.0
    for i, (k, p) in enumerate(items):
        adj = min(1.0, (m - i) * p)
        running = max(running, adj)
        out[k] = running
    return out


# ------------------------------------------------------------- router helpers

def rank_with_budget(inv, reg, cap_map, request, budget):
    """The shipped router with a hard token budget applied after the gate."""
    cands, _ = inv.score_candidates(reg, request, cap_map)
    ranked = inv.cost_gate(cands, 4.0)
    if ranked and budget:
        best = ranked[0].get("_cap_overlap", 0)
        affordable = [c for c in ranked
                      if (c.get("tokens_est") or 0) <= budget
                      and c.get("_cap_overlap", 0) >= best]
        if affordable:
            ranked = affordable
    return ranked


def row_for(ranked, case):
    exp_cap = case.get("cap")
    exp_skill = case.get("skill")
    chosen = ranked[0] if ranked else None
    top3 = ranked[:3]
    rank = 0
    for i, c in enumerate(ranked, 1):
        if exp_cap and exp_cap in (c.get("tags") or []):
            rank = i
            break
    row = {
        "id": case.get("id"),
        "source": case.get("source"),
        "expected_cap": exp_cap,
        "expected_skill": exp_skill,
        "chosen": (chosen or {}).get("name"),
        "chosen_caps": (chosen or {}).get("_caps") or [],
        "chosen_tags": (chosen or {}).get("tags") or [],
        "chosen_tokens": (chosen or {}).get("tokens_est"),
        "cap_rank": rank,
        "cap_top1": bool(exp_cap and exp_cap in ((chosen or {}).get("tags") or [])),
        "cap_top3": bool(exp_cap and any(exp_cap in (c.get("tags") or []) for c in top3)),
        "mrr": (1.0 / rank) if rank else 0.0,
    }
    if exp_skill:
        row["strict_top1"] = (row["chosen"] == exp_skill)
    return row


def skill_names(reg):
    return {s.get("name") for s in (reg.get("local", []) + reg.get("plugin", [])
                                    + reg.get("marketplace", []))}


# ------------------------------------------------------------------- analysis

def analyse(inv, reg, cap_map, cases, n_boot):
    out = {}
    systems = ["full", "keyword_substring", "bm25", "no_ledger", "no_cost_gate",
               "full_budget", "name_only", "random"]
    rows = {s: run_eval.evaluate(s, cases, reg, cap_map, inv) for s in systems}
    allskills = (reg.get("local", []) + reg.get("plugin", [])
                 + reg.get("marketplace", []))
    out["n_cases"] = len(cases)
    out["n_authored"] = sum(1 for c in cases if c.get("source") == "authored")
    out["n_historical"] = sum(1 for c in cases if c.get("source") == "historical")

    full = rows["full"]
    ref = rows["keyword_substring"]
    case_caps = [c.get("cap") or "?" for c in cases]

    # annotate the full router's rows with what the request actually named,
    # so the error analysis can tell an inference miss from a ranking miss
    for r in full:
        w = inv.infer_capabilities(r["request"], cap_map)
        r["inferred_caps"] = sorted(w.keys())
        r["inferred_head"] = None
        r["expected_cap_in_top3"] = False
    for case, r in zip(cases, full):
        ranked = rank_with_budget(inv, reg, cap_map, case["request"], 0)
        exp = case.get("cap")
        r["expected_cap_in_top3"] = bool(
            exp and any(exp in (c.get("tags") or []) for c in ranked[:3]))
        w = inv.infer_capabilities(case["request"], cap_map)
        primary = {c for c, v in w.items() if v[0] >= 2}
        holders = {}
        for sk in allskills:
            for t in sk.get("tags") or []:
                holders[t] = holders.get(t, 0) + 1
        if primary:
            r["inferred_head"] = min(primary,
                                     key=lambda c: (w[c][1], holders.get(c, 0)))

    sig = {}
    pvals = {}
    for s in systems:
        if s == "full":
            continue
        r = rows[s]
        b = sum(1 for a, c in zip(full, r) if a["cap_top1"] and not c["cap_top1"])
        c_ = sum(1 for a, c in zip(full, r) if c["cap_top1"] and not a["cap_top1"])
        p = mcnemar_exact(b, c_)
        pvals[s] = p
        boot = paired_bootstrap(full, r, "mrr", n_boot)
        clus = cluster_bootstrap(full, r, "mrr", case_caps)
        sig[s] = {
            "discordant_full_only": b,
            "discordant_baseline_only": c_,
            "mcnemar_p_raw": p,
            "mrr_diff": boot["mean_diff"],
            "mrr_ci_low": boot["ci_low"],
            "mrr_ci_high": boot["ci_high"],
            "cluster_ci_low": clus["ci_low"],
            "cluster_ci_high": clus["ci_high"],
            "clusters": clus["clusters"],
        }
    adj = holm_bonferroni(pvals)
    for s, p in adj.items():
        sig[s]["mcnemar_p_holm"] = p
    out["significance"] = sig

    def prop(rows_, field):
        vals = [r[field] for r in rows_ if field in r]
        if not vals:
            return None
        hits = sum(1 for v in vals if v)
        p, lo, hi = wilson(hits, len(vals))
        return {"n": len(vals), "hits": hits, "p": p, "ci_low": lo, "ci_high": hi}

    out["intervals"] = {
        "full_cap_top1": prop(full, "cap_top1"),
        "baseline_cap_top1": prop(ref, "cap_top1"),
        "full_on_topic": prop(full, "on_topic"),
        "baseline_on_topic": prop(ref, "on_topic"),
    }
    out["intervals"]["full_strict_top1"] = prop(
        [r for r in full if "strict_top1" in r], "strict_top1")
    out["intervals"]["baseline_strict_top1"] = prop(
        [r for r in ref if "strict_top1" in r], "strict_top1")

    names = {s.get("name") for s in allskills}
    covered = 0
    providers = {}
    for c in cases:
        exp = c.get("cap")
        if not exp:
            continue
        hits = [s for s in allskills if exp in (s.get("tags") or [])]
        if hits:
            covered += 1
            providers[exp] = len(hits)
    absent = sum(1 for c in cases if c.get("skill") and c["skill"] not in names)
    out["oracle"] = {
        "cases_with_a_provider": covered,
        "cases_total": len(cases),
        "coverage": covered / len(cases) if cases else 0.0,
        "expected_skill_absent_from_registry": absent,
        "mean_providers_per_capability": (sum(providers.values()) / len(providers)
                                          if providers else 0.0),
        "max_providers_for_a_capability": max(providers.values()) if providers else 0,
    }
    out["headroom"] = {
        "oracle_cap_top1": 1.0,
        "full_cap_top1": sum(1 for r in full if r["cap_top1"]) / len(full),
        "baseline_cap_top1": sum(1 for r in ref if r["cap_top1"]) / len(ref),
    }

    def split_of(cid):
        return "test" if (zlib.crc32((cid or "").encode()) % 2) == 0 else "dev"

    halves = {}
    for label in ("dev", "test"):
        f = [r for r in full if split_of(r["id"]) == label]
        b = [r for r in ref if split_of(r["id"]) == label]
        fs = [r for r in f if "strict_top1" in r]
        bs = [r for r in b if "strict_top1" in r]
        halves[label] = {
            "n": len(f),
            "full_cap_top1": sum(1 for r in f if r["cap_top1"]) / len(f) if f else 0.0,
            "baseline_cap_top1": sum(1 for r in b if r["cap_top1"]) / len(b) if b else 0.0,
            "full_strict_top1": (sum(1 for r in fs if r["strict_top1"]) / len(fs)
                                 if fs else 0.0),
            "baseline_strict_top1": (sum(1 for r in bs if r["strict_top1"]) / len(bs)
                                     if bs else 0.0),
        }
    # significance inside each half: the test half is the honest number,
    # because the taxonomy repair was driven by the dev half alone.
    half_sig = {}
    for label in ("dev", "test"):
        f = [r for r in full if split_of(r["id"]) == label]
        b = [r for r in ref if split_of(r["id"]) == label]
        if not f:
            continue
        bb = sum(1 for a, c in zip(f, b) if a["cap_top1"] and not c["cap_top1"])
        cc = sum(1 for a, c in zip(f, b) if c["cap_top1"] and not a["cap_top1"])
        boot = paired_bootstrap(f, b, "mrr", n_boot)
        fs = [r for r in f if "strict_top1" in r]
        bs = [r for r in b if "strict_top1" in r]
        half_sig[label] = {
            "n": len(f),
            "discordant_full_only": bb,
            "discordant_baseline_only": cc,
            "mcnemar_p": mcnemar_exact(bb, cc),
            "mrr_diff": boot["mean_diff"],
            "mrr_ci_low": boot["ci_low"],
            "mrr_ci_high": boot["ci_high"],
            "full_cap_top1": sum(1 for r in f if r["cap_top1"]) / len(f),
            "baseline_cap_top1": sum(1 for r in b if r["cap_top1"]) / len(b),
            "full_strict_top1": (sum(1 for r in fs if r["strict_top1"]) / len(fs)
                                 if fs else 0.0),
            "baseline_strict_top1": (sum(1 for r in bs if r["strict_top1"]) / len(bs)
                                     if bs else 0.0),
        }
    out["half_significance"] = half_sig
    out["halves"] = halves

    frontier = []
    # Rank once per case, then apply each budget to the same ranked list.
    # Equivalent to re-ranking per budget, and six times cheaper.
    ranked_all = [rank_with_budget(inv, reg, cap_map, c["request"], 0)
                  for c in cases]
    for budget in (500, 1000, 2000, 4000, 8000, 0):
        frows = []
        for c, ranked in zip(cases, ranked_all):
            if budget and ranked:
                best = ranked[0].get("_cap_overlap", 0)
                affordable = [x for x in ranked
                              if (x.get("tokens_est") or 0) <= budget
                              and x.get("_cap_overlap", 0) >= best]
                if affordable:
                    ranked = affordable
            frows.append(row_for(ranked, c))
        costs = [r["chosen_tokens"] or 0 for r in frows]
        strict = [r for r in frows if "strict_top1" in r]
        frontier.append({
            "budget": budget or "none",
            "cap_top1": sum(1 for r in frows if r["cap_top1"]) / len(frows),
            "strict_top1": (sum(1 for r in strict if r["strict_top1"]) / len(strict)
                            if strict else 0.0),
            "mean_cost": sum(costs) / len(costs),
            "median_cost": sorted(costs)[len(costs) // 2],
        })
    out["frontier"] = frontier

    # Capability-level failures, split by WHERE the routing went wrong:
    # the request never named the expected capability, or it did and the
    # ranking still missed it. This is the distinction that decides whether
    # the fix belongs in the taxonomy or in the ranker.
    cats = {}
    examples = {}
    for r in full:
        if r["cap_top1"]:
            continue
        exp = r["expected_cap"]
        inferred = exp in (r.get("inferred_caps") or [])
        if not r["chosen"]:
            key = "no skill chosen"
        elif not inferred:
            key = "inference error: the request never named the capability"
        elif r.get("expected_cap_in_top3"):
            key = "ranking error: right capability was in the top three"
        else:
            key = "ranking error: right capability was inferred but not ranked"
        cats[key] = cats.get(key, 0) + 1
        examples.setdefault(key, []).append({
            "id": r["id"], "request": r["request"], "chosen": r["chosen"],
            "expected_cap": exp,
        })
    # which capabilities account for the failures, and is the failure an
    # inference miss or a ranking miss
    by_cap = {}
    for r in full:
        if r["cap_top1"]:
            continue
        exp = r["expected_cap"] or "?"
        d = by_cap.setdefault(exp, {"n": 0, "inference": 0, "ranking": 0,
                                    "cases": 0, "hits": 0})
        d["n"] += 1
        if exp not in (r.get("inferred_caps") or []):
            d["inference"] += 1
        else:
            d["ranking"] += 1
    for c in cases:
        exp = c.get("cap")
        if exp in by_cap:
            by_cap[exp]["cases"] += 1
    out["errors"] = {
        "by_category": dict(sorted(cats.items(), key=lambda kv: -kv[1])),
        "examples": {k: v[:3] for k, v in examples.items()},
        "total_failures": sum(cats.values()),
        "by_capability": dict(sorted(by_cap.items(),
                                     key=lambda kv: -kv[1]["n"])),
    }

    scats = {}
    for r in full:
        if "strict_top1" not in r or r["strict_top1"]:
            continue
        if r["chosen"] is None:
            key = "no skill chosen"
        elif r["expected_cap"] and r["expected_cap"] in r["chosen_tags"]:
            key = "right capability, sibling skill chosen"
        elif r["chosen_tags"]:
            key = "wrong capability"
        else:
            key = "untagged skill chosen"
        scats[key] = scats.get(key, 0) + 1
    out["errors"]["strict_by_category"] = dict(sorted(scats.items(),
                                                      key=lambda kv: -kv[1]))

    dropped = survived = still_cap = 0
    for c in cases:
        exp = c.get("cap")
        spec = cap_map.get(exp) or {}
        low = c["request"].lower()
        kws = [k for k in (spec.get("strong") or []) if k.lower() in low]
        kws += [k for k in (spec.get("weak") or []) if k.lower() in low]
        if not kws:
            continue
        victim = max(kws, key=len)
        stripped = low.replace(victim.lower(), " ", 1)
        dropped += 1
        weights = inv.infer_capabilities(stripped, cap_map)
        if exp in weights:
            still_cap += 1
        ranked = inv.score_candidates(reg, stripped, cap_map)[0]
        if ranked and exp in (ranked[0].get("tags") or []):
            survived += 1
    out["robustness"] = {
        "cases_with_a_matched_keyword": dropped,
        "capability_still_inferred": still_cap,
        "capability_recall_after_drop": (still_cap / dropped) if dropped else 0.0,
        "same_skill_still_chosen": survived,
        "skill_survival_after_drop": (survived / dropped) if dropped else 0.0,
    }
    return out


def to_markdown(a):
    L = ["# Statistical analysis", ""]
    L.append("Cases: %d (%d authored, %d historical)."
             % (a["n_cases"], a["n_authored"], a["n_historical"]))
    L.append("")

    L += ["## 1. Is the improvement distinguishable from zero?", "",
          "McNemar exact test on capability top-1 (discordant pairs only), "
          "plus a paired bootstrap over MRR. p-values are Holm-corrected "
          "across the six baselines.", "",
          "The first interval resamples cases; the second resamples "
          "capabilities, which is the honest unit because cases are "
          "clustered by the capability they expect.", "",
          "| baseline | full only right | baseline only right | MRR diff | "
          "95% CI (cases) | 95% CI (clusters) | McNemar p (raw) | p (Holm) |",
          "|---|---|---|---|---|---|---|---|"]
    for s, v in sorted(a["significance"].items(),
                       key=lambda kv: kv[1]["mcnemar_p_holm"]):
        L.append("| %s | %d | %d | %+.3f | [%.3f, %.3f] | [%.3f, %.3f] | "
                 "%.2g | %.2g |" % (
                     s, v["discordant_full_only"], v["discordant_baseline_only"],
                     v["mrr_diff"], v["mrr_ci_low"], v["mrr_ci_high"],
                     v.get("cluster_ci_low", 0.0), v.get("cluster_ci_high", 0.0),
                     v["mcnemar_p_raw"], v["mcnemar_p_holm"]))
    L.append("")

    L += ["## 2. Intervals on the headline numbers", "",
          "| quantity | n | point | 95% CI (Wilson) |", "|---|---|---|---|"]
    for k, v in a["intervals"].items():
        if not v:
            continue
        L.append("| %s | %d | %.3f | [%.3f, %.3f] |"
                 % (k, v["n"], v["p"], v["ci_low"], v["ci_high"]))
    L.append("")

    o = a["oracle"]
    h = a["headroom"]
    L += ["## 3. Oracle ceiling and headroom", "",
          "- Cases with at least one skill carrying the expected capability: "
          "**%d / %d** (%.3f)." % (o["cases_with_a_provider"], o["cases_total"],
                                   o["coverage"]),
          "- Expected skill present in the registry: %d cases absent."
          % o["expected_skill_absent_from_registry"],
          "- Mean providers per capability: %.1f, worst case %d skills."
          % (o["mean_providers_per_capability"], o["max_providers_for_a_capability"]),
          "- Ranking headroom: shipped router %.3f, pre-fix matcher %.3f, "
          "perfect ranker 1.000." % (h["full_cap_top1"], h["baseline_cap_top1"]),
          ""]

    L += ["## 4. A split the design was not tuned on", "",
          "Cases are split by a stable hash of the case id. The taxonomy and "
          "the router rules were designed while every case was visible, so "
          "this is a leakage-aware check, not a clean held-out evaluation.", "",
          "| split | n | full top-1 | baseline top-1 | full strict | "
          "baseline strict |", "|---|---|---|---|---|---|"]
    for label in ("dev", "test"):
        v = a["halves"][label]
        L.append("| %s | %d | %.3f | %.3f | %.3f | %.3f |" % (
            label, v["n"], v["full_cap_top1"], v["baseline_cap_top1"],
            v["full_strict_top1"], v["baseline_strict_top1"]))
    L.append("")

    hs = a.get("half_significance", {})
    if hs:
        L += ["Significance inside each half. The taxonomy repair was driven "
              "by the dev half alone, so the test half is the honest "
              "number.", "",
              "| split | n | full top-1 | baseline top-1 | full only right | "
              "baseline only right | MRR diff | 95% CI | McNemar p |",
              "|---|---|---|---|---|---|---|---|---|"]
        for label in ("dev", "test"):
            v = hs[label]
            L.append("| %s | %d | %.3f | %.3f | %d | %d | %+.3f | "
                     "[%.3f, %.3f] | %.2g |" % (
                         label, v["n"], v["full_cap_top1"],
                         v["baseline_cap_top1"], v["discordant_full_only"],
                         v["discordant_baseline_only"], v["mrr_diff"],
                         v["mrr_ci_low"], v["mrr_ci_high"], v["mcnemar_p"]))
        L.append("")

    L += ["## 5. The accuracy-cost frontier", "",
          "| token budget | cap top-1 | strict top-1 | mean cost | "
          "median cost |", "|---|---|---|---|---|"]
    for f in a["frontier"]:
        L.append("| %s | %.3f | %.3f | %s | %s |" % (
            f["budget"], f["cap_top1"], f["strict_top1"],
            "{:,}".format(int(round(f["mean_cost"]))),
            "{:,}".format(int(round(f["median_cost"])))))
    L.append("")

    e = a["errors"]
    L += ["## 6. Error analysis", "",
          "Every capability-level failure of the shipped router, categorised.", "",
          "| category | count |", "|---|---|"]
    for k, v in e["by_category"].items():
        L.append("| %s | %d |" % (k, v))
    L.append("| **total failures** | **%d** |" % e["total_failures"])
    L.append("")
    L += ["Which capabilities account for the failures, and is the failure an "
          "inference miss (the request never named the capability) or a "
          "ranking miss (it did, and the ranker still missed it)?", "",
          "| capability | cases | failures | inference misses | ranking misses |",
          "|---|---|---|---|---|"]
    for cap, v in list(e.get("by_capability", {}).items())[:20]:
        L.append("| %s | %d | %d | %d | %d |" % (
            cap, v["cases"], v["n"], v["inference"], v["ranking"]))
    L.append("")
    L += ["Strict-subset failures:", "",
          "| category | count |", "|---|---|"]
    for k, v in e["strict_by_category"].items():
        L.append("| %s | %d |" % (k, v))
    L.append("")
    for k, exs in e["examples"].items():
        L.append("**%s**" % k)
        L.append("")
        for ex in exs:
            L.append("- " + BT + ex["request"][:70] + BT + " -> chose " + BT
                     + str(ex["chosen"]) + BT + " (expected capability " + BT
                     + str(ex["expected_cap"]) + BT + ")")
        L.append("")

    rb = a["robustness"]
    L += ["## 7. Robustness to a missing keyword", "",
          "The strongest matching keyword is deleted from the request and the "
          "request is routed again.", "",
          "- Cases with a matched keyword: %d" % rb["cases_with_a_matched_keyword"],
          "- Expected capability still inferred: %d (%.3f)"
          % (rb["capability_still_inferred"], rb["capability_recall_after_drop"]),
          "- Same skill still chosen: %d (%.3f)"
          % (rb["same_skill_still_chosen"], rb["skill_survival_after_drop"]),
          ""]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-dir", default=None)
    ap.add_argument("--bootstrap", type=int, default=10000)
    ap.add_argument("--out", default=str(HERE / "analysis.json"))
    args = ap.parse_args()

    inv = run_eval.load_router(args.state_dir)
    root = inv.skill_root()
    reg = inv.load_registry(root)
    cap_map = inv.load_capabilities(root)
    cases = run_eval.read_cases([
        str(HERE / "benchmark-a.jsonl"),
        str(HERE / "benchmark-b.jsonl"),
        str(HERE / "benchmark-c.jsonl"),
        str(HERE / "historical.jsonl"),
    ])
    print("cases: %d, capabilities: %d, registry: %d" % (
        len(cases), len(cap_map),
        len(reg.get("local", [])) + len(reg.get("plugin", [])
                                       + reg.get("marketplace", []))))

    a = analyse(inv, reg, cap_map, cases, args.bootstrap)
    Path(args.out).write_text(json.dumps(a, indent=2, ensure_ascii=False) + "\n",
                               encoding="utf-8")
    print("wrote", args.out)
    (HERE / "analysis.md").write_text(to_markdown(a), encoding="utf-8")
    print("wrote", HERE / "analysis.md")
    for s, v in sorted(a["significance"].items(),
                       key=lambda kv: kv[1]["mcnemar_p_holm"]):
        print("  vs %-18s delta_mrr=%+.3f CI[%.3f,%.3f] p_holm=%.3g"
              % (s, v["mrr_diff"], v["mrr_ci_low"], v["mrr_ci_high"],
                 v["mcnemar_p_holm"]))


if __name__ == "__main__":
    main()
