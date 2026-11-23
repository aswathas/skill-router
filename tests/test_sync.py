# -*- coding: utf-8 -*-
"""The skill exists in two repos. They must not drift.

`aswathas/skill-router` carries the router and its own copy of the
aswath-capability skill. `aswathas/aswath-skills` carries the published copy
that every harness loads. The same files have already drifted once - the
ledger fold was fixed in one copy and not the other, and the router silently
stopped learning. This test is the guard.

It skips when the second repo is not on the machine, so it never fails a
checkout that only has one of them.
"""

import os
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HERE = REPO / "skills" / "aswath-capability" / "scripts"

OTHER_ENV = "ASWATH_SKILLS_REPO"
OTHER_DEFAULT = "~/Projects/aswath-skills-wk"
SHARED = ("invoke.py", "embed.py", "semantic.py", "precedent.py",
          "build-registry.py", "query-registry.py", "record-outcome.py",
          "taxonomy-audit.py", "stage-install.py")


def _other_scripts():
    root = Path(os.environ.get(OTHER_ENV, OTHER_DEFAULT)).expanduser()
    d = root / "skills" / "orchestration" / "aswath-capability" / "scripts"
    return d if d.is_dir() else None


def test_the_two_copies_of_the_skill_are_identical():
    other = _other_scripts()
    if other is None:
        return  # the second repo is not on this machine
    shared = [n for n in SHARED if (HERE / n).is_file() and (other / n).is_file()]
    assert shared, "no shared scripts found - the paths have moved"
    drifted = []
    for name in shared:
        a = (HERE / name).read_bytes()
        b = (other / name).read_bytes()
        if a != b:
            drifted.append(name)
    assert not drifted, ("these files differ between the two repos, and the "
                         "router and the harness will not agree: %s" % ", ".join(drifted))
