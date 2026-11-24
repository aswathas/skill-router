# Decision log

One entry per real choice. Oldest first. Each entry names the prompt that produced the
decision and the command that proves it.

## D1 — Install in Claude Code through a marketplace, not by copying files into the plugins folder
- Date: 2026-11-17
- Prompt: "intall our aswath router?"
- Context: `~/.claude/plugins/aswath-skill-router/` already held the plugin files and
  `~/.claude/settings.json` already listed `aswath-skill-router` as enabled, but
  `claude plugin list` did not show it and `claude plugin details aswath-skill-router`
  answered "not found". The learning hook had never fired in Claude Code.
- Options:
  - Keep the hand-copied folder and hope the flag is enough — stays unregistered, the
    hook never loads, and the failure is invisible until you check.
  - Load it per session with `claude --plugin-dir` — works, but only for that one run.
  - Register a local marketplace and install through the CLI — persistent, tracked in
    `installed_plugins.json`, and the same commands work on the second PC.
- Chosen: local marketplace plus `claude plugin install`. The plugin was already
  registered by name in settings but not installed, and only an install record makes the
  hooks load and survive a restart.
- Evidence: `claude plugin install aswath-skill-router@aswath-skill-router -y --json` ->
  `{"outcome":"ok","plugin":"aswath-skill-router@aswath-skill-router","scope":"user"}`;
  `claude plugin list` -> `aswath-skill-router@aswath-skill-router  Version: 0.1.0  Status: enabled`.
- Consequence: the plugin is now installed and enabled in Claude Code on this PC, and
  the install is reproducible with two commands instead of a file copy.

## D2 — Ship the Claude manifests in this repo, not only on the machine
- Date: 2026-11-17
- Prompt: "yes push"
- Context: the repo shipped `.minimax-plugin/plugin.json` only. There was no
  `.claude-plugin/` anywhere in the tree, so no marketplace could be added from GitHub
  and the second PC could not install the plugin without repeating the local hack.
- Options:
  - Patch only the local copy — the fix stays on one machine and dies with it.
  - Add a Claude manifest and a repo-root marketplace manifest — Claude Code can then
    install from `aswathas/skill-router` with `claude plugin marketplace add` plus
    `claude plugin install`.
  - Publish a separate plugin repo — more moving parts, no new capability.
- Chosen: add the manifests to this repo. The plugin already lived here; the missing
  piece was the Claude-facing metadata, not a new home.
- Evidence: `claude plugin marketplace add "C:/Users/ADMIN/.claude/plugins/aswath-skill-router" --json` ->
  `{"outcome":"ok","marketplace":"aswath-skill-router"}`; the same manifest shape is now
  at `.claude-plugin/marketplace.json` with `"source": "plugins/aswath-skill-router"`.
- Consequence: a second machine installs the plugin from GitHub with two commands and
  no hand-edited files.

## D3 — Compare tool names case-insensitively instead of forking the plugin per harness
- Date: 2026-11-17
- Prompt: "intall our aswath router?"
- Context: `learning-hook.py` compared `tool == "skill"` and matched the edit tools
  against `("edit", "write", "notebook_edit")`. MiniMax Code sends lowercase tool names;
  Claude Code sends `Skill`, `Edit`, `Write`, `NotebookEdit`. The hook therefore never
  saw a skill load in Claude Code, so the router never learned anything here.
- Options:
  - Maintain two copies of the plugin, one per harness — the files drift again, which is
    how the mismatch started.
  - Lowercase the tool name once at the point of reading the payload and accept both
    spellings of the notebook tool — one code path, both harnesses.
  - Rewrite the hook around a harness adapter — more code than the problem needs.
- Chosen: lowercase at the payload boundary. `tool` becomes
  `str(...).strip().lower()` and `notebookedit` joins the edit tuple.
- Evidence: simulated Claude payloads against the repo copy:
  `Skill` + `Edit` -> `{"outcome":"accept","note":"live: edit edited a.md after loading the skill"}`;
  `Skill` + `Write` -> same with `write`; `NotebookEdit` -> same with `notebookedit`.
  MiniMax-style lowercase `skill` + `edit` still produces the same observation.
- Consequence: the same hook file serves both harnesses, and Claude Code sessions now
  feed the learning ledger.

## D4 — Keep the lowercase matcher entries next to the capitalized ones
- Date: 2026-11-17
- Prompt: "yes push"
- Context: `hooks/hooks.json` is shared by both harnesses, and the PostToolUse matcher
  decides which tool calls reach the hook at all. Claude Code matches `Skill|Edit|...`
  but not `skill|edit|...`; MiniMax Code matches the lowercase set.
- Options:
  - Replace the lowercase list with the capitalized one — fixes Claude Code, silently
    stops the MiniMax hook from ever firing.
  - List both spellings — one line, both harnesses keep working.
  - Split `hooks.json` per harness — a second file and a second maintenance path.
- Chosen: list both spellings: `skill|Skill|edit|Edit|write|Write|notebook_edit|NotebookEdit|bash|Bash`.
- Evidence: the hook fires for both payload shapes in the D3 evidence run, and the
  lowercase MiniMax path still writes its observation.
- Consequence: the shared hook file stays shared.

## D5 — Bump both manifests to 0.1.1
- Date: 2026-11-17
- Prompt: "yes push"
- Context: the shared hook files changed, so both manifests describe a plugin that no
  longer matches the code they ship with.
- Options:
  - Leave 0.1.0 in both — a version that lies about its own contents.
  - Bump only the Claude manifest — the MiniMax manifest keeps describing changed files.
  - Bump both to 0.1.1 — one release, two harnesses, matching contents.
- Chosen: both to 0.1.1.
- Evidence: `plugins/aswath-skill-router/.minimax-plugin/plugin.json` and
  `plugins/aswath-skill-router/.claude-plugin/plugin.json` both read `"version": "0.1.1"`,
  and the marketplace entry in `.claude-plugin/marketplace.json` pins the same version.
- Consequence: a cached install on either harness is invalidated by the version change
  rather than silently running stale code.

## D6 — Write the marketplace source as "./plugins/aswath-skill-router"
- Date: 2026-11-17
- Prompt: "yes push"
- Context: after the first merge, installing from the GitHub marketplace failed with
  `source: Invalid string: must start with "./"`. Claude Code wants a relative
  marketplace source written as `./<path>`, not `<path>`.
- Options:
  - Move the plugin to the repo root and use `"source": "./"` — relocates files to satisfy
    a string rule, and breaks the `plugins/<name>` layout the MiniMax install uses.
  - Write `"./plugins/aswath-skill-router"` — one prefix, layout untouched.
  - Publish the plugin in its own repository — more moving parts for the same result.
- Chosen: `"./plugins/aswath-skill-router"`. The layout stays as the MiniMax side expects
  it and the rule is satisfied.
- Evidence: `claude plugin install aswath-skill-router@aswath-skill-router -y --json`
  -> failed with `source: Invalid string: must start with "./"` against the merged
  manifest; after the fix the same command against the same manifest returned
  `{"outcome":"ok","plugin":"aswath-skill-router@aswath-skill-router"}`.
- Consequence: the GitHub marketplace installs the plugin, so a second machine needs
  `claude plugin marketplace add aswathas/skill-router` and nothing else.

## D7 — Resolve the plugin root at runtime, from whichever variable the harness exports
- Date: 2026-11-18
- Prompt: "solve this" (the pasted error: `Failed with non-blocking status code: sh: /scripts/learning-hook.sh: No such file or directory`)
- Context: the shared `hooks.json` addressed the hook script as `"${PLUGIN_ROOT}/scripts/learning-hook.sh"`.
  `${PLUGIN_ROOT}` is the MiniMax Code placeholder. Claude Code substitutes and exports
  `${CLAUDE_PLUGIN_ROOT}` instead, and exports no `PLUGIN_ROOT` at all, so the path collapsed to
  `/scripts/learning-hook.sh` and the hook died on every prompt in Claude Code. One file has to
  serve both harnesses.
- Options:
  - Two hook files, one per harness, selected by the harness - Claude Code reads
    `hooks/hooks.json` from the plugin root and MiniMax reads its own path, so a shared file
    cannot be swapped per harness without two plugin packages.
  - Ask Claude Code to substitute `${PLUGIN_ROOT}` - it does not; the variable is not one of its
    placeholders and no amount of editing the manifest makes it one.
  - Resolve the root at runtime from the environment, preferring the Claude variable and falling
    back to the MiniMax one - `sh -c 'p="${CLAUDE_PLUGIN_ROOT:-${PLUGIN_ROOT}}"; exec sh "$p/scripts/learning-hook.sh" <event>'`.
    Claude Code exports `CLAUDE_PLUGIN_ROOT` and leaves `PLUGIN_ROOT` unset, so it takes the first
    branch; MiniMax substitutes `${PLUGIN_ROOT}` into the command text, so the fallback branch
    carries the right path. Neither harness sees a literal `${...}` left in the path.
  - Hard-code an absolute path - breaks on every other machine and every plugin version.
- Chosen: the runtime resolver.
- Evidence: `printenv CLAUDE_PLUGIN_ROOT` in a live Claude Code hook process returns
  `C:/Users/ADMIN/.claude/plugins/cache/aswath-skill-router/aswath-skill-router/0.1.1`, and
  `PLUGIN_ROOT` is unset. Running the new command with that variable exported resolved
  `RESOLVED=[C:/Users/ADMIN/.claude/plugins/cache/aswath-skill-router/aswath-skill-router/0.1.1]`
  and exited 0. A live `claude -p` run afterwards produced no "No such file" error and the hook
  wrote its session state (`session-d36697d6-...json` holding the prompt), which is the hook's own
  proof that it ran.
- Consequence: the `command` field works on both harnesses. `commandWindows` is left untouched:
  Claude Code does not read that key (it ran the `sh` command on Windows, which is why the failure
  was a `sh:` error), and MiniMax's PowerShell path already substitutes `${PLUGIN_ROOT}` correctly.
- Note on the resolver form: the exact token `${CLAUDE_PLUGIN_ROOT}` deliberately does not appear in
  the command, so a harness that substitutes placeholders textually leaves the expression intact
  and the shell resolves it from the environment.

## D8 — Fold the ledger into the score, not into the registry file
- Date: 2026-11-23
- Prompt: "how should or hwo will the skill router used is it working"
- Context: the shared ledger stores outcomes as counts per skill
  (`{"skills": {"mdview": {"accepts": 1, ...}}}`). `build-registry.py` read
  `ledger.get(entry["name"])`, which returned that whole dict, and wrote it into
  `entry["quality"]`. `invoke.quality_of()` then read `q.get("score", 0)` from the
  dict and got 0. The ledger was therefore present on disk and inert: the benchmark
  showed `no_ledger` 0.795 against `full` 0.792, i.e. removing the ledger changed
  nothing.
- Options:
  - Rewrite the ledger into a flat map at write time - the plugin hook owns that file
    and would have to learn a new format.
  - Flatten it in `build-registry.py` only - the weight is then correct but only
    after a registry rebuild, and the registry was 10 days stale.
  - Flatten it where the count becomes a number, and apply it live at query time -
    one formula, used by both the builder and the CLI.
- Chosen: flatten in `load_ledger()` (accept +10, reject -50, partial +2, keyed by
  name and by slug) and apply the same weight live in the CLI before ranking. The
  builder writes it into the registry; the CLI overrides it with the current ledger
  so a fresh score takes effect without a rebuild.
- Evidence: `router learn` prints `aswath-publish-github +30`,
  `superpowers:writing-plans +70`, `some-generic-skill -50`; `router ask` prints the
  ledger weight next to the match score; `router rebuild` now stamps `quality` on
  plugin skills as well as local and marketplace ones.
- Consequence: rejecting a skill now demotes it at the next query, not at the next
  rebuild.

## D9 — One CLI in this repo, installed through a PATH shim
- Date: 2026-11-23
- Prompt: "how to make this full fledget i want it like taste model or skill router like command code i need complete working of ths"
- Context: the router could only be driven as `python <path>/scripts/invoke.py`, and
  that path existed in two copies that had already drifted.
- Options:
  - Install the skill into every harness root - more copies, the same drift.
  - Ship a CLI in this repo and expose it through `~/bin` - one implementation, one
    PATH entry, every harness gets the same command.
  - Rewrite the ranker as a service - no caller needs a daemon.
- Chosen: `bin/router.py` in this repo, exposed as `router` through
  `~/bin/router` and `~/bin/router.cmd`. The CLI imports the shipped ranker from
  `skills/aswath-capability/scripts/invoke.py`, so it cannot drift from it.
- Evidence: `router ask "roast this UI and fix it"` -> `design-taste-frontend`;
  `router ask "write a python script that parses csv"` -> `aswath-csvjson`; the same
  commands work from `cmd.exe` through `router.cmd`.
- Consequence: one command works in every harness, and the ranker stays single-copy.

## D10 — Fetch a skill from the internet, judge it, then mint it as ours
- Date: 2026-11-23
- Prompt: "everything also one more feature find the best skill in the internet and update automaticallyu or if new task is given get new skills(tested with some evals download and load that skill automaticcly for the task and use it then copy that skill and store it under aswath skills(forging) ( not use this lets try this additonaly copying best skills and building something bettert than them for our own custom skills)"
- Context: the catalogue is 3,261 skills and still does not cover everything. The
  user wants a skill found on the internet to be fetched, tested, used for the task
  and then kept as an `aswath-*` skill.
- Options:
  - Install the third-party skill as it is - the catalogue stops being ours and the
    naming, the description rule and the category rule are all broken.
  - Mint it into `aswath-skills` under our conventions, with provenance - the
    catalogue keeps one naming scheme and one rule set, and the origin stays
    recorded.
  - Fetch at request time with no gate - a wrong skill wins the need and is kept.
- Chosen: `router ensure` decides whether the catalogue can answer the need. If the
  request names no capability in full, it searches GitHub for `SKILL.md`, downloads
  the repos, screens the candidates, runs each survivor against the 298-case
  benchmark, and mints the winner into `aswath-skills` as `aswath-<slug>` with a
  `Use when` description, an origin line, a manifest row, a README row and a
  re-run of `install.ps1`.
- Evidence: `router ensure "detect and fix memory leaks in a rust binary"` ->
  no installed skill names the need -> fetched `claude-dev-suite/claude-dev-suite` ->
  `rust-security` won the need and stole 1 of 298 cases (`--allow-steal 1`) ->
  forged to `skills/utilities/aswath-rust-security/SKILL.md` -> `install.ps1` linked
  it into `~/.claude/skills` and `~/.agents/skills` -> `router ask "rust security
  vulnerabilities cargo audit"` now answers `aswath-rust-security`.
- Consequence: the catalogue can grow from the internet without losing its shape.

## D11 — Quote the skill description in the forged frontmatter
- Date: 2026-11-23
- Prompt: same as D10.
- Context: the first forge wrote `description: Use when | Rust security patterns...
  USE WHEN: user works with "Rust"...`. A plain YAML scalar ends at the first `: `,
  so the frontmatter failed to parse and the harness loaded the skill with the
  description `> Origin: github.com/claude-dev-suite/claude-dev-suite. Fetched and
  re-published under the aswath`.
- Options:
  - Strip the colon out of the description - silently edits the author's text.
  - Write the description as a quoted scalar - one line of code, no text lost.
  - Drop descriptions with colons - loses half the good candidates.
- Chosen: quoted scalar, whitespace collapsed to one line.
- Evidence: `skills/utilities/aswath-rust-security/SKILL.md` reads
  `description: "Use when | Rust security patterns..."` and the harness lists the
  skill as `aswath-rust-security: Use when | Rust security patterns for web
  applications. ...`.
- Consequence: a fetched skill loads with the description it was written with.

## D12 — A local embedding layer, used only where the taxonomy says nothing
- Date: 2026-11-24
- Prompt: "lets solve the limit"
- Context: the stated limit is the one the repo's own analysis names: BM25 ties
  the shipped router on exact-skill selection (strict top-1 0.397 both), and
  accuracy rises with token cost. The error analysis behind it: 42 of 45
  failures were requests that never named the capability, so the keyword
  matcher inferred nothing and the router picked whatever was left. 27 of 38
  strict failures were a sibling skill of the right capability winning.
- Options:
  - Train a ranker - the user declined model weights on purpose; the compounding
    lever is the ledger and the taxonomy.
  - Add a semantic layer over the catalogue - the "bolt-on later" step the
    resolution model always allowed, and the one that attacks the named cause.
  - Fix it with better keywords - the taxonomy is already the audited artefact
    and the failures are requests that share no word with it.
- Chosen: a local embedding layer, used in two measured places and no others.
  The provider is the embedding model already sitting in LM Studio
  (`text-embedding-nomic-embed-text-v1.5`), so nothing leaves the machine and no
  key is needed.
- What was measured and rejected, in order:
  - Capability centroids (the mean of a capability's skill vectors) as a semantic
    capability inference: **0.805 -> 0.399 top-1**. A centroid over up to 800
    skills drifts toward the generic direction of the catalogue. "compare the
    top three cloud providers" was nearest to the cost-tokens centroid.
  - Many capabilities voted by the nearest skills: **0.805 -> 0.483**. Twenty
    voted capabilities drown the taxonomy; every skill carrying a common tag
    scores.
  - A distinctive-name anchor ("changelog" in the request must reach
    changelog-generator): **0.805 -> 0.742 top-1**, strict top-1 unchanged. A
    rare name word pulls in wrong skills as often as right ones.
  - A name-only embedding as the strict-skill tie-break: it picks the expected
    skill in 6 of 63 strict cases.
  - What the data says about the strict subset: the expected skill sits at
    **median rank 154** by description similarity, and its nearest sibling
    reaches only 0.76 cosine. The strict subset is not a duplicate-skill
    problem; it is an identifier-resolution problem.
- What was kept, and what it is worth (298 cases, same metrics):
  | profile | capability top-1 | strict top-1 | mean cost |
  |---|---|---|---|
  | keyword only | 0.805 | 0.206 | 2435 |
  | conservative (default) | 0.805 | 0.222 | 2096 |
  | aggressive | 0.795 | 0.254 | 1947 |
  The conservative profile rescues only when the keywords said nothing at all,
  keeps every capability case, lifts the exact-skill rate and cuts mean cost by
  14%. The aggressive profile wins three exact-skill cases and loses three
  capability cases (McNemar on the strict subset: 3-0, p = 0.125), so it is
  opt-in.
- Evidence: `python evals/run_semantic_eval.py` prints both rows and the
  discordant pairs; `router sem status` shows the index (3,015 skills, 79
  capability centroids, 768 dimensions, 12.6 MB packed); `router ask` answers in
  0.3 s with the semantic line showing whether the layer fired.
- Consequence: the shipped ranking in `invoke.py` is unchanged, so the numbers
  the paper quotes still describe it. The semantic layer is additive, measured
  separately, and falls back to the keyword path when the local provider is
  down.

## D13 — Keep the embedding index small and local
- Date: 2026-11-24
- Prompt: "lets solve the limit"
- Context: the first index stored 3,065 vectors of 768 floats as JSON floats:
  101 MB, and parsing it took a second on every call.
- Options:
  - Load it once per process and cache it - still 101 MB on disk and a second
    per process.
  - Pack the vectors as base64 float32 - 12.6 MB, and a fraction of the parse.
- Chosen: base64 float32, and the parsed cache is memoised on the file's mtime.
- Evidence: `embed.py build` writes 12.6 MB; `embed.py status` loads it in
  0.96 s cold and 0.000 s warm; `router ask` answers in 0.31 s.
- Consequence: the index is cheap enough to keep on disk and use on every
  request.

## D14 — Precedent routing: the hook records the pairing, the router uses it
- Date: 2026-11-24
- Prompt: "solv eit fully >?"
- Context: the last wall on the strict subset is not a matching problem. On
  this machine 25 of the 63 strict expectations are for skills that are not
  installed at all, so the ceiling is 0.603. Of the 38 that are installed, the
  keyword router picks the right one in 13 cases, the semantic one in 12, and
  the union of the two is 14 - the signals agree on the same cases, so no
  combination of them can go further. The failures are sibling choices
  between interchangeable skills, and only history says which twin the user
  means.
- Options:
  - Keep tuning the matcher - the semantic-lead path was measured and left
    strict top-1 unchanged while costing capability top-1 0.805 -> 0.779.
  - Prefer local over marketplace, or plugin over marketplace - there is no
    bias to exploit: the expected skill is local in 33 of the 38 installed
    cases and the chosen one is local in 30.
  - Record the pairing the hook already sees - the hook had the request text
    and the loaded skill and was writing down neither.
- Chosen: the hook now writes a `load` row carrying the request and the skill;
  `scripts/precedent.py` reads those rows; the router gives the skill that was
  used before a bonus of 8, and re-inserts it if the matcher dropped it
  entirely. A load is precedent, not an outcome: it never touches the ledger
  score, so it cannot inflate a skill that has not proven itself.
- Evidence: `router ask "bump the version and publish the release notes for the
  plugin"` -> `version-bump`, with `precedent: version-bump (used before, match
  1.00)`; `router precedent` lists the pairs; the simulated hook run writes one
  `load` row and the store reads it back; `pytest tests` -> 58 passed.
- Consequence: the part of the limit that can be solved is solved, and it is
  the part the benchmark cannot see, because the benchmark has no history. It
  works on the requests this machine has actually been asked.

## D15 — One ranking path for every command, and a load is never an outcome
- Date: 2026-11-24
- Prompt: "push everything solve everything and push"
- Context: two loose ends found while finishing. First, `ask`, `why` and
  `ensure` each ranked on their own path, so the router could explain one
  answer and give another. Second, the hook's new `load` row went through the
  same writer as the accepts, which counted it as a partial outcome - so a
  skill that was merely loaded moved its ledger score by +2, and the decision
  log said it must not.
- Options:
  - Fix the routing in each command - three copies of the same sequence, and
    the same drift again.
  - One shared ranking function, and a flag on the writer that says whether an
    event counts.
- Chosen: `rank_all()` in the CLI, used by `ask`, `why` and `ensure`, and
  `observe(..., count=False)` for the load row. The hook's rule is now tested:
  a load writes the request and the skill, and leaves the ledger score at zero.
- Evidence: `router ask`, `router why version-bump` and `router ensure` now
  return the same skill for the same request; `pytest tests` -> 62 passed,
  including three new hook tests for the load/accept/reject rules.
- Consequence: the CLI has one ranking path, and precedent can never inflate a
  skill's quality score. The plugin moves to 0.1.4 because the shared hook file
  changed after 0.1.3 was published.

## D16 — The name anchor, tried twice and refused both times
- Date: 2026-11-24
- Prompt: "push everything solve everything and push"
- Context: a real case showed the router's remaining weakness plainly.
  "bump the version and publish the release notes for the plugin" answers
  `release`, not `version-bump`: the taxonomy inferred one capability
  (`deployment`), `version-bump` carries none of it, and the capability layer
  decided before the name was read. The obvious fix is to let a rare word in
  the request that appears in a skill's name promote that skill.
- What was tried:
  - **Anchor applied to every skill** (the first attempt, in the ranker
    itself): capability top-1 0.805 -> **0.742**, strict top-1 unchanged at
    0.206. A rare name word pulls in wrong skills as often as right ones.
  - **Anchor applied only to the skills the taxonomy ignored** (capability
    overlap zero), which cannot outvote the taxonomy and can only rescue a
    skill it dropped: capability top-1 0.805 -> **0.711**, strict 0.206 ->
    0.190. Worse, and for the same reason: a skill the taxonomy ignored is
    usually ignored for a reason.
- Options:
  - Keep the anchor and accept the loss - the capability layer is the
    strongest signal in the system, and both measurements say the anchor is
    not merely redundant but actively wrong.
  - Let history decide instead - the precedent store records which skill was
    used for a request like this one, and the router prefers it. It needs one
    real use, not a guess about the words.
- Chosen: no anchor. The second attempt was reverted; `semantic.py` carries
  no anchor code. The case is left to precedent, which is the mechanism that
  was measured to work on exactly this kind of question.
- Evidence: both measurements are reproduced by the same harness over the
  298 cases; after the revert `evals/run_semantic_eval.py` reports capability
  top-1 0.805, strict 0.222, mean cost 2096, unchanged.
- Consequence: the router keeps asking the same question and answering it
  with the taxonomy. Where the taxonomy is wrong, the ledger and the
  precedent store correct it over time, and a rejected skill stops being
  offered.

## D17 — Install the eight missing skills from their source repositories, not from the crawler registry
- Date: 2026-11-24
- Prompt: "yes" (to installing third-party plugins, which would lift the measurable ceiling)
- Context: 25 of the 63 strict expectations named skills that were not installed
  here, so the ceiling was 0.603. The biggest source, `majiayu000/claude-skill-registry`,
  turned out to hold 312,160 `SKILL.md` files, and the copies under it are
  *pointers*, not skills: "This pointer keeps old links working. It is not an
  installable skill."
- Options:
  - Install the registry wholesale - 312,000 skills, most of them pointers and
    duplicates, against a catalogue of 114. It is a crawler index, not a
    library.
  - Install the eight that fill a real gap, from the repositories that
    actually wrote them, and leave the rest.
  - Install nothing and report the ceiling - the skills are useful to the owner
    whatever the benchmark says.
- Chosen: install the eight from their source repositories, each with a real
  frontmatter and no scripts:
  | skill | source |
  |---|---|
  | `fix-ci` | `Asymmetric-al/core` |
  | `fix-merge-conflicts` | `Asymmetric-al/core` |
  | `loop-on-ci` | `Asymmetric-al/core` |
  | `deslop` | `Asymmetric-al/core` |
  | `improve-animations` | `Asymmetric-al/core` |
  | `handoff-doc` | `MiniMax-AI/mcode-stack` |
  | `long-command-check` | `MiniMax-AI/mcode-stack` |
  | `long-session-check` | `MiniMax-AI/mcode-stack` |
- Evidence: capability top-1 0.805 -> **0.815**, strict top-1 0.206 -> **0.270**
  (0.286 with the semantic layer), mean cost 2435 -> 2052. The exact benchmark
  request "find the failing checks on this pr and fix them" now answers
  `fix-ci`, and the semantic layer rescued the `ci-delivery` capability to do it.
- Consequence: the strict ceiling here is now 46/63 = 0.730. The remaining 17
  missing skills are pointer-only in the crawler registry, and the local plugin
  catalogue cache is empty, so they are not obtainable from here.

## D18 — Park on evidence, not on a list
- Date: 2026-11-24
- Prompt: "yes" (to applying the catalogue parking)
- Context: the aggressive keep set from the repo was written for a machine
  with 1,387 visible skills. This machine has 114, of which most are in daily
  use. Parking 68 would have broken the owner's own workflow for a token
  saving the harness does not even charge in full.
- Options:
  - Apply the aggressive list anyway - it is the documented rule, and it is
    wrong here.
  - Keep nothing and park nothing - the token cost stays.
  - Keep by evidence: the skills the owner has used (the ledger and the
    observation log), the harness-critical families, our own `aswath-*` set,
    and the eight freshly fetched ones. Park the rest.
- Chosen: the evidence-based keep set. `bin/park-skills.py` now reads the
  ledger and the observation log and never parks a skill the owner has used;
  `DAILY_KEEP` and `FETCHED_KEEP` hold the families that are not in evidence
  yet.
- Evidence: the dry run listed 6 candidates - five `openspec-*` skills and one
  duplicate. The openspec set was added to the keep list because it is one
  workflow used together, and the duplicate `minimax-compaction-handoff`
  (ours is `aswath-minimax-compaction-handoff`) was parked. One directory
  moved, from 114 to 113.
- Consequence: the catalogue stays usable, the duplicate is gone, and the rule
  is now evidence-based, so it gets sharper as the ledger grows.

## D17 — The published skill's resolver now uses this repo's ranking
- Date: 2026-11-24
- Prompt: "do we need to do more or how to use the router"
- Context: the router CLI and the published `aswath-capability` skill ranked
  the same request differently, because the skill's `query-registry.py` carried
  its own scorer. Everything this repo measured — the semantic layer, the
  precedent, the ledger weight — only applied to the command. The agent's own
  routing was the one place it did not reach.
- Options:
  - Leave the skill alone - the command is the tool, the skill is legacy.
  - Make the skill's resolver call this repo's modules - one ranking path for
    both the command and the agent.
  - Port the measurements into the skill - two implementations to keep in
    step forever.
- Chosen: the skill's resolver imports `semantic.py` and `precedent.py` from
  its own directory and uses them when they are present, falling back to its
  local scorer when the embedding index is not there. The change was made in
  the published repo and mirrored here, so the two copies stay identical and
  the sync test holds.
- Evidence: `query-registry.py need "find the failing checks on this pr and
  fix them"` prints `semantic layer: on (rescued ci-delivery)` and answers
  `fix-ci` first; `pytest tests` -> 62 passed, the sync test included.
- Consequence: the numbers this repo measures are now the numbers the agent
  actually routes with.

## D18 — The steering hook: the router's answer on every prompt
- Date: 2026-11-24
- Prompt: "ok let me use and try is this automatically enable in my claude coee to use"
- Context: the learning loop was automatic - every prompt, skill load, edit and
  delete was being recorded - but the *routing* was not. Claude Code injects
  the whole catalogue and picks a skill by its own judgement, and the router's
  answer sat unused unless someone called it. The router knows more than that
  judgement does: the taxonomy, the ledger, the semantic index, and what was
  used last time.
- Options:
  - Leave it as a command - the router is available but never consulted
    unless asked, which is most of the value left on the table.
  - A UserPromptSubmit hook that runs the router and injects its answer -
    every request arrives with the recommendation attached.
  - A hook that always injects - predictable, but it puts a line in the
    context for prompts that need no skill at all.
- Chosen: `bin/router-steer.py` as a UserPromptSubmit hook, and it says
  nothing unless it has something: a named capability, a precedent, or a
  clear lead. One or two lines, never blocking the prompt, never failing the
  session. `router hook install` writes the settings entry, `router hook
  uninstall` removes it, and the settings file is backed up first.
- Also chosen: the command is an absolute path, not `%USERPROFILE%`. The hook
  runs in whatever shell the harness picks, and only an absolute path is the
  same in all of them.
- Evidence: `echo '{"hook_event_name":"UserPromptSubmit","prompt":"find the
  failing checks on this pr and fix them"}' | python bin/router-steer.py` ->
  `Skill router: fix-ci [ci-delivery]. Next: loop-on-ci.` The same command
  with the CSV prompt -> `Skill router: gws-sheets [data]. Next:
  aswath-csvjson.` `router hook status` -> installed; `settings.json` parses
  and carries the entry.
- Consequence: the router now steers, and the request still works if the
  hook is silent.
- Note: the user was asked about starting LM Studio at logon and said no, so
  it was not added. The semantic layer falls back to the keyword path when
  the provider is not running, and says so.
