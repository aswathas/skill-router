#!/usr/bin/env python3
"""Semantic layer for the router: what the keyword matcher cannot see.

The shipped router ranks on the taxonomy: a request is matched to a
capability by keyword, and a skill carrying that capability wins. The
benchmark's own error analysis says where that breaks: 42 of 45 failures
were requests that never named the capability at all.

This layer adds a local embedding index over the catalogue and uses it in
two places, both measured against the same 298 cases:

  rescue  when the keywords name no capability, the skill nearest to the
          request votes for its capability. Exactly one capability is
          added, because twenty voted capabilities drown the taxonomy -
          that was measured, and it cost 30 points of top-1.
  tie     among the skills with the winning capability, the one nearest to
          the request wins the exact-skill check.

What it is not: a replacement for the taxonomy. The capability layer still
decides what kind of job this is. This only covers the requests that name
nothing, and breaks ties the taxonomy cannot.

The embedding provider is a local LM Studio server with an
OpenAI-compatible endpoint. Nothing leaves the machine. If the server is
down, the router falls back to the keyword path and says so.

    python semantic.py status
    python semantic.py query "wire my calendar to a slack channel"
"""

import importlib.util
import json
import math
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE_ENV = "SKILL_ROUTER_STATE_DIR"
DEFAULT_STATE = Path.home() / ".minimax" / "local-runtime" / "skill-learning"

# Measured on the 298-case benchmark against the shipped router.
#
#   profile        cap top-1   strict top-1   mean cost
#   keyword only     0.805        0.206         2435
#   conservative     0.805        0.222         2096
#   aggressive       0.795        0.254         1947
#
# The conservative profile rescues only when the keywords said nothing at
# all, and never costs a capability case. The aggressive one rescues more
# often: it wins three exact-skill cases and loses three capability ones.
# The default is the conservative one, because a capability miss is worse
# than picking a sibling of the right skill.
PROFILES = {
    "conservative": {"vote_at": 0.65, "tie": True, "shortlist": 400,
                     "rescue_when": "none"},
    "aggressive": {"vote_at": 0.60, "tie": True, "shortlist": 400,
                   "rescue_when": "no_strong"},
}
PARAMS = dict(PROFILES["conservative"])
ENABLE_ENV = "SKILL_ROUTER_SEMANTIC"
PROFILE_ENV = "SKILL_ROUTER_SEMANTIC_PROFILE"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / ("%s.py" % name))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


embed = _load("embed")
invoke = _load("invoke")


def state_dir():
    env = os.environ.get(STATE_ENV)
    return Path(env) if env else DEFAULT_STATE


def enabled():
    """Semantic is on unless it is switched off, and off if the index is gone."""
    env = os.environ.get(ENABLE_ENV, "auto").strip().lower()
    if env in ("0", "off", "false", "no"):
        return False
    if env in ("1", "on", "true", "yes"):
        return True
    return (state_dir() / "embeddings.json").is_file()


def status():
    cache = embed.load_cache()
    return {
        "enabled": enabled(),
        "model": cache.get("model"),
        "dim": cache.get("dim"),
        "skills": len(embed.skill_vectors(cache)),
        "capabilities": len(embed.capability_vectors(cache)),
        "cache": str(embed.cache_path()),
    }


def _words(text):
    return set(w for w in re.findall(r"[a-z0-9]{4,}", (text or "").lower()))


def prefilter(reg, req, cap):
    """Cheap lexical prefilter: the skills that share a word with the request.

    The embedding index holds every skill. Scanning all of them for one
    request costs seconds in pure Python, so the search is narrowed by a
    word overlap first and the vectors are only compared inside that pool.
    """
    want = _words(req)
    if not want:
        return []
    scored = []
    for s in invoke.all_skills(reg):
        text = ("%s %s %s" % (s.get("name") or "", s.get("slug") or "",
                              s.get("description") or "")).lower()
        hits = sum(1 for w in want if w in text)
        if hits:
            scored.append((hits, s))
    scored.sort(key=lambda t: -t[0])
    return [s for _, s in scored[:cap]]


def rank(reg, cap_map, req, params=None):
    """Rank the catalogue for a request, with the semantic layer applied.

    Returns (ranked, info). info carries what the layer did, so the CLI can
    say whether the semantic path was used or the fallback was.
    """
    if params is None:
        profile = os.environ.get(PROFILE_ENV, "conservative").strip().lower()
        params = dict(PROFILES.get(profile, PROFILES["conservative"]))
    params = dict(PARAMS, **params)
    info = {"semantic": False, "rescued": None, "neighbours": 0, "reason": ""}
    cands, _ = invoke.score_candidates(reg, req, cap_map)
    if not enabled() or not params.get("vote_at"):
        info["reason"] = "semantic layer off"
        return invoke.cost_gate(cands, 4.0), info

    cache = embed.load_cache()
    skill_vecs = embed.skill_vectors(cache)
    if not skill_vecs:
        info["reason"] = "no embedding index"
        return invoke.cost_gate(cands, 4.0), info

    pool = prefilter(reg, req, params["shortlist"])
    if not pool:
        info["reason"] = "no lexical pool"
        return invoke.cost_gate(cands, 4.0), info

    try:
        vecs, _ = embed.embed_texts([req])
        qvec = vecs[0]
    except Exception as e:  # the provider is down: fall back, do not fail
        info["reason"] = "provider unavailable: %s" % type(e).__name__
        return invoke.cost_gate(cands, 4.0), info

    sem = []
    for s in pool:
        v = skill_vecs.get(s.get("slug"))
        if v:
            sem.append((embed.cosine(qvec, v), s))
    sem.sort(key=lambda t: -t[0])
    info["semantic"] = True
    info["neighbours"] = len(sem)

    votes = {}
    for sim, s in sem:
        if sim < params["vote_at"]:
            continue
        for cap_name in s.get("tags") or []:
            if sim > votes.get(cap_name, 0):
                votes[cap_name] = sim

    keyword_infer = invoke.infer_capabilities
    rescued = [None]

    def infer(text, cap_map, _v=votes, _orig=keyword_infer):
        got = _orig(text, cap_map)
        if not _v:
            return got
        strong = [c for c, (w, _) in got.items() if w >= 2]
        if strong:
            return got
        # A weak keyword hit is still evidence. The semantic rescue only
        # speaks when the keywords said nothing at all, or it overrules
        # words that were actually written.
        if got and params.get("rescue_when", "no_strong") == "none":
            return got
        best = max(_v.items(), key=lambda kv: kv[1])
        if best[1] < params["vote_at"]:
            return got
        got[best[0]] = (2, 10 ** 5)
        rescued[0] = best[0]
        return got

    invoke.infer_capabilities = infer
    try:
        cands, _ = invoke.score_candidates(reg, req, cap_map)
    finally:
        invoke.infer_capabilities = keyword_infer
    info["rescued"] = rescued[0]

    if params.get("tie") and cands:
        sim_of = {s.get("slug"): sim for sim, s in sem}
        best_overlap = max((c.get("_cap_overlap", 0) for c in cands), default=0)
        group = [c for c in cands
                 if c.get("_cap_overlap", 0) == best_overlap and best_overlap > 0]
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

    return invoke.cost_gate(cands, 4.0), info


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    p = sub.add_parser("query")
    p.add_argument("text")
    p.add_argument("--top", type=int, default=10)
    args = ap.parse_args(argv)
    if args.cmd == "status":
        st = status()
        for k, v in st.items():
            print("%-14s %s" % (k, v))
        return 0
    reg = json.loads((state_dir() / "skills.json").read_text(encoding="utf-8"))
    cache = embed.load_cache()
    for c, name in embed.query(args.text, reg, cache, top=args.top):
        print("%.4f  %s" % (c, name))
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
