#!/usr/bin/env python3
"""Roast and fix a UI build, delegated to an external agent runtime.

This is the aswath-capability roast loop. It does NOT use the host's native
orchestrator. Every agent role (critic, verifier, fixer) is a delegated call
to a headless agent CLI via scripts/delegate.py - cmdc or agy, configurable in
registry/backends.json.

Pipeline:
  1. Roast   - N critics in parallel, one lens each
  2. Dedupe  - collapse the same defect reported from different angles
  3. Verify  - each finding is judged by independent lenses; majority refutes
  4. Fix     - a single fixer applies only the surviving findings
  5. Guard   - scope check: did the fixer stay inside the findings?
  6. Re-verify - did the fixes land, and did anything break?

Usage:
    python roast-and-fix.py --target ../my-page/index.html --backend cmdc
    python roast-and-fix.py --target ./site --screenshots a.png,b.png --max-rounds 2
    python roast-and-fix.py --target ./site --backend agy --report out.json
"""

import argparse
import concurrent.futures
import shutil
import difflib
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import delegate  # noqa: E402

LENSES = [
    {
        "key": "taste",
        "brief": (
            "You are a design director with a strong, specific point of view. You judge visual taste: "
            "is this layout and visual language the way an award-recognized studio would have done it, "
            "or does it read as templated, generated, or safe? Call out centred-hero-on-a-gradient, "
            "generic sans-serif-at-16px, default blue-grey palette, uniform card grid with no hierarchy, "
            "and copy that could belong to any product."
        ),
    },
    {
        "key": "correctness",
        "brief": (
            "You are an accessibility and correctness reviewer. You check contrast ratios, focus order and "
            "visible focus states, hit-target sizes, semantic HTML, keyboard operability, screen-reader "
            "labels, responsive behaviour at small widths, and whether the layout breaks with long or "
            "missing content. You read the source, not just the picture."
        ),
    },
    {
        "key": "user",
        "brief": (
            "You are the user's advocate. Ask: what does someone come here to DO, can they do it, do they "
            "know what to do next, is anything ambiguous? Also judge hierarchy: is the most important thing "
            "actually the most prominent thing? And judge trust: does it look like a real product or a demo?"
        ),
    },
]

VERIFY_LENSES = [
    "does it actually reproduce in the source",
    "is it a real defect or merely a stylistic preference",
    "would a real user actually notice this",
]

FINDINGS_SCHEMA = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "severity": {"type": "string", "enum": ["critical", "major", "minor", "nit"]},
                    "location": {"type": "string"},
                    "problem": {"type": "string"},
                    "fix": {"type": "string"},
                },
                "required": ["title", "severity", "location", "problem", "fix"],
            },
        }
    },
    "required": ["findings"],
}

VERDICT_SCHEMA = {
    "type": "object",
    "properties": {"real": {"type": "boolean"}, "reason": {"type": "string"}},
    "required": ["real", "reason"],
}

FIX_SCHEMA = {
    "type": "object",
    "properties": {
        "applied": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "status": {"type": "string"},
                    "note": {"type": "string"},
                },
                "required": ["title", "status"],
            },
        },
        "skipped": {"type": "array", "items": {"type": "string"}},
        "summary": {"type": "string"},
    },
    "required": ["applied", "skipped", "summary"],
}

REVERIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "fixed": {"type": "boolean"},
                    "evidence": {"type": "string"},
                },
                "required": ["title", "fixed", "evidence"],
            },
        },
        "unrequestedChanges": {"type": "array", "items": {"type": "string"}},
        "stillBroken": {"type": "array", "items": {"type": "string"}},
        "note": {"type": "string"},
    },
    "required": ["verdicts", "unrequestedChanges", "stillBroken", "note"],
}

SEVERITY_RANK = {"critical": 0, "major": 1, "minor": 2, "nit": 3}


# ---------------------------------------------------------------- snapshots

def snapshot(paths):
    snap = {}
    for p in paths:
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        snap[str(p)] = {
            "text": text,
            "hash": hashlib.sha256(text.encode("utf-8", "replace")).hexdigest(),
            "lines": len(text.splitlines()),
        }
    return snap


def visible_text(markup):
    """The text a user actually sees: scripts, styles, comments and tags removed."""
    t = re.sub(r"<script\b.*?</script>", " ", markup, flags=re.S | re.I)
    t = re.sub(r"<style\b.*?</style>", " ", t, flags=re.S | re.I)
    t = re.sub(r"<!--.*?-->", " ", t, flags=re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    return t


def diff_scope(before, after, allowed_text=""):
    """How much did the fixer change, and did it invent anything?"""
    changed, added, removed = [], 0, 0
    invented = []
    for path, new in after.items():
        old = before.get(path)
        if old is None:
            changed.append(path)
            added += new["lines"]
            continue
        if old["hash"] == new["hash"]:
            continue
        changed.append(path)
        d = list(difflib.unified_diff(
            old["text"].splitlines(), new["text"].splitlines(), lineterm="", n=0
        ))
        for line in d:
            if line.startswith("+") and not line.startswith("+++"):
                added += 1
            elif line.startswith("-") and not line.startswith("---"):
                removed += 1
        # Invented content: a new proper noun in the VISIBLE TEXT. Markup and
        # class names are ignored - renaming a class is not inventing a brand.
        old_words = set(re.findall(r"\b[A-Z][A-Za-z]{2,}\b", visible_text(old["text"])))
        new_words = set(re.findall(r"\b[A-Z][A-Za-z]{2,}\b", visible_text(new["text"])))
        # A term the findings asked for is requested content, not invented.
        allowed = set(re.findall(r"\b[A-Z][A-Za-z]{2,}\b", allowed_text))
        for w in sorted(new_words - old_words - allowed):
            invented.append(f"{w} (in {Path(path).name})")
    return {
        "files_changed": len(changed),
        "changed": changed,
        "lines_added": added,
        "lines_removed": removed,
        "invented_terms": invented,
    }


# ---------------------------------------------------------------- delegates

def call(backend, prompt, schema, cwd, allow_edits, timeout, retries, model=None):
    """Delegate one prompt to the configured backend and return the envelope."""
    cfg_all = delegate.load_backends(Path(__file__).resolve().parent.parent)
    cfg = dict(cfg_all["backends"][backend])
    cfg["_id"] = backend
    if schema and not cfg.get("supports_schema"):
        prompt = prompt + "\n\n" + cfg.get("json_hint", "") + "\n" + json.dumps(schema)
    return delegate.run_once(cfg, prompt, schema, cwd, allow_edits, timeout, model=model)


def resolve_roles(root, args):
    """Pick a backend per role: structured roles need schema enforcement (agy),
    editing roles want an agent with a strong editing toolkit (cmdc)."""
    cfg_all = delegate.load_backends(root)
    roles = cfg_all.get("role_backends", {})
    structured = args.structured_backend or roles.get("structured") or "agy"
    editing = args.editing_backend or roles.get("editing") or "cmdc"
    return structured, editing


def findings_from(res):
    parsed = res.get("parsed") or {}
    f = parsed.get("findings")
    if isinstance(f, list):
        return [x for x in f if isinstance(x, dict) and x.get("title")]
    return []


def verdict_from(res):
    parsed = res.get("parsed") or {}
    if isinstance(parsed.get("real"), bool):
        return parsed
    return None


SCRATCH_DIRS = (".hallmark", ".aswath", ".agyclaude", ".cmdc")


def clean_scratch(root_dir):
    """Delegated agents write scratch dirs into the working directory.
    Remove them so the target is left as it was found (plus the fixes)."""
    removed = []
    for name in SCRATCH_DIRS:
        d = Path(root_dir) / name
        if d.is_dir():
            try:
                shutil.rmtree(d)
                removed.append(name)
            except OSError:
                pass
    return removed


def key_of(f):
    return f"{str(f.get('title','')).lower().strip()}|{str(f.get('location','')).lower().strip()}"


def dedupe(findings):
    seen = {}
    for f in findings:
        k = key_of(f)
        if k not in seen:
            seen[k] = f
    return list(seen.values())


# ---------------------------------------------------------------- main flow

def roast_and_fix(args, root):
    target = Path(args.target).resolve()
    if not target.exists():
        raise SystemExit(f"target not found: {target}")
    structured_backend, editing_backend = resolve_roles(root, args)
    tiers = delegate.load_backends(root).get("model_tiers", {})
    if args.backend:
        structured_backend = editing_backend = args.backend
    cwd = args.cwd or str(target.parent)
    files = [target] if target.is_file() else [
        p for p in sorted(target.rglob("*"))
        if p.is_file() and p.suffix.lower() in (".html", ".css", ".jsx", ".tsx", ".js", ".ts", ".vue", ".svelte")
    ]
    if not files:
        raise SystemExit(f"no source files under {target}")

    shots = [s for s in (args.screenshots or "").split(",") if s.strip()]
    shot_note = (f"Read these screenshots as images: {', '.join(shots)}"
                 if shots else "No screenshots were supplied. Judge from the source and say so.")
    context = args.context or ""

    findings_schema = json.dumps(FINDINGS_SCHEMA)
    all_confirmed = []
    seen_keys = set()
    usage_total = {"input": 0, "output": 0, "cache_read": 0}
    rounds_run = 0
    scope_reports = []
    reverify_reports = []

    for round_no in range(1, args.max_rounds + 1):
        rounds_run = round_no
        print(f"[round {round_no}] roasting with {len(LENSES)} critics on {structured_backend}", flush=True)

        critic_prompts = [
            f"{lens['brief']}\n\n"
            f"TARGET: {target}\n{shot_note}\n\n"
            f"CONTEXT:\n{context}\n\n"
            "Rules:\n"
            "- Every finding must be ACTIONABLE and SPECIFIC. 'Looks generic' is not a finding.\n"
            "- The fix field must describe the concrete change, not a principle.\n"
            "- location must point at something real: file:line, component name, or a screenshot region.\n"
            "- Do not report the same problem twice.\n"
            "- At most 8 findings, most severe first. An empty list is a valid answer.\n"
            f"{delegate.load_backends(root)['backends'][structured_backend].get('json_hint','')}\n"
            f"Schema:\n{findings_schema}"
            for lens in LENSES
        ]

        with concurrent.futures.ThreadPoolExecutor(max_workers=len(critic_prompts)) as ex:
            critic_results = list(ex.map(
                lambda p: call(structured_backend, p, FINDINGS_SCHEMA, cwd, False, args.timeout, args.retries, model=tiers.get("strong")),
                critic_prompts,
            ))
        for r in critic_results:
            u = r.get("usage") or {}
            for k in usage_total:
                usage_total[k] += u.get(k, 0) or 0

        raw = [f for r in critic_results for f in findings_from(r)]
        fresh = dedupe([f for f in raw if key_of(f) not in seen_keys])
        print(f"[round {round_no}] {len(raw)} raw findings, {len(fresh)} new", flush=True)
        if not fresh:
            print("[round %d] no new findings - done" % round_no, flush=True)
            break
        for f in fresh:
            seen_keys.add(key_of(f))

        # Cap BEFORE verification, not after. Verification cost scales with the
        # number of findings, so capping afterwards verifies 21 findings and
        # then throws 18 away.
        fresh.sort(key=lambda f: SEVERITY_RANK.get(f.get("severity"), 9))
        if args.max_findings and len(fresh) > args.max_findings:
            print(f"[round {round_no}] capping {len(fresh)} findings to the top "
                  f"{args.max_findings} before verification", flush=True)
            fresh = fresh[:args.max_findings]

        # Verify: every finding judged by independent lenses; majority refutes.
        lenses = VERIFY_LENSES[:args.verify_lenses] if args.verify_lenses else VERIFY_LENSES

        def verify_one(f):
            votes = []
            for lens in lenses:
                p = (f"Try to REFUTE this finding about {target}. Default to real=false if uncertain.\n\n"
                     f"FINDING: {f.get('title')}\nLOCATION: {f.get('location')}\nPROBLEM: {f.get('problem')}\n\n"
                     f"Judge it via this lens: {lens}. Read the actual source at {target} before deciding.\n"
                     f"A defensible stylistic preference is NOT real.\n"
                     f"{delegate.load_backends(root)['backends'][structured_backend].get('json_hint','')}\n"
                     f"Schema:\n{json.dumps(VERDICT_SCHEMA)}")
                votes.append(call(structured_backend, p, VERDICT_SCHEMA, cwd, False, args.timeout, args.retries, model=tiers.get("fast")))
            verdicts = [verdict_from(v) for v in votes]
            verdicts = [v for v in verdicts if v]
            refuted = sum(1 for v in verdicts if not v["real"])
            real = bool(verdicts) and refuted < (len(verdicts) // 2 + 1)
            return f, real, verdicts

        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
            verified = list(ex.map(verify_one, fresh))
        for _, _, votes in verified:
            for v in votes:
                pass

        survivors = [f for f, real, _ in verified if real]
        killed = len(fresh) - len(survivors)
        print(f"[round {round_no}] {len(survivors)} confirmed, {killed} refuted", flush=True)
        if not survivors:
            break

        survivors.sort(key=lambda f: SEVERITY_RANK.get(f.get("severity"), 9))
        before = snapshot(files)

        fix_prompt = (
            f"Apply these confirmed findings to the source at {target}.\n\n"
            + "\n\n".join(
                f"{i+1}. [{f.get('severity')}] {f.get('title')}\n"
                f"   location: {f.get('location')}\n"
                f"   problem: {f.get('problem')}\n"
                f"   fix: {f.get('fix')}"
                for i, f in enumerate(survivors)
            )
            + "\n\nHARD CONSTRAINTS - violating these makes the work worse:\n"
            "- Apply ONLY the fixes listed above. Do not restyle, restructure, rename, or reorganise "
            "anything else.\n"
            "- Do NOT run your own audit, review, or critique. Do NOT apply a fix that is not in "
            "the list above. If you think a different change is needed, record it in 'skipped' "
            "with your reasoning instead of doing it.\n"
            "- Do NOT rewrite the file. Do NOT rewrite whole sections. Make the smallest edit that "
            "fixes each finding.\n"
            "- Do NOT invent a product, brand, company, feature, statistic, or copy. If the finding "
            "does not ask for new text, keep the existing text.\n"
            "- Do NOT change the visual direction, palette, typeface, or layout system.\n"
            "- Keep the existing file structure, class names, and element order unless a finding "
            "explicitly names them.\n"
            "- If a finding genuinely does not apply, skip it and record why.\n"
            "- Never delete existing content that no finding asked you to remove.\n"
            f"\n{delegate.load_backends(root)['backends'][editing_backend].get('json_hint','')}\n"
            f"Schema:\n{json.dumps(FIX_SCHEMA)}"
        )

        fix_res = call(editing_backend, fix_prompt, FIX_SCHEMA, cwd, True, args.timeout, args.retries, model=tiers.get("strong"))
        after = snapshot(files)
        findings_text = " ".join(
            f"{f.get('title','')} {f.get('problem','')} {f.get('fix','')}" for f in survivors
        )
        scope = diff_scope(before, after, findings_text)
        scope_reports.append(scope)
        # The agent's self-report is not evidence - it may claim zero fixes
        # while changing the file, or claim fixes it never made. The diff is
        # the ground truth for whether anything changed.
        reported = (fix_res.get("parsed") or {}).get("applied") or []
        actually_changed = scope["lines_added"] + scope["lines_removed"]
        applied = reported if reported else ([{"title": "(unreported)", "status": "changed"}] if actually_changed else [])
        if not reported and actually_changed:
            print(f"[round {round_no}] NOTE: fixer changed the file but reported no structured "
                  f"result - the diff is being used as the source of truth", flush=True)
        print(f"[round {round_no}] fixer applied {len(applied)} fixes; "
              f"{scope['files_changed']} file(s) changed, +{scope['lines_added']}/-{scope['lines_removed']} lines",
              flush=True)

        # Scope guard: a fix that rewrites the page is not a fix.
        budget = 8 * len(survivors) + 25
        scope_violation = None
        if scope["lines_added"] > budget:
            scope_violation = (
                f"fixer changed {scope['lines_added']} lines for {len(survivors)} findings "
                f"(budget {budget}) - this looks like a rewrite, not a fix"
            )
        if scope["invented_terms"]:
            scope_violation = (scope_violation or "") + \
                f"; invented new content: {', '.join(scope['invented_terms'][:8])}"
        if scope_violation:
            print(f"[round {round_no}] SCOPE WARNING: {scope_violation}", flush=True)

        reverify_prompt = (
            f"Verify EACH confirmed finding below against the current source at {target}.\n\n"
            "CONFIRMED FINDINGS:\n"
            + "\n\n".join(
                f"{i+1}. {f.get('title')}\n   location: {f.get('location')}\n"
                f"   problem: {f.get('problem')}\n   required fix: {f.get('fix')}"
                for i, f in enumerate(survivors)
            )
            + "\n\nFIX REPORT (may be empty or inaccurate - verify against the source):\n"
            + json.dumps(fix_res.get("parsed") or {}, indent=2)
            + "\n\nRules:\n"
            "- For EACH numbered finding, read the source and decide whether it is now fixed. "
            "Do not assume the fixer's report is true - check the code.\n"
            "- 'fixed' is true only if the source actually satisfies the required fix.\n"
            "- evidence must quote the line or value that proves your verdict.\n"
            "- unrequestedChanges: anything the fixer changed that NO finding asked for - a "
            "different fix, a new section, new copy, a new brand name, a restyle. Report it even "
            "if the result looks good, because it means the fixer did not do what it was told.\n"
            "- stillBroken: problems the fixes introduced or left behind.\n"
            "- Be honest. A fix that did not work is worse than no fix, because it hides the problem.\n"
            f"{delegate.load_backends(root)['backends'][structured_backend].get('json_hint','')}\n"
            f"Schema:\n{json.dumps(REVERIFY_SCHEMA)}"
        )
        reverify = call(structured_backend, reverify_prompt, REVERIFY_SCHEMA, cwd, False, args.timeout, args.retries, model=tiers.get("fast"))
        rv = reverify.get("parsed") or {}

        all_confirmed.extend(dict(f, round=round_no) for f in survivors)

        # "Clean" now means something: every confirmed finding was actually
        # addressed. A single unfixed finding is not clean, however good the
        # page looks.
        verdicts = rv.get("verdicts") or []
        unfixed = [v for v in verdicts if not v.get("fixed")]
        unrequested = rv.get("unrequestedChanges") or []
        if unfixed:
            print(f"[round {round_no}] NOT CLEAN: {len(unfixed)}/{len(verdicts)} confirmed findings "
                  f"still unfixed: {[v.get('title') for v in unfixed]}", flush=True)
        else:
            print(f"[round {round_no}] all {len(verdicts)} confirmed findings verified fixed", flush=True)
        if unrequested:
            print(f"[round {round_no}] FIXER DEVIATED - changes not requested by any finding: "
                  f"{unrequested[:5]}", flush=True)
        if scope_violation and not unfixed:
            print(f"[round {round_no}] findings fixed BUT scope was violated: {scope_violation}", flush=True)

        # A finding the fixer did not fix must be retried next round, not
        # silently marked as seen.
        for v in unfixed:
            t = v.get("title")
            if t:
                for f in survivors:
                    if f.get("title") == t:
                        seen_keys.discard(key_of(f))
        reverify_reports.append({
            "round": round_no,
            "verdicts": verdicts,
            "unfixed": [v.get("title") for v in unfixed],
            "unrequested_changes": unrequested,
            "scope_violation": scope_violation,
        })

    by_sev = {}
    for f in all_confirmed:
        by_sev[f.get("severity")] = by_sev.get(f.get("severity"), 0) + 1

    cleaned = clean_scratch(cwd)
    if cleaned:
        print(f"cleaned scratch dirs: {', '.join(cleaned)}", flush=True)

    report = {
        "target": str(target),
        "scratch_cleaned": cleaned,
        "backend": args.backend or structured_backend,
        "structured_backend": structured_backend,
        "editing_backend": editing_backend,
        "rounds": rounds_run,
        "confirmed_count": len(all_confirmed),
        "bySeverity": by_sev,
        "confirmed": all_confirmed,
        "scope": scope_reports,
        "reverify": reverify_reports,
        "verify_lenses": args.verify_lenses or len(VERIFY_LENSES),
        "usage": usage_total,
    }
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"report -> {args.report}")
    print(json.dumps({k: v for k, v in report.items() if k != "confirmed"}, indent=2, ensure_ascii=False))
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", required=True)
    ap.add_argument("--backend", default=None, help="override every role")
    ap.add_argument("--structured-backend", default=None)
    ap.add_argument("--editing-backend", default=None)
    ap.add_argument("--screenshots", default="")
    ap.add_argument("--context", default="")
    ap.add_argument("--cwd", default=None)
    ap.add_argument("--max-rounds", type=int, default=2)
    ap.add_argument("--max-findings", type=int, default=8)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--verify-lenses", type=int, default=3,
                    help="how many independent lenses judge each finding (2 = both must agree)")
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--retries", type=int, default=1)
    ap.add_argument("--report", default=None)
    args = ap.parse_args()

    root = Path(__file__).resolve().parent.parent
    return roast_and_fix(args, root)


if __name__ == "__main__":
    sys.exit(0 if main() else 0)
