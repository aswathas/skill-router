# Prompt record

The prompts that shaped this work, in order. `aswath-chronicle` is not running for this
repo, so the record is written by hand here.

## 2026-11-17 — router install
- Prompt: "intall our aswath router?"
- Decision it produced: D1 (install through a local marketplace, not a file copy), D3
  (case-insensitive tool names), D4 (both matcher spellings), D5 (version bump).
- Work it caused: the plugin was installed and enabled in Claude Code; the manifest was
  written in Claude shape; the hook was patched so a Claude-shaped payload registers a
  skill load. Files touched outside this repo: `~/.claude/settings.json`,
  `~/.claude/plugins/aswath-skill-router/.claude-plugin/plugin.json`,
  `~/.claude/plugins/aswath-skill-router/.claude-plugin/marketplace.json`, and the
  installed copy under `~/.claude/plugins/cache/`.

## 2026-11-17 — router push
- Prompt: "yes push"
- Decision it produced: D2 (ship the Claude manifests in this repo), D4, D5.
- Work it caused: this branch. Added `.claude-plugin/marketplace.json` and
  `plugins/aswath-skill-router/.claude-plugin/plugin.json`, widened the matcher, made
  the tool comparison case-insensitive, bumped both manifests to 0.1.1, and wrote the
  decision log, change inventory, prompt record and build log.

## 2026-11-17 — unrelated session change, recorded for completeness
- Prompt: "make caveman , as hook for always"
- Decision it produced: none in this repo. The caveman voice hook was registered in
  `~/.claude/settings.json` and the shared state file reset to `ultra`.
- Work it caused: `~/.claude/settings.json`, `~/.minimax/caveman-state.txt`,
  `~/.minimax/HOOKS-README.md`. No file in this repo was touched by that work.

## 2026-11-18 — Claude Code hook failure
- Prompt: "Failed with non-blocking status code: sh: /scripts/learning-hook.sh: No such file or directory ," and then "solve this"
- Decision it produced: D7 (resolve the plugin root at runtime from `CLAUDE_PLUGIN_ROOT`, falling
  back to `PLUGIN_ROOT`, instead of hard-coding `${PLUGIN_ROOT}` in the shared hook file).
- Work it caused: the `command` field of both hooks in
  `plugins/aswath-skill-router/hooks/hooks.json`, both manifests and the marketplace entry bumped
  to 0.1.2, and the records below. The same fix was mirrored into the installed copies on this
  machine (`~/.claude/plugins/cache/aswath-skill-router/aswath-skill-router/0.1.1`,
  `.../0.1.0` and `~/.minimax/plugins/aswath-skill-router`) so the error stops here and now,
  while the upstream fix travels by pull request.

## 2026-11-23 — the router as a complete command
- Prompt: "install enders game book" (unrelated; the book was fetched through the
  bookfetch MCP and converted with Calibre).
- Prompt: "https://github.com/aswathas/skill-router intall this bro?" - answered by
  checking the installed plugins: `aswath-skill-router@aswath-skill-router` version
  0.1.2 was already installed and enabled, with the marketplace refreshed and the
  upstream manifest still at 0.1.2. No install was needed.
- Prompt: "how should or hwo will the skill router used is it working" - produced the
  finding that the ledger was inert (D8).
- Prompt: "how to make this full fledget i want it like taste model or skill router like
  command code i need complete working of ths" - produced the CLI decision (D9), the
  scope decision to include catalogue parking, and the fetch-and-forge feature (D10).
- Prompt: "everything also one more feature find the best skill in the internet and
  update automaticallyu or if new task is given get new skills(tested with some evals
  download and load that skill automaticcly for the task and use it then copy that skill
  and store it under aswath skills(forging) ( not use this lets try this additonaly
  copying best skills and building something bettert than them for our own custom
  skills)" - produced D10 and D11.
- Work it caused: `bin/router.py`, `bin/park-skills.py`, the ledger fix in
  `skills/aswath-capability/scripts/build-registry.py`, `evals/run_eval.py`,
  `tests/test_cli.py`, the shims in `~/bin`, and the records below. The forged skill
  landed in the separate `aswath-skills` repo
  (`skills/utilities/aswath-rust-security/`), with its manifest and README rows.

## 2026-11-24 — solving the strict top-1 limit
- Prompt: "lets solve the limit", after the router was pushed, merged and
  explained. The limit is the one the repo's own analysis names: BM25 ties the
  shipped router on exact-skill selection, and accuracy rises with token cost.
- Decision it produced: D12 (a local embedding layer, used only where the
  taxonomy says nothing, with the failed variants recorded) and D13 (a packed,
  memoised index).
- Work it caused: `skills/aswath-capability/scripts/embed.py`,
  `skills/aswath-capability/scripts/semantic.py`,
  `evals/run_semantic_eval.py`, `evals/exp_semantic.py`, `evals/exp_grid.py`,
  `tests/test_semantic.py`, the `router sem` commands, and the records above.

## 2026-11-24 — solving the strict limit with precedent
- Prompt: "solv eit fully >?"
- Decision it produced: D14 (the hook records the request/skill pairing, the
  router uses it) and D3 in the aswath-skills repo.
- Work it caused: the `load` observation in the learning hook, the three
  version bumps, `scripts/precedent.py`, the precedent in `router ask`, the
  `router precedent` command, `tests/test_precedent.py`, and the records above.

## 2026-11-24 — finishing, and the two loose ends it exposed
- Prompt: "push everything solve everything and push"
- Decision it produced: D15 (one ranking path for ask/why/ensure; a load never
  counts as an outcome) and the plugin version bump to 0.1.4.
- Work it caused: `rank_all()` in `bin/router.py`, `observe(..., count=False)`
  in the learning hook, `tests/test_learning_hook.py`, `tests/test_sync.py`, the
  version bumps in the three manifests, and the records above.

## 2026-11-24 — the name anchor, refused
- Prompt: "push everything solve everything and push"
- Decision it produced: D16 (no name anchor; precedent handles the case).
- Work it caused: the two measurements, and the revert of
  `skills/aswath-capability/scripts/semantic.py`. Net file change: none.
