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

