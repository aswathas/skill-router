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
