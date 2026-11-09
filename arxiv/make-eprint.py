#!/usr/bin/env python3
"""Build the arXiv eprint source package.

The .tex in paper/ is already self-contained: the bibliography is written as
inline \bibitem entries, so no .bbl is needed and arXiv's own TeX engine has
acmart available. This script copies the current paper source into
arxiv/eprint/ and packs it into arxiv/skill-router-eprint.tar.gz, which is
exactly what the arXiv submission form asks for.

Run it after every paper rebuild:

    python arxiv/make-eprint.py
"""

import pathlib
import shutil
import tarfile
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAPER = ROOT / "paper"
OUT_DIR = ROOT / "arxiv"
EPRINT = OUT_DIR / "eprint"
TARBALL = OUT_DIR / "skill-router-eprint.tar.gz"


def main():
    tex = PAPER / "skill-router.tex"
    if not tex.is_file():
        raise SystemExit("paper/skill-router.tex not found - run paper/build.py first")
    if EPRINT.exists():
        shutil.rmtree(EPRINT)
    EPRINT.mkdir(parents=True)
    shutil.copy2(tex, EPRINT / tex.name)

    readme = (
        "Capability Routing for Agent Skill Libraries\n"
        "\n"
        "Source for the arXiv eprint submission.\n"
        "\n"
        "skill-router.tex  the paper (acmart, sigconf). The bibliography is\n"
        "                  inline \\bibitem entries, so no .bbl file is needed.\n"
        "                  arXiv's TeX engine provides acmart.\n"
        "\n"
        "Artefact: https://github.com/aswathas/skill-router\n"
    )
    (EPRINT / "README.txt").write_text(readme, encoding="utf-8")

    if TARBALL.exists():
        TARBALL.unlink()
    with tarfile.open(TARBALL, "w:gz") as tar:
        for f in sorted(EPRINT.iterdir()):
            tar.add(f, arcname=f.name)

    print("eprint dir :", EPRINT)
    print("tarball    :", TARBALL, TARBALL.stat().st_size, "bytes")
    print("contents   :", [p.name for p in EPRINT.iterdir()])
    print("built at   :", time.strftime("%Y-%m-%d %H:%M:%S"))


if __name__ == "__main__":
    main()
