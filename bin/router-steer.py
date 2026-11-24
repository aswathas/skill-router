#!/usr/bin/env python3
"""The steering hook: attach the router's answer to every request.

Claude Code injects the whole skill catalogue into the context and picks a
skill by its own judgement. The router knows more than that judgement does:
it has the taxonomy, the outcome ledger, the semantic index and the record of
what was used last time. This hook runs on every prompt and puts the router's
answer where the model will read it.

It prints one or two lines. It never blocks the prompt, never fails the
session, and says nothing when it has nothing useful to say.

The wiring lives in the user's settings:

    "UserPromptSubmit": [
      { "matcher": "*", "hooks": [
        { "type": "command",
          "command": "python \\"C:/Users/ADMIN/Projects/skill-router/bin/router-steer.py\\"",
          "timeout": 10 } ] } ]

`router hook install` writes that block; `router hook uninstall` removes it.
"""

import importlib.util
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SCRIPTS = REPO / "skills" / "aswath-capability" / "scripts"
TIMEOUT_BUDGET = 6.0


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def read_prompt():
    """The request text, from the hook payload on stdin."""
    try:
        raw = sys.stdin.read()
    except Exception:
        return ""
    if not raw:
        return ""
    try:
        data = json.loads(raw)
    except ValueError:
        return ""
    for key in ("prompt", "user_prompt", "userPrompt", "text"):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def main():
    prompt = read_prompt()
    if not prompt or len(prompt) > 4000:
        return 0
    try:
        router = _load(REPO / "bin" / "router.py", "router_cli")
        inv = router.invoke()
        reg = router.load_registry()
        cap_map = router.load_caps(inv)
        cands, info, prec = router.rank_all(reg, cap_map, prompt)
    except Exception:
        return 0
    if not cands:
        return 0

    top = cands[0]
    second = cands[1] if len(cands) > 1 else None
    # Only steer when there is something worth steering towards: a named
    # capability, a precedent, or a clear lead.
    named = bool(top.get("_caps"))
    if not (named or prec.get("skill") or info.get("semantic")):
        return 0
    if not named and not prec.get("skill"):
        return 0

    caps = ",".join(top.get("_caps") or [])[:60]
    line = "Skill router: %s" % top.get("name")
    if caps:
        line += " [%s]" % caps
    if prec.get("skill") == top.get("name"):
        line += " (used for a similar request before)"
    line += "."
    if second and second.get("name") != top.get("name"):
        line += " Next: %s." % second.get("name")
    print(line)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except Exception:
        sys.exit(0)
