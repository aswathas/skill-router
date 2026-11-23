# -*- coding: utf-8 -*-
"""Tests for the semantic layer (scripts/embed.py, scripts/semantic.py)."""

import importlib.util
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


embed = _load(REPO / "skills" / "aswath-capability" / "scripts" / "embed.py", "embed_t")
semantic = _load(REPO / "skills" / "aswath-capability" / "scripts" / "semantic.py", "semantic_t")


def test_vectors_survive_the_round_trip():
    v = [0.5, -0.25, 0.125, 0.0]
    packed = embed._pack(v)
    assert isinstance(packed, str)
    back = list(embed._unpack(packed))
    assert len(back) == len(v)
    for a, b in zip(v, back):
        assert abs(a - b) < 1e-6


def test_cosine_of_a_vector_with_itself_is_one():
    v = [0.3, 0.4, 0.5]
    assert abs(embed.cosine(v, v) - 1.0) < 1e-6


def test_cosine_with_an_empty_vector_is_zero():
    assert embed.cosine([], [1.0]) == 0.0


def test_the_shipped_profile_never_costs_a_capability_case():
    # Measured on the 298-case benchmark: the conservative profile kept
    # capability top-1 at 0.805 and lifted strict top-1 from 0.206 to 0.222.
    assert semantic.PROFILES["conservative"]["vote_at"] >= 0.65
    assert semantic.PROFILES["conservative"]["rescue_when"] == "none"
    assert semantic.PARAMS == semantic.PROFILES["conservative"]


def test_semantic_can_be_switched_off():
    old = os.environ.get(semantic.ENABLE_ENV)
    os.environ[semantic.ENABLE_ENV] = "off"
    try:
        assert semantic.enabled() is False
    finally:
        if old is None:
            os.environ.pop(semantic.ENABLE_ENV, None)
        else:
            os.environ[semantic.ENABLE_ENV] = old


def test_prefilter_keeps_the_skills_that_share_a_word():
    reg = {"local": [{"name": "gws-calendar", "slug": "gws-calendar",
                      "description": "read a google calendar"},
                     {"name": "unrelated-thing", "slug": "unrelated-thing",
                      "description": "formats json files"}],
           "plugin": [], "marketplace": []}
    pool = semantic.prefilter(reg, "read my calendar", 10)
    names = [s["name"] for s in pool]
    assert "gws-calendar" in names
    assert "unrelated-thing" not in names


def test_a_dead_provider_falls_back_to_the_keyword_path():
    reg = {"local": [{"name": "gws-calendar", "slug": "gws-calendar",
                      "description": "read a google calendar",
                      "tags": ["integrations-calendar"]}],
           "plugin": [], "marketplace": []}
    cap_map = {"integrations-calendar": {"strong": ["calendar"], "weak": []}}
    # semantic.py loads its own instance of embed.py, so the patch goes on
    # that one, not on this test's.
    old_post = semantic.embed._post
    semantic.embed._post = lambda texts: (_ for _ in ()).throw(OSError("provider down"))
    try:
        # A request the cache has never seen, so the provider is really called.
        ranked, info = semantic.rank(reg, cap_map,
                                     "read my calendar qwerty-unseen-request")
    finally:
        semantic.embed._post = old_post
    assert ranked, "the keyword path must still answer"
    assert info["semantic"] is False
    assert "provider" in info["reason"]
