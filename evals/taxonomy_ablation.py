#!/usr/bin/env python3
"""Taxonomy ablation: the shipped router with the ORIGINAL taxonomy.

The paper claims the taxonomy is the load-bearing part. This measures it
end to end rather than by assertion:

  v1  the taxonomy as it was before the error-analysis repair
      (evals/taxonomy-v1.json)
  v2  the repaired taxonomy (the shipped one)

The v1 registry is built from scratch in a temporary state directory with
v1's keyword lists, so the skills are tagged the way they would have been
tagged before the repair. The same router, the same benchmark, the same
cost gate. The only thing that changes is the taxonomy.

Writes evals/taxonomy-ablation.json and evals/taxonomy-ablation.md.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
INVOKE = ROOT / "skills" / "aswath-capability" / "scripts" / "invoke.py"
BUILD = ROOT / "skills" / "aswath-capability" / "scripts" / "build-registry.py"
sys.path.insert(0, str(HERE))

import run_eval  # noqa: E402


def build_registry_with(caps_path, state_dir):
    """Build a registry using a given taxonomy, in a throwaway state dir."""
    state_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(caps_path, state_dir / "capabilities.json")
    env = dict(os.environ)
    env["SKILL_ROUTER_STATE_DIR"] = str(state_dir)
    proc = subprocess.run([sys.executable, str(BUILD)],
                          env=env, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise SystemExit("registry build failed:\n" + (proc.stderr or "")[-2000:])
    return state_dir


def load_router_for(state_dir):
    os.environ["SKILL_ROUTER_STATE_DIR"] = str(state_dir)
    inv = run_eval.load_router(str(state_dir))
    root = inv.skill_root()
    reg = inv.load_registry(root)
    cap_map = inv.load_capabilities(root)
    return inv, reg, cap_map


def summarise(rows):
    n = len(rows)
    strict = [r for r in rows if "strict_top1" in r]
    return {
        "n": n,
        "cap_top1": sum(1 for r in rows if r["cap_top1"]) / n,
        "cap_top3": sum(1 for r in rows if r["cap_top3"]) / n,
        "mrr": sum(r["mrr"] for r in rows) / n,
        "on_topic": sum(1 for r in rows if r.get("on_topic")) / n,
        "mean_cost": sum((r.get("chosen_tokens") or 0) for r in rows) / n,
        "strict_n": len(strict),
        "strict_top1": (sum(1 for r in strict if r["strict_top1"]) / len(strict)
                        if strict else 0.0),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "taxonomy-ablation.json"))
    args = ap.parse_args()

    cases = run_eval.read_cases([
        str(HERE / "benchmark-a.jsonl"),
        str(HERE / "benchmark-b.jsonl"),
        str(HERE / "benchmark-c.jsonl"),
        str(HERE / "historical.jsonl"),
    ])

    tmp = Path(tempfile.mkdtemp(prefix="taxonomy-v1-"))
    try:
        v1_state = build_registry_with(HERE / "taxonomy-v1.json", tmp / "v1")
        inv1, reg1, cap1 = load_router_for(v1_state)
        rows_v1 = run_eval.evaluate("full", cases, reg1, cap1, inv1)

        # the shipped state directory, explicitly: the v1 run above pointed
        # SKILL_ROUTER_STATE_DIR at the throwaway directory
        shipped_state = Path(os.environ.get("SKILL_ROUTER_ORIGINAL_STATE_DIR")
                             or (Path.home() / ".minimax" / "local-runtime"
                                 / "skill-learning"))
        inv2, reg2, cap2 = load_router_for(shipped_state)
        rows_v2 = run_eval.evaluate("full", cases, reg2, cap2, inv2)

        s1, s2 = summarise(rows_v1), summarise(rows_v2)
        b = sum(1 for x, y in zip(rows_v2, rows_v1)
                if x["cap_top1"] and not y["cap_top1"])
        c = sum(1 for x, y in zip(rows_v2, rows_v1)
                if y["cap_top1"] and not x["cap_top1"])
        p = run_eval.__dict__  # keep linters quiet about unused import
        import analysis
        pval = analysis.mcnemar_exact(b, c)
        boot = analysis.paired_bootstrap(rows_v2, rows_v1, "mrr", 10000)

        out = {
            "v1_original_taxonomy": s1,
            "v2_repaired_taxonomy": s2,
            "paired": {
                "v2_only_right": b,
                "v1_only_right": c,
                "mcnemar_p": pval,
                "mrr_diff": boot["mean_diff"],
                "mrr_ci_low": boot["ci_low"],
                "mrr_ci_high": boot["ci_high"],
            },
            "registry_sizes": {"v1": len(reg1.get("local", []))
                               + len(reg1.get("plugin", []))
                               + len(reg1.get("marketplace", [])),
                               "v2": len(reg2.get("local", []))
                               + len(reg2.get("plugin", []))
                               + len(reg2.get("marketplace", []))},
        }
        Path(args.out).write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
        md = [
            "# Taxonomy ablation", "",
            "The shipped router, the same benchmark, the same cost gate. The "
            "only thing that changes is the taxonomy: v1 is the taxonomy as "
            "it was before the error-analysis repair, v2 is the repaired one.",
            "",
            "| taxonomy | cap top-1 | cap top-3 | MRR | strict top-1 | "
            "on-topic | mean cost |",
            "|---|---|---|---|---|---|---|",
            "| v1 original | %.3f | %.3f | %.3f | %.3f | %.3f | %s |" % (
                s1["cap_top1"], s1["cap_top3"], s1["mrr"], s1["strict_top1"],
                s1["on_topic"], "{:,}".format(int(round(s1["mean_cost"])))),
            "| v2 repaired | %.3f | %.3f | %.3f | %.3f | %.3f | %s |" % (
                s2["cap_top1"], s2["cap_top3"], s2["mrr"], s2["strict_top1"],
                s2["on_topic"], "{:,}".format(int(round(s2["mean_cost"])))),
            "",
            "Paired: the repaired taxonomy is right where the original is "
            "wrong on %d cases, wrong where it is right on %d, McNemar "
            "p = %.2g, MRR difference %+.3f with a 95%% paired bootstrap "
            "interval of [%.3f, %.3f]." % (
                b, c, pval, boot["mean_diff"], boot["ci_low"], boot["ci_high"]),
            "",
        ]
        (HERE / "taxonomy-ablation.md").write_text("\n".join(md), encoding="utf-8")
        print("wrote", args.out)
        print("v1 cap_top1 %.3f -> v2 %.3f (p=%.2g)"
              % (s1["cap_top1"], s2["cap_top1"], pval))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
