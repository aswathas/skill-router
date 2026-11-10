#!/usr/bin/env python3
"""Iteration 3: apply an independent agent's taxonomy proposals and measure.

An agent was given the dev-half failure diagnosis and nothing else, and
proposed keyword repairs for four capabilities (evals/agent-repair-proposals.json).
Those proposals were never applied to the shipped taxonomy, because the
evaluation pipeline was frozen once the ablation had been measured.

This script applies them in a throwaway state directory, rebuilds the registry
with the proposed taxonomy, and re-runs the shipped router on the whole
benchmark. Nothing here touches the shipped system or the committed results:
the point is to measure the next iteration, not to adopt it.

Because the proposals came from the dev-half diagnosis alone, the test half
stays a held-out measurement of this candidate. It is a single pre-specified
candidate, not a search over the test set.

Usage:
    python evals/iteration3.py [--out evals/iteration3.json]
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import run_eval  # noqa: E402
import analysis  # noqa: E402

SKILL = ROOT / "skills" / "aswath-capability"
SHIPPED_CAPS = SKILL / "registry" / "capabilities.json"
PROPOSALS = HERE / "agent-repair-proposals.json"


def split_of(cid):
    """The same stable hash the analysis harness uses."""
    return "test" if (zlib.crc32((cid or "").encode()) % 2) == 0 else "dev"


def shipped_state_dir():
    env = os.environ.get("SKILL_ROUTER_ORIGINAL_STATE_DIR")
    if env:
        return Path(env)
    return Path.home() / ".minimax" / "local-runtime" / "skill-learning"


def proposed_taxonomy():
    """The shipped taxonomy with the agent's keyword additions applied."""
    caps = json.loads(SHIPPED_CAPS.read_text(encoding="utf-8"))
    proposals = json.loads(PROPOSALS.read_text(encoding="utf-8"))["proposals"]
    table = caps["capabilities"]
    applied = []
    for p in proposals:
        spec = table.setdefault(p["capability"], {})
        spec.setdefault("strong", [])
        spec.setdefault("weak", [])
        for field, key in (("strong", "add_strong"), ("weak", "add_weak")):
            for kw in p.get(key) or []:
                if kw not in spec[field]:
                    spec[field].append(kw)
        applied.append(p["capability"])
    return caps, sorted(applied)


def build_state(caps, state_dir):
    """A throwaway state dir holding the proposed taxonomy and the ledger."""
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "capabilities.json").write_text(json.dumps(caps, indent=2),
                                                  encoding="utf-8")
    ledger = shipped_state_dir() / "ledger.json"
    if ledger.is_file():
        shutil.copy2(ledger, state_dir / "ledger.json")
    env = dict(os.environ, SKILL_ROUTER_STATE_DIR=str(state_dir))
    proc = subprocess.run([sys.executable, str(SKILL / "scripts" / "build-registry.py"),
                           "--out", str(state_dir / "skills.json")],
                          env=env, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit("registry build failed:\n" + (proc.stderr or "")[-2000:])
    return state_dir


def rows_for(state_dir, cases):
    inv = run_eval.load_router(str(state_dir))
    reg = inv.load_registry(inv.skill_root())
    cap_map = inv.load_capabilities(inv.skill_root())
    return run_eval.evaluate("full", cases, reg, cap_map, inv)


def compare(label, ids, base_rows, new_rows):
    a = [x for x in base_rows if x["id"] in ids]
    c = [x for x in new_rows if x["id"] in ids]
    b = sum(1 for x, y in zip(a, c) if y["cap_top1"] and not x["cap_top1"])
    d = sum(1 for x, y in zip(a, c) if x["cap_top1"] and not y["cap_top1"])
    boot = analysis.paired_bootstrap(c, a, "mrr", 10000)
    return {
        "split": label,
        "n": len(a),
        "shipped_cap_top1": sum(1 for x in a if x["cap_top1"]) / len(a),
        "proposed_cap_top1": sum(1 for x in c if x["cap_top1"]) / len(c),
        "discordant_proposed_only": b,
        "discordant_shipped_only": d,
        "mcnemar_p": analysis.mcnemar_exact(b, d),
        "mrr_diff": boot["mean_diff"],
        "mrr_ci_low": boot["ci_low"],
        "mrr_ci_high": boot["ci_high"],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "iteration3.json"))
    args = ap.parse_args()

    cases = run_eval.read_cases([
        str(HERE / "benchmark-a.jsonl"), str(HERE / "benchmark-b.jsonl"),
        str(HERE / "benchmark-c.jsonl"), str(HERE / "historical.jsonl"),
    ])

    caps, applied = proposed_taxonomy()
    tmp = Path(tempfile.mkdtemp(prefix="iteration3-"))
    try:
        state = build_state(caps, tmp / "state")
        base_rows = rows_for(shipped_state_dir(), cases)
        new_rows = rows_for(state, cases)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    allids = {x["id"] for x in base_rows}
    out = {
        "_comment": ("Iteration 3: the independent agent's dev-half proposals, "
                     "applied to the shipped taxonomy in a throwaway state "
                     "directory and measured against the shipped system. The "
                     "shipped taxonomy is NOT changed by this script."),
        "capabilities_changed": applied,
        "splits": [
            compare("overall", allids, base_rows, new_rows),
            compare("dev", {x["id"] for x in base_rows
                            if split_of(x["id"]) == "dev"}, base_rows, new_rows),
            compare("test", {x["id"] for x in base_rows
                             if split_of(x["id"]) == "test"}, base_rows, new_rows),
        ],
        "flipped_cases": [
            {"id": a["id"], "request": a["request"],
             "shipped_chosen": a["chosen"], "proposed_chosen": c["chosen"],
             "split": split_of(a["id"])}
            for a, c in zip(base_rows, new_rows)
            if a["cap_top1"] != c["cap_top1"]
        ],
    }
    Path(args.out).write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    for s in out["splits"]:
        print("%-8s n=%3d shipped=%.4f proposed=%.4f delta=%+.4f "
              "discordant %d/%d p=%.3g"
              % (s["split"], s["n"], s["shipped_cap_top1"],
                 s["proposed_cap_top1"],
                 s["proposed_cap_top1"] - s["shipped_cap_top1"],
                 s["discordant_proposed_only"], s["discordant_shipped_only"],
                 s["mcnemar_p"]))
    print("wrote", args.out)


if __name__ == "__main__":
    main()
