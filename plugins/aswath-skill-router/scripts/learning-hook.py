#!/usr/bin/env python3
"""Live learning hook for the capability router.

Fires on every user prompt and after every tool use. It records what the
session actually did with a skill, so the router can learn which skill a
request really needed instead of guessing from the request text alone.

Evidence rules, deliberately conservative:

  accept   a skill was loaded and the session then edited or wrote files
  reject   a skill was loaded and the session then deleted a file that
           same skill had produced
  nothing  anything else

A delete that does not target a file the skill produced is NOT evidence
against that skill. Neither is a file the skill never touched.

Every path exits 0. A hook that has no opinion must never block the agent.

Usage:
    learning-hook.py --event <UserPromptSubmit|PostToolUse> [--payload-file PATH]
    learning-hook.py --event ... < payload.json
"""

import argparse
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

DELETE_RE = re.compile(r"\b(rm|del|unlink|remove)\b", re.I)
SKILL_ROOT_MARK = "SKILL.md"


def state_dir():
    env = os.environ.get("SKILL_ROUTER_STATE_DIR")
    if env:
        return Path(env)
    return Path.home() / ".minimax" / "local-runtime" / "skill-learning"


def read_payload(path):
    try:
        if path:
            return Path(path).read_text(encoding="utf-8", errors="replace")
        data = sys.stdin.read()
        # PowerShell 5.1 pipes to native processes with a UTF-8 BOM, and
        # sometimes two of them. Strip them or every parse fails.
        return data.lstrip("﻿")
    except Exception:
        return ""


def parse(text):
    if not text.strip():
        return {}
    try:
        return json.loads(text)
    except Exception:
        # some hosts hand over a JSON-lines blob; take the last object
        for line in reversed(text.strip().splitlines()):
            line = line.strip()
            if line.startswith("{"):
                try:
                    return json.loads(line)
                except Exception:
                    continue
    return {}


def atomic_write(path, obj):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        pass


def score_of(rec):
    a = rec.get("accepts", 0)
    r = rec.get("rejects", 0)
    p = rec.get("partials", 0)
    total = a + r + p
    if total == 0:
        return 0
    if p:
        return round((a + 0.5 * p - r) / total * 100)
    return round((a - r) / total * 100)


def ledger_path():
    return state_dir() / "ledger.json"


def load_ledger():
    p = ledger_path()
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"schema": 1, "skills": {}}


def record(skill, outcome, note):
    """Append one outcome to the ledger, atomically."""
    if not skill:
        return
    led = load_ledger()
    skills = led.setdefault("skills", {})
    rec = skills.setdefault(skill, {"accepts": 0, "rejects": 0, "partials": 0, "notes": []})
    if outcome == "accept":
        rec["accepts"] = rec.get("accepts", 0) + 1
    elif outcome == "reject":
        rec["rejects"] = rec.get("rejects", 0) + 1
    else:
        rec["partials"] = rec.get("partials", 0) + 1
    rec["notes"] = (rec.get("notes") or [])[-19:] + [
        {"note": note, "at": time.strftime("%Y-%m-%dT%H:%M:%S")}]
    rec["score"] = score_of(rec)
    rec["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    atomic_write(ledger_path(), led)


def observe(skill, outcome, note, session):
    """Record the outcome and log the raw event."""
    d = state_dir()
    try:
        d.mkdir(parents=True, exist_ok=True)
        with (d / "observations.ndjson").open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "session": session,
                "skill": skill,
                "outcome": outcome,
                "note": note,
            }, ensure_ascii=False) + "\n")
    except Exception:
        pass
    record(skill, outcome, note)


def session_file(session):
    return state_dir() / ("session-%s.json" % (session or "default"))


def load_session(session):
    try:
        return json.loads(session_file(session).read_text(encoding="utf-8"))
    except Exception:
        return {"skill": None, "files": [], "request": ""}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--event", default="")
    ap.add_argument("--payload-file", default=None)
    args, _ = ap.parse_known_args()

    payload = parse(read_payload(args.payload_file))
    session = str(payload.get("session_id") or payload.get("sessionId") or "default")
    st = load_session(session)
    event = args.event or payload.get("hook_event_name") or payload.get("event") or ""

    tool = payload.get("tool_name") or payload.get("toolName") or ""
    tinput = payload.get("tool_input") or payload.get("toolInput") or {}
    if not isinstance(tinput, dict):
        tinput = {}

    try:
        if event == "UserPromptSubmit":
            st["request"] = str(payload.get("prompt") or payload.get("user_prompt") or "")[:400]
            st["skill"] = None
            st["files"] = []
            atomic_write(session_file(session), st)
            return 0

        if event == "PostToolUse":
            if tool == "skill":
                name = tinput.get("name") or tinput.get("skill") or ""
                st["skill"] = name or None
                st["files"] = []
                atomic_write(session_file(session), st)
                return 0

            skill = st.get("skill")
            if not skill:
                return 0

            if tool in ("edit", "write", "notebook_edit"):
                path = tinput.get("file_path") or tinput.get("path") or ""
                if path:
                    files = st.get("files") or []
                    if path not in files:
                        files.append(path)
                        st["files"] = files
                        atomic_write(session_file(session), st)
                    observe(skill, "accept",
                            "live: %s edited %s after loading the skill"
                            % (tool, os.path.basename(str(path))), session)
                return 0

            if tool == "bash":
                cmd = str(tinput.get("command") or "")
                if not DELETE_RE.search(cmd):
                    return 0
                produced = [str(f) for f in (st.get("files") or [])]
                for f in produced:
                    base = os.path.basename(f)
                    if base and base in cmd:
                        observe(skill, "reject",
                                "live: a file this skill produced was deleted", session)
                        st["files"] = [x for x in produced if x != f]
                        atomic_write(session_file(session), st)
                        return 0
                return 0
    except Exception as err:
        # never let a hook failure reach the agent
        if os.environ.get("SKILL_ROUTER_HOOK_DEBUG"):
            sys.stderr.write("learning-hook: %r\n" % (err,))
        return 0
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except Exception as err:
        if os.environ.get("SKILL_ROUTER_HOOK_DEBUG"):
            sys.stderr.write("learning-hook fatal: %r\n" % (err,))
        sys.exit(0)
