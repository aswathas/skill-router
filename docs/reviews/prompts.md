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
