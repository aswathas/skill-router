# Reproducing the numbers

## Requirements

- Python 3.9+ (tested on 3.14). No third-party packages for the router,
  the registry builder, the auditor or the evaluation harness.
- `reportlab` — only if you want to rebuild the PDF rendering
  (`pip install reportlab`). The `.tex` needs a LaTeX install with
  `acmart` instead.
- A skill library to route over. The shipped numbers were measured against
  4,205 skills (1,119 local, 306 plugin, 2,780 marketplace).

## 1. Build the registry

~~~bash
python skills/aswath-capability/scripts/build-registry.py
~~~

Scans every root the host can reach and writes the index to the shared state
directory. Override the location with `SKILL_ROUTER_STATE_DIR`:

~~~bash
export SKILL_ROUTER_STATE_DIR="$PWD/.state"
python skills/aswath-capability/scripts/build-registry.py
~~~

Expected on the shipped machine: 4,205 skills, 78 capabilities.

## 2. Audit the taxonomy

~~~bash
python skills/aswath-capability/scripts/taxonomy-audit.py
~~~

Expected: **0 unroutable, 0 stale, 0 starved**. The audit is only meaningful
if the auditor and the tagger use identical evidence rules; if you change
`build-registry.py`'s matching rules, change `taxonomy-audit.py`'s too, or the
audit will call correct tags stale.

## 3. Run the evaluation

~~~bash
cd evals
python run_eval.py
~~~

Writes `results.json` and `results.md`. It needs the registry from step 1
(shared state directory, or `--state-dir`).

The `random` baseline is seeded deterministically per request, so a re-run
reproduces the same numbers.

## 4. Rebuild the paper

~~~bash
cd paper
python build.py
~~~

Reads `../evals/results.json` and regenerates the tables, `skill-router.tex`
and `skill-router.pdf`. The tables in the paper are computed from the eval
artefacts at build time, so the paper cannot drift from the harness.

To compile the LaTeX yourself:

~~~bash
pdflatex skill-router.tex
~~~

with `acmart` installed. The reportlab PDF and the LaTeX PDF are rendered from
the same `content.py`, so they carry the same text.

## Determinism

- The router is deterministic: same registry, same request → same skill.
- The `random` baseline uses a per-request CRC32 seed: stable across runs.
- The batch learner (`scripts/learn.py`) replays stored transcripts and is
  deterministic given the same corpus.
- The live hook is not: it observes a real session, so its ledger evolves with
  use. That is the point of it, and also why its effect is hard to measure in
  a fixed benchmark.

## Notes from the build

- **PowerShell 5.1 pipes a UTF-8 BOM into native stdin.** Any JSON parser fed
  from a PowerShell pipeline must strip it.
- **Never rewrite YAML config with a round-trip dumper.** Editing config as
  text preserves indentation and anchors; `yaml.safe_dump` does not.
- **The registry builder must scan every root the host scans.** A skill the
  host can invoke but the router cannot see is a silent hole.
