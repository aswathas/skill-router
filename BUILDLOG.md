# Build log

What shipped, when, and where. Releases before this file existed are described by the
git history; each entry below names the branch, the change and how it was verified.

## 2026-11-17 — v0.1.1, Claude Code plugin support
- Branch: `feat/claude-code-plugin`
- Shipped:
  - `.claude-plugin/marketplace.json` — the plugin can now be installed in Claude Code
    from GitHub, so a second machine needs no hand-copied files.
  - `plugins/aswath-skill-router/.claude-plugin/plugin.json` — the Claude manifest. The
    MiniMax manifest is not a valid Claude manifest: Claude Code wants `author` as an
    object and hook paths that start with `./`.
  - PostToolUse matcher widened to cover both harness spellings of the tool names.
  - `learning-hook.py` compares tool names case-insensitively and accepts
    `notebookedit` alongside `notebook_edit`.
  - Both manifests bumped to 0.1.1.
- Verified:
  - `claude plugin install aswath-skill-router@aswath-skill-router -y --json` on the
    local marketplace -> `{"outcome":"ok"}`; `claude plugin details` ->
    `Hooks (2) UserPromptSubmit, PostToolUse`, projected cost `~0 tok`.
  - Hook replay against the repo copy with `SKILL_ROUTER_STATE_DIR` pointed at a temp
    directory: Claude payloads (`Skill`+`Edit`, `Skill`+`Write`, `NotebookEdit`) and
    MiniMax payloads (`skill`+`edit`) each wrote one `accept` observation to
    `observations.ndjson`.
- Where: `aswathas/skill-router`, branch `feat/claude-code-plugin`.
- Records: `docs/reviews/decision-log.md` (D1-D5), `docs/reviews/change-inventory.md`,
  `docs/reviews/prompts.md`.

## 2026-11-17 — v0.1.1 follow-up, marketplace source path
- Branch: `fix/marketplace-source-path`
- Shipped: `.claude-plugin/marketplace.json` now writes the plugin source as
  `./plugins/aswath-skill-router`.
- Why: the merged manifest was rejected by the installer with
  `source: Invalid string: must start with "./"`. Claude Code wants a relative source
  written with the `./` prefix.
- Verified: `claude plugin install aswath-skill-router@aswath-skill-router -y --json`
  -> `{"outcome":"ok"}` against the corrected manifest.
- Where: `aswathas/skill-router`, branch `fix/marketplace-source-path`.
- Records: `docs/reviews/decision-log.md` (D6), `docs/reviews/change-inventory.md`.

## 2026-11-18 — v0.1.2, Claude Code plugin-root resolution
- Branch: `fix/claude-plugin-root`
- Shipped:
  - `plugins/aswath-skill-router/hooks/hooks.json` — both `command` values now resolve the plugin
    root at runtime: `sh -c 'p="${CLAUDE_PLUGIN_ROOT:-${PLUGIN_ROOT}}"; exec sh "$p/scripts/learning-hook.sh" <event>'`.
    Claude Code exports `CLAUDE_PLUGIN_ROOT` and substitutes no `PLUGIN_ROOT`, so the shared file
    addressed `/scripts/learning-hook.sh` and died on every prompt. MiniMax substitutes
    `${PLUGIN_ROOT}`, which the fallback branch picks up. `commandWindows` is unchanged: Claude Code
    does not read that key, and MiniMax's PowerShell path was already correct.
  - `.claude-plugin/marketplace.json`, `plugins/aswath-skill-router/.claude-plugin/plugin.json` and
    `plugins/aswath-skill-router/.minimax-plugin/plugin.json` bumped to 0.1.2.
- Verified:
  - `printenv CLAUDE_PLUGIN_ROOT` in a live hook process returns the cache path; `PLUGIN_ROOT` is unset.
  - The new command with that variable exported printed
    `RESOLVED=[C:/Users/ADMIN/.claude/plugins/cache/aswath-skill-router/aswath-skill-router/0.1.1]`
    and exited 0.
  - A live `claude -p` run afterwards printed no "No such file" error, and the hook wrote
    `~/.agents/state/session-d36697d6-9505-48f8-8e25-d61c3b70e7e5.json` holding the prompt — the
    hook's own trace that it ran.
- Where: `aswathas/skill-router`, branch `fix/claude-plugin-root`.
- Records: `docs/reviews/decision-log.md` (D7), `docs/reviews/change-inventory.md`,
  `docs/reviews/prompts.md`.


## 2026-11-23 — the router becomes a command, and the ledger starts counting

- What:
  - `bin/router.py`, the CLI: `ask`, `why`, `list`, `learn`, `rebuild`, `eval`,
    `fetch`, `test`, `ensure`, `forge`, `park`. It imports the shipped ranker, so it
    cannot drift from it.
  - The ledger now folds into the score. `build-registry.py` read a dict where a
    number belonged, so `quality` was always 0 and the outcome ledger never moved a
    ranking. Accept +10, reject -50, partial +2, applied live at query time and
    written into the registry at rebuild time.
  - `router ensure` closes the loop the user asked for: a need the catalogue cannot
    answer is searched for on GitHub, the candidates are screened, each survivor is
    run against the 298-case benchmark, and the winner is minted into `aswath-skills`
    as `aswath-<slug>` with a `Use when` description, an origin line, a manifest row,
    a README row and a re-run of `install.ps1`.
  - `bin/park-skills.py` gained `--root`, so parking works on the Claude root as well
    as the MiniMax one, and the keep set now protects the skills the session depends
    on by name.
  - `evals/run_eval.py` writes its markdown beside its json, so a local run cannot
    overwrite the evidence the paper quotes.
- Why: the router was real but not usable — no command, a stale registry, a ledger
  that could not change a decision, and no way to answer a need the catalogue did not
  already cover.
- Verified:
  - `pytest tests` -> 47 passed.
  - `router ask "roast this UI and fix it"` -> `design-taste-frontend`;
    `router ask "write a python script that parses csv"` -> `aswath-csvjson`.
  - `router ensure "detect and fix memory leaks in a rust binary"` -> fetched
    `claude-dev-suite/claude-dev-suite`, judged `rust-security` (wins the need, 1 case
    stolen of 298), forged it into
    `C:\Users\ADMIN\Projects\aswath-skills-wk\skills\utilities\aswath-rust-security`,
    and `install.ps1` linked it into `~/.claude/skills` and `~/.agents/skills`.
  - `router ask "rust security vulnerabilities cargo audit"` -> `aswath-rust-security`.
  - Benchmark on this machine (3,261 skills in the catalogue): top-1 0.805, MRR 0.833.
    The paper's 0.849 was measured on a 4,225-skill catalogue on another machine.
- Where: `aswathas/skill-router`, branch `feat/router-cli`.
- Records: `docs/reviews/decision-log.md` (D8-D11), `docs/reviews/change-inventory.md`,
  `docs/reviews/prompts.md`.

## 2026-11-24 — a local embedding layer for the requests that name nothing

- What:
  - `scripts/embed.py`: embeds the catalogue with the embedding model already in
    LM Studio. No key, nothing leaves the machine. Vectors are stored base64
    float32, so the index is 12.6 MB instead of 101 MB.
  - `scripts/semantic.py`: the layer. `rescue` adds exactly one capability,
    voted by the skill nearest to the request, and only when the keywords
    named none. `tie` lets the nearest skill win among the carriers of the
    winning capability. The shipped ranking in `invoke.py` is untouched, so the
    numbers the paper quotes still describe it.
  - `evals/run_semantic_eval.py`: the measurement, on the same 298 cases, with
    McNemar on the strict subset.
  - `router sem status|build|query|eval`, and `router ask` now uses the layer
    and says whether it fired.
- Why: 42 of 45 routing failures were requests that never named the capability,
  and 27 of 38 strict failures were a sibling of the right skill winning.
- What was tried and rejected, with the numbers: capability centroids
  (top-1 0.805 -> 0.399), many capabilities voting (0.805 -> 0.483), a
  distinctive-name anchor (0.805 -> 0.742), a name-only embedding as the
  tie-break (6 of 63 strict cases).
- What shipped: conservative by default - capability top-1 0.805 unchanged,
  strict top-1 0.206 -> 0.222, mean cost 2435 -> 2096. Aggressive is opt-in:
  strict 0.254 for three capability cases lost.
- Verified:
  - `pytest tests` -> 54 passed.
  - `python evals/run_semantic_eval.py` -> both rows and 0-3 discordant pairs.
  - `router ask "wire my calendar to a slack channel so meetings announce
    themselves"` -> `gws-calendar-agenda`, with the semantic line, in 0.31 s.
  - With the provider stopped, the router still answers and says why.
- Where: `aswathas/skill-router`, branch `feat/semantic-layer`.
- Records: `docs/reviews/decision-log.md` (D12-D13), `docs/reviews/change-inventory.md`,
  `docs/reviews/prompts.md`.

## 2026-11-24 — the last wall: precedent

- What:
  - The learning hook writes a `load` observation carrying the request and the
    skill that was loaded. The pairing was already in the hook's hands and was
    being thrown away.
  - `scripts/precedent.py` reads those rows and answers which skill was used
    last time for a request like this one.
  - `router ask` gives that skill a bonus of 8 and re-inserts it if the matcher
    dropped it. `router precedent` shows the history.
- Why: the strict-subset failures are sibling choices, not matching failures.
  25 of 63 expected skills are not installed on this machine, so the ceiling is
  0.603. Of the 38 installed, the keyword router is right in 13 cases, the
  semantic one in 12, and their union is 14 - there is no combined headroom.
  Only history distinguishes two interchangeable skills.
- Verified:
  - `pytest tests` -> 58 passed.
  - Simulated hook run -> one `load` row with the request in it; the store
    reads it back; `router ask` picks the skill that was used before and says
    so.
  - The plugin version moved to 0.1.3 because the shared hook file changed.
- Where: `aswathas/skill-router`, branch `feat/precedent-routing`.
- Records: `docs/reviews/decision-log.md` (D14), `docs/reviews/change-inventory.md`,
  `docs/reviews/prompts.md`.

## 2026-11-24 — one ranking path, and the load rule

- What:
  - `bin/router.py`: `rank_all()` is now the only ranking path. `ask`, `why`
    and `ensure` all use it, so the router cannot explain one answer and give
    another.
  - The learning hook's `load` row no longer counts as an outcome. A load
    says which skill was used for a request; it does not say whether the work
    succeeded, so it must not move the ledger score.
  - `tests/test_learning_hook.py` pins the three hook rules, and
    `tests/test_sync.py` fails when the two copies of the capability skill
    drift - the failure that once made the router silently stop learning.
  - The plugin moves to 0.1.4.
- Verified: `pytest tests` -> 62 passed; `router ask`, `router why` and
  `router ensure` agree; the simulated hook run leaves the ledger score at
  zero for a load.
- Where: `aswathas/skill-router`, branch `feat/one-ranking-path`.
- Records: `docs/reviews/decision-log.md` (D15), `docs/reviews/change-inventory.md`,
  `docs/reviews/prompts.md`.

## 2026-11-24 — eight skills installed, parking on evidence

- What:
  - Eight skills installed in `~/.claude/skills` from the repositories that
    actually wrote them: `fix-ci`, `fix-merge-conflicts`, `loop-on-ci`,
    `deslop` and `improve-animations` from `Asymmetric-al/core`, and
    `handoff-doc`, `long-command-check` and `long-session-check` from
    `MiniMax-AI/mcode-stack`. Each has a real frontmatter and no scripts.
  - The biggest source, `majiayu000/claude-skill-registry`, was not used: it
    holds 312,160 `SKILL.md` files and its copies are pointers, not skills.
  - `bin/park-skills.py` now parks on evidence. A skill the owner has used -
    in the ledger or the observation log - is never parked.
- Why: 25 of the 63 strict expectations named skills that were not installed
  here, so the ceiling was 0.603. And the aggressive keep list was written for
  a 1,387-skill catalogue; this machine has 114, most of them in daily use.
- Measured: capability top-1 0.805 -> **0.815**, strict top-1 0.206 -> **0.270**
  (0.286 with the semantic layer), mean cost 2435 -> **2052**. The benchmark
  request "find the failing checks on this pr and fix them" now answers
  `fix-ci`. The strict ceiling here is 46/63 = 0.730.
- Parking: one directory moved - `minimax-compaction-handoff`, a duplicate of
  `aswath-minimax-compaction-handoff`. 114 -> 113.
- Where: `aswathas/skill-router`, branch `main`.
- Records: `docs/reviews/decision-log.md` (D17-D18), `docs/reviews/change-inventory.md`,
  `docs/reviews/prompts.md`.
