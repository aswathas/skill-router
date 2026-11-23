# -*- coding: utf-8 -*-
"""Tests for the learning hook (plugins/aswath-skill-router/scripts/learning-hook.py).

The hook has two rules that matter and are easy to break:

  a load is precedent, not an outcome - it must never move the ledger score
  an edit after a load is an accept, and a delete of what the skill produced
  is a reject
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / "plugins" / "aswath-skill-router" / "scripts" / "learning-hook.py"


def _run(state, event, payload):
    f = Path(state) / "payload.json"
    f.write_text(json.dumps(payload), encoding="utf-8")
    env = dict(os.environ)
    env["SKILL_ROUTER_STATE_DIR"] = str(state)
    subprocess.run([sys.executable, str(HOOK), "--event", event,
                    "--payload-file", str(f)],
                   capture_output=True, text=True, env=env)


def _state():
    d = tempfile.mkdtemp()
    return Path(d)


def test_a_load_records_the_request_but_not_the_score():
    state = _state()
    _run(state, "UserPromptSubmit",
         {"session_id": "s1", "hook_event_name": "UserPromptSubmit",
          "prompt": "bump the version and publish the release notes"})
    _run(state, "PostToolUse",
         {"session_id": "s1", "hook_event_name": "PostToolUse",
          "tool_name": "Skill", "tool_input": {"name": "version-bump"}})
    obs = [json.loads(l) for l in
           (state / "observations.ndjson").read_text(encoding="utf-8").splitlines() if l.strip()]
    loads = [o for o in obs if o.get("outcome") == "load"]
    assert len(loads) == 1
    assert loads[0]["skill"] == "version-bump"
    assert "release notes" in (loads[0].get("request") or "")
    ledger = state / "ledger.json"
    if ledger.is_file():
        led = json.loads(ledger.read_text(encoding="utf-8"))
        rec = (led.get("skills") or {}).get("version-bump") or {}
        assert rec.get("accepts", 0) == 0
        assert rec.get("partials", 0) == 0
        assert rec.get("score", 0) == 0


def test_an_edit_after_a_load_is_an_accept():
    state = _state()
    _run(state, "UserPromptSubmit",
         {"session_id": "s2", "hook_event_name": "UserPromptSubmit",
          "prompt": "do the thing"})
    _run(state, "PostToolUse",
         {"session_id": "s2", "hook_event_name": "PostToolUse",
          "tool_name": "Skill", "tool_input": {"name": "demo"}})
    _run(state, "PostToolUse",
         {"session_id": "s2", "hook_event_name": "PostToolUse",
          "tool_name": "Write", "tool_input": {"file_path": "notes.md"}})
    led = json.loads((state / "ledger.json").read_text(encoding="utf-8"))
    rec = (led.get("skills") or {}).get("demo") or {}
    assert rec.get("accepts", 0) == 1


def test_deleting_what_the_skill_produced_is_a_reject():
    state = _state()
    _run(state, "UserPromptSubmit",
         {"session_id": "s3", "hook_event_name": "UserPromptSubmit",
          "prompt": "do the thing"})
    _run(state, "PostToolUse",
         {"session_id": "s3", "hook_event_name": "PostToolUse",
          "tool_name": "Skill", "tool_input": {"name": "demo"}})
    _run(state, "PostToolUse",
         {"session_id": "s3", "hook_event_name": "PostToolUse",
          "tool_name": "Write", "tool_input": {"file_path": "notes.md"}})
    _run(state, "PostToolUse",
         {"session_id": "s3", "hook_event_name": "PostToolUse",
          "tool_name": "Bash", "tool_input": {"command": "rm notes.md"}})
    led = json.loads((state / "ledger.json").read_text(encoding="utf-8"))
    rec = (led.get("skills") or {}).get("demo") or {}
    assert rec.get("rejects", 0) == 1
