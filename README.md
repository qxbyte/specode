<p align="right"><strong>English</strong> | <a href="./README.zh-CN.md">中文</a></p>

# specode

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./README.md#license)
[![specode](https://img.shields.io/badge/specode-0.11.0-blue.svg)](./plugins/specode/.claude-plugin/plugin.json)
[![task-swarm](https://img.shields.io/badge/task--swarm-0.3.0-blue.svg)](./plugins/task-swarm/.claude-plugin/plugin.json)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-compatible-8A2BE2)](https://github.com/qxbyte/specode#installation)
[![CodeBuddy](https://img.shields.io/badge/CodeBuddy-2.97.1%2B-1E90FF)](https://github.com/qxbyte/specode#installation)
[![Tests](https://img.shields.io/badge/pytest-329%20cases-success)](./plugins/specode/tests)

> A specification-driven workflow plugin for CLI coding agents
> (Claude Code / CodeBuddy).

specode turns a one-line requirement into a disciplined,
document-first delivery loop. The agent is walked through a fixed
phase pipeline — **requirements → design → tasks → implementation →
acceptance** — with five Markdown documents
(`requirements.md` / `bugfix.md` / `design.md` / `tasks.md` /
`implementation-log.md`) as the single source of truth. At every
phase gate the user picks the next move through an in-chat
selector; in between, advisory hooks keep the agent on script
without ever blocking a tool call.

If you've watched an LLM agent drift mid-task, lose context across
windows, or merge unreviewed code, specode is the rails.

## Highlights

- **Document-first discipline.** Every requirement begins with a spec
  doc, not code. Hooks remind the agent to consult and update docs
  before — and after — touching code.
- **Advisory hooks, never blocking.** All seven hooks `exit 0`. They
  inject guidance into the model's context (status footer, phase
  selector, doc-sync reminder, silent lock heartbeat) but never abort
  a tool call. No mid-flow "hook denied" surprises.
- **Session-bound state.** Every host session has its own state file
  at `~/.specode/sessions/<session_id>.json` (atomic writes). Open
  three CLI windows in parallel and they stay disambiguated.
- **Phase-gate selectors.** At each decision point the agent renders
  one of three selector skeletons (single-select / wizard /
  multi-select) drawn from 11 fixed scenarios — you steer, the
  agent executes.
- **Parallel task execution is a separate plugin.** specode emits
  `tasks.md` in a task-swarm-compatible format (`## 阶段 N:` stages +
  `@writes` / `@depends-on` tags); multi-agent orchestration now lives
  in the standalone **task-swarm** plugin, which you can hand the
  approved `tasks.md` to from the `tasks-execution` selector.
- **Obsidian-aware doc root.** Three-tier resolution
  (env > config > auto-detected Obsidian vault) keeps your specs in
  your knowledge base, not scattered across project folders.
- **Status footer on every active turn.** You always know where you
  are:
  ```
  ─── spec-mode ─── spec: <slug> | session: <8-prefix> | phase: <p> | /specode:end to exit
  ```
- **Per-session JSONL logs** for "why did the agent go off-script"
  forensics, with automatic secret redaction and 500-char string
  truncation.
- **Main agent writes spec docs directly.** No subagent fork — the
  main agent reads template skeletons from `assets/templates/<phase>.md`
  and fills them against your original requirement text, keeping
  context and conversational state intact (a previous `spec-writer`
  subagent was removed in 0.10.11 precisely because it couldn't
  see the main agent's context and tended to hallucinate generic
  template content).

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

The same marketplace also ships **task-swarm**, a standalone multi-agent
orchestrator. specode delegates the execution phase to it when installed
(otherwise specode self-executes sequentially). Install it from the same
marketplace — no second `marketplace add` needed:

```sh
# Claude Code
claude plugin install task-swarm@specode
# CodeBuddy
codebuddy plugin install task-swarm@specode
```

### One-shot (Claude Code only)

```sh
claude --plugin-url https://github.com/qxbyte/specode/archive/refs/heads/main.zip
```

### Local development

```sh
git clone https://github.com/qxbyte/specode.git
claude    --plugin-dir ./specode/plugins/specode
codebuddy --plugin-dir ./specode/plugins/specode

# add task-swarm too if you want delegated multi-agent execution
claude --plugin-dir ./specode/plugins/specode --plugin-dir ./specode/plugins/task-swarm
```

### Uninstall

```sh
claude plugin uninstall specode@specode
claude plugin uninstall task-swarm@specode   # if installed
claude plugin marketplace remove specode
# optional: wipe user-level state
rm -rf ~/.specode ~/.config/specode
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

### 1. Configure your document root (first run)

specode stores spec docs under `<doc_root>/specs/<slug>/`. Bind a
root once and it's remembered:

```sh
/specode:spec --set-vault <path>     # use an Obsidian vault
/specode:spec --set-root <path>      # any folder works (equivalent)
/specode:spec --detect-vault         # list detected Obsidian vaults
/specode:spec --vault-status         # show current root + resolution source
```

If unset, specode auto-detects an Obsidian vault, otherwise asks at
spec creation.

### 2. Start a spec

```sh
/specode:spec -n <slug> <requirement>     # recommended: explicit slug
/specode:spec <requirement>               # or let the agent derive one
/specode:spec <name>: <requirement>       # or set display name + requirement
```

`-n` keeps the slug verbatim (Unicode allowed — Chinese, Japanese,
emoji), only forbidding filesystem-dangerous characters. The
slug-less form lets the agent infer one, which is convenient but
less predictable.

After creation, the agent walks you through two consecutive
selectors:

1. **project-root-choice** — where generated code should live (decoupled
   from the doc directory).
2. **workflow-choice** — start from `requirements.md`, jump to
   `bugfix.md` for a fix flow, etc.

From here, every model turn ends with the status footer and (at
phase gates) a selector for the next step.

### 3. Manage sessions

```sh
/specode:continue [slug]    # resume — current session or a named spec
/specode:status             # show mode / phase / lock / pending selector
/specode:end                # end the session (docs preserved)
```

State is keyed by host `session_id`, so each terminal window keeps
its own thread.

### 4. Run tasks (sequential, or hand off to task-swarm)

Once `tasks.md` is approved, the `tasks-execution` selector offers
three paths: sequential single-agent execution, a pause/adjust loop,
or handing the `tasks.md` to the standalone **task-swarm** plugin for
multi-agent parallel execution. task-swarm used to ship inside
specode; it has since been extracted into its own plugin. specode
still emits `tasks.md` in the task-swarm-compatible format, so the
handoff is just pointing the other plugin at the approved file.

### 5. Inspect session logs

specode writes per-session event streams to
`~/.specode/logs/<session_id>.jsonl` (hooks, agent tool calls,
phase / lock transitions). Use them when debugging
"why did the agent skip a phase":

```sh
sh "$CLAUDE_PLUGIN_ROOT/scripts/run.sh" \
   "$CLAUDE_PLUGIN_ROOT/scripts/spec_log.py" replay --session <id>
```

Secrets are redacted by default (`password / api_key / token / …`)
and strings truncate at 500 chars. Extend
`~/.config/specode/config.json.redact_keys` to add more.

### 6. Global bypass (debug only)

```sh
SPECODE_GUARD=off   # short-circuit all hooks to exit 0
SPECODE_LOG=off     # disable session logging
```

## Architecture

```
.claude-plugin/marketplace.json   single-plugin marketplace manifest
plugins/specode/
  .claude-plugin/plugin.json      plugin manifest
  hooks/hooks.json                7 advisory hook handlers
  commands/                       /specode:spec, :continue, :end,
                                  :status
  scripts/                        spec_vault / spec_init /
                                  spec_session / spec_lint /
                                  spec_status / spec_log
  skills/specode/                 SKILL.md + references/
  assets/templates/               seed templates
  tests/                          pytest suite
```

## Contributing

See [`CONTRIBUTING.md`](./CONTRIBUTING.md) for the stdlib-only
runtime rule, hook safety contract (advisory only, never `exit 2`),
and test conventions.

## License

MIT
