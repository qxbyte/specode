<p align="right"><strong>English</strong> | <a href="./README.zh-CN.md">中文</a></p>

# specode

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./README.md#license)
[![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)](./plugins/specode/.claude-plugin/plugin.json)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-compatible-8A2BE2)](https://github.com/qxbyte/specode#installation)
[![CodeBuddy](https://img.shields.io/badge/CodeBuddy-2.97.1%2B-1E90FF)](https://github.com/qxbyte/specode#installation)

> A lightweight spec-driven workflow plugin for CLI coding agents
> (Claude Code / CodeBuddy).

specode 1.0.0 turns a one-line requirement into a disciplined,
document-first delivery loop — but it carries almost no machinery of
its own. It is an **orchestration shell**: at each phase
(requirements → design → 执行 → 验收) it **delegates the heavy
lifting to [superpowers](https://github.com/obra/superpowers) skills**,
and when superpowers isn't installed it falls back to a first-class
**specode-native** path so the plugin works standalone. Every spec
lands the same **3 fixed documents** in your specs directory.

If you've watched an LLM agent drift mid-task or merge unreviewed
code, specode is the rails — now thin enough to stay out of your way.

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

## Installation

### From GitHub (recommended)

Works with either CLI; the plugin manifest is shared.
CodeBuddy verified on 2.97.1.

```sh
# CodeBuddy
codebuddy plugin marketplace add https://github.com/qxbyte/specode
codebuddy plugin install specode@specode

# Claude Code
claude plugin marketplace add https://github.com/qxbyte/specode
claude plugin install specode@specode
```

For the full superpowers-backed experience, also install the
**superpowers** plugin; for multi-agent parallel execution, also install
**task-swarm** (in this same marketplace). specode runs fine without
either via its native fallbacks.

### One-shot (Claude Code only)

```sh
claude --plugin-url https://github.com/qxbyte/specode/archive/refs/heads/main.zip
```

### Local development

```sh
git clone https://github.com/qxbyte/specode.git
claude    --plugin-dir ./specode/plugins/specode
codebuddy --plugin-dir ./specode/plugins/specode
```

### Uninstall

```sh
claude plugin uninstall specode@specode
claude plugin marketplace remove specode
# optional: wipe user-level config
rm -rf ~/.config/specode
```

### Update

```sh
# Claude Code
claude plugin update specode@specode
claude plugin marketplace update specode

# CodeBuddy
codebuddy plugin update specode@specode
codebuddy plugin marketplace update specode
```

## Usage

specode has exactly three commands.

### 1. Start a spec

```sh
/spec <requirement>
```

`cd` to your project directory first — specode uses the current
terminal cwd as the project root (no prompt). On the **first ever**
run it asks once for your document management directory and remembers
it. The agent then walks the pipeline:

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
/spec continue <slug>
```

`<slug>` is required. specode locates `<specsRoot>/<slug>/` and infers
the phase from the documents present (and the `- [ ]` progress in
`design.md`), then continues from there. Use `/spec list` to find a
slug.

### 3. List specs

```sh
/spec list
```

Lists every spec under `<specsRoot>` with its inferred phase. Overview
only — it does not resume.

## Architecture

```
.claude-plugin/marketplace.json   marketplace manifest (specode + task-swarm)
plugins/specode/
  .claude-plugin/plugin.json      plugin manifest (version 1.0.0)
  hooks/hooks.json                1 advisory SessionStart hook
  commands/spec.md                /spec, /spec continue, /spec list
  scripts/
    resolve_root.py               specsRoot resolution + persistence + list
    spec_hooks.py                 SessionStart discipline injection
    run.sh / run.cmd              python3 → python → py interpreter probe
  skills/specode/
    SKILL.md                      the orchestration shell (all behavior)
    references/
      selectors.md                执行方式 selector verbatim examples
      obsidian.md                 specsRoot path resolution + conventions
      superpowers-wiring.md       phase ↔ superpowers skill mapping
  assets/templates/               requirements.md / design.md /
                                  implementation-log.md seed templates
  tests/                          hermetic pytest suite (resolve_root.py)
```

The companion **task-swarm** plugin (`plugins/task-swarm/`) is a
standalone multi-agent orchestrator that specode optionally hands off
to; see its own README and `CLAUDE.md`.

## Contributing

See [`CONTRIBUTING.md`](./CONTRIBUTING.md) for the stdlib-only
runtime rule, the `run.sh` CLI invocation contract, the advisory-hook
rule, hermetic test conventions, and the release procedure.

## License

MIT
