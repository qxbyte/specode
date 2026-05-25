# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A single-plugin marketplace for **specode** — a specification-driven workflow plugin for Claude Code and CodeBuddy CLIs. The plugin walks a host agent through a fixed phase pipeline (requirements → design → tasks → implementation → acceptance) using five Markdown documents as the single source of truth, with advisory hooks and `AskUserQuestion` selectors at phase gates.

All implementation lives under `plugins/specode/`. The repo root only contains the marketplace manifest (`.claude-plugin/marketplace.json`), the README, the CHANGELOG, and CONTRIBUTING. Plugin internals are listed in README §Architecture — do not re-derive the file tree, read the README.

## Commands

```sh
# Run the test suite (must be from repo root; tests are hermetic and redirect $HOME)
python3 -m pytest plugins/specode/tests/ -v

# Single test file
python3 -m pytest plugins/specode/tests/test_spec_session_business.py -v

# Single test
python3 -m pytest plugins/specode/tests/test_spec_session_hooks.py::test_on_user_prompt_injects_status_footer -v

# Local plugin install (development)
claude    --plugin-dir ./plugins/specode
codebuddy --plugin-dir ./plugins/specode
```

There is no lint or typecheck step configured at the repo level. Lint logic the plugin itself ships (`spec_lint.py`) is for the user's spec docs, not this codebase.

## Non-negotiable conventions

These are the rules from `CONTRIBUTING.md` that are easy to violate and expensive to fix. Read CONTRIBUTING.md in full before opening a PR.

### Runtime is stdlib-only
Code under `plugins/specode/scripts/` MUST use only the Python 3.8+ standard library. Plugin users install via host CLI `plugin install`; they do not `pip install`. Tests under `plugins/specode/tests/` MAY use `pytest` (dev dependency only).

### CLI invocation must go through `run.sh`
Every script under `plugins/specode/scripts/` is a CLI invoked from hooks or directly by the host agent via the `run.sh` wrapper with the absolute `$CLAUDE_PLUGIN_ROOT` (fallback `$CODEBUDDY_PLUGIN_ROOT`) path:

```sh
sh "${CLAUDE_PLUGIN_ROOT:-${CODEBUDDY_PLUGIN_ROOT}}/scripts/run.sh" \
   "${CLAUDE_PLUGIN_ROOT:-${CODEBUDDY_PLUGIN_ROOT}}/scripts/<name>.py" \
   <verb> <args...>
```

`run.sh` probes `python3 → python → py` (with Windows Store alias-stub skipping) so the script works on any host with Python 3.8+. Bare `python3 <name>.py` calls fail in most cwds — when adding a new entry point, match the wrapper template used everywhere in `hooks/hooks.json` and `commands/*.md`.

### Hook safety contract
Hooks in `spec_session.py` are advisory. Every handler MUST:
1. Be wrapped in `@_safe_hook` (catches all exceptions, returns 0).
2. **Never `exit 2`** — push guidance via `additionalContext` JSON to stdout and still `exit 0`. The one exception is `hook_on_pre_tool_use` for direct edits to `tasks.md`, which escalated to a hard block in 0.10.21 (see CHANGELOG); do not add other exit-2 paths without explicit need.
3. Honour `SPECODE_GUARD=off` for global bypass (early-return with no output and no state writes).
4. Tolerate non-TTY stdin (`_read_stdin_payload()` handles this).

Performance budgets (CONTRIBUTING §Performance budget): `UserPromptSubmit` <80ms (fires every user turn), `PreToolUse`/`PostToolUse Task` <100ms, `Stop` <300ms, `SessionStart`/`SessionEnd` <500ms.

### On-disk schema evolution
Two schemas the plugin owns:
- `~/.specode/sessions/<session_id>.json` — per-host-session state
- `<spec-dir>/.config.json` — per-spec config + lock holder

Rules:
- New writes use neutral names (`session_id`, not `claude_session_id`; `holder`, not host-specific names).
- Read sites MUST fall back through historical names. Auto-migrate on read so the next write lands the new key transparently — see `read_session()` and `StateMachine.load()` for the existing pattern, and `test_read_session_migrates_legacy_claude_session_id` / `test_load_migrates_legacy_claude_session_id` as test templates.
- Bump minor for renames with a read-side fallback; bump major if a rename breaks reads.
- All state writes use `tempfile + os.replace + fsync` (see `_atomic_write_json` in `_ss_io.py`). If one side of the dual write (sessions file + spec config) fails, roll back and exit 1 — never leave in-memory half-success.

### Test conventions
- Scripts are CLIs, not importable modules. Tests invoke them via `subprocess.run` through the `run_script` fixture in `tests/conftest.py`.
- Use the `fake_home` fixture to redirect `$HOME`, `XDG_CONFIG_HOME`, `APPDATA`, `LOCALAPPDATA`, and clear `SPECODE_ROOT` / `SPECODE_GUARD`. Tests MUST be hermetic — never touch the real `~/.specode/`.
- Use `init_spec` fixture to scaffold a spec directory the way `spec_init.py` would.
- Every persisted-schema change needs a "legacy file migration" regression test.

## Architecture — the parts that span multiple files

### `spec_session.py` internal layout
`spec_session.py` itself is a 231-line thin entry: argparse + `COMMANDS` dispatch + main. The implementation is split across sibling modules in the same `scripts/` directory:

| File | Responsibility |
|---|---|
| `_ss_io.py` | Atomic write helpers, session/spec config IO, lock utils (`_is_lock_stale` / `_session_short`), shared constants (`VALID_PHASES`, `STALE_LOCK_SECONDS`) |
| `_ss_selectors.py` | `SELECTOR_PROMPTS` dict + `_fill_selector`. `test_selectors_drift.py` parses this file by regex — keep the `SELECTOR_PROMPTS: dict[str, str] = {...}` literal grep-able. |
| `_ss_reminders.py` | Reminder template strings (status footer, doc-priority, code-doc sync, mode reminders) + help text rendering |
| `_ss_business.py` | All `cmd_*` business commands + `_update_session_for_spec` + `_auto_pending_selector` |
| `_ss_hooks.py` | All `hook_on_*` handlers + `_safe_hook` decorator + task-swarm plan reminder helpers + fast-path regex constants |
| `_ss_catalog.py` | B2 `on-user-prompt-catalog` hook: keyword-triggered reference catalog (description-as-trigger) |

`spec_session.py` filename is preserved because `hooks.json`, every `commands/*.md`, and `tests/conftest.py:run_script` reference it by name. It also re-exports `read_session`, `read_spec_config`, `_session_short`, `_is_lock_stale` for `spec_status.py:25`. **Do not rename `spec_session.py` and do not delete those re-exports.**

### Hook → CLI → state-file flow
1. Host CLI fires a hook event (`SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse Task`, `Stop`, `SessionEnd`) per `hooks/hooks.json`.
2. The hook command shells into `run.sh` → `spec_session.py <hook-subcommand>`, which reads the JSON payload from stdin.
3. Handlers (wrapped in `@_safe_hook` from `_ss_hooks.py`) read `~/.specode/sessions/<session_id>.json` and the active spec's `.config.json`, then emit `additionalContext` JSON to stdout to inject guidance (status footer, selector reminder, doc-sync nag, B2 catalog hits) into the next agent turn.
4. The host agent, following `skills/specode/SKILL.md`, responds to the injection by calling `AskUserQuestion` for selectors or by invoking a `spec_session.py` business subcommand (`acquire` / `phase-transition` / etc.) which atomically updates both state files.

### Session as the integration boundary
Everything is keyed by the host's `session_id` (injected by `SessionStart`, re-injected every `UserPromptSubmit`). Multiple terminal windows = multiple session files = multiple parallel specs. Lock holder is the `session_id`; stale-lock window is 30 minutes (`STALE_LOCK_SECONDS` in `_ss_io.py`). The agent MUST NOT invent a session_id, MUST NOT parse one from user input, MUST NOT echo full IDs in chat (8-char prefix only).

### Document root resolution
Three-tier with no fallback (`spec_vault.py`):
1. `--root` flag or `SPECODE_ROOT` env (highest)
2. `~/.config/specode/config.json.obsidianRoot`
3. Auto-detected Obsidian vault → `<vault>/spec-in/<os>-<user>/specs`

If all three miss, `spec_init.py` exits 3 with a setup hint. Do NOT add a cwd or `~/specs` fallback. The `--detect-vault` / `--vault-status` / `--set-vault` / `--set-root` / `--sync-status` flags are routed in `commands/spec.md`; some of them are "fast-path" hooks where the hook pre-renders the output and the agent only prints it verbatim (see `FAST_PATH_HELP` / `FAST_PATH_VAULT` constants in `_ss_hooks.py`).

### Phase pipeline + selectors
Valid phases (`VALID_PHASES` in `_ss_io.py`): `intake → requirements/bugfix → design → tasks → implementation → acceptance → iteration`. Transitions go through `spec_session.py phase-transition`, which also sets `pending_selector` so the next hook turn knows which `AskUserQuestion` skeleton to remind about. The 7 fixed selector scenarios are defined in `SELECTOR_PROMPTS` (in `_ss_selectors.py`) and documented in `skills/specode/references/selectors.md`; `tests/test_selector_prompts.py` snapshots them, and `tests/test_selectors_drift.py` guards against drift between the constants and the references doc.

### Reference catalog (description-as-trigger)
Every `skills/specode/references/*.md` file carries a YAML frontmatter `description: Use when …` that captures *when* a reader should pick it up (superpowers style — trigger-first, not summary-first). The `on-user-prompt-catalog` hook (`_ss_catalog.py`) maintains a `CATALOG` dict of keyword regex → reference key (e.g. `lock|takeover|接管` → `lock-protocol`, `task-swarm|@writes|reviewer` → `task-swarm`); each `UserPromptSubmit` it scans the prompt, lists hit references with their descriptions, and emits an advisory injection. Active-only (silent for `idle`/`readonly`/`ended`). `tests/test_catalog.py` enforces: every `CATALOG` key has a real reference file, every targeted reference has a non-empty `description` field. When adding a new reference or extending keyword coverage, update both the frontmatter and `CATALOG`.

### task-swarm orchestration
`task_swarm.py` is a separate state machine for the implementation phase. The state file is the single source of truth (`<spec-dir>/.task-swarm/runs/<run_id>/state.json`). The flow is `init → plan → fork (N coders) → advance → writeback → resolve`, with reviewer (advisory, one round of P0 fixes if findings carry evidence tags) and validator (blocking pass/fail loop, deadloop guard after 3 identical failures). The four subagent role definitions live in `agents/task-swarm-{coder,planner,reviewer,validator}.md`; they are intentionally tool-restricted (reviewer/validator have no Edit/Write — physical isolation). Supporting modules:
- `task_swarm_state.py` — state machine load/save with legacy migration
- `task_swarm_parse_md.py` — parses `tasks.md` `## 阶段 N:` sections + `@writes` / `@depends-on` tags
- `task_swarm_outbox.py` — parses subagent `result.md` / `review.md` / `validation.md` per the schemas in `references/task-swarm.md` §4
- `task_swarm_writeback.py` — line-safe diff back into `tasks.md` (exits 1 on out-of-bounds; see 0.10.21 CHANGELOG entry for the multi-line `reproduce_cmd` bug)
- `task_swarm_prompt.py` — materializes per-agent prompts into `agents/<key>/prompt.md`

### Session logging
`spec_log.py` writes append-only JSONL events to `~/.specode/logs/<session_id>.jsonl` (hook fires, tool calls, CLI invocations, phase/lock changes). Default redaction of secret-like keys (`password`, `api_key`, `token`, `secret`, `authorization`, `cookie`) and 500-char string truncation. Disable with `SPECODE_LOG=off` or `~/.config/specode/config.json.logging=false`. Any logging exception is swallowed — logging never blocks business flow. When adding a new hook or CLI subcommand, call `_log_event("event_name", payload, session_id)` at the entry point to keep replay useful.

## Release procedure (summary)

Detailed steps are in CONTRIBUTING.md §Release. The two manifests carrying `version` MUST match or the plugin tag tooling refuses:
- `plugins/specode/.claude-plugin/plugin.json` → `"version"`
- `.claude-plugin/marketplace.json` → `plugins[0].version`

Workflow: bump both manifests → rename `## Unreleased` in CHANGELOG to `## X.Y.Z (YYYY-MM-DD)` + add a fresh `## Unreleased` above → run tests → commit + push → `claude plugin tag --dry-run plugins/specode` → `claude plugin tag plugins/specode --push`. Tag format is `specode--v{version}` (annotated). **Pushing the tag IS the release** — there is no tarball or registry artifact; host CLIs fetch the marketplace manifest from GitHub by git tag.

Semver "API surface" for this plugin = slash command set, agent names, hook event names, and persisted-state schema fields. Field renames with a read-side fallback are minor; without fallback are major.

## Where to look for what

- **README.md** — what the plugin does, install/usage, architecture map.
- **CONTRIBUTING.md** — the full version of the conventions summarised above (stdlib rule, CLI wrapper contract, hook safety, schema evolution, performance budgets, release).
- **CHANGELOG.md** — narrative history; useful when a behavior seems weird because it documents past bugs and the reasoning behind subtle fixes (e.g. 0.10.21 writeback line-safe, 0.10.13 / 0.10.17 task-swarm STATUS recovery).
- **plugins/specode/skills/specode/SKILL.md** + **references/** — the runtime behavior spec the *host agent* follows. When modifying selectors, phase order, or the lock protocol, the SKILL.md and the corresponding `references/<topic>.md` need to stay in sync with the CLI behavior; selector drift is enforced by `tests/test_selectors_drift.py`.
