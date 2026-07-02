# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A **three-plugin** marketplace for Claude Code and CodeBuddy CLIs. The root is only the marketplace shell; each plugin under `plugins/<name>/` is self-contained with its own `plugin.json`, skills, scripts, tests, and CHANGELOG.

- **specode** (`plugins/specode/`, v5.1.2) — a **lightweight spec-driven workflow plugin**. It is not a state machine: it is a thin **orchestration shell** (壳) that walks a host agent through a phase pipeline (requirements → design → 执行方式 → 执行 → 验收) and, at each phase, **delegates the heavy lifting to superpowers skills** (`brainstorming` / `writing-plans` / `subagent-driven-development` / `executing-plans` / `verification-before-completion`). When superpowers is absent, specode falls back to a **specode-native** path (first-class, not an afterthought). It produces **3 fixed documents** (`requirements.md` / `design.md` / `implementation-log.md`) under the user's specs directory. **This is the plugin this `CLAUDE.md` documents** unless stated otherwise.
- **task-swarm** (`plugins/task-swarm/`, v0.10.1) — a standalone implementation-phase orchestrator (multi-coder fork + reviewer/validator state machine), extracted out of specode in milestone M1. It has its own CLI (`scripts/task_swarm/`), state machine, agents, skill, and CHANGELOG. specode hands off to it only via the user-chosen "委托 task-swarm" option in the 执行方式 selector, with **zero import** (calls task-swarm's own `/task-swarm:swarm` command).
- **obsidian-wiki** (`plugins/obsidian-wiki/`, v2.0.0) — a **skills-only** plugin (no commands, no hooks) for maintaining an Obsidian LLM-Wiki: a deterministic structure layer (Home tree / per-dir READMEs / partition pages via `wiki-struct`), content curation (`wiki-curate`), and a unified orchestrator (`wiki-orchestrate`). Generic code + per-vault config in the home-dir registry `~/.config/obsidian-wiki/` (fallback: `<vault>/.wiki/config.json`), zero hardcoded structure. Largely independent of the other two — its only historical tie is that the old spec→knowledge distill capability was **extracted out of it into specode's `distill`** in its own v2.0.0.

**Recent context (read before touching memory/knowledge/distill code):** specode 4.0.0 + task-swarm 0.10.0 **ripped out the *original* memory-injection engine** — codemap recall, rule-check, auto-distill, `_ingest_lessons.py`, `.ai-memory/knowledge/*.yml` writes — because round 1/2 baselines showed that recall round-trip did not net-save tokens. **specode 5.1.0 then re-introduced experience retrieval/injection, but on a deliberately different footing: KB is 定位用 (pointers to real code), not 事实用 (truth).** Producer = a new stdlib CLI `scripts/knowledge.py` + a rewritten `distill` that emits **atomic `case`/`navigation` knowledge-points** to the project's `<project_root>/knowledge-base/` (`cases/` + `navigation/` + a `MEMORY.md` index, **gitignored**, optional Obsidian copy). Consumer = `skills/specode/references/retrieval.md`, a **two-tier gated** retrieval (Tier-1 reads only the small MEMORY index; Tier-2 reads ≤5 hit docs to locate real code) wired into the **requirements + design** phases — **execution / task-swarm get zero injection**. The injected `参考定位` section is always labeled 非事实来源; real code stays the sole source of truth. This is **not** the old codemap recall (model-judged not script-recalled, pointers not content, default reads only a small index). The sanctioned style going forward is the 5.1.0 location-oriented one — do **not** reintroduce the *old* content-injection style without an explicit ask. The v3 memory engine still lives at tag/branch `backup/specode-v3.4.0-task-swarm-v0.9.2`. See §Experience retrieval below.

The repo root holds: the marketplace manifest (`.claude-plugin/marketplace.json`, which lists **all three** plugins), `scripts/check_marketplace_versions.py` (the version-sync gate, see below), the READMEs (EN + zh-CN), the root CHANGELOG, and CONTRIBUTING. Plugin internals are listed in README §Architecture — do not re-derive the file tree, read the README.

## Commands

```sh
# pytest is a DEV-ONLY dependency (the runtime is stdlib-only). On a PEP-668
# Homebrew Python you cannot pip-install globally, so this repo keeps a project
# venv at ./.venv (gitignored). Create it once, then use ./.venv/bin/python:
python3 -m venv .venv && .venv/bin/python -m pip install pytest   # one-time setup

# specode test suite (hermetic — fixtures redirect $HOME / XDG_CONFIG_HOME)
.venv/bin/python -m pytest plugins/specode/tests/ -v
.venv/bin/python -m pytest plugins/specode/tests/test_resolve_root.py -v   # single file

# task-swarm test suite (same subprocess-CLI + hermetic-$HOME conventions)
.venv/bin/python -m pytest plugins/task-swarm/tests/ -v

# obsidian-wiki tests are stdlib `unittest` (NO pytest needed) and live NEXT
# TO the source (test_*.py beside the module, not in a tests/ dir). They import
# the sibling module by name, so run from inside that dir (cwd on sys.path):
( cd plugins/obsidian-wiki/lib && python3 -m unittest discover -p 'test_*.py' )
( cd plugins/obsidian-wiki/skills/wiki-struct/scripts && python3 -m unittest discover -p 'test_*.py' )

# Marketplace version-sync gate — run before any release commit (see Release)
python3 scripts/check_marketplace_versions.py

# Local plugin install (development) — swap the dir per plugin
claude    --plugin-dir ./plugins/specode
codebuddy --plugin-dir ./plugins/specode
```

There is no lint or typecheck step configured at the repo level. The only CI is `.github/workflows/check-marketplace-versions.yml`, which runs the version-sync gate on every PR/push that touches a manifest.

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

`run.sh` probes `python3 → python → py` (with Windows Store alias-stub skipping) so the script works on any host with Python 3.8+. Bare `python3 <name>.py` calls fail in most cwds — when adding a new entry point, match the wrapper template used in `hooks/hooks.json` and `commands/*.md`. The wrapper template now includes a `find`-based fallback for an empty `$CLAUDE_PLUGIN_ROOT` (the env var is not reliably set in skill-driven Bash calls).

### Templates describe structure, not behavior
`assets/templates/*.md` are the *output* of the workflow — the host agent reads them only *after* deciding what to write. So **never put behavioral constraints (rules, "必须", gating checks) into templates**: they get stamped into every spec on disk, dilute the signal, and have zero authority over the agent's pre-write decisions.

Behavioral constraints belong in places the agent reads *before* it generates content:
- `skills/specode/SKILL.md` (always-loaded persona/orchestration rules)
- `commands/spec.md` / `continue.md` / `list.md` / `distill.md` (loaded when the user invokes the matching `/specode:*` command)
- `skills/specode/references/*.md` (selector verbatim examples, path resolution, superpowers wiring)
- The `SessionStart` hook's `additionalContext` injection (`scripts/spec_hooks.py`)

### Test conventions
- Scripts are CLIs, not importable modules. Tests invoke them via `subprocess.run` through the `run_script` fixture in `tests/conftest.py`.
- Use the `fake_home` fixture to redirect `$HOME`, `XDG_CONFIG_HOME`, and clear `SPECODE_ROOT`. Tests MUST be hermetic — never touch the real `~/.specode/` or `~/.config/specode/`.

## Architecture — the parts that span multiple files

### The orchestration shell (壳)
specode has almost no runtime logic. The behavior lives in **`skills/specode/SKILL.md`** (always-loaded), which drives the host agent through the phase pipeline. At each phase the agent **first tries to invoke the matching superpowers skill via the `Skill` tool**; if it's unavailable, it runs the **specode-native** fallback inline. The phase ↔ skill map:

| phase | superpowers skill (if installed) | specode-native fallback |
|---|---|---|
| requirements (澄清 + 需求) | `superpowers:brainstorming` | AskUserQuestion 澄清 wizard + 按模板写 |
| design (可执行计划) | `superpowers:writing-plans` | 按 design 模板拆 `## Task N` + `验证: AC-N` + `- [ ]` TDD 步骤 |
| 执行 | `superpowers:subagent-driven-development` / `executing-plans` (or 委托 task-swarm) | 主代理按 design Task 顺序 TDD（红→绿） |
| 验收 | `superpowers:verification-before-completion` (+ optional `requesting-code-review`) | 对照 design 测试要点 / `AC-N` 逐条核验 |

Both superpowers and task-swarm are **soft dependencies** (run-time only, called via SKILL prose, zero import). specode installed alone must run the whole 启动→coding 完成 loop via the native fallbacks — the fallback path is a first-class peer of the superpowers path, not a footnote.

### `distill` — the off-pipeline 4th command
`/specode:distill <slug>` is **not** part of the requirements→验收 pipeline and does **not** produce or touch the 3 fixed docs. It is a user-triggered organizer (own command `commands/distill.md` + own skill `skills/distill/SKILL.md`). **As of 5.1.0** it converts a finished spec into **atomic `case`/`navigation` knowledge-points** written to **`<project_root>/knowledge-base/`** as the primary product (`cases/` + `navigation/` + a `MEMORY.md` index rebuilt by `knowledge.py memory-rebuild` from each doc's frontmatter), with an **optional** copy to Obsidian (user supplies an absolute path, 直写不拼接). `knowledge-base/` is **gitignored** (local-private; `knowledge.py ensure-gitignore`). Still **md-only** (no yml / codemap / `.ai-memory`). It is **standalone/manual**, but 5.1.0 re-hooks an **optional prompt at acceptance end** gated by the existing `auto_distill` default — the prompt only *offers* to run it; distill is never silently auto-run. (Pre-5.1.0 it was an Obsidian-primary 5-category organizer defaulting to `/Volumes/External HD/.../11-KnowledgeBase/<slug>/`; that shape is gone.) `skills/distill/references/*.md` (breakdown-heuristics / doc-template) are aligned to this case/navigation reality.

### Experience retrieval / injection (5.1.0 — 定位用·非事实用)
A producer→index→consumer loop layered on the shell (see Recent context). The invariant: **KB content locates real code; it is never the source of truth.**
- **Producer** — `distill` writes atomic `case`/`navigation` points (file paths + call chains + reusable navigation experience) to `<project_root>/knowledge-base/`; `knowledge.py memory-rebuild` regenerates `MEMORY.md` from each doc's frontmatter (frontmatter = single source of truth → drift-safe; `memory-validate` reports drift).
- **Index contract (锁步演进)** — frontmatter keys `标题/类型/来源/tags/描述`, `类型 ∈ {case, navigation}`, and the MEMORY columns `| 标题 | 类型 | 描述 | 来源 | 路径 | tags |` are **byte-identical** across three sites: `skills/distill/references/doc-template.md` (writes), `scripts/knowledge.py` `_COLS` (indexes), `skills/specode/references/retrieval.md` (reads). Change one → change all three (the 变更纪律 stated in retrieval.md).
- **Consumer** — `skills/specode/references/retrieval.md` drives a two-tier gated retrieval in the **requirements + design** phases: Tier-1 `Read`s the small `MEMORY.md` and matches the current need's 页面/字段/域 against `tags`+`描述`; on a hit, Tier-2 `Read`s ≤5 docs and uses their 前后端文件 + 调用链 to jump to **real code**. The injected 「参考定位（非事实来源）」 段 is pointers only. KB absent → silently skipped (default cost ≈ one small index read — the v3-token-bloat avoidance). **Execution / task-swarm receive nothing** (zero-injection boundary).

### The 3 fixed documents (硬约束)
Whatever the execution engine, a spec **always** produces exactly these 3, with **fixed filenames**, **fixed location** `<specsRoot>/<slug>/`:

| doc | filename | content |
|---|---|---|
| 需求 | `requirements.md` | 散文 spec：背景 / 范围(in/out) / 验收 `- [ ] AC-N` / 开放问题。Plain prose, no formalized requirement clauses. Bug fixes use Current/Expected prose here — there is no separate `bugfix.md`. |
| 设计 | `design.md` | superpowers writing-plans 可执行计划格式：`Goal` / `Architecture` / `Tech Stack` + `## Task N`（each with `**Files:**`, `验证: AC-N` back-reference, `- [ ]` TDD steps）. |
| 执行日志 | `implementation-log.md` | 执行期追加：设计偏离 / 关键决策 / 最终验收小结。 |

The engine only decides *who generates the content*, never the form/name/location. When delegating to superpowers (whose `brainstorming`/`writing-plans` have their own default output paths), the agent does **后置落盘归位**: after the skill returns, verify `<specsRoot>/<slug>/<fixed-name>` exists; if not, `mv`/rename the skill's actual output into place. This double-保险 keeps the invariant true regardless of whether the skill obeyed the up-front path instruction.

### scripts/ layout
| `scripts/` member | Role |
|---|---|
| `resolve_root.py` | The specsRoot / project_root / defaults business CLI. specsRoot resolution + persistence + spec listing + project_root single-reader/writer + autonomous-mode defaults. stdlib-only. Invoked from `commands/*.md` and SKILL prose via `run.sh`. |
| `knowledge.py` | **(5.1.0+)** The knowledge-base index CLI. stdlib-only verbs: `ensure-gitignore` (skips when the project is non-git **and** has no existing `.gitignore`) / `memory-rebuild` (rebuild `MEMORY.md` from each knowledge-point's frontmatter) / `memory-validate` (drift detection) / `copy-to --kb <src> --dest <abs>` (one-step dual-landing: copy `cases/`+`navigation/` to an absolute dest + rebuild its MEMORY). Invoked by `distill` via `run.sh`; tests in `tests/test_knowledge.py`. |
| `spec_hooks.py` | The only hook handler: `SessionStart` injects an advisory discipline reminder via `additionalContext` and exits 0. Tolerates non-TTY/empty stdin, swallows all exceptions (advisory, never blocks). |
| `run.sh` / `run.cmd` | Python interpreter probes (`python3 → python → py`) — Windows alias-stub handling lives here. |

There is no heavy state-machine package, no launcher indirection, no shared logging module — those were all removed in 1.0.0.

### specsRoot resolution + first-time setup (`resolve_root.py`)
Resolution order (no cwd / `~/specs` fallback):
1. `--root` flag or `SPECODE_ROOT` env (highest, temporary override)
2. `~/.config/specode/config.json.specsRoot` (the normal source — read on every activation)
3. None → **first-time setup**: `get-root` exits 3; the active `commands/*.md` command then calls `AskUserQuestion` for the user's document directory and calls `set-root --root <abs>` to persist it. The user-provided directory is used **verbatim as the specs root** — specode makes no structural assumptions and does no path concatenation.

verbs: `get-root [--root P]` (exit 0/3), `set-root --root <abs>` (exit 0/1), `list-specs [--root P]` (lists spec slugs one per line: subdirs containing any of the 3 fixed docs, plus empty subdirs — intake-phase specs whose dir exists but requirements.md is not yet written; hidden dirs excluded). Config writes use `tempfile + os.replace + fsync` (`_atomic_write_json`).

There is **no** persistent state file. "Am I in an active spec, and which phase?" is inferred entirely from (a) the current conversation context (which slug this turn is driving) + (b) which fixed docs exist in `<specsRoot>/<slug>/` + (c) `- [ ]` checkbox progress in `design.md`. This is the **文档即状态** principle — see SKILL.md §续接 for the inference table.

### Hook → behavior flow
The host CLI fires exactly one hook: `SessionStart` → `run.sh` → `spec_hooks.py session-start`, which emits an advisory `additionalContext` reminder that specode is available and how to activate it (`/specode:spec`, `/specode:continue <slug>`, `/specode:list`). No selector guard, no per-turn footer, no logging, no doc-sync nag — all removed in 1.0.0. The hook is advisory only: it never `exit 2`s and any exception is swallowed.

### The 执行方式 selector (the only per-spec selector)
After `design.md` is confirmed, the agent calls `AskUserQuestion` with an **adaptive 4-option** selector (each option shown only if its engine is installed): 委托 task-swarm / superpowers subagent-driven / superpowers executing-plans / specode 自执行. It is driven by SKILL prose + verbatim examples in `references/selectors.md` — there is **no constant library, no snapshot/drift test, no PreToolUse hard-validation**. The "逐字按范例" rule (don't invent or shorten the options) is enforced only by SKILL.md, which is acceptable for the single-user scenario this rewrite targets.

### task-swarm hand-off (zero hard dependency)
specode does not import task-swarm and does not know its install path. When the user picks "委托 task-swarm", the agent reads `design.md`'s Task list + each Task's `**Files:**`, mechanically derives a `pipeline.yml` (shown to the user first), then drives task-swarm via its own `/task-swarm:swarm` command (whose `$CLAUDE_PLUGIN_ROOT` self-resolves). If task-swarm is absent, it degrades to specode 自执行 or a superpowers execution path. `pipeline.yml` is a transient artifact only — not one of the 3 fixed products.

## Release procedure (summary)

Detailed steps are in CONTRIBUTING.md §Release. Each plugin releases **independently** — bumping one does not require touching the others. For the plugin being released, two manifests carrying `version` MUST match exactly or both `scripts/check_marketplace_versions.py` (CI gate) and the `claude plugin tag` tooling refuse:
- `plugins/<plugin>/.claude-plugin/plugin.json` → `"version"`
- `.claude-plugin/marketplace.json` → **that plugin's** entry's `version` (leave the other two entries alone)

Workflow (per plugin): bump both manifests → rename `## Unreleased` in the plugin's CHANGELOG to `## X.Y.Z (YYYY-MM-DD)` + add a fresh `## Unreleased` above → `python3 scripts/check_marketplace_versions.py` (must pass) → run that plugin's tests → commit + push → `claude plugin tag --dry-run plugins/<plugin>` → `claude plugin tag plugins/<plugin> --push`. Tag format is `<plugin>--v{version}` (annotated, e.g. `specode--v5.0.1`, `task-swarm--v0.10.1`). **Pushing the tag IS the release** — host CLIs fetch the marketplace manifest from GitHub by git tag.

Semver "API surface" for **specode** = the four command names (`/specode:spec <需求>` / `/specode:continue <slug>` / `/specode:list` / `/specode:distill [<slug>]`), the `SessionStart` hook event, the persisted `config.json.specsRoot` field, and the 3 fixed document filenames. Removing/renaming any of these is **major**; adding a backwards-compatible capability is **minor**.

## Where to look for what

- **README.md** / **README.zh-CN.md** — what each plugin does, install/usage, the lite architecture map. Keep both in sync on release.
- **CONTRIBUTING.md** — the full version of the conventions above (stdlib rule, CLI wrapper contract, hook advisory rule, hermetic test conventions, release).
- **CHANGELOG.md** (root) + each **plugins/<name>/CHANGELOG.md** — narrative history. Recent inflections: specode 4.0.0 / task-swarm 0.10.0 ripped out the memory-injection engine; **specode 5.1.0 re-introduced retrieval/injection on a 定位用 (pointers-not-facts) basis** (`knowledge.py` + project `knowledge-base/` + `references/retrieval.md`). Older entries cover the pre-1.0.0 heavy state machine and task-swarm's M1 extraction. Branch `backup/specode-v3.4.0-task-swarm-v0.9.2` preserves the v3 memory-injection code.
- **plugins/specode/skills/specode/SKILL.md** + **references/** — the runtime behavior spec the *host agent* follows for the main pipeline (phase orchestration, native fallbacks, 执行方式 selector, specsRoot setup, task-swarm bridge). When changing phase order, the selector, or the fixed-product invariant, keep SKILL.md and the matching `references/<topic>.md` in sync.
- **plugins/specode/skills/distill/SKILL.md** — authoritative behavior for the off-pipeline distill command (5.1.0: writes atomic case/navigation points to project `knowledge-base/`).
- **plugins/specode/skills/specode/references/retrieval.md** + **plugins/specode/scripts/knowledge.py** — the 5.1.0 experience-retrieval consumer (two-tier gated spec) and producer-index CLI. Keep the MEMORY/frontmatter contract byte-identical with `skills/distill/references/doc-template.md` (the 变更纪律).
- **plugins/task-swarm/** — its own SKILL.md (`skills/task-swarm/`), agents (`agents/task-swarm-{coder,reviewer,validator}.md`), CLI package (`scripts/task_swarm/`), and CHANGELOG; self-documenting and only loosely coupled to specode (called via `/task-swarm:swarm`).
- **plugins/obsidian-wiki/** — has its own **AGENTS.md** (the host-agent behavior contract, analogous to specode's SKILL.md), README, `config.example.json`, and three skills (`wiki-struct` / `wiki-curate` / `wiki-orchestrate`). Self-contained; not part of the spec workflow.
- **scripts/check_marketplace_versions.py** — the version-sync gate; its docstring records why it exists (a real 2026-06-28 incident where the catalog drifted from the plugin tree).
