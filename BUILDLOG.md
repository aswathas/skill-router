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

