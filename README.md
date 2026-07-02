<p align="right"><strong>English</strong> | <a href="./README.zh-CN.md">中文</a></p>

# pluginhub

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./README.md#license)
[![specode](https://img.shields.io/badge/specode-5.1.2-blue.svg)](./plugins/specode/.claude-plugin/plugin.json)
[![task-swarm](https://img.shields.io/badge/task--swarm-0.10.1-blue.svg)](./plugins/task-swarm/.claude-plugin/plugin.json)
[![obsidian-wiki](https://img.shields.io/badge/obsidian--wiki-2.0.0-blue.svg)](./plugins/obsidian-wiki/.claude-plugin/plugin.json)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-compatible-8A2BE2)](https://github.com/qxbyte/pluginhub#installation)
[![CodeBuddy](https://img.shields.io/badge/CodeBuddy-2.97.1%2B-1E90FF)](https://github.com/qxbyte/pluginhub#installation)
[![Tests](https://img.shields.io/badge/pytest-255%20cases-success)](./plugins/task-swarm/tests)

> qxbyte's plugin marketplace for CLI coding agents
> (Claude Code / CodeBuddy).

**pluginhub** is a small plugin marketplace: add it once, then install
any plugin it hosts. More plugins will land here over time.

## Plugins

| Plugin | Version | What it does |
| --- | --- | --- |
| **specode** | 5.1.2 | A lightweight spec-driven **workflow** — orchestration shell that delegates each phase to [superpowers](https://github.com/obra/superpowers) skills (first-class native fallback) and lands 3 fixed docs per spec. **v5.1.2**: distill polish — `ensure-gitignore` skips in a non-git project with no existing `.gitignore` (no stray file); new `knowledge.py copy-to` verb (one-step dual-landing: copy cases/navigation + rebuild the dest's MEMORY) now used by distill Step 5; navigation `来源` keeps the origin slug (reusing specs listed in body). **v5.1.1**: validation-driven fixes — distill runs `design-unchecked` before sedimenting (warns if the spec isn't fully executed, so knowledge points don't reference unbuilt code); dedup navigation points against MEMORY before writing; retrieval emphasizes semantic relevance over tag-overlap. **v5.1.0**: reintroduces experience retrieval/injection on a new "pointers-not-facts" footing — new stdlib `knowledge.py` (ensure-gitignore/memory-rebuild/memory-validate); distill now emits **atomic case/navigation knowledge-points** to the project's `<project_root>/knowledge-base/` (cases/ + navigation/ + a MEMORY index, gitignored), optionally copied to Obsidian; new `references/retrieval.md` two-tier gated retrieval wired into the requirements/design phases (inject pointers not facts, default reads only the small index, ≤5 docs on hit); acceptance re-hooks the distill prompt via the existing `auto_distill` default. **v5.0.1**: the `distill` skill is now `user-invocable: false` (hides the bare `/distill` + the duplicate `/specode:distill`, leaving one clean command entry); distill is now **md-only** (dropped the dead `--format yml|both` + `codemap knowledge write` path); purged all remaining `.ai-memory`/codemap doc references and removed the obsolete recall section from the requirements template. **v5.0.0 BREAKING**: commands dropped the redundant `specode-` prefix — `/specode:spec` / `/specode:continue` / `/specode:list` / `/specode:distill` (were `/specode:specode-*`); the `distill` skill dir + name were renamed to `distill`; the `specode` orchestration skill is now `user-invocable: false` so the bare `/specode` no longer shows in the slash menu (still auto-activates via its commands). Preserved AI-EDS-era features: project-level `CLAUDE.md` / `AGENT.md` filesystem scan injected as `## 项目级约束` section (痛点 #14 方案 D), SessionStart cache-vs-marketplace drift hint (M8), autonomous-mode defaults — 5 schema keys + 5 `SPECODE_*` env vars + `read-defaults` / `write-default` / `reset-default` verbs (M1+M9). **v4.0.0 BREAKING**: removed memory-injection pipeline — P3-1 `codemap recall` injection / P3-2 rule-acknowledgement post-check / acceptance auto-distill prompt all dropped; round 1/2 baseline showed the recall round-trip did not net save token. `distill` skill v4 rewritten as a **manual-only Obsidian organizer** — `/specode:distill <slug>` writes md (default) to `/Volumes/External HD/Obsidian/Notes/11-KnowledgeBase/<slug>/`, no `.ai-memory/` writes. To restore v3 behaviour: `git checkout backup/specode-v3.4.0-task-swarm-v0.9.2`. |
| **task-swarm** | 0.10.1 | Multi-agent **orchestration** driven by a `pipeline.yml`: semantic task groups with cross-group concurrency, fork coders, per-group reviewer + validator loops. **v0.10.1**: the `task-swarm` orchestration skill is now `user-invocable: false` so the bare `/task-swarm` no longer shows in the slash menu (the `/task-swarm:swarm` command is unchanged). Preserved AI-EDS-era features: frontmatter-first `project_root` + registry-based run lookup (0.7.x), `## 项目级约束（必读）` section + `_PROJECT_AGENT_DOCS.md` inbox sentinel (0.7.3 + 0.7.4), lifecycle group with `init` dedupe (`--on-existing {error/resume/abort-old/force-new}` flag) + `run.pipeline_end_validator` (0.8.0 + 0.8.1), M2 `run-loop` auto-driver (0.8.1), task.md `## 开发纪律 (范式参考)` section listing superpowers skill names as paradigm identifiers (0.9.0–0.9.2). **v0.10.0 BREAKING**: removed `_ingest_lessons.py` + `cmd_resolve` auto-ingest + `--no-ingest` flag — `cmd_resolve` no longer writes `<project_root>/.ai-memory/knowledge/cases\|pitfalls/*.yml`. To restore v0.9.x behaviour: `git checkout backup/specode-v3.4.0-task-swarm-v0.9.2`. See [`plugins/task-swarm/`](./plugins/task-swarm). |
| **obsidian-wiki** | 2.0.0 | Maintain an Obsidian LLM-Wiki with three skills: deterministic structure layer (`wiki-struct`: Home tree / READMEs / partition pages), content curation (`wiki-curate`: ingest / curate / lint), unified orchestrator (`wiki-orchestrate`). Generic code + per-vault config in the home-dir registry `~/.config/obsidian-wiki/` (falls back to `<vault>/.wiki/config.json`). **v2.0.0 BREAKING**: the spec-distill skill was extracted into specode's `/specode:distill`. See [`plugins/obsidian-wiki/`](./plugins/obsidian-wiki). |

`## Installation` covers the whole marketplace; the other sections
(Highlights, Usage, Architecture) document **specode**, the flagship
plugin. For **task-swarm**, see its sources and `CHANGELOG` under
[`plugins/task-swarm/`](./plugins/task-swarm); for **obsidian-wiki**,
see its own `README.md` / `AGENTS.md` under
[`plugins/obsidian-wiki/`](./plugins/obsidian-wiki).

## Highlights

- **Orchestration shell, not a state machine.** specode delegates each
  phase to a mature superpowers skill (`brainstorming` → `writing-plans`
  → `subagent-driven-development` / `executing-plans` →
  `verification-before-completion`). It owns only what's uniquely its
  own: the spec lifecycle, fixed-doc landing, and the task-swarm bridge.
- **Works standalone (native fallback).** No superpowers? specode runs
  the clarify / plan / execute / verify loop itself with `AskUserQuestion`
  wizards and sequential TDD. The native path is a first-class peer, not
  an afterthought.
- **3 fixed documents, fixed names, fixed location.** Every spec
  produces `requirements.md` / `design.md` / `implementation-log.md`
  under `<specsRoot>/<slug>/` — whatever engine generated the content.
  Bug fixes use prose in `requirements.md` (no `bugfix.md`).
- **Documents are the state.** No persistent session files, no locks,
  no status footer, no logging. "Which phase am I in?" is inferred from
  which fixed docs exist plus the `- [ ]` checkbox progress in
  `design.md`.
- **One adaptive selector.** After `design.md` is confirmed, an
  `AskUserQuestion` selector offers up to 4 execution paths — only the
  ones whose engine is installed: 委托 task-swarm / superpowers
  subagent-driven / superpowers executing-plans / specode 自执行.
- **First-run specsRoot setup.** On first use specode asks once for your
  document directory and uses it **verbatim** as the specs root, then
  persists it to `~/.config/specode/config.json.specsRoot` and never
  asks again.
- **One lightweight hook.** A single advisory `SessionStart` hook reminds
  the agent specode is available. No blocking, no per-turn machinery.
- **Parallel execution is a separate plugin.** Pick "委托 task-swarm" and
  specode reads `design.md`, derives a `pipeline.yml`, and hands off to
  the standalone **task-swarm** plugin (zero import).
- **Project-level constraints follow the chain.** specode + task-swarm
  (AI-EDS v0.9 痛点 #14 方案 D, preserved into v4.0.0 / v0.10.0) scan
  `CLAUDE.md` / `AGENT.md` / `AGENTS.md` / `CODEBUDDY.md` at
  `<project_root>`, its parent directory, and any subdir touched by
  `@writes`, and surface the matched **absolute paths** (not content)
  into both `requirements.md` (`## 项目级约束`) and every coder /
  reviewer / validator `task.md` (`## 项目级约束（必读）`).
  `_PROJECT_AGENT_DOCS.md` inbox sentinel reinforces the hard
  constraint. Fixes the silent drop where independent subagent
  processes never see the host agent's auto-loaded instruction files.
- **Autonomous mode / CI friendly (opt-in).** Set
  `SPECODE_INTERACTIVE=false` plus relevant `SPECODE_PROJECT_ROOT` /
  `SPECODE_EXECUTION_MODE` / `SPECODE_AUTO_DISTILL` /
  `SPECODE_SPECS_ROOT_DEFAULT` env vars (or persist via
  `resolve_root.py write-default --key X --value Y`), and every
  `AskUserQuestion` gate that would normally block in CI / long-running
  sessions skips silently with the configured default. Schema default
  is `interactive=true` so existing installs see **zero behaviour
  change** — only opt-in users get the autonomous path.
- **Location-oriented knowledge, not memory injection.** The old AI-EDS
  memory-injection pipeline (specode P3-1 `codemap recall` + P3-2
  rule-check + acceptance auto-distill, plus task-swarm `cmd_resolve`
  auto-ingest writing `.ai-memory/knowledge/*.yml`) was removed in
  v4.0.0 / v0.10.0 after baseline experiments (3 cases) showed the
  recall round-trip did not net save token; neither plugin reads /
  writes `.ai-memory/knowledge/`. **v5.1.0 reintroduced retrieval on a
  deliberately different, pointers-not-facts footing**: run
  `/specode:distill <slug>` manually to sediment atomic
  case / navigation knowledge points into the project's own
  `<project_root>/knowledge-base/` (gitignored; optional copy to an
  Obsidian dir you specify), and the requirements / design phases run a
  two-tier gated retrieval over its small `MEMORY.md` index to locate
  real code faster — real code stays the sole source of truth, and
  execution / task-swarm receive zero injection.
  To restore v3.4.0 / v0.9.2 behaviour: `git checkout backup/specode-v3.4.0-task-swarm-v0.9.2`.

## Installation

> 📌 **Marketplace name is `pluginhub` (the repo name), not `qxbyte` (the owner name).**
> All install / uninstall commands use `<plugin>@pluginhub`, e.g. `specode@pluginhub` and `task-swarm@pluginhub`. Using `@qxbyte` will fail with `Marketplace "qxbyte" not found`. Cached plugins are also stored under `~/.claude/plugins/cache/pluginhub/<plugin>/<version>/` — useful when troubleshooting which version is actually loaded.

### From GitHub (recommended)

Works with either CLI; the plugin manifest is shared.
CodeBuddy verified on 2.97.1.

```sh
# CodeBuddy
codebuddy plugin marketplace add https://github.com/qxbyte/pluginhub
codebuddy plugin install specode@pluginhub

# Claude Code
claude plugin marketplace add https://github.com/qxbyte/pluginhub
claude plugin install specode@pluginhub
```

For the full superpowers-backed experience, also install the
**superpowers** plugin. For multi-agent parallel execution, also install
**task-swarm** from this same marketplace (no second `marketplace add`
needed) — specode delegates the execution phase to it when installed, and
self-executes sequentially otherwise:

```sh
# Claude Code
claude plugin install task-swarm@pluginhub
# CodeBuddy
codebuddy plugin install task-swarm@pluginhub
```

specode runs fine without either via its native fallbacks.

### One-shot (Claude Code only)

```sh
claude --plugin-url https://github.com/qxbyte/pluginhub/archive/refs/heads/main.zip
```

### Local development

```sh
git clone https://github.com/qxbyte/pluginhub.git
claude    --plugin-dir ./pluginhub/plugins/specode
codebuddy --plugin-dir ./pluginhub/plugins/specode

# add task-swarm too if you want delegated multi-agent execution
claude --plugin-dir ./pluginhub/plugins/specode --plugin-dir ./pluginhub/plugins/task-swarm
```

### Uninstall

```sh
claude plugin uninstall specode@pluginhub
claude plugin uninstall task-swarm@pluginhub   # if installed
claude plugin marketplace remove pluginhub
# optional: wipe user-level config (and legacy ~/.specode state)
rm -rf ~/.specode ~/.config/specode
```

### Update

```sh
# Claude Code
claude plugin update specode@pluginhub
claude plugin marketplace update pluginhub

# CodeBuddy
codebuddy plugin update specode@pluginhub
codebuddy plugin marketplace update pluginhub
```

## Usage

specode has exactly four commands.

### 1. Start a spec

```sh
/specode:spec <requirement>
```

`cd` to your project directory first — specode derives the default
project root from the cwd (`git rev-parse --show-toplevel`, falling
back to cwd) and asks you to confirm it once per spec. On the **first
ever** run it also asks once for your document management directory
and remembers it. The agent then walks the pipeline:

1. **requirements** — clarify + write `requirements.md` (via
   `superpowers:brainstorming`, or a native `AskUserQuestion` wizard).
2. **design** — produce an executable plan `design.md` (via
   `superpowers:writing-plans`, or native Task breakdown).
3. **执行方式 selector** — pick how to execute (adaptive 4 options; see
   Highlights).
4. **execute** — run the plan with TDD, appending to
   `implementation-log.md`.
5. **verify** — check against the design's test points and the
   `requirements.md` `AC-N` items, then ask you to accept.

All output lands under `<specsRoot>/<slug>/` as the 3 fixed documents.

### 2. Resume a spec

```sh
/specode:continue <slug>
```

`<slug>` is required. specode locates `<specsRoot>/<slug>/` and infers
the phase from the documents present (and the `- [ ]` progress in
`design.md`), then continues from there. Use `/specode:list` to
find a slug.

### 3. List specs

```sh
/specode:list
```

Lists every spec under `<specsRoot>` with its inferred phase. Overview
only — it does not resume.

### 4. Distill knowledge (off-pipeline)

```sh
/specode:distill <slug> [--target-dir <abs-path>]
```

Manually sediments a finished spec (plus the current agent context)
into atomic **case / navigation knowledge points** under the project's
own `<project_root>/knowledge-base/` (cases/ + navigation/ + a
`MEMORY.md` index, gitignored), optionally copying them to an Obsidian
directory. The requirements / design phases later retrieve these as
**location pointers, never facts** — real code stays the sole source
of truth. Never auto-run; the acceptance phase only offers it.

## Architecture

```
.claude-plugin/marketplace.json   marketplace manifest (specode + task-swarm + obsidian-wiki)
plugins/specode/
  .claude-plugin/plugin.json      plugin manifest
  hooks/hooks.json                1 advisory SessionStart hook
  commands/spec.md        /specode:spec (new spec)
  commands/continue.md    /specode:continue <slug>
  commands/list.md        /specode:list
  commands/distill.md     /specode:distill <slug> (off-pipeline sedimenter)
  scripts/
    resolve_root.py               specsRoot / project_root / defaults CLI
    knowledge.py                  knowledge-base index CLI (MEMORY rebuild/validate/copy-to)
    spec_hooks.py                 SessionStart discipline injection
    run.sh / run.cmd              python3 → python → py interpreter probe
  skills/specode/
    SKILL.md                      the orchestration shell (all behavior)
    references/
      selectors.md                执行方式 selector verbatim examples
      obsidian.md                 specsRoot path resolution + conventions
      superpowers-wiring.md       phase ↔ superpowers skill mapping
      retrieval.md                two-tier gated experience retrieval spec
  skills/distill/
    SKILL.md                      /specode:distill behavior (case/navigation points)
    references/                   breakdown heuristics + doc templates
  assets/templates/               requirements.md / design.md /
                                  implementation-log.md seed templates
  tests/                          hermetic pytest suite (resolve_root.py + knowledge.py)
```

The companion **task-swarm** plugin (`plugins/task-swarm/`) is a
standalone multi-agent orchestrator that specode optionally hands off
to; see its own `skills/task-swarm/SKILL.md` and `CHANGELOG.md`. The
**obsidian-wiki** plugin (`plugins/obsidian-wiki/`) is self-contained
and documented by its own `README.md` / `AGENTS.md`.

## Contributing

See [`CONTRIBUTING.md`](./CONTRIBUTING.md) for the stdlib-only
runtime rule, the `run.sh` CLI invocation contract, the advisory-hook
rule, hermetic test conventions, and the release procedure.

## License

MIT
