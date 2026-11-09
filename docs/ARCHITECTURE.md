# Architecture

Five parts. The order matters: the first two make the problem small, the third
makes it addressable, the fourth does the work, the fifth makes it improve.

~~~
                       ┌──────────────────────────┐
   user need ───────►  │  1. CATALOG GATE          │  what the model can see
                       │  (config key + parking)   │
                       └───────────┬──────────────┘
                                   │
                       ┌───────────▼──────────────┐
                       │  2. CAPABILITY TAXONOMY   │  what each skill is for
                       │  capabilities.json        │  (78 capabilities,
                       │  + evidence-based tagging  │   4 evidence channels)
                       └───────────┬──────────────┘
                                   │
                       ┌───────────▼──────────────┐
                       │  3. ROUTER (invoke.py)    │  need → exactly one skill
                       │  weighted inference,      │
                       │  head capability,         │
                       │  Pareto cost gate         │
                       └───────────┬──────────────┘
                                   │  score
                       ┌───────────▼──────────────┐
   session events ───► │  4. LEARNING LOOP         │  accept / reject
                       │  learning-hook.py         │  → ledger.json
                       └───────────┬──────────────┘
                                   │
                       ┌───────────▼──────────────┐
                       │  5. NATIVE EVOLUTION      │  report a broken or
                       │  CHANNEL (bin/mavis.js)   │  missing skill
                       └──────────────────────────┘
~~~

## 1. Catalog gate and parking

The host reads three external skill roots (`<agents>/skills`, `<claude>/skills`,
`<codex>/skills`) plus its own data directory, and exposes all of them by
default. A single configuration key disables the three external roots:

~~~yaml
skills:
  external:
    enabled: false
~~~

That removes 1,205 of 1,241 visible skills. The data directory root cannot be
gated this way — the host always scans it — so the skills that live there are
**parked**: moved to `skills-off/` with a manifest at
`skills-off-manifest.json` recording what was moved.

A move is not a copy: no disk cost, and `restore <name>` is one move back.
The keep set is explicit in `bin/park-skills.py`.

> **Note.** `~/.agents/skills` is *not* parked. All 1,073 local registry skills
> live there; parking it would empty the router's own library. The catalog
> gate already hides it from the host, which is all that is needed.

## 2. The capability taxonomy

A capability tag is a claim that a skill provides a kind of job. Four
evidence channels, decreasing in strength:

| channel | example | strength |
|---|---|---|
| file stem | `reference/critique.md` | strongest |
| strong keyword | `write documentation`, `unit test` | strong |
| weak keyword | a single word in the skill **name** | weak |
| exact / required token | `cli` must not match `clickmeeting` | constraint, not evidence |

Two rules that were learned the hard way:

- **Match per name token, never as a raw substring.** Substring matching made
  `form` match `transform`, `test` match `latest`, `git` match `digit` and
  `lock` match `block`.
- **A single common noun is not strong evidence.** `process` as a strong
  keyword made one capability cover 159 of 1,318 skills — no coverage at all.

The auditor (`taxonomy-audit.py`) and the tagger (`build-registry.py`) use
*identical* evidence rules. When they disagreed, the auditor called correct
tags stale and its output was noise.

Audit output on the shipped taxonomy:

| check | meaning | value |
|---|---|---|
| UNROUTABLE | skills no capability can reach | 0 |
| STALE | tags unsupported by their own evidence | 0 |
| STARVED | capabilities with no provider | 0 |

## 3. The router

`invoke.py` resolves a need and then *acts* — the chosen skill's body is
loaded, not merely reported. Scoring has five stages:

1. **Capability inference.** The request is matched against every capability's
   keyword lists. A strong phrase counts double a weak name word, because a
   request usually names its object strongly and its context weakly
   (`write unit tests for the auth module` is a request for `testing`).
2. **Head capability.** Among the capabilities the request names, the one
   mentioned *first* carries the intent. Ties are broken towards the more
   specific capability, measured by how many skills carry it.
3. **Capability match.** A skill scores by the capabilities it carries that
   the request also names. Primary capabilities dominate; a capability named
   in passing contributes little.
4. **Name relevance and ledger.** Name-word overlap and the learned quality
   score act as tie-breakers. A negative ledger score is a **capped penalty**,
   not a ban: a rejected skill stays reachable as a last resort.
5. **Cost gate (Pareto).** A skill is too expensive only if some other skill
   matches *at least as well* and costs a fraction of it.

The naive cost gate (cheapest cover wins) deleted the better match: a 3.5K
token skill that matched exactly died because a 64-token skill matched loosely
and was cheaper.

### State

The registry index and the outcome ledger live in one directory so that two
installs of the router cannot drift:

~~~
~/.minimax/local-runtime/skill-learning/
    skills.json        registry index (every skill, its tags, its token cost)
    ledger.json        outcome ledger (accept / reject counts per skill)
    capabilities.json  the taxonomy
~~~

Overridable with `SKILL_ROUTER_STATE_DIR`, which is what makes the repo
runnable outside one home directory.

## 4. The learning loop

`plugins/aswath-skill-router` wires two hooks:

- **UserPromptSubmit** — remember the prompt.
- **PostToolUse** — when a skill is loaded, remember it. When the session then
  edits or writes a file, that is an **accept**. When the session then deletes
  a file that the *same skill* produced, that is a **reject**.

The rule is deliberately conservative: a delete that does not target a file the
skill produced is not evidence against it. An early version counted any delete
in the window as a rejection, which produced systematically pessimistic scores.

`scripts/learn.py` is a batch learner that replays stored transcripts and
enforces the same rules. It is how the corpus of 304 sessions was scored and
how 19 skills acquired a quality score.

**Every path exits zero.** A hook with no opinion must never block the agent.

## 5. The native evolution channel

The host exposes a mechanism for reporting that a skill is missing a step or
uses a wrong default. On this machine it existed but could not be reached: its
calls are not top-level JSON-RPC methods, but live on a separate service
contract reachable only through a transport method the command line did not
speak. `bin/mavis.js` implements that transport.

Two operations — revert and lifecycle — remain unavailable; the embedded
runtime answers them with a hard error. That is a limit of the environment,
not of the design.

## Registry construction

`build-registry.py` scans **all** the roots the host can reach:

- `~/.minimax/skills`, `~/.minimax/.builtin-skills`, `~/.agents/skills`,
  `~/.claude/skills`, `~/.codex/skills`
- plugin skills under `~/.claude/plugins` and `~/.minimax/plugins`
- marketplace entries from the host's plugin catalog cache

Before the builder was taught to scan the built-in and plugin roots, 14
installed skills and a bundle of plugin skills were invisible to the router:
they could be invoked by name but never selected. Making the router's view
match the host's view was a precondition for trusting any evaluation.
