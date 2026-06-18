# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A two-plugin marketplace for Claude Code and CodeBuddy CLIs:

- **specode** (`plugins/specode/`) — a **lightweight spec-driven workflow plugin**. As of 1.0.0 it is no longer a state machine: it is a thin **orchestration shell** (壳) that walks a host agent through a phase pipeline (requirements → design → 执行方式 → 执行 → 验收) and, at each phase, **delegates the heavy lifting to superpowers skills** (`brainstorming` / `writing-plans` / `subagent-driven-development` / `executing-plans` / `verification-before-completion`). When superpowers is absent, specode falls back to a **specode-native** path (first-class, not an afterthought). It produces **3 fixed documents** (`requirements.md` / `design.md` / `implementation-log.md`) under the user's specs directory. **This is the plugin this `CLAUDE.md` documents** unless stated otherwise.
- **task-swarm** (`plugins/task-swarm/`) — a standalone implementation-phase orchestrator (multi-coder fork + reviewer/validator state machine), extracted out of specode in milestone M1. It has its own CLI, state machine, agents, and `CLAUDE.md`. specode hands off to it only via the user-chosen "委托 task-swarm" option in the 执行方式 selector, with **zero import** (calls task-swarm's own `/task-swarm:swarm` command).

Most implementation referenced here lives under `plugins/specode/`. The repo root only contains the marketplace manifest (`.claude-plugin/marketplace.json`, which lists **both** plugins), the README, the CHANGELOG, and CONTRIBUTING. Plugin internals are listed in README §Architecture — do not re-derive the file tree, read the README.

## Commands

```sh
# Run the test suite (must be from repo root; tests are hermetic and redirect $HOME)
python3 -m pytest plugins/specode/tests/ -v

# Single test file (the lite suite currently covers only resolve_root.py)
python3 -m pytest plugins/specode/tests/test_resolve_root.py -v

# Local plugin install (development)
claude    --plugin-dir ./plugins/specode
codebuddy --plugin-dir ./plugins/specode
```

There is no lint or typecheck step configured at the repo level.

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

`run.sh` probes `python3 → python → py` (with Windows Store alias-stub skipping) so the script works on any host with Python 3.8+. Bare `python3 <name>.py` calls fail in most cwds — when adding a new entry point, match the wrapper template used in `hooks/hooks.json` and `commands/specode-*.md`. The wrapper template now includes a `find`-based fallback for an empty `$CLAUDE_PLUGIN_ROOT` (the env var is not reliably set in skill-driven Bash calls).

### Templates describe structure, not behavior
`assets/templates/*.md` are the *output* of the workflow — the host agent reads them only *after* deciding what to write. So **never put behavioral constraints (rules, "必须", gating checks) into templates**: they get stamped into every spec on disk, dilute the signal, and have zero authority over the agent's pre-write decisions.

Behavioral constraints belong in places the agent reads *before* it generates content:
- `skills/specode/SKILL.md` (always-loaded persona/orchestration rules)
- `commands/specode-spec.md` / `specode-continue.md` / `specode-list.md` (loaded when the user invokes the matching `/specode:specode-*` command)
- `skills/specode/references/*.md` (selector verbatim examples, path resolution, superpowers wiring)
- The `SessionStart` hook's `additionalContext` injection (`scripts/spec_hooks.py`)

### Test conventions
- Scripts are CLIs, not importable modules. Tests invoke them via `subprocess.run` through the `run_script` fixture in `tests/conftest.py`.
- Use the `fake_home` fixture to redirect `$HOME`, `XDG_CONFIG_HOME`, and clear `SPECODE_ROOT`. Tests MUST be hermetic — never touch the real `~/.specode/` or `~/.config/specode/`.

## Architecture — the parts that span multiple files

### The orchestration shell (壳)
specode 1.0.0 has almost no runtime logic. The behavior lives in **`skills/specode/SKILL.md`** (always-loaded), which drives the host agent through the phase pipeline. At each phase the agent **first tries to invoke the matching superpowers skill via the `Skill` tool**; if it's unavailable, it runs the **specode-native** fallback inline. The phase ↔ skill map:

| phase | superpowers skill (if installed) | specode-native fallback |
|---|---|---|
| requirements (澄清 + 需求) | `superpowers:brainstorming` | AskUserQuestion 澄清 wizard + 按模板写 |
| design (可执行计划) | `superpowers:writing-plans` | 按 design 模板拆 `## Task N` + `验证: AC-N` + `- [ ]` TDD 步骤 |
| 执行 | `superpowers:subagent-driven-development` / `executing-plans` (or 委托 task-swarm) | 主代理按 design Task 顺序 TDD（红→绿） |
| 验收 | `superpowers:verification-before-completion` (+ optional `requesting-code-review`) | 对照 design 测试要点 / `AC-N` 逐条核验 |

Both superpowers and task-swarm are **soft dependencies** (run-time only, called via SKILL prose, zero import). specode installed alone must run the whole 启动→coding 完成 loop via the native fallbacks — the fallback path is a first-class peer of the superpowers path, not a footnote.

### The 3 fixed documents (硬约束)
Whatever the execution engine, a spec **always** produces exactly these 3, with **fixed filenames**, **fixed location** `<specsRoot>/<slug>/`:

| doc | filename | content |
|---|---|---|
| 需求 | `requirements.md` | 散文 spec：背景 / 范围(in/out) / 验收 `- [ ] AC-N` / 开放问题。Plain prose, no formalized requirement clauses. Bug fixes use Current/Expected prose here — there is no separate `bugfix.md`. |
| 设计 | `design.md` | superpowers writing-plans 可执行计划格式：`Goal` / `Architecture` / `Tech Stack` + `## Task N`（each with `**Files:**`, `验证: AC-N` back-reference, `- [ ]` TDD steps）. |
| 执行日志 | `implementation-log.md` | 执行期追加：设计偏离 / 关键决策 / 最终验收小结。 |

The engine only decides *who generates the content*, never the form/name/location. When delegating to superpowers (whose `brainstorming`/`writing-plans` have their own default output paths), the agent does **后置落盘归位**: after the skill returns, verify `<specsRoot>/<slug>/<fixed-name>` exists; if not, `mv`/rename the skill's actual output into place. This double-保险 keeps the invariant true regardless of whether the skill obeyed the up-front path instruction.

### scripts/ layout (only two scripts)
| `scripts/` member | Role |
|---|---|
| `resolve_root.py` | The only business CLI. specsRoot resolution + persistence + spec listing. stdlib-only. Invoked from the `commands/specode-*.md` command files via `run.sh`. |
| `spec_hooks.py` | The only hook handler: `SessionStart` injects an advisory discipline reminder via `additionalContext` and exits 0. Tolerates non-TTY/empty stdin, swallows all exceptions (advisory, never blocks). |
| `run.sh` / `run.cmd` | Python interpreter probes (`python3 → python → py`) — Windows alias-stub handling lives here. |

There is no heavy state-machine package, no launcher indirection, no shared logging module — those were all removed in 1.0.0.

### specsRoot resolution + first-time setup (`resolve_root.py`)
Resolution order (no cwd / `~/specs` fallback):
1. `--root` flag or `SPECODE_ROOT` env (highest, temporary override)
2. `~/.config/specode/config.json.specsRoot` (the normal source — read on every activation)
3. None → **first-time setup**: `get-root` exits 3; the active `commands/specode-*.md` command then calls `AskUserQuestion` for the user's document directory and calls `set-root --root <abs>` to persist it. The user-provided directory is used **verbatim as the specs root** — specode makes no structural assumptions and does no path concatenation.

verbs: `get-root [--root P]` (exit 0/3), `set-root --root <abs>` (exit 0/1), `list-specs [--root P]` (lists subdirs containing `requirements.md`, one slug per line). Config writes use `tempfile + os.replace + fsync` (`_atomic_write_json`).

There is **no** persistent state file. "Am I in an active spec, and which phase?" is inferred entirely from (a) the current conversation context (which slug this turn is driving) + (b) which fixed docs exist in `<specsRoot>/<slug>/` + (c) `- [ ]` checkbox progress in `design.md`. This is the **文档即状态** principle — see SKILL.md §续接 for the inference table.

### Hook → behavior flow
The host CLI fires exactly one hook: `SessionStart` → `run.sh` → `spec_hooks.py session-start`, which emits an advisory `additionalContext` reminder that specode is available and how to activate it (`/specode:specode-spec`, `/specode:specode-continue <slug>`, `/specode:specode-list`). No selector guard, no per-turn footer, no logging, no doc-sync nag — all removed in 1.0.0. The hook is advisory only: it never `exit 2`s and any exception is swallowed.

### The 执行方式 selector (the only per-spec selector)
After `design.md` is confirmed, the agent calls `AskUserQuestion` with an **adaptive 4-option** selector (each option shown only if its engine is installed): 委托 task-swarm / superpowers subagent-driven / superpowers executing-plans / specode 自执行. It is driven by SKILL prose + verbatim examples in `references/selectors.md` — there is **no constant library, no snapshot/drift test, no PreToolUse hard-validation**. The "逐字按范例" rule (don't invent or shorten the options) is enforced only by SKILL.md, which is acceptable for the single-user scenario this rewrite targets.

### task-swarm hand-off (zero hard dependency)
specode does not import task-swarm and does not know its install path. When the user picks "委托 task-swarm", the agent reads `design.md`'s Task list + each Task's `**Files:**`, mechanically derives a `pipeline.yml` (shown to the user first), then drives task-swarm via its own `/task-swarm:swarm` command (whose `$CLAUDE_PLUGIN_ROOT` self-resolves). If task-swarm is absent, it degrades to specode 自执行 or a superpowers execution path. `pipeline.yml` is a transient artifact only — not one of the 3 fixed products.

## Release procedure (summary)

Detailed steps are in CONTRIBUTING.md §Release. The two manifests carrying `version` MUST match or the plugin tag tooling refuses:
- `plugins/specode/.claude-plugin/plugin.json` → `"version"`
- `.claude-plugin/marketplace.json` → the **specode** entry's `version` (do not touch the task-swarm entry)

Workflow: bump both manifests → rename `## Unreleased` in CHANGELOG to `## X.Y.Z (YYYY-MM-DD)` + add a fresh `## Unreleased` above → run tests → commit + push → `claude plugin tag --dry-run plugins/specode` → `claude plugin tag plugins/specode --push`. Tag format is `specode--v{version}` (annotated). **Pushing the tag IS the release** — host CLIs fetch the marketplace manifest from GitHub by git tag.

Semver "API surface" for this plugin (2.0.0+) = the three command names (`/specode:specode-spec <需求>` / `/specode:specode-continue <slug>` / `/specode:specode-list`), the `SessionStart` hook event, the persisted `config.json.specsRoot` field, and the 3 fixed document filenames. Removing/renaming any of these is **major**; adding a backwards-compatible capability is **minor**. (2.0.0 renamed the single `/spec` command — with `continue`/`list` subcommands — into these three flat, separately-discoverable commands.)

## Where to look for what

- **README.md** — what the plugin does, install/usage, the lite architecture map.
- **CONTRIBUTING.md** — the full version of the conventions above (stdlib rule, CLI wrapper contract, hook advisory rule, hermetic test conventions, release).
- **CHANGELOG.md** — narrative history; the 1.0.0 entry records the lightweight refactor (what was deleted, the orchestration-shell model, no-read-side-fallback migration). Older entries document the pre-1.0.0 heavy state machine and task-swarm's M1 extraction.
- **plugins/specode/skills/specode/SKILL.md** + **references/** — the runtime behavior spec the *host agent* follows (phase orchestration, native fallbacks, 执行方式 selector, specsRoot setup, task-swarm bridge). When changing phase order, the selector, or the fixed-product invariant, keep SKILL.md and the matching `references/<topic>.md` in sync.
