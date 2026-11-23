#!/usr/bin/env python3
"""router - one command for the skill router.

    router ask "build me a landing page"     what to use, and why
    router why pdf                           why that skill, in detail
    router list --cap design-direction       the catalogue, filtered
    router learn                             fold the outcome ledger into ranking
    router rebuild                           re-index the installed skills
    router eval                              run the 298-case benchmark
    router fetch "keyword research"          find a skill on the internet
    router forge <dir> --cap X               mint a fetched skill into aswath-skills
    router park [--apply]                    trim the catalogue the agent sees

The router's own ranking lives in skills/aswath-capability/scripts/invoke.py.
This CLI adds the command surface, the live ledger weight and the fetch/forge
loop. It does not reimplement the ranker.
"""

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILL_SCRIPTS = REPO / "skills" / "aswath-capability" / "scripts"


def state_dir():
    env = os.environ.get("SKILL_ROUTER_STATE_DIR")
    return Path(env) if env else Path.home() / ".minimax" / "local-runtime" / "skill-learning"


def state_path(name):
    return state_dir() / name


def load_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def invoke():
    """Import the shipped ranker so this CLI never drifts from it."""
    spec = importlib.util.spec_from_file_location("aswath_invoke", SKILL_SCRIPTS / "invoke.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- the ledger ----------------------------------------------------------
# The shared ledger stores outcomes as counts per skill. build-registry.py
# expected a flat {name: score} map, so the quality it wrote into the
# registry was always empty and the ledger never moved a ranking. The
# weight is applied here, live, at query time: a rejected skill is demoted
# the moment you reject it, without waiting for a registry rebuild.
REJECT_PENALTY = 50
ACCEPT_REWARD = 10
PARTIAL_REWARD = 2


def ledger_quality():
    """{slug: score} from the outcome ledger."""
    led = load_json(state_path("ledger.json"), {}) or {}
    skills = led.get("skills") or {}
    out = {}
    for key, rec in skills.items():
        if not isinstance(rec, dict):
            continue
        score = (rec.get("accepts", 0) * ACCEPT_REWARD
                 - rec.get("rejects", 0) * REJECT_PENALTY
                 + rec.get("partials", 0) * PARTIAL_REWARD)
        if score:
            out[key] = score
    return out


def apply_quality(reg, quality):
    """Stamp the live ledger weight onto the registry entries."""
    for group in ("local", "plugin", "marketplace"):
        for s in reg.get(group) or []:
            name = s.get("name") or ""
            slug = s.get("slug") or ""
            q = quality.get(name) or quality.get(slug)
            if q is not None:
                s["quality"] = q
    return reg


def load_registry(quality=True):
    reg = load_json(state_path("skills.json"))
    if reg is None:
        raise SystemExit("registry not found - run: router rebuild")
    if quality:
        apply_quality(reg, ledger_quality())
    return reg


def load_caps(inv):
    p = state_path("capabilities.json")
    data = load_json(p, {}) or {}
    return data.get("capabilities", {})


# --- commands ------------------------------------------------------------
def cmd_ask(args):
    inv = invoke()
    reg = load_registry()
    cap_map = load_caps(inv)
    semantic = semantic_layer()
    info = {}
    if semantic is not None and semantic.enabled():
        cands, info = semantic.rank(reg, cap_map, args.need)
        if args.cheap_cap:
            cands = inv.cost_gate(cands, args.cheap_cap)
    else:
        cands, caps = inv.score_candidates(reg, args.need, cap_map)
        cands = inv.cost_gate(cands, args.cheap_cap)
    prec = apply_precedent(cands, args.need, reg)
    if not cands:
        print("no skill in the catalogue matches this need.")
        print("try: router fetch \"%s\"" % args.need)
        return 2
    top = cands[: args.top]
    if args.json:
        print(json.dumps({
            "need": args.need,
            "semantic": info,
            "precedent": prec,
            "results": [{
                "name": c.get("name"),
                "slug": c.get("slug"),
                "source": c.get("source"),
                "tokens": inv.tokens_of(c),
                "score": c.get("_match"),
                "capabilities": c.get("_caps"),
                "quality": inv.quality_of(c),
            } for c in top],
        }, indent=2, ensure_ascii=False))
        return 0
    best = top[0]
    print("need    : %s" % args.need)
    print("skill   : %s  (%s, %s tokens)"
          % (best.get("name"), best.get("source"), inv.tokens_of(best)))
    print("why     : capability %s | match %s | ledger %s"
          % (",".join(best.get("_caps") or []) or "-",
             best.get("_match"), inv.quality_of(best)))
    print("path    : %s" % (best.get("path") or "-"))
    if info.get("semantic"):
        print("semantic: on | rescued %s | neighbours %s"
              % (info.get("rescued") or "no", info.get("neighbours")))
    elif info.get("reason"):
        print("semantic: off (%s)" % info["reason"])
    if prec.get("skill"):
        print("precedent: %s (used before, match %.2f)" % (prec["skill"], prec["score"]))
    if len(top) > 1:
        print("others  :")
        for c in top[1:]:
            print("          %-38s %-10s %5s tok  match %s"
                  % (c.get("name"), c.get("source"), inv.tokens_of(c), c.get("_match")))
    return 0


PRECEDENT_BONUS = 8


def apply_precedent(cands, need, reg=None):
    """Let what was used last time break a tie between interchangeable skills.

    Two skills can both answer "generate a changelog" and no matching can
    say which one the user means. The learning hook records the request and
    the skill that was loaded for it, so this is history, not a guess.

    A skill the matcher dropped entirely is put back: the precedent is
    stronger evidence than the matcher's silence.
    """
    path = SKILL_SCRIPTS / "precedent.py"
    if not path.is_file():
        return {}
    spec = importlib.util.spec_from_file_location("aswath_precedent", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    hit = mod.lookup(need)
    if not hit:
        return {}
    skill = hit["skill"]
    for c in cands:
        if c.get("name") == skill:
            c["_match"] = c.get("_match", 0) + PRECEDENT_BONUS
            hit["applied"] = True
            break
    else:
        # The matcher dropped it. If it is installed, the precedent puts it
        # back at the top: history is better evidence than a zero score.
        for group in ("local", "plugin", "marketplace"):
            for s in (reg or {}).get(group) or []:
                if s.get("name") == skill:
                    item = dict(s)
                    item["_match"] = PRECEDENT_BONUS
                    item["_caps"] = []
                    item["_cap_overlap"] = 0
                    cands.insert(0, item)
                    hit["applied"] = True
                    hit["restored"] = True
                    break
            if hit.get("applied"):
                break
        else:
            hit["installed"] = False
    cands.sort(key=lambda c: -c.get("_match", 0))
    return hit


def semantic_layer():
    """The semantic layer, if it is installed. None when it is not."""
    path = SKILL_SCRIPTS / "semantic.py"
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("aswath_semantic", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def cmd_precedent(args):
    """Show the history behind a request: which skill was used last time."""
    path = SKILL_SCRIPTS / "precedent.py"
    if not path.is_file():
        raise SystemExit("precedent store not installed")
    spec = importlib.util.spec_from_file_location("aswath_precedent", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not args.request:
        rows = mod.observations()
        loads = [r for r in rows if r.get("outcome") == "load"]
        pairs = mod.precedents()
        print("observations  : %d" % len(rows))
        print("skill loads   : %d" % len(loads))
        print("distinct asks : %d" % len(pairs))
        for req, skills in list(pairs.items())[:15]:
            print("  %-56s %s" % (req[:56], ", ".join(sorted(skills))))
        return 0
    hit = mod.lookup(args.request, args.threshold)
    if not hit:
        print("no precedent for that request")
        return 1
    print("skill   : %s" % hit["skill"])
    print("match   : %.2f" % hit["score"])
    print("before  : %s" % (hit.get("request") or "")[:140])
    return 0


def cmd_sem(args):
    """Build the embedding index, show its state, or query it."""
    semantic = semantic_layer()
    if semantic is None:
        raise SystemExit("semantic layer not installed")
    if args.action == "status":
        for k, v in semantic.status().items():
            print("%-14s %s" % (k, v))
        return 0
    if args.action == "build":
        embed = semantic.embed
        reg = json.loads(Path(state_dir() / "skills.json").read_text(encoding="utf-8"))
        caps = json.loads(Path(state_dir() / "capabilities.json").read_text(encoding="utf-8"))
        embed.build(reg, caps.get("capabilities", {}))
        return 0
    if args.action == "eval":
        script = REPO / "evals" / "run_semantic_eval.py"
        out = str(REPO / "evals" / "local" / "semantic.json")
        r = subprocess.run([sys.executable, str(script), "--out", out],
                           capture_output=True, text=True)
        sys.stdout.write(r.stdout or "")
        sys.stderr.write(r.stderr or "")
        return r.returncode
    reg = json.loads(Path(state_dir() / "skills.json").read_text(encoding="utf-8"))
    cache = semantic.embed.load_cache()
    for c, name in semantic.embed.query(args.text, reg, cache, top=args.top):
        print("%.4f  %s" % (c, name))
    return 0


def cmd_why(args):
    inv = invoke()
    reg = load_registry()
    cap_map = load_caps(inv)
    cands, _ = inv.score_candidates(reg, args.skill, cap_map)
    hit = None
    for c in cands:
        if (c.get("slug") == args.skill or c.get("name") == args.skill
                or (c.get("name") or "").lower() == args.skill.lower()):
            hit = c
            break
    if hit is None:
        print("skill not in the registry: %s" % args.skill)
        return 2
    led = load_json(state_path("ledger.json"), {}) or {}
    rec = (led.get("skills") or {}).get(hit.get("slug")) or \
          (led.get("skills") or {}).get(hit.get("name")) or {}
    print("name        : %s" % hit.get("name"))
    print("source      : %s" % hit.get("source"))
    print("path        : %s" % (hit.get("path") or "-"))
    print("capabilities: %s" % ", ".join(hit.get("tags") or []) or "-")
    print("tokens      : %s" % inv.tokens_of(hit))
    print("ledger      : accepts %s rejects %s partials %s -> %s"
          % (rec.get("accepts", 0), rec.get("rejects", 0), rec.get("partials", 0),
             inv.quality_of(hit)))
    for n in rec.get("notes") or []:
        print("  - %s (%s)" % (n.get("note"), n.get("at")))
    return 0


def cmd_list(args):
    inv = invoke()
    reg = load_registry()
    cap_map = load_caps(inv)
    rows = []
    for s in inv.all_skills(reg):
        if args.cap and args.cap not in (s.get("tags") or []):
            continue
        rows.append(s)
    rows.sort(key=lambda s: (-inv.quality_of(s), s.get("name") or ""))
    for s in rows[: args.limit]:
        print("%-44s %-10s %6s tok  %s"
              % (s.get("name"), s.get("source"), inv.tokens_of(s),
                 ",".join(s.get("tags") or [])[:40]))
    print("%d skills" % len(rows))
    return 0


def cmd_learn(args):
    """Report the ledger weight the router now applies. Nothing to write."""
    q = ledger_quality()
    obs = 0
    p = state_path("observations.ndjson")
    if p.is_file():
        obs = sum(1 for line in p.read_text(encoding="utf-8").splitlines() if line.strip())
    print("observations : %d" % obs)
    print("scored skills: %d" % len(q))
    for k, v in sorted(q.items(), key=lambda kv: -abs(kv[1])):
        print("  %-40s %+d" % (k, v))
    return 0


def cmd_rebuild(args):
    script = SKILL_SCRIPTS / "build-registry.py"
    cmd = [sys.executable, str(script)]
    if args.home:
        cmd += ["--home", args.home]
    r = subprocess.run(cmd, capture_output=True, text=True)
    sys.stdout.write(r.stdout or "")
    sys.stderr.write(r.stderr or "")
    return r.returncode


def cmd_eval(args):
    """Run the benchmark.

    The committed artefacts in evals/ are the numbers the paper quotes, and
    a test checks that they still agree. A local run therefore writes
    somewhere else, or the paper stops matching its own evidence.
    """
    script = REPO / "evals" / "run_eval.py"
    out = args.out or str(REPO / "evals" / "local" / "results.json")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(script), "--out", out]
    r = subprocess.run(cmd, capture_output=True, text=True)
    sys.stdout.write(r.stdout or "")
    sys.stderr.write(r.stderr or "")
    print("written   : %s" % out)
    print("note      : the committed evals/results.json is the paper's evidence")
    print("            and is left untouched on purpose")
    return r.returncode


def main(argv=None):
    ap = argparse.ArgumentParser(prog="router", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("ask", help="resolve a need to one skill")
    p.add_argument("need")
    p.add_argument("--top", type=int, default=4)
    p.add_argument("--json", action="store_true")
    p.add_argument("--cheap-cap", type=int, default=None)
    p.set_defaults(func=cmd_ask)

    p = sub.add_parser("why", help="explain one skill")
    p.add_argument("skill")
    p.set_defaults(func=cmd_why)

    p = sub.add_parser("list", help="the catalogue")
    p.add_argument("--cap")
    p.add_argument("--limit", type=int, default=40)
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("learn", help="ledger weight applied to routing")
    p.set_defaults(func=cmd_learn)

    p = sub.add_parser("rebuild", help="re-index installed skills")
    p.add_argument("--home")
    p.set_defaults(func=cmd_rebuild)

    p = sub.add_parser("eval", help="run the benchmark")
    p.add_argument("--out")
    p.set_defaults(func=cmd_eval)

    p = sub.add_parser("fetch", help="find a skill on the internet")
    p.add_argument("need")
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--download", action="store_true")
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser("test", help="judge a fetched skill against the benchmark")
    p.add_argument("path")
    p.add_argument("--need", required=True)
    p.add_argument("--allow-steal", type=int, default=0)
    p.set_defaults(func=cmd_test)

    p = sub.add_parser("ensure", help="find or fetch a skill for the need")
    p.add_argument("need")
    p.add_argument("--limit", type=int, default=3)
    p.add_argument("--screen", type=int, default=8)
    p.add_argument("--allow-steal", type=int, default=0)
    p.set_defaults(func=cmd_ensure)

    p = sub.add_parser("forge", help="mint a fetched skill into aswath-skills")
    p.add_argument("path")
    p.add_argument("--slug")
    p.add_argument("--cap")
    p.add_argument("--category")
    p.add_argument("--source")
    p.add_argument("--install", action="store_true")
    p.set_defaults(func=cmd_forge)

    p = sub.add_parser("precedent", help="what the last time used, for this request")
    p.add_argument("request", nargs="?", default="")
    p.add_argument("--threshold", type=float, default=0.6)
    p.set_defaults(func=cmd_precedent)

    p = sub.add_parser("sem", help="the semantic layer")
    p.add_argument("action", nargs="?", default="status",
                   choices=["status", "build", "query", "eval"])
    p.add_argument("text", nargs="?", default="")
    p.add_argument("--top", type=int, default=10)
    p.set_defaults(func=cmd_sem)

    p = sub.add_parser("park", help="trim the catalogue the agent sees")
    p.add_argument("action", nargs="?", default="status",
                   choices=["status", "park", "restore", "restore-all"])
    p.add_argument("--root", default="claude", choices=["claude", "minimax", "agents"])
    p.add_argument("--name", default="")
    p.add_argument("--apply", action="store_true")
    p.set_defaults(func=cmd_park)

    args = ap.parse_args(argv)
    if not hasattr(args, "func"):
        ap.print_help()
        return 2
    return args.func(args)


# --- fetch / forge / park ------------------------------------------------
def _gh(args, check=True):
    r = subprocess.run(["gh"] + args, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise SystemExit("gh failed: %s" % (r.stderr or "").strip()[:400])
    return r


def _frontmatter(text):
    """Parse the YAML frontmatter a SKILL.md must carry."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end < 0:
        return {}, text
    block = text[3:end]
    body = text[end + 4:]
    fm = {}
    key = None
    for line in block.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" in line and not line.startswith(" "):
            key, _, val = line.partition(":")
            key = key.strip()
            fm[key] = val.strip().strip('"').strip("'")
        elif key:
            fm[key] = (fm[key] + " " + line.strip()).strip()
    return fm, body


def cmd_fetch(args):
    """Search GitHub for a skill that covers the need, then score it."""
    inv = invoke()
    cap_map = load_caps(inv)
    terms = " ".join(inv.free_text(args.need)[:8]) or args.need
    out = []
    try:
        r = _gh(["api", "-X", "GET", "search/code",
                 "-f", "q=%s filename:SKILL.md" % terms,
                 "-f", "per_page=%d" % (args.limit * 3)], check=False)
        items = []
        if r.returncode == 0:
            items = (json.loads(r.stdout or "{}").get("items") or [])
        if not items:
            r = _gh(["api", "-X", "GET", "search/repositories",
                     "-f", "q=claude agent skill %s" % terms,
                     "-f", "per_page=%d" % args.limit], check=False)
            if r.returncode == 0:
                items = [(json.loads(r.stdout or "{}").get("items") or [])]
    except Exception as e:  # gh missing
        raise SystemExit("gh not available: %s" % e)

    seen = set()
    for it in items:
        repo = (it.get("repository") or {}).get("full_name") or it.get("full_name")
        path = it.get("path") or ""
        if not repo or repo in seen:
            continue
        seen.add(repo)
        out.append({"repo": repo, "path": path, "url": it.get("html_url")})
        if len(out) >= args.limit:
            break
    if not out:
        print("nothing on GitHub matched: %s" % terms)
        return 1
    fetch_dir = state_dir() / "fetched"
    fetch_dir.mkdir(parents=True, exist_ok=True)
    report = []
    for cand in out:
        cand["candidates"] = []
        raw = _gh(["api", "repos/%s/contents/%s" % (cand["repo"], cand["path"])], check=False)
        if raw.returncode != 0:
            continue
        try:
            blob = json.loads(raw.stdout)
            content = _decode_blob(blob)
        except Exception:
            continue
        fm, body = _frontmatter(content)
        desc = fm.get("description") or ""
        caps = sorted(inv.infer_capabilities("%s %s" % (fm.get("name", ""), desc), cap_map))
        cand["candidates"].append({
            "name": fm.get("name"),
            "description": desc[:200],
            "capabilities": caps,
        })
        report.append(cand)
    dest = fetch_dir / "last-fetch.json"
    dest.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    for c in report:
        for k in c["candidates"]:
            print("%-30s %-28s %s" % (c["repo"], k["name"], ",".join(k["capabilities"])[:50]))
    print("report: %s" % dest)
    if args.download:
        return _download_all(report, fetch_dir)
    return 0


def _download_all(report, fetch_dir):
    """Pull the repos that matched and unpack every SKILL.md inside them."""
    done = 0
    for cand in report:
        repo = cand["repo"]
        dest = fetch_dir / repo.replace("/", "__")
        if dest.exists():
            cand["local_dir"] = str(dest)
            cand.setdefault("skill_dirs", [str(p.parent) for p in dest.rglob("SKILL.md")])
            done += 1
            continue
        dest.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(["gh", "api", "repos/%s/zipball/HEAD" % repo],
                           capture_output=True)
        if r.returncode != 0 or not r.stdout:
            shutil.rmtree(dest, ignore_errors=True)
            continue
        import zipfile
        zpath = dest.with_suffix(".zip")
        zpath.write_bytes(r.stdout)
        with zipfile.ZipFile(zpath) as z:
            z.extractall(dest)
        zpath.unlink(missing_ok=True)
        skills = [p.parent for p in dest.rglob("SKILL.md")]
        cand["local_dir"] = str(dest)
        cand["skill_dirs"] = [str(p) for p in skills]
        done += 1
        print("downloaded %s -> %d SKILL.md" % (repo, len(skills)))
    # The report on disk has to carry the local paths, or the next command
    # has nothing to test.
    dest = fetch_dir / "last-fetch.json"
    dest.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("%d repos fetched into %s" % (done, fetch_dir))
    return 0


def _decode_blob(blob):
    import base64
    if blob.get("encoding") == "base64":
        return base64.b64decode(blob["content"]).decode("utf-8", "ignore")
    return blob.get("content") or ""


def _candidate_entry(path, inv, cap_map):
    """A fetched skill expressed as a registry entry, so the ranker can judge it."""
    skill_md = Path(path)
    if skill_md.is_dir():
        skill_md = skill_md / "SKILL.md"
    text = skill_md.read_text(encoding="utf-8", errors="ignore")
    fm, body = _frontmatter(text)
    name = fm.get("name") or skill_md.parent.name
    desc = fm.get("description") or ""
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", name.lower()).strip("-")
    tags = sorted(inv.infer_capabilities("%s %s" % (name, desc), cap_map))
    return {
        "name": name,
        "slug": slug,
        "description": desc,
        "tags": tags,
        "source": "local",
        "tokens_est": max(1, len(body) // 4),
        "path": str(skill_md.parent),
    }


def cmd_test(args):
    """Judge a fetched skill against the benchmark before it is installed.

    A candidate must win the need it was fetched for, and must not steal
    cases that another skill already handled correctly.
    """
    inv = invoke()
    reg = load_registry()
    cap_map = load_caps(inv)
    entry = _candidate_entry(args.path, inv, cap_map)
    reg2 = json.loads(json.dumps(reg))
    reg2.setdefault("local", []).append(entry)

    target = inv.score_candidates(reg2, args.need, cap_map)[0]
    top = target[0] if target else None
    wins_target = bool(top and top.get("slug") == entry["slug"])

    cases = []
    for name in ("benchmark-a.jsonl", "benchmark-b.jsonl",
                 "benchmark-c.jsonl", "historical.jsonl"):
        p = REPO / "evals" / name
        if p.is_file():
            for line in p.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    cases.append(json.loads(line))

    regressions = []
    steals = 0
    checked = 0
    for c in cases:
        want = c.get("cap") or c.get("skill")
        base = inv.score_candidates(reg, c["request"], cap_map)[0]
        withc = inv.score_candidates(reg2, c["request"], cap_map)[0]
        if not base or not withc:
            continue
        checked += 1
        b, w = base[0], withc[0]
        if w.get("slug") != entry["slug"] or b.get("slug") == entry["slug"]:
            continue
        good = bool(want) and (want in (b.get("tags") or []) or want == b.get("slug"))
        if good:
            steals += 1
            regressions.append(c["id"])
    print("candidate   : %s (%s)" % (entry["name"], entry["slug"]))
    print("capabilities: %s" % ", ".join(entry["tags"]))
    print("tokens      : %s" % entry["tokens_est"])
    print("wins target : %s" % wins_target)
    print("cases       : %d checked, %d stolen from a correct skill" % (checked, steals))
    if regressions:
        print("regressions : %s" % ", ".join(regressions[:20]))
    ok = wins_target and steals <= args.allow_steal
    print("verdict     : %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def cmd_ensure(args):
    """Make sure a skill exists for the need, fetching one if it does not.

    A need that names no capability in full is the case the catalogue
    cannot answer: the router has no keyword to match on. Then the internet
    is searched, the candidates are judged, the winner is minted into
    aswath-skills and installed, and its path is printed so it can be loaded.
    """
    inv = invoke()
    cap_map = load_caps(inv)
    weights = inv.infer_capabilities(args.need, cap_map)
    strong = [c for c, (w, _) in weights.items() if w >= 2]
    reg = load_registry()
    cands = inv.score_candidates(reg, args.need, cap_map)[0]
    best = cands[0] if cands else None
    if strong and best is not None:
        print("skill   : %s" % best.get("name"))
        print("why     : capability %s" % ",".join(best.get("_caps") or []))
        print("path    : %s" % (best.get("path") or "-"))
        return 0
    print("no installed skill names this need.")
    print("capabilities named: %s" % (", ".join(sorted(weights)) or "none"))
    print("searching the internet for a skill that does...")
    fetch_args = argparse.Namespace(need=args.need, limit=args.limit, download=True)
    cmd_fetch(fetch_args)
    report = load_json(state_dir() / "fetched" / "last-fetch.json", []) or []
    want_caps = set(weights)
    want_words = set(inv.free_text(args.need))
    ranked = []
    for cand in report:
        for sdir in cand.get("skill_dirs") or []:
            try:
                entry = _candidate_entry(sdir, inv, cap_map)
            except Exception:
                continue
            desc_words = set(inv.free_text("%s %s" % (entry["name"], entry["description"])))
            rel = (3 * len(set(entry["tags"]) & want_caps)
                   + len(want_words & desc_words))
            ranked.append((rel, sdir, entry, cand.get("repo")))
    ranked.sort(key=lambda t: -t[0])
    screened = 0
    tried = 0
    for rel, sdir, entry, repo in ranked[: args.screen]:
        if rel <= 0:
            continue
        tried += 1
        # Cheap screen first: does the candidate even win the need?
        reg2 = json.loads(json.dumps(reg))
        reg2.setdefault("local", []).append(entry)
        top = inv.score_candidates(reg2, args.need, cap_map)[0]
        if not top or top[0].get("slug") != entry["slug"]:
            continue
        screened += 1
        test_args = argparse.Namespace(path=sdir, need=args.need,
                                       allow_steal=args.allow_steal)
        if cmd_test(test_args) != 0:
            continue
        forge_args = argparse.Namespace(path=sdir, slug=None, cap=None,
                                        category=None, install=True,
                                        source="github.com/%s" % repo if repo else None)
        cmd_forge(forge_args)
        print("installed for this task: %s" % sdir)
        return 0
    print("no candidate passed the gate (%d screened, %d ranked)" % (screened, len(ranked)))
    return 1


# --- forge ---------------------------------------------------------------
CATEGORY_KEYWORDS = {
    "context": ("context", "token", "compact", "memory", "session", "window"),
    "publishing": ("publish", "post", "github", "linkedin", "instagram", "release",
                   "ship", "push", "share"),
    "workflow": ("spec", "plan", "commit", "record", "decide", "brief", "forge",
                 "approve", "checklist", "review"),
    "orchestration": ("orchestrat", "delegat", "agent", "parallel", "task",
                      "pipeline", "capability", "unit"),
    "writing": ("write", "wording", "reply", "resume", "cv", "email", "say",
                "prose", "voice", "talk"),
    "utilities": ("convert", "csv", "json", "form", "schedule", "transform",
                  "fetch", "parse", "extract", "download", "translate"),
}


def _category_for(text, dest_root=None, name=""):
    """Pick the aswath-skills category by the question the skill answers.

    The repo's rule is one line: a skill lives in the folder of the question
    it answers. The questions are fixed, so a keyword map is enough. The
    name counts for more than the description: a skill called rust-security
    that mentions memory once is not a context skill.
    """
    low = (text or "").lower()
    low_name = (name or "").lower()
    best, best_hits = "utilities", 0
    for cat, words in CATEGORY_KEYWORDS.items():
        hits = sum(1 for w in words if w in low)
        hits += 3 * sum(1 for w in words if w in low_name)
        if hits > best_hits:
            best, best_hits = cat, hits
    # One stray word is not a question. Anything weak stays in utilities,
    # which is where a narrow tool belongs.
    if best_hits < 2:
        return "utilities"
    return best


def cmd_forge(args):
    """Mint a third-party skill into our own catalogue under aswath-<slug>."""
    src = Path(args.path)
    skill_md = src / "SKILL.md" if src.is_dir() else src
    if not skill_md.is_file():
        raise SystemExit("no SKILL.md at %s" % skill_md)
    text = skill_md.read_text(encoding="utf-8", errors="ignore")
    fm, body = _frontmatter(text)
    name = fm.get("name") or src.name
    slug = args.slug or name.lower().replace(" ", "-")
    slug = "aswath-" + slug if not slug.startswith("aswath-") else slug
    desc = (fm.get("description") or "").strip()
    if not desc:
        raise SystemExit("candidate has no description - it is a document, not a skill")
    if not desc.lower().startswith("use when"):
        desc = "Use when %s" % (desc[0].lower() + desc[1:])

    dest_root = Path(os.environ.get("ASWATH_SKILLS_REPO",
                                    "~/Projects/aswath-skills-wk")).expanduser()
    category = args.category or _category_for(desc, dest_root, name)
    dest = dest_root / "skills" / category / slug
    dest.mkdir(parents=True, exist_ok=True)
    # The description goes on one line and in quotes. A plain YAML scalar
    # breaks on the first ": " in the text, and a skill whose frontmatter
    # does not parse loads with no description at all.
    desc_line = " ".join(desc.split())
    front = '---\nname: "%s"\ndescription: "%s"\n---\n' % (
        slug, desc_line.replace('"', '\\"'))
    provenance = ""
    if args.source:
        provenance = ("\n> Origin: %s. Fetched and re-published under the aswath\n"
                      "> naming so the catalogue stays ours. Check the upstream\n"
                      "> licence before redistributing.\n" % args.source)
    (dest / "SKILL.md").write_text(front + provenance + body.lstrip(), encoding="utf-8")
    # Carry the resources the candidate needs, but never its git metadata.
    for f in src.iterdir() if src.is_dir() else []:
        if f.name == "SKILL.md" or f.name.startswith("."):
            continue
        target = dest / f.name
        if f.is_dir():
            shutil.copytree(f, target, dirs_exist_ok=True)
        else:
            shutil.copy2(f, target)

    _manifest_row(dest_root, slug, category, desc)
    _readme_row(dest_root, slug, category, desc)
    print("forged : %s" % (dest / "SKILL.md"))
    print("category: %s" % category)
    if args.install:
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                            "-File", str(dest_root / "install.ps1"), "-Target", "all"],
                           capture_output=True, text=True)
        print(r.stdout.strip()[-800:])
        if r.returncode != 0:
            sys.stderr.write(r.stderr)
            return r.returncode
    else:
        print("next   : run install.ps1 to link it into the harnesses")
    return 0


def _manifest_row(dest_root, slug, category, desc):
    path = dest_root / "manifest.json"
    if not path.is_file():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    skills = data.setdefault("skills", [])
    if any(s.get("name") == slug for s in skills):
        return
    skills.append({
        "name": slug,
        "category": category,
        "path": "skills/%s/%s/SKILL.md" % (category, slug),
        "description": desc,
        "resources": [],
    })
    data["updated"] = time.strftime("%Y-%m-%d")
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _readme_row(dest_root, slug, category, desc):
    path = dest_root / "README.md"
    if not path.is_file():
        return
    lines = path.read_text(encoding="utf-8").splitlines()
    row = "| `%s` | %s | `/%s` |" % (slug, desc, slug)
    if any("`%s`" % slug in l for l in lines):
        return
    out, placed = [], False
    in_section = False
    for line in lines:
        if line.startswith("### "):
            in_section = line[4:].split(" ")[0].strip() == category
        if in_section and not placed and line.startswith("|---"):
            out.append(line)
            out.append(row)
            placed = True
            continue
        out.append(line)
    if placed:
        path.write_text("\n".join(out) + "\n", encoding="utf-8")


def cmd_park(args):
    """Show what parking would move, or move it. Nothing is deleted."""
    script = REPO / "bin" / "park-skills.py"
    base = [sys.executable, str(script), "--root", args.root]
    action = args.action
    cmd = list(base)
    if action in ("park", "restore-all") and not args.apply:
        cmd.append("--dry-run")
    cmd.append(action)
    if action == "restore":
        cmd.append(args.name)
    r = subprocess.run(cmd, capture_output=True, text=True)
    sys.stdout.write(r.stdout or "")
    sys.stderr.write(r.stderr or "")
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
