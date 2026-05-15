# spec-mode-plugin

Specification-driven workflow plugin for **Claude Code** and **CodeBuddy**.

The original `spec-mode` was a skill (markdown instructions). Skills rely on
the model remembering and obeying rules in context, which degrades as context
grows. This plugin moves the load-bearing rules into Claude Code hooks —
deterministic shell commands the harness runs — so the rules are enforced by
the *runtime*, not by the model's discipline.

## What it enforces

Once a spec is active, these invariants are **harness-enforced**:

| ID | Rule | Hook |
|---|---|---|
| **INV-1** | Editing a source file requires either that file being listed in `tasks.md` / `## Affected Files`, or a same-turn edit to `design.md` / `tasks.md` / `bugfix.md`, or `freeform` mode | `PreToolUse` |
| **INV-2** | A turn that touched source code must touch at least one spec document before stop | `Stop` |
| **INV-3** | Spec-doc writes are rejected if the session was evicted by another window | `PreToolUse` |
| **INV-4** | Edits to `requirements.md` require a same-turn rewrite of `acceptance-checklist.md` | `Stop` |
| **INV-5** | Each user turn injects a status block (`spec / phase / lock / turn`) into the model's context | `UserPromptSubmit` |
| **INV-6** | Source code edits are forbidden in pre-implementation phases (intake / requirements / bugfix / design / tasks) | `PreToolUse` |

INV-1 and INV-2 form the **Code-Doc Sync Guard (CDSG)** — the central
contribution beyond the original skill.

## Architecture

```
plugin.json              ← Claude Code / CodeBuddy plugin manifest
hooks/hooks.json         ← 6 event handlers with shell short-circuit on sentinel
skills/spec-mode/        ← original skill content (SKILL.md + references)
commands/                ← /spec, /spec-continue, /spec-status, /spec-end
scripts/
  spec_guard.py          ← hook entry; dispatches to handlers; audit log
  spec_state.py          ← read-only state probe + sentinel + Claude-session record
  spec_sync.py           ← INV-1/2/3/4/6 logic; ledger; phase gate; glob matcher
  spec_session.py        ← (existing) lock + phase + active-pointer model
  spec_init.py / spec_lint.py / spec_status.py / spec_choice.py / spec_vault.py
adapters/codebuddy/      ← assumed-API-compatible note + open items
tests/                   ← 19 pytest cases (unit + integration)
state/                   ← runtime data (gitignored)
```

## Install (local dev)

```sh
claude --plugin-dir /path/to/spec-mode-plugin
```

The plugin is discovered automatically; `plugin.json`, `hooks/hooks.json`,
`skills/`, and `commands/` are all picked up. Once running:

```
/help                              # list /spec-mode:* commands
/reload-plugins                    # after editing plugin files
```

Hook activity logs to `~/.spec-mode/audit/<date>.log` (UTC).

## Usage

Inside a Claude Code session with the plugin loaded:

```
/spec-mode:spec --persist <requirement>     # start persistent spec session
/spec-mode:spec-continue [slug]             # resume / switch
/spec-mode:spec-status                      # show current session
/spec-mode:spec-end                         # end persistent session

/spec-mode:spec --freeform                  # relax INV-1 (INV-2 still enforced)
/spec-mode:spec --strict                    # restore INV-1
/spec-mode:spec --sync-status               # ledger / pending sync / last violation
```

Once a spec is active:

- Every user prompt is augmented with a `spec-mode active` status block
  identifying the spec, phase, lock state, turn id, and freeform mode.
- Edits to project source files outside `tasks.md` are blocked unless a
  same-turn doc change preceded them (INV-1).
- Stopping a turn that touched code without touching docs fails until the
  model adds a `design.md` / `tasks.md` / `implementation-log.md` entry
  (INV-2).
- `requirements.md` edits force `acceptance-checklist.md` updates in the
  same turn (INV-4).
- Code edits during `intake` / `requirements` / `bugfix` / `design` / `tasks`
  phases are absolutely refused — freeform does NOT exempt INV-6.

## Asymmetry note

INV-2 is **unidirectional**: source-code change ⇒ doc change required, but
doc-only edits (typo fixes, wording tweaks) do NOT require a code change.
`implementation-log.md` counts as a doc change to satisfy INV-2 cheaply —
`spec_lint.py` reports a soft WARNING for log entries shorter than 30 chars
or that don't reference any actual code file (the *cosmetic-doc* concern).

## Performance

| Hook | Wall-clock budget |
|---|---|
| `SessionStart` / `SessionEnd` | always runs Python; <500ms |
| `UserPromptSubmit` | only runs Python when `~/.spec-mode/.any-active` sentinel exists; <80ms |
| `PreToolUse` / `PostToolUse` / `Stop` | same shell short-circuit; <100ms when running |

When no spec is active, the shell `[ ! -e ~/.spec-mode/.any-active ]` check
exits before any Python startup → effectively free.

## Bypass switch

```sh
export SPEC_MODE_GUARD=off
```

Every hook returns 0 immediately, without audit. Debugging only.

## CodeBuddy support

`hooks/hooks.json` uses `${CLAUDE_PLUGIN_ROOT:-${CODEBUDDY_PLUGIN_ROOT}}` so
the plugin works under both harnesses *if* CodeBuddy's hook payload protocol
matches Claude Code's. Open items live at `adapters/codebuddy/README.md`.
CodeBuddy real-run verification has not yet happened — see that adapter
README before deploying to CodeBuddy users.

## Tests

```sh
python3 -m pip install --user pytest
python3 -m pytest tests/ -v
```

19 cases covering INV-1..INV-6 paths, freeform behavior, lock states,
phase gate matrix, and glob/literal tasks_files matching.

## Status

- Phase 1: hook wiring ✓
- Phase 2: state layer + status injection + short-circuit ✓
- Phase 3: Code-Doc Sync Guard (INV-1/2/4) ✓
- Phase 4: verify-lock + phase gate (INV-3/6) ✓
- Phase 5: CodeBuddy static adapter (env var fallback + open items doc) ✓
- Phase 6: pytest suite + docs + old-skill stub ✓
- *Live CodeBuddy verification* — pending user

## License

MIT
