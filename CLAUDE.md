# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A two-plugin marketplace for Claude Code and CodeBuddy CLIs:

- **specode** (`plugins/specode/`) — a specification-driven workflow plugin. It walks a host agent through a fixed phase pipeline (requirements → design → tasks → implementation → acceptance) using five Markdown documents as the single source of truth, with advisory hooks and `AskUserQuestion` selectors at phase gates. **This is the plugin this `CLAUDE.md` documents** unless stated otherwise.
- **task-swarm** (`plugins/task-swarm/`) — a standalone implementation-phase orchestrator (multi-coder fork + reviewer/validator state machine) extracted out of specode in milestone M1. It has its own CLI, state machine, agents, and concerns; it should eventually get its own `CLAUDE.md`. specode currently hands off to it only manually (see the `tasks-execution` selector and the "task-swarm" pointer under Architecture below) — automatic delegation is a later milestone.

Most implementation referenced here lives under `plugins/specode/`. The repo root only contains the marketplace manifest (`.claude-plugin/marketplace.json`, which now lists **both** plugins), the README, the CHANGELOG, and CONTRIBUTING. Plugin internals are listed in README §Architecture — do not re-derive the file tree, read the README.

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

Performance budgets (CONTRIBUTING §Performance budget): `UserPromptSubmit` <80ms (fires every user turn), `PreToolUse`/`PostToolUse` <100ms, `Stop` <300ms, `SessionStart`/`SessionEnd` <500ms.

### On-disk schema evolution
Two schemas the plugin owns:
- `~/.specode/sessions/<session_id>.json` — per-host-session state
- `<spec-dir>/.config.json` — per-spec config + lock holder

Rules:
- New writes use neutral names (`session_id`, not `claude_session_id`; `holder`, not host-specific names).
- Read sites MUST fall back through historical names. Auto-migrate on read so the next write lands the new key transparently — see `read_session()` and `StateMachine.load()` for the existing pattern, and `test_read_session_migrates_legacy_claude_session_id` / `test_load_migrates_legacy_claude_session_id` as test templates.
- Bump minor for renames with a read-side fallback; bump major if a rename breaks reads.
- All state writes use `tempfile + os.replace + fsync` (see `_atomic_write_json` in `spec_session/_io.py`). If one side of the dual write (sessions file + spec config) fails, roll back and exit 1 — never leave in-memory half-success.

### Test conventions
- Scripts are CLIs, not importable modules. Tests invoke them via `subprocess.run` through the `run_script` fixture in `tests/conftest.py`.
- Use the `fake_home` fixture to redirect `$HOME`, `XDG_CONFIG_HOME`, `APPDATA`, `LOCALAPPDATA`, and clear `SPECODE_ROOT` / `SPECODE_GUARD`. Tests MUST be hermetic — never touch the real `~/.specode/`.
- Use `init_spec` fixture to scaffold a spec directory the way `spec_init.py` would.
- Every persisted-schema change needs a "legacy file migration" regression test.

### Templates describe structure, not behavior
`assets/templates/*.md` are the *output* of the workflow — the host agent reads them only *after* deciding what to write. So **never put behavioral constraints (rules, "必须", gating checks) into templates**: they get stamped into every spec on disk, dilute the signal, and have zero authority over the agent's pre-write decisions.

Behavioral constraints belong in places the agent reads *before* it generates content:
- `skills/specode/SKILL.md` (always-loaded persona/rules)
- `commands/*.md` (loaded when the user invokes the command)
- `spec_session/_selectors.py SELECTOR_PROMPTS` (injected at phase gates)
- Hook `additionalContext` injections (`spec_session/_hooks.py`, `_catalog.py`)

`spec_init.py:FALLBACK_TEMPLATES` is the in-code emergency skeleton if `assets/templates/*.md` fails to load — keep it minimal (titles, metadata block, lint-required anchors like `### 需求 1`), not a full v3 mirror. See 0.10.23 / 0.10.24 CHANGELOG for the principle in context.

## Architecture — the parts that span multiple files

### scripts/ layout
The one heavyweight CLI in specode (`spec_session.py`) is a subdirectory package with a thin same-name launcher at the `scripts/` root. Python's FileFinder gives package precedence over module within a path entry, and the launcher is exec'd (not imported), so `spec_session.py` (launcher) and `spec_session/` (package) coexist safely. The launcher injects `scripts/` into `sys.path` and calls `<pkg>.cli.main()`. (task-swarm used to ship a parallel `task_swarm.py` launcher + `task_swarm/` package here; both moved to the standalone `plugins/task-swarm/` plugin in M1 — see the "task-swarm" pointer below.)

| `scripts/` member | Role |
|---|---|
| `spec_session.py` | Thin launcher (~40 lines: utf-8 stdout reconfigure + sys.path + `from spec_session.cli import main`). Filename preserved because `hooks.json`, every `commands/*.md`, and `tests/conftest.py:run_script` reference it by name. |
| `spec_session/` package | `__init__.py` (re-exports `read_session` / `read_spec_config` / `_session_short` / `_is_lock_stale` for `spec_status.py:25`), `cli.py` (argparse + `COMMANDS` dispatch + main), `_io.py`, `_selectors.py`, `_reminders.py`, `_business.py`, `_hooks.py`, `_catalog.py` |
| `spec_init.py` / `spec_lint.py` / `spec_log.py` / `spec_status.py` / `spec_vault.py` | Single-file CLIs at the top level. `spec_log.py` is also shared (defensively imported by several `spec_session/` modules for session logging). |
| `run.sh` / `run.cmd` | Python interpreter probes (`python3 → python → py`) — Windows alias-stub handling lives here. |

**Do not rename** `spec_session.py` (that filename is the API surface). **Do not delete** `spec_session/__init__.py` re-exports (spec_status.py depends on them). Inside the package, intra-package imports are absolute (`from spec_session._io import …`) for clear error messages.

### `_THIS_DIR` convention inside the package
Modules under `spec_session/` that need to find sibling top-level scripts or the plugin manifest (e.g. `_catalog.py` locating `skills/specode/references/`, `_reminders.py` reading `.claude-plugin/plugin.json`) define `_THIS_DIR = Path(__file__).resolve().parents[1]` — that resolves to `scripts/`, keeping `_THIS_DIR.parent / ".claude-plugin"` semantically identical to the pre-split layout. Don't use `parents[0]` (it points inside the package).

### Hook → CLI → state-file flow
1. Host CLI fires a hook event (`SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `Stop`, `SessionEnd`) per `hooks/hooks.json`.
2. The hook command shells into `run.sh` → `spec_session.py <hook-subcommand>` (the launcher), which imports `spec_session.cli.main` and dispatches the hook subcommand handler.
3. Handlers (wrapped in `@_safe_hook` from `spec_session/_hooks.py`) read `~/.specode/sessions/<session_id>.json` and the active spec's `.config.json`, then emit `additionalContext` JSON to stdout to inject guidance (status footer, selector reminder, doc-sync nag, B2 catalog hits) into the next agent turn.
4. The host agent, following `skills/specode/SKILL.md`, responds to the injection by calling `AskUserQuestion` for selectors or by invoking a `spec_session.py` business subcommand (`acquire` / `phase-transition` / etc.) which atomically updates both state files.

### Session as the integration boundary
Everything is keyed by the host's `session_id` (injected by `SessionStart`, re-injected every `UserPromptSubmit`). Multiple terminal windows = multiple session files = multiple parallel specs. Lock holder is the `session_id`; stale-lock window is 30 minutes (`STALE_LOCK_SECONDS` in `spec_session/_io.py`). The agent MUST NOT invent a session_id, MUST NOT parse one from user input, MUST NOT echo full IDs in chat (8-char prefix only).

### Document root resolution
Three-tier with no fallback (`spec_vault.py`):
1. `--root` flag or `SPECODE_ROOT` env (highest)
2. `~/.config/specode/config.json.obsidianRoot`
3. Auto-detected Obsidian vault → `<vault>/spec-in/<os>-<user>/specs`

If all three miss, `spec_init.py` exits 3 with a setup hint. Do NOT add a cwd or `~/specs` fallback. The `--detect-vault` / `--vault-status` / `--set-vault` / `--set-root` / `--sync-status` flags are routed in `commands/spec.md`; some of them are "fast-path" hooks where the hook pre-renders the output and the agent only prints it verbatim (see `FAST_PATH_HELP` / `FAST_PATH_VAULT` constants in `spec_session/_hooks.py`).

### Phase pipeline + selectors
Valid phases (`VALID_PHASES` in `spec_session/_io.py`): `intake → requirements/bugfix → design → tasks → implementation → acceptance → iteration`. Transitions go through `spec_session.py phase-transition`, which also sets `pending_selector` so the next hook turn knows which `AskUserQuestion` skeleton to remind about. The 7 fixed selector scenarios are defined in `SELECTOR_PROMPTS` (in `spec_session/_selectors.py`) and documented in `skills/specode/references/selectors.md`; `tests/test_selector_prompts.py` snapshots them, and `tests/test_selectors_drift.py` parses the file by regex (keep the `SELECTOR_PROMPTS: dict[str, str] = {...}` literal grep-able).

### Reference catalog (description-as-trigger)
Every `skills/specode/references/*.md` file carries a YAML frontmatter `description: Use when …` that captures *when* a reader should pick it up (superpowers style — trigger-first, not summary-first). The `on-user-prompt-catalog` hook (`spec_session/_catalog.py`) maintains a `CATALOG` dict of keyword regex → reference key (e.g. `lock|takeover|接管` → `lock-protocol`, `iteration|迭代|变更` → `iteration`); each `UserPromptSubmit` it scans the prompt, lists hit references with their descriptions, and emits an advisory injection. Active-only (silent for `idle`/`readonly`/`ended`). `tests/test_catalog.py` enforces: every `CATALOG` key has a real reference file, every targeted reference has a non-empty `description` field. When adding a new reference or extending keyword coverage, update both the frontmatter and `CATALOG`.

### task-swarm orchestration (now a separate plugin)
The implementation-phase orchestrator (multi-coder fork + reviewer/validator state machine) is **no longer part of specode**. It was extracted in M1 into the standalone `plugins/task-swarm/` plugin, which owns its own CLI, state machine (`<spec-dir>/.task-swarm/runs/<run_id>/state.json`), subagent role definitions, and references — document those internals in task-swarm's own `CLAUDE.md`, not here.

specode's only coupling to it today is a manual hand-off: after `tasks.md` is generated, the `tasks-execution` selector (in `spec_session/_selectors.py`) offers an option that tells the user to run the standalone `task-swarm` plugin (its `/task-swarm` command) against this spec's `tasks.md`. The `tasks.md` format specode emits (`## 阶段 N:` sections + `- [ ] N.M ... @writes:...` tags) is intentionally kept task-swarm-compatible. Automatic delegation (specode driving task-swarm directly) is a later milestone — for now it is user-initiated.

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
- **CHANGELOG.md** — narrative history; useful when a behavior seems weird because it documents past bugs and the reasoning behind subtle fixes (e.g. 0.10.23–0.10.24 template-vs-constraint separation, and the M1 entry recording task-swarm's extraction into its own plugin). Older task-swarm-specific fixes (0.10.21 writeback line-safe, 0.10.13 / 0.10.17 STATUS recovery) are now history of the standalone task-swarm plugin.
- **plugins/specode/skills/specode/SKILL.md** + **references/** — the runtime behavior spec the *host agent* follows. When modifying selectors, phase order, or the lock protocol, the SKILL.md and the corresponding `references/<topic>.md` need to stay in sync with the CLI behavior; selector drift is enforced by `tests/test_selectors_drift.py`.
