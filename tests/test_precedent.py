# -*- coding: utf-8 -*-
"""Tests for the precedent store (scripts/precedent.py)."""

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


precedent = _load(REPO / "skills" / "aswath-capability" / "scripts" / "precedent.py",
                  "precedent_t")


def _state(tmp, rows):
    d = Path(tmp)
    d.mkdir(parents=True, exist_ok=True)
    with (d / "observations.ndjson").open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return d


def test_a_load_becomes_a_precedent():
    with tempfile.TemporaryDirectory() as tmp:
        d = _state(tmp, [
            {"outcome": "load", "skill": "changelog-generator",
             "request": "generate a changelog from the commits"},
        ])
        old = precedent.state_dir
        precedent.state_dir = lambda: d
        try:
            hit = precedent.lookup("make a changelog from the commits")
        finally:
            precedent.state_dir = old
    assert hit is not None
    assert hit["skill"] == "changelog-generator"


def test_an_accept_is_not_precedent():
    with tempfile.TemporaryDirectory() as tmp:
        d = _state(tmp, [
            {"outcome": "accept", "skill": "changelog-generator",
             "request": "generate a changelog from the commits"},
        ])
        old = precedent.state_dir
        precedent.state_dir = lambda: d
        try:
            hit = precedent.lookup("generate a changelog from the commits")
        finally:
            precedent.state_dir = old
    assert hit is None


def test_an_unrelated_request_finds_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        d = _state(tmp, [
            {"outcome": "load", "skill": "changelog-generator",
             "request": "generate a changelog from the commits"},
        ])
        old = precedent.state_dir
        precedent.state_dir = lambda: d
        try:
            hit = precedent.lookup("fix the failing tests on the pull request")
        finally:
            precedent.state_dir = old
    assert hit is None


def test_similarity_ignores_filler_words():
    a = precedent._words("bump the version and publish the release notes")
    b = precedent._words("publish release notes for the plugin version")
    assert precedent.similarity(a, b) > 0.6
