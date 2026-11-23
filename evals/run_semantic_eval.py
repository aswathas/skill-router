#!/usr/bin/env python3
"""Measure the semantic layer against the shipped router, on the same cases.

Same 298 labelled cases, same metrics, same cost gate as the shipped
benchmark. The only difference between the two systems is the semantic
layer, so the difference in the numbers is what the layer is worth.

    python evals/run_semantic_eval.py [--out evals/local/semantic.json]

The committed evals/results.json is the paper's evidence and is not
touched. This writes beside it.
"""

import argparse
import importlib.util
import json
import math
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


semantic = _load(SCRIPTS / "semantic.py", "semantic_mod")
invoke = semantic.invoke


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


def score(ranked, case):
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
        "cap_top3": bool(exp_cap and any(exp_cap in (c.get("tags") or [])
                                         for c in ranked[:3])),
        "mrr": (1.0 / rank) if rank else 0.0,
        "cost": (chosen or {}).get("tokens_est") or 0,
        "chosen": (chosen or {}).get("name"),
    }
    if exp_skill:
        row["strict_top1"] = row["chosen"] == exp_skill
        row["strict_rank"] = next(
            (i for i, c in enumerate(ranked, 1) if c.get("name") == exp_skill), 0)
    return row


def summarise(rows):
    n = len(rows)
    out = {
        "n": n,
        "cap_top1": sum(1 for r in rows if r["cap_top1"]) / n,
        "cap_top3": sum(1 for r in rows if r["cap_top3"]) / n,
        "mrr": sum(r["mrr"] for r in rows) / n,
        "mean_cost": sum(r["cost"] for r in rows) / n,
    }
    strict = [r for r in rows if "strict_top1" in r]
    if strict:
        out["strict_n"] = len(strict)
        out["strict_top1"] = sum(1 for r in strict if r["strict_top1"]) / len(strict)
        out["strict_mrr"] = sum((1.0 / r["strict_rank"]) if r["strict_rank"] else 0.0
                                for r in strict) / len(strict)
    return out


def mcnemar(b, c):
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, sum(math.comb(n, i) for i in range(0, k + 1)) / (2 ** n))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "local" / "semantic.json"))
    ap.add_argument("--vote-at", type=float, default=None)
    ap.add_argument("--no-tie", action="store_true")
    ap.add_argument("--rescue-when", choices=["no_strong", "none"], default=None)
    args = ap.parse_args()
    reg = json.loads((semantic.state_dir() / "skills.json").read_text(encoding="utf-8"))
    caps = json.loads((semantic.state_dir() / "capabilities.json").read_text(encoding="utf-8"))
    cap_map = caps.get("capabilities", {})
    cases = load_cases()

    params = dict(semantic.PARAMS)
    if args.vote_at is not None:
        params["vote_at"] = args.vote_at
    if args.no_tie:
        params["tie"] = False
    if args.rescue_when:
        params["rescue_when"] = args.rescue_when
    base_rows = []
    sem_rows = []
    rescues = 0
    t0 = time.time()
    for case in cases:
        req = case["request"]
        cands, _ = invoke.score_candidates(reg, req, cap_map)
        base_rows.append(score(invoke.cost_gate(cands, 4.0), case))
        ranked, info = semantic.rank(reg, cap_map, req, params)
        sem_rows.append(score(ranked, case))
        if info.get("rescued"):
            rescues += 1

    base = summarise(base_rows)
    sem = summarise(sem_rows)
    strict_base = [r.get("strict_top1") for r in base_rows if "strict_top1" in r]
    strict_sem = [r.get("strict_top1") for r in sem_rows if "strict_top1" in r]
    b = sum(1 for x, y in zip(strict_base, strict_sem) if x and not y)
    c = sum(1 for x, y in zip(strict_base, strict_sem) if y and not x)
    p = mcnemar(b, c)

    print("cases %d, rescued %d, %.0fs" % (len(cases), rescues, time.time() - t0))
    for label, s in (("keyword", base), ("semantic", sem)):
        print("%-9s top1=%.3f top3=%.3f mrr=%.3f strict=%.3f cost=%.0f"
              % (label, s["cap_top1"], s["cap_top3"], s["mrr"],
                 s.get("strict_top1", 0), s["mean_cost"]))
    print("strict discordant: keyword-only=%d semantic-only=%d p=%.3f" % (b, c, p))
    out = {"base": base, "semantic": sem, "rescued": rescues,
           "discordant": {"keyword_only": b, "semantic_only": c, "p": p},
           "params": params}
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("written %s" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
