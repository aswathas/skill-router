#!/usr/bin/env python3
"""Precedent: what the user asked for last time, and which skill did it.

The benchmark's error analysis names the last wall: 27 of 38 strict failures
were a sibling skill of the right capability winning. Two skills can both
answer "generate a changelog", and no amount of matching says which one the
user means. Only history does.

The learning hook already sees both halves of that pair - the request text
and the skill that was loaded - and now records them together. This module
reads those records and answers one question: for a request like this one,
which skill did we use before?

    python precedent.py stats
    python precedent.py lookup "generate a changelog from the commits"

Nothing here guesses. If the history does not cover the request, the answer
is empty and the router ranks as usual.
"""

import json
import os
import re
import sys
from pathlib import Path

STATE_ENV = "SKILL_ROUTER_STATE_DIR"
DEFAULT_STATE = Path.home() / ".minimax" / "local-runtime" / "skill-learning"
STOP = set("""this that with from have been will your about there their when what
which while into only just also very much many some more most other another make
made need needs want thing things do does did i am we you me my our can could
should would please help now new use using used get got give let""".split())


def state_dir():
    env = os.environ.get(STATE_ENV)
    return Path(env) if env else DEFAULT_STATE


def _words(text):
    return set(w for w in re.findall(r"[a-z0-9]+", (text or "").lower())
               if w not in STOP and len(w) > 2)


def observations():
    """Every recorded event, newest last."""
    p = state_dir() / "observations.ndjson"
    if not p.is_file():
        return []
    rows = []
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    except OSError:
        return []
    return rows


def precedents():
    """{normalised request: {skill: count}} from the recorded loads."""
    out = {}
    for row in observations():
        if row.get("outcome") != "load":
            continue
        req = row.get("request")
        skill = row.get("skill")
        if not req or not skill:
            continue
        key = _norm(req)
        out.setdefault(key, {})
        out[key][skill] = out[key].get(skill, 0) + 1
    return out


def _norm(text):
    return " ".join(sorted(_words(text)))


def similarity(a_words, b_words):
    if not a_words or not b_words:
        return 0.0
    inter = len(a_words & b_words)
    return inter / float(min(len(a_words), len(b_words)))


def lookup(request, threshold=0.6):
    """The skill used last time for a request like this one.

    Returns {"skill", "score", "request", "count"} or None.
    """
    want = _words(request)
    if not want:
        return None
    best = None
    for row in observations():
        if row.get("outcome") != "load":
            continue
        req = row.get("request")
        skill = row.get("skill")
        if not req or not skill:
            continue
        s = similarity(want, _words(req))
        if s < threshold:
            continue
        if best is None or s > best["score"]:
            best = {"skill": skill, "score": s, "request": req, "count": 1}
    return best


def bonus(request, threshold=0.6):
    """The routing bonus a precedent earns, by skill name."""
    hit = lookup(request, threshold)
    if not hit:
        return {}
    return {hit["skill"]: hit}


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("stats")
    p = sub.add_parser("lookup")
    p.add_argument("request")
    p.add_argument("--threshold", type=float, default=0.6)
    args = ap.parse_args(argv)
    rows = observations()
    if args.cmd == "stats":
        loads = [r for r in rows if r.get("outcome") == "load"]
        pairs = precedents()
        print("observations   : %d" % len(rows))
        print("skill loads    : %d" % len(loads))
        print("distinct asks  : %d" % len(pairs))
        for req, skills in list(pairs.items())[:10]:
            print("  %-58s %s" % (req[:58], ", ".join(sorted(skills))))
        return 0
    hit = lookup(args.request, args.threshold)
    if not hit:
        print("no precedent for that request")
        return 1
    print("skill   : %s" % hit["skill"])
    print("match   : %.2f" % hit["score"])
    print("before  : %s" % (hit["request"] or "")[:120])
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
