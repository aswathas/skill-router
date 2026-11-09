#!/usr/bin/env python3
"""Evaluate the capability router against a labelled benchmark.

Six systems are compared on the same cases:

  full             the router as shipped
  no_ledger        the router with the outcome ledger neutralised
                   (isolates what the learning loop contributes)
  no_cost_gate     the router without the Pareto cost gate
                   (isolates what the cost gate contributes)
  keyword_substring  the pre-fix ranking, faithfully reimplemented
                   (raw substring matching, flat strong/weak inference,
                    cheapest-wins gate)
  bm25              Okapi BM25 over skill name + description: a real
                   retrieval baseline, taxonomy-blind and cost-blind
  name_only        pick by name-word overlap alone
  random           uniform over the catalogue

Metrics
  cap_top1     expected capability present on the chosen skill
  cap_top3     expected capability present within the top three
  mrr          1 / rank of the first skill carrying the expected capability
  strict_top1  chosen skill equals the single expected skill (subset)
  mean_cost    mean tokens the chosen skill costs to invoke
  iso_top1     cap_top1 on the lexically isolated subset, where the request
               shares no exact keyword string with the expected capability

Usage:
    python evals/run_eval.py [--out evals/results.json] [--state-dir DIR]
"""

import argparse
import importlib.util
from collections import Counter
import json
import os
import random
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
INVOKE_PATH = ROOT / "skills" / "aswath-capability" / "scripts" / "invoke.py"


def load_router(state_dir=None):
    spec = importlib.util.spec_from_file_location("router_invoke", INVOKE_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["router_invoke"] = mod
    spec.loader.exec_module(mod)
    if state_dir:
        os.environ["SKILL_ROUTER_STATE_DIR"] = str(state_dir)
    return mod


def read_cases(paths):
    cases = []
    for p in paths:
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    cases.append(json.loads(line))
    return cases


# ------------------------------------------------------------------ baselines

LEGACY_STOP = set("""a an the my our your this that these those i me we it is are was were be been being
to of for on in with and or but if then than so as at by from into about over under need needs
want make build create design page ui work thing stuff help please""".split())


def legacy_rank(reg, cap_map, text, cheap_cap=4.0):
    """The pre-fix ranking, reimplemented.

    Flat strong+weak inference by raw substring, substring name and
    description hits, additive capability overlap, and a cost gate that
    compares against the cheapest full-cover candidate rather than the
    best-matching one.
    """
    low = (text or "").lower()
    caps = set()
    for cap, spec in cap_map.items():
        kws = (list(spec.get("strong") or []) + list(spec.get("weak") or [])) if isinstance(spec, dict) else list(spec or [])
        for kw in kws:
            if kw.lower() in low:
                caps.add(cap)
                break
    words = [w for w in re.findall(r"[a-z0-9\-]+", low) if w not in LEGACY_STOP and len(w) > 2]
    out = []
    for s in reg.get("local", []) + reg.get("plugin", []) + reg.get("marketplace", []):
        stags = set(s.get("tags") or [])
        overlap = len(caps & stags)
        name = ((s.get("name") or "") + " " + (s.get("slug") or "")).lower()
        desc = (s.get("description") or "").lower()
        nh = sum(1 for w in words if w in name)
        dh = sum(1 for w in words if w in desc)
        score = overlap * 10 + nh * 3 + dh
        if score <= 0:
            continue
        if s.get("source") in ("local", "plugin"):
            score += 5
        item = dict(s)
        item["_match"] = score
        item["_caps"] = sorted(caps & stags)
        item["_cap_overlap"] = overlap
        out.append(item)
    out.sort(key=lambda s: (
        -s["_match"],
        -(s.get("quality", {}).get("score", 0) if isinstance(s.get("quality"), dict) else (s.get("quality") or 0)),
        0 if s.get("source") in ("local", "plugin") else 1,
        s.get("tokens_est") or 10 ** 9,
        s.get("name") or "",
    ))
    full = [c for c in out if c["_cap_overlap"] > 0 and (c.get("tokens_est") or 0) > 0]
    if full:
        cheapest = min(c.get("tokens_est") or 0 for c in full)
        allowed = cheapest * cheap_cap
        out = [c for c in out
               if (c.get("tokens_est") or 0) <= allowed
               or c["_cap_overlap"] == 0
               or (c.get("tokens_est") or 0) == 0]
    return out


_BM25_INDEX = {}


def _bm25_tokens(text):
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return [w for w in words if len(w) > 1]


def bm25_index(reg):
    """Okapi BM25 over skill name + description.

    A real retrieval baseline: no taxonomy, no cost gate, no ledger. It sees
    exactly what a bag-of-words retriever would see. The index is cached
    because the corpus is the same for every query.
    """
    key = id(reg)
    if key in _BM25_INDEX:
        return _BM25_INDEX[key]
    import math
    skills = (list(reg.get("local", [])) + list(reg.get("plugin", []))
              + list(reg.get("marketplace", [])))
    docs = []
    for s in skills:
        toks = _bm25_tokens((s.get("name") or "") + " "
                            + (s.get("slug") or "") + " "
                            + (s.get("description") or ""))
        docs.append(Counter(toks))
    n = len(docs)
    avgdl = (sum(sum(d.values()) for d in docs) / n) if n else 0.0
    df = Counter()
    for d in docs:
        for t in d:
            df[t] += 1
    k1, b = 1.5, 0.75
    index = {"skills": skills, "docs": docs, "df": df, "n": n,
             "avgdl": avgdl or 1.0, "k1": k1, "b": b}
    _BM25_INDEX[key] = index
    return index


def bm25_rank(reg, cap_map, text):
    """Rank skills by BM25. Deliberately taxonomy-blind."""
    import math
    ix = bm25_index(reg)
    q = _bm25_tokens(text)
    if not q:
        return []
    qcount = Counter(q)
    k1, b = ix["k1"], ix["b"]
    n, avgdl = ix["n"], ix["avgdl"]
    out = []
    for s, d in zip(ix["skills"], ix["docs"]):
        dl = sum(d.values())
        score = 0.0
        for t in qcount:
            f = d.get(t, 0)
            if not f:
                continue
            idf = math.log(1 + (n - ix["df"].get(t, 0) + 0.5)
                            / (ix["df"].get(t, 0) + 0.5))
            score += idf * (f * (k1 + 1)) / (f + k1 * (1 - b + b * dl / avgdl))
        if score > 0:
            item = dict(s)
            item["_match"] = score
            out.append(item)
    out.sort(key=lambda s: (-s["_match"], s.get("name") or ""))
    return out


def name_only_rank(reg, cap_map, text):
    low = (text or "").lower()
    words = [w for w in re.findall(r"[a-z0-9]+", low) if len(w) > 2]
    out = []
    for s in reg.get("local", []) + reg.get("plugin", []) + reg.get("marketplace", []):
        name = ((s.get("name") or "") + " " + (s.get("slug") or "")).lower()
        hits = sum(1 for w in words if w in name)
        if hits <= 0:
            continue
        item = dict(s)
        item["_match"] = hits
        item["_caps"] = []
        out.append(item)
    out.sort(key=lambda s: (-s["_match"], s.get("tokens_est") or 10 ** 9, s.get("name") or ""))
    return out


def random_rank(reg, cap_map, text, seed=20261109):
    """Uniform over the catalogue.

    The seed is mixed with the request, otherwise every case draws the
    same three skills and the baseline measures one lucky draw rather
    than chance.
    """
    import zlib
    all_ = reg.get("local", []) + reg.get("plugin", []) + reg.get("marketplace", [])
    rnd = random.Random(seed ^ zlib.crc32((text or "").encode("utf-8")))
    picked = [dict(s) for s in rnd.sample(all_, min(3, len(all_)))]
    for item in picked:
        item["_match"] = 0
        item["_caps"] = []
    return picked


# ------------------------------------------------------------------- scoring

TOPIC_STOP = set("""this that with from have been will your about there their when what
which while into only just also very much many some more most other another
make made need needs want thing things stuff here does done going going""".split())


def content_words(text):
    words = re.findall(r"[a-z][a-z0-9\-]{3,}", (text or "").lower())
    return {w for w in words if w not in TOPIC_STOP and len(w) >= 5}


def topic_overlap(request, skill):
    """Share of the request's content words that appear in the chosen skill.

    This measures on-topic-ness without consulting the taxonomy at all,
    so it is comparable across every system, including random.
    """
    rw = content_words(request)
    if not rw:
        return 0.0
    text = (((skill or {}).get("name") or "") + " " +
            ((skill or {}).get("slug") or "") + " " +
            ((skill or {}).get("description") or "")).lower()
    sw = set(re.findall(r"[a-z0-9\-]{4,}", text))
    hit = 0
    for w in rw:
        if any(sw_word.startswith(w[:4]) for sw_word in sw):
            hit += 1
    return hit / len(rw)


def evaluate(system, cases, reg, cap_map, inv, verbose=False):
    rows = []
    for case in cases:
        req = case["request"]
        if system == "full":
            cands, _ = inv.score_candidates(reg, req, cap_map)
            ranked = inv.cost_gate(cands, 4.0)
        elif system == "no_ledger":
            saved = inv.quality_of
            inv.quality_of = lambda s: 0
            try:
                cands, _ = inv.score_candidates(reg, req, cap_map)
                ranked = inv.cost_gate(cands, 4.0)
            finally:
                inv.quality_of = saved
        elif system == "no_cost_gate":
            saved = inv.cost_gate
            inv.cost_gate = lambda c, cap=None: c
            try:
                cands, _ = inv.score_candidates(reg, req, cap_map)
                ranked = inv.cost_gate(cands, 4.0)
            finally:
                inv.cost_gate = saved
        elif system == "full_budget":
            cands, _ = inv.score_candidates(reg, req, cap_map)
            ranked = inv.cost_gate(cands, 4.0)
            if ranked:
                best = ranked[0].get("_cap_overlap", 0)
                affordable = [c for c in ranked
                              if (c.get("tokens_est") or 0) <= 2000
                              and c.get("_cap_overlap", 0) >= best]
                if affordable:
                    ranked = affordable
        elif system == "keyword_substring":
            ranked = legacy_rank(reg, cap_map, req)
        elif system == "bm25":
            ranked = bm25_rank(reg, cap_map, req)
        elif system == "name_only":
            ranked = name_only_rank(reg, cap_map, req)
        elif system == "random":
            ranked = random_rank(reg, cap_map, req)
        else:
            raise ValueError(system)

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
            "request": req,
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
        ov = topic_overlap(req, chosen) if chosen else 0.0
        row["topic_overlap"] = ov
        row["on_topic"] = ov >= 0.2
        if exp_skill:
            row["strict_top1"] = (row["chosen"] == exp_skill)
            row["strict_rank"] = next(
                (i for i, c in enumerate(ranked, 1) if c.get("name") == exp_skill), 0)
        rows.append(row)

    return rows


def score(rows, cases_by_id, cap_map):
    n = len(rows)
    out = {
        "n": n,
        "cap_top1": sum(1 for r in rows if r["cap_top1"]) / n if n else 0,
        "cap_top3": sum(1 for r in rows if r["cap_top3"]) / n if n else 0,
        "mrr": sum(r["mrr"] for r in rows) / n if n else 0,
        "mean_cost": (sum((r["chosen_tokens"] or 0) for r in rows) / n) if n else 0,
        "no_match": sum(1 for r in rows if not r["chosen"]) ,
    }
    out["topic_overlap"] = sum(r.get("topic_overlap", 0.0) for r in rows) / n if n else 0
    out["on_topic"] = sum(1 for r in rows if r.get("on_topic")) / n if n else 0

    costs = sorted((r["chosen_tokens"] or 0) for r in rows)
    if costs:
        out["median_cost"] = costs[len(costs) // 2]
        out["p90_cost"] = costs[min(len(costs) - 1, int(len(costs) * 0.9))]

    strict = [r for r in rows if "strict_top1" in r]
    if strict:
        out["strict_n"] = len(strict)
        out["strict_top1"] = sum(1 for r in strict if r["strict_top1"]) / len(strict)
        out["strict_mrr"] = sum((1.0 / r["strict_rank"]) if r["strict_rank"] else 0.0
                                for r in strict) / len(strict)

    # lexically isolated subset: the request shares no exact keyword
    # string with the expected capability's keyword lists
    iso = []
    for r in rows:
        exp = r["expected_cap"]
        spec = cap_map.get(exp) or {}
        kws = [k.lower() for k in (spec.get("strong") or [])] + [k.lower() for k in (spec.get("weak") or [])]
        low = r["request"].lower()
        if not any(k in low for k in kws):
            iso.append(r)
    if iso:
        out["iso_n"] = len(iso)
        out["iso_top1"] = sum(1 for r in iso if r["cap_top1"]) / len(iso)
        out["iso_top3"] = sum(1 for r in iso if r["cap_top3"]) / len(iso)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-dir", default=None,
                    help="router state directory (default: SKILL_ROUTER_STATE_DIR or ~/.minimax/local-runtime/skill-learning)")
    ap.add_argument("--out", default=str(HERE / "results.json"))
    ap.add_argument("--cases", nargs="*", default=None)
    args = ap.parse_args()

    inv = load_router(args.state_dir)
    root = inv.skill_root()
    reg = inv.load_registry(root)
    cap_map = inv.load_capabilities(root)
    print("registry: %d local, %d plugin, %d marketplace"
          % (len(reg.get("local", [])), len(reg.get("plugin", [])), len(reg.get("marketplace", []))))
    print("capabilities: %d" % len(cap_map))

    case_files = args.cases or [
        str(HERE / "benchmark-a.jsonl"),
        str(HERE / "benchmark-b.jsonl"),
        str(HERE / "benchmark-c.jsonl"),
        str(HERE / "historical.jsonl"),
    ]
    cases = []
    for cf in case_files:
        p = Path(cf)
        if p.is_file():
            cases += read_cases([p])
        else:
            print("skip missing case file:", p.name)
    authored = [c for c in cases if c.get("source") == "authored"]
    historical = [c for c in cases if c.get("source") == "historical"]
    print("cases: %d authored, %d historical" % (len(authored), len(historical)))

    systems = ["random", "name_only", "bm25", "keyword_substring", "no_ledger",
               "no_cost_gate", "full_budget", "full"]
    results = {"systems": {}, "by_split": {}}
    per_system_rows = {}
    for sysname in systems:
        rows = evaluate(sysname, cases, reg, cap_map, inv)
        per_system_rows[sysname] = rows
        results["systems"][sysname] = score(rows, None, cap_map)
        results["by_split"][sysname] = {
            "authored": score([r for r in rows if r["source"] == "authored"], None, cap_map),
            "historical": score([r for r in rows if r["source"] == "historical"], None, cap_map),
            "authored_strict": score([r for r in rows if r["source"] == "authored"
                                      and "strict_top1" in r], None, cap_map),
        }
        s = results["systems"][sysname]
        print("%-18s top1=%.3f top3=%.3f mrr=%.3f strict=%.3f ontopic=%.3f mean=%.0f median=%.0f"
              % (sysname, s["cap_top1"], s["cap_top3"], s["mrr"],
                 s.get("strict_top1", 0), s.get("on_topic", 0),
                 s["mean_cost"], s.get("median_cost", 0)))

    # per-capability accuracy for the full router
    bycap = {}
    for r in per_system_rows["full"]:
        if r["source"] != "authored":
            continue
        c = r["expected_cap"]
        d = bycap.setdefault(c, {"n": 0, "hit": 0})
        d["n"] += 1
        d["hit"] += 1 if r["cap_top1"] else 0
    results["per_capability"] = {k: {"n": v["n"], "acc": v["hit"] / v["n"]}
                                 for k, v in sorted(bycap.items())}

    # head-to-head: the shipped router against the pre-fix matcher, per case.
    # Reported so the accuracy/cost trade-off in the paper can be audited.
    legacy_rows = {r["id"]: r for r in per_system_rows["keyword_substring"]}
    h2h = {"full_wins": 0, "legacy_wins": 0, "both": 0, "neither": 0}
    win_full_cost, win_legacy_cost = [], []
    for r in per_system_rows["full"]:
        lr = legacy_rows.get(r["id"])
        if lr is None:
            continue
        f_ok, l_ok = bool(r["cap_top1"]), bool(lr["cap_top1"])
        if f_ok and not l_ok:
            h2h["full_wins"] += 1
            win_full_cost.append(r["chosen_tokens"] or 0)
            win_legacy_cost.append(lr["chosen_tokens"] or 0)
        elif l_ok and not f_ok:
            h2h["legacy_wins"] += 1
        elif f_ok and l_ok:
            h2h["both"] += 1
        else:
            h2h["neither"] += 1
    h2h["n"] = h2h["full_wins"] + h2h["legacy_wins"] + h2h["both"] + h2h["neither"]
    h2h["mean_cost_full_on_wins"] = (sum(win_full_cost) / len(win_full_cost)) if win_full_cost else 0
    h2h["mean_cost_legacy_on_wins"] = (sum(win_legacy_cost) / len(win_legacy_cost)) if win_legacy_cost else 0
    results["head_to_head"] = h2h
    print("head-to-head vs pre-fix:", json.dumps(h2h))

    results["cases"] = per_system_rows["full"]
    results["meta"] = {
        "registry_local": len(reg.get("local", [])),
        "registry_plugin": len(reg.get("plugin", [])),
        "registry_marketplace": len(reg.get("marketplace", [])),
        "capabilities": len(cap_map),
        "n_authored": len(authored),
        "n_historical": len(historical),
    }
    Path(args.out).write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("wrote", args.out)

    md = ["# Evaluation results", "",
          "Case counts: %d authored, %d historical. Registry: %d local, %d plugin, %d marketplace. Capabilities: %d."
          % (len(authored), len(historical),
             len(reg.get("local", [])), len(reg.get("plugin", [])), len(reg.get("marketplace", [])),
             len(cap_map)), "",
          "## Headline", "",
          "| system | cap top-1 | cap top-3 | MRR | strict top-1 | on-topic | mean tokens | median tokens |",
          "|---|---|---|---|---|---|---|---|"]
    for name in systems:
        s = results["systems"][name]
        md.append("| %s | %.3f | %.3f | %.3f | %.3f | %.3f | %.0f | %.0f |" % (
            name, s["cap_top1"], s["cap_top3"], s["mrr"], s.get("strict_top1", 0),
            s.get("on_topic", 0), s["mean_cost"], s.get("median_cost", 0)))
    md += ["", "## Lexically isolated subset", "",
           "Cases where the request shares no exact keyword string with the expected capability.",
           "", "| system | n | top-1 | top-3 |", "|---|---|---|---|"]
    for name in systems:
        s = results["systems"][name]
        if "iso_n" in s:
            md.append("| %s | %d | %.3f | %.3f |" % (name, s["iso_n"], s["iso_top1"], s["iso_top3"]))
    md += ["", "## Strict subset (one unambiguous skill per case)", "",
           "| system | n | strict top-1 | strict MRR |", "|---|---|---|---|"]
    for name in systems:
        s = results["systems"][name]
        if "strict_n" in s:
            md.append("| %s | %d | %.3f | %.3f |" % (name, s["strict_n"], s["strict_top1"], s["strict_mrr"]))
    md += ["", "## Head-to-head against the pre-fix matcher", "",
           "| outcome | cases |", "|---|---|",
           "| shipped router right, pre-fix wrong | %d |" % h2h["full_wins"],
           "| pre-fix right, shipped router wrong | %d |" % h2h["legacy_wins"],
           "| both right | %d |" % h2h["both"],
           "| both wrong | %d |" % h2h["neither"],
           "",
           "Mean cost of the chosen skill on the cases only the shipped router "
           "gets right: shipped router %d tokens, pre-fix matcher %d tokens."
           % (h2h["mean_cost_full_on_wins"], h2h["mean_cost_legacy_on_wins"]),
           ""]
    md += ["", "## Per-capability top-1 (full router)", "",
           "| capability | n | accuracy |", "|---|---|---|"]
    for cap, d in sorted(results["per_capability"].items(), key=lambda kv: kv[1]["acc"]):
        md.append("| %s | %d | %.3f |" % (cap, d["n"], d["acc"]))
    (HERE / "results.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("wrote", HERE / "results.md")


if __name__ == "__main__":
    main()
