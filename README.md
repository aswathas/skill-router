# skill-router

`Capability routing for agent skill libraries.`

Coding agents accumulate skills faster than they can read them. This repo is a
system that keeps the catalog small, and routes each request to **exactly one**
skill that actually fits — plus the evidence, the evaluation harness and the
paper that measures whether it works.

It was built and measured on one machine with **4,225 installed skills**.

| | before | after |
|---|---|---|
| skills visible to the agent | 1,387 | **44** (−96.8%) |
| catalog listing cost (tokens, est.) | 1,922,567 | **89,205** (−95.4%) |
| capabilities in the taxonomy | 51 | **78** |
| skills no capability could reach | 845 | **0** |
| tags unsupported by their own evidence | 78 | **0** |

Routing accuracy over a 298-case benchmark:

| system | capability top-1 | strict top-1 | MRR | on-topic | mean tokens |
|---|---|---|---|---|---|
| random | 0.010 | 0.000 | 0.022 | 0.050 | 2,153 |
| name-only | 0.198 | 0.127 | 0.292 | 0.248 | 703 |
| BM25 (real retrieval baseline) | 0.473 | **0.397** | 0.570 | 0.560 | 1,898 |
| keyword-substring (pre-fix) | 0.614 | 0.206 | 0.678 | 0.460 | 592 |
| **full (shipped)** | **0.849** | **0.397** | **0.878** | **0.799** | 2,881 |

The paper reports three negative results honestly: the outcome ledger does not
measurably improve routing at this scale, **BM25 ties the full router on
exact-skill selection**, and accuracy rises with token cost.

The biggest single gain came from the **taxonomy**, not the ranker. An error
analysis showed that 98 of 101 failures were cases where the request never
named the expected capability at all. Repairing the taxonomy on one half of
the benchmark lifted accuracy on the held-out half from 0.556 to 0.742, and
over the whole benchmark from 0.661 to 0.849 (p = 3.2e-15); see
[docs/EVALUATION.md](docs/EVALUATION.md).

**[Read the paper](paper/skill-router.pdf)** · [LaTeX source](paper/skill-router.tex)

---

## What's new here

This is not a new learning algorithm. It is a decomposition, a taxonomy
discipline and an evaluation protocol for a problem that agent hosts solve by
accident.

**1. Gating and ranking are separated, and each is measured on its own.**
Agent hosts expose every installed skill to the model. The cost that matters is
not the right skill — it is paid once — but the *catalog*, paid on every
request. Splitting the problem into "remove what the model never needs" and
"choose one from what remains" gives two independent levers: gating alone cuts
the visible catalog by 97%; ranking alone, with a careful taxonomy, lifts strict
selection accuracy by 50% over a lexical baseline. Doing only one leaves most
of the value on the table.

**2. A capability taxonomy where every tag is a claim that needs evidence.**
Four evidence channels of decreasing strength, weak keywords matched per name
token rather than as raw substrings, and — the part that matters most — an
auditor that uses *exactly* the same evidence rules as the tagger. When they
disagreed, the audit output was noise. The audit is a maintained artefact with
its own metrics (unroutable skills, stale tags), not a one-off annotation pass.
This is the load-bearing contribution: on the pre-repair taxonomy, 845 of
1,318 local and plugin skills had no reachable capability until a small number
of families were named.

**3. An evaluation protocol that resists its own taxonomy.**
Benchmark requests are paraphrased to avoid the taxonomy's keyword strings,
the harness *computes* a lexically isolated subset and reports it separately,
and an on-topic rate consults no taxonomy at all. The subset is measured under
two definitions, and the result is unflattering and reported anyway: on
isolated cases the shipped router drops to less than half its overall
accuracy.

**4. Two negative results, stated rather than smoothed.**
The outcome ledger — Reflexion's intuition applied to skill selection — does
not measurably improve routing at the scale of the available evidence, and
accuracy rises with token cost. Both are quantified, not hidden.

**5. A repaired native skill-evolution channel.**
It existed in the host and was unreachable from the command line: not a
top-level JSON-RPC method, but on a separate service contract behind a
transport method the CLI did not speak. Repairing it was a precondition for
everything else.

What this is *not*: no gradient descent, no learned ranker, no LLM re-ranker,
no human-preference study. The router is a deterministic program, which is also
why the selection cannot be trained the way tool selection usually is.

---

## What it does

Five coupled parts. Each one exists because the measurement demanded it.

1. **Catalog gating.** The host exposes three external skill roots by default.
   One configuration key turns them off, removing 1,343 of 1,387 visible
   skills without touching the data directory root the host always scans.
2. **Parking.** Skills in the always-scanned root cannot be gated by config.
   They are *moved* to a holding directory with a manifest, so any one of them
   can be restored. A move, not a copy: no disk cost, fully reversible.
3. **A capability taxonomy.** A hand-curated vocabulary of job kinds, where
   every tag is a *claim that needs evidence*. Four evidence channels of
   decreasing strength, and an auditor that uses exactly the same rules as the
   tagger — otherwise the auditor calls correct tags stale and the output is
   noise.
4. **The router.** Free-text need → exactly one skill, loaded rather than
   merely reported. Capability inference with weighted evidence, a *head
   capability* rule, name relevance, a capped ledger penalty, and a **Pareto**
   cost gate.
5. **A learning loop.** A plugin hook watches sessions and scores skills from
   what actually happened: files the skill produced that survived the session
   are an accept, files it produced that got deleted are a reject.

Plus a repair: the host's native skill-evolution channel existed but was
unreachable from the command line. It works now.

---

## Install

The repo is host-agnostic in layout but tuned for MiniMax Code (mcode).
Everything is plain Python 3 with no third-party dependencies.

~~~bash
git clone https://github.com/aswathas/skill-router.git
cd skill-router

# 1. the router skill -> any skills root the agent reads
cp -r skills/aswath-capability ~/.agents/skills/

# 2. the learning-loop plugin -> the host's plugin directory (auto-discovered)
cp -r plugins/aswath-skill-router ~/.minimax/plugins/

# 3. the catalog gate -> merge into your config
#    (see config/config.sample.yaml)
~~~

Then rebuild the registry so the router can see what is installed:

~~~bash
python ~/.agents/skills/aswath-capability/scripts/build-registry.py
python ~/.agents/skills/aswath-capability/scripts/taxonomy-audit.py
~~~

`taxonomy-audit.py` should report **0 unroutable, 0 stale, 0 starved**.

> **Portability.** The router keeps its mutable state in one place, overridable
> with `SKILL_ROUTER_STATE_DIR`. Nothing in this repo hardcodes a home
> directory, so it runs from a checkout, a container or CI.

---

## Use

~~~bash
# what does this need? (decide + show the exact call)
python scripts/invoke.py "equity research on Indian green energy stocks"

# decide and print the skill body
python scripts/invoke.py "review this diff for security bugs" --load

# machine-readable
python scripts/invoke.py "write unit tests for the auth module" --json

# what does the taxonomy fail to cover?
python scripts/query-registry.py gap "build an ecommerce site with cart and checkout"

# coverage stats
python scripts/query-registry.py stats
~~~

Park and restore the skills the host always scans:

~~~bash
python bin/park-skills.py status
python bin/park-skills.py park
python bin/park-skills.py restore <skill-name>
python bin/park-skills.py restore-all
~~~

The `mavis` CLI in `bin/` drives the host's native channels (catalog listing,
skill-evolution signalling) over the desktop transport.

---

## Evaluate it yourself

~~~bash
cd evals
python run_eval.py            # writes results.json and results.md
~~~

Seven systems are compared on the same 298 cases: `random`, `name_only`,
`keyword_substring` (a faithful reimplementation of the pre-fix matcher),
`no_ledger`, `no_cost_gate`, `full_budget` and `full`.

Metrics: capability top-1 / top-3 / MRR, strict top-1 (one unambiguous skill
per case), a taxonomy-independent **on-topic** rate, and on-invoke token cost.

The benchmark is written in natural language and deliberately avoids the
taxonomy's own keyword strings where a paraphrase exists. The harness computes
a **lexically isolated subset** (66 cases under the shipped taxonomy, 126 under
the pre-repair lists) and reports it separately, so the
evaluation is not circular.

See [docs/EVALUATION.md](docs/EVALUATION.md).

---

## Repository layout

~~~
bin/                  mavis CLI, park-skills.py
skills/aswath-capability/
    SKILL.md          the agent-facing instruction bundle
    scripts/          invoke, build-registry, taxonomy-audit, query-registry,
                      learn, record-outcome, delegate, stage-install
    registry/         capabilities.json (the taxonomy), ledger + backend samples
    reference/        authoring, promotion, quality bar
    docs/             design notes, quickstart
plugins/aswath-skill-router/
    hooks/            UserPromptSubmit + PostToolUse wiring
    scripts/          learning-hook.{py,ps1,sh}
evals/                benchmark-a/b/c.jsonl, historical.jsonl, run_eval.py,
                      results.json, results.md, system-metrics.json
paper/                content.py (single source), build.py, build_pdf.py,
                      skill-router.tex, skill-router.pdf
config/               config.sample.yaml
docs/                 architecture, evaluation, reproduction notes
~~~

---

## Design decisions

- **Gating and ranking are separate problems.** Gating removes what the model
  never needs before it sees it. Ranking picks one skill from what remains.
  Doing only one leaves most of the value on the table.
- **Evidence channels, not vibes.** Strong phrases, weak name words, exact
  tokens, file stems. Weak keywords match **per name token**, never as raw
  substrings — otherwise `form` matches `transform`, `test` matches `latest`,
  `git` matches `digit`, `lock` matches `block`.
- **A generic noun is not strong evidence.** `process` as a strong keyword made
  one capability cover 159 of 1,318 skills. That is no coverage at all.
- **The auditor and the tagger must agree.** If they use different definitions
  of evidence, the audit output is noise.
- **Pareto cost gate, not cheapest-wins.** A skill is too expensive only if
  another skill matches *at least as well* and costs a fraction of it. The
  naive rule deletes the better match.
- **A rejected skill is demoted, not banned.** Negative ledger evidence is a
  capped penalty, so a skill stays reachable as a last resort.
- **One source of truth for mutable state.** The registry index and the outcome
  ledger live in one directory, so two installs of the router cannot drift.

---

## Limitations

- The evaluation is **one machine, one catalogue, one author**. The benchmark
  reflects one person's request habits and capability labels.
- The **strict subset is small** (63 cases) and is the metric we trust most.
- Capability labels are coarse: a skill can carry the expected capability and
  still be a poor answer. There is no human-preference study.
- The **learning loop is a null result** at this scale: 19 scored skills is too
  few to measure its effect. The mechanism is sound; the evidence is not there.
- The catalog gate is **host-specific** — it relies on one configuration key
  whose name and semantics are properties of this host, not a standard.
- Two native evolution operations (revert, lifecycle) are unavailable in the
  embedded runtime.

---

## Paper

*Capability Routing for Agent Skill Libraries* — ACM-style (`acmart`, `sigconf`).

- [`paper/skill-router.pdf`](paper/skill-router.pdf) — rendered artefact
- [`paper/skill-router.tex`](paper/skill-router.tex) — canonical LaTeX source
- [`paper/content.py`](paper/content.py) — the single content definition both
  artefacts are generated from

The tables in the paper are generated from `evals/results.json` at build time,
so the paper cannot drift from the harness that produced the numbers.

~~~bash
cd paper && python build.py      # writes skill-router.tex and skill-router.pdf
~~~

The PDF is rendered with reportlab because this machine has no LaTeX toolchain.
Compiling the `.tex` with `acmart` produces the same paper.

---

## License

MIT. See [LICENSE](LICENSE).
