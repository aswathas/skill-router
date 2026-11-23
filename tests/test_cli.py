# -*- coding: utf-8 -*-
"""Tests for the router CLI (bin/router.py)."""

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _load():
    spec = importlib.util.spec_from_file_location("router_cli", REPO / "bin" / "router.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["router_cli"] = mod
    spec.loader.exec_module(mod)
    return mod


router = _load()


def test_frontmatter_is_split_out():
    fm, body = router._frontmatter(
        "---\nname: demo\ndescription: A demo skill\n---\n\n# Body\ntext\n")
    assert fm["name"] == "demo"
    assert fm["description"] == "A demo skill"
    assert body.strip().startswith("# Body")


def test_frontmatter_without_markers_is_all_body():
    fm, body = router._frontmatter("no frontmatter here")
    assert fm == {}
    assert body == "no frontmatter here"


def test_ledger_quality_reject_costs_more_than_accept_earns():
    router.state_dir = lambda: Path("/nonexistent")
    ledger = {"skills": {"good": {"accepts": 2, "rejects": 0},
                         "bad": {"accepts": 0, "rejects": 1}}}
    orig = router.load_json
    router.load_json = lambda path, default=None: ledger
    try:
        q = router.ledger_quality()
    finally:
        router.load_json = orig
    assert q["good"] == 20
    assert q["bad"] == -50


def test_quality_is_stamped_onto_the_registry():
    reg = {"local": [{"name": "Demo Skill", "slug": "demo-skill"}],
           "plugin": [], "marketplace": []}
    router.apply_quality(reg, {"demo-skill": 30})
    assert reg["local"][0]["quality"] == 30


def test_category_follows_the_question_not_one_stray_word():
    assert router._category_for("publish to linkedin", name="aswath-publish-linkedin") == "publishing"
    # 'memory' alone is not a question, so it must not pick the context folder.
    assert router._category_for("memory safety in rust", name="rust-security") == "utilities"


def test_candidate_entry_carries_the_taxonomy_tags():
    inv = router.invoke()
    caps = {"security-ops": {"strong": ["security"], "weak": []}}
    entry = router._candidate_entry(_write_skill(), inv, caps)
    assert entry["slug"] == "demo"
    assert "security-ops" in entry["tags"]
    assert entry["source"] == "local"


def test_forged_frontmatter_survives_a_colon_in_the_description():
    # A plain YAML scalar breaks on ': ' and the skill then loads with no
    # description at all. The forge quotes it.
    desc = "Use when | security patterns. USE WHEN: user works with Rust"
    line = '---\nname: "aswath-demo"\ndescription: "%s"\n---\n' % desc
    assert 'description: "' in line
    assert json.loads('"%s"' % desc.replace('"', '\\"')) == desc


def _write_skill(tmp=None):
    import tempfile
    d = Path(tempfile.mkdtemp())
    (d / "SKILL.md").write_text(
        "---\nname: demo\ndescription: security patterns for rust\n---\n\nbody\n",
        encoding="utf-8")
    return d
