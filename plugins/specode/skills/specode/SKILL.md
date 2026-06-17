---
name: specode
description: Lightweight spec-driven workflow orchestration shell. Across the requirements → design → 「执行方式」 → execute → acceptance phases it autonomously calls mature superpowers skills to do the heavy lifting (clarification, design, TDD execution, acceptance), falling back to specode-native when superpowers is absent, and files the three fixed artifacts (requirements.md / design.md / implementation-log.md) into the user's document directory. Activates only when the user invokes `/spec <request>`, `/spec continue <slug>`, `/spec list`, or explicitly asks to enter spec mode; otherwise behave as a normal conversation.
---

# specode — orchestration shell

specode is no longer a state machine. It is an **orchestration shell** that handles only its own distinctive value: the spec lifecycle, fixed on-disk artifacts, "documents-as-state" phase inference, the `执行方式` selector, and the task-swarm handoff bridge. The heavy lifting (clarification, design, TDD execution, acceptance) is done by **autonomously calling superpowers** skills in the matching phase; when superpowers is absent, **specode-native fallback** takes over. There is no persistent session file, no multi-window locking, no spec config file, no status-summary footer line, no forced code-doc sync nagging, and no session log collection.

## Activation Guard

Activate only in one of these cases:

- The current user input is `/spec <request>`, `/spec continue <slug>`, or `/spec list`.
- The user explicitly says "use spec mode" / "按 spec 流程做" / equivalent.

Otherwise **do not activate**; handle as normal conversation. There is **no session file** — whether a spec is active is inferred entirely from the **current conversation context** (which slug is running this turn) plus the **documents under that slug's directory in obsidian**. No persistent state file is ever read.

## Core invariant 🔒

Regardless of the execution engine (superpowers, task-swarm, or specode-native), a spec's artifacts are **always** the 3 documents below, with **fixed filenames**, **filed in a fixed location** at `<specsRoot>/<slug>/`. The engine only decides *who generates the content*; it never changes the artifacts' shape, naming, or location.

| Document | Fixed filename | Content |
|---|---|---|
| Requirements | `requirements.md` | Prose spec: background / why · scope (in/out) · acceptance `- [ ] AC-N` · open questions. Pure natural language, no formalized clause syntax. |
| Design | `design.md` | superpowers writing-plans executable-plan format: `Goal` / `Architecture` / `Tech Stack` + `## Task N` (each Task carries `**Files:**` file scope, `验证: AC-N` back-reference to requirements, and `- [ ]` TDD steps). |
| Execution log | `implementation-log.md` | Appended during execution: design deviations / key decisions / final acceptance summary. |

Bug fixes do not get a separate `bugfix.md` — write Current / Expected directly in `requirements.md` as prose. `pipeline.yml` is generated only temporarily when delegating to task-swarm; it is not a fixed artifact.

## specsRoot resolution (read on every start; ask only once if missing)

**Every time specode starts, first call `resolve_root.py get-root` via run.sh to read specsRoot.** Only when the config is missing (typically first use) ask the user via `AskUserQuestion`, then immediately `set-root` to write it back to config. Afterwards all sessions use it silently and automatically, never prompting again.

All specode CLIs **must** be invoked through the `run.sh` wrapper, with the script path built as an **absolute path** using `$CLAUDE_PLUGIN_ROOT` (fallback `$CODEBUDDY_PLUGIN_ROOT`). Never assume cwd is the scripts directory, and never call a bare `python3 <script>`:

```bash
sh "${CLAUDE_PLUGIN_ROOT:-${CODEBUDDY_PLUGIN_ROOT}}/scripts/run.sh" \
   "${CLAUDE_PLUGIN_ROOT:-${CODEBUDDY_PLUGIN_ROOT}}/scripts/resolve_root.py" \
   <verb> <args...>
```

`run.sh` auto-probes the interpreter (`python3 → python → py`) and execs through the args. The verbs match `commands/spec.md`:

| verb | Purpose | exit |
|---|---|---|
| `get-root [--root P]` | Resolve specsRoot (`--root` > env `SPECODE_ROOT` > config.specsRoot) | 0 ok / 3 unconfigured |
| `set-root --root <abs>` | Absolute path, persisted to `~/.config/specode/config.json.specsRoot` | 0 / 1 path not absolute |
| `list-specs [--root P]` | List subdirectory names (slugs, one per line) under root that contain `requirements.md` | 0 / 3 unconfigured |

**First-time setup flow**: `get-root` exits 3 → call `AskUserQuestion` to ask the user for the document directory (absolute path, used **verbatim** as the specs root; specode makes no assumptions about its structure and appends nothing) → after the user provides it, persist with `set-root --root <abs>` → never ask again. `project_root` defaults to the **current terminal cwd** (the convention is to `cd` into the project directory before chatting) and is not asked. Path-resolution details are in `references/obsidian.md`.

## Flow (start → coding complete)

Each phase is annotated "if superpowers is installed, call it / otherwise go native". To decide "installed or not": **first try to call the matching superpowers skill via the `Skill` tool; if it is unavailable (skill missing / call fails), take the native branch.**

1. **specsRoot**: `get-root` (first-time setup if missing) → obtain `<specsRoot>` → `mkdir -p <specsRoot>/<slug>/` (the host agent derives the kebab-case slug from the request); `project_root = cwd`.
2. **requirements (clarify + requirements)**:
   - superpowers installed → call `superpowers:brainstorming` (it internally does clarification + requirements exploration + the user-approval gate).
   - not installed → **specode-native**: the host agent clarifies with an `AskUserQuestion` wizard (2-4 blocking sub-questions), then writes per the `assets/templates/requirements.md` template.
   - Relocate the artifact to `<specsRoot>/<slug>/requirements.md` (see §superpowers orchestration + relocation).
3. **design (executable plan)**:
   - superpowers installed → call `superpowers:writing-plans` (it internally does self-review + user review).
   - not installed → **specode-native**: break down into `## Task N` + `**Files:**` + `验证: AC-N` + `- [ ]` TDD steps per the `assets/templates/design.md` template.
   - Relocate the artifact to `<specsRoot>/<slug>/design.md`.
4. **「执行方式」selector**: after design completes, call `AskUserQuestion` to present it (adaptive 4 options, see §执行方式 selector), verbatim per the `references/selectors.md` example.
5. **Execution** (branches by selector choice, all TDD):
   - Delegate to task-swarm (installed) → see §task-swarm handoff.
   - superpowers subagent-driven (installed) → call `superpowers:subagent-driven-development`.
   - superpowers executing-plans (installed) → call `superpowers:executing-plans`.
   - specode self-execute (fallback) → the host agent runs TDD in `design.md` Task order (write failing test → run red → implement → run green), checking off each `- [ ]`.
   - Append to `implementation-log.md` during execution.
6. **Acceptance (coding complete)**:
   - superpowers installed → call `superpowers:verification-before-completion` (optionally also `superpowers:requesting-code-review`).
   - not installed → **specode-native**: the host agent verifies item by item against `design.md` test points / the `AC-N` in `requirements.md`.
   - Say "请验收" in prose and write an acceptance summary in `implementation-log.md`. **There is no formal acceptance-gate selector.**

phase ↔ skill quick map: `requirements` → brainstorming; `design` → writing-plans; execution → subagent-driven-development / executing-plans (the task-swarm path does not use superpowers); acceptance → verification-before-completion / requesting-code-review.

## superpowers orchestration + relocation (belt and suspenders)

superpowers' brainstorming / writing-plans have their own default output paths + filenames (e.g. `docs/superpowers/specs/YYYY-MM-DD-*.md`), so when delegating, specode must actively relocate to guarantee the core invariant holds:

1. **Pre-instruction**: before calling the skill, explicitly tell it the target **absolute path + fixed filename** (superpowers' spec location supports user-preference overrides) — brainstorming's spec output → `<specsRoot>/<slug>/requirements.md`, writing-plans' plan output → `<specsRoot>/<slug>/design.md` (the design format *is* the writing-plans format, so it slots in seamlessly).
2. **Post-relocation (backstop)**: after the skill returns, verify `<specsRoot>/<slug>/<fixed-name>` is in place; if not, `mv` / rename the file the skill actually produced to the fixed location. The invariant holds whether or not the skill honored the pre-instruction.

Which superpowers skill to call when, and how to do pre/post, is detailed in `references/superpowers-wiring.md`.

## Absence fallback (first-class, not a footnote)

specode treats both superpowers and task-swarm as **soft dependencies** (purely runtime, invoked via this SKILL's prose, zero imports). When absent, clarification / planning / execution / acceptance **all sink down to specode itself**, guaranteeing a full start → coding-complete run with only specode installed. The fallback matrix is a **first-class path on par with "call superpowers"**:

| phase | matching plugin | absent → specode-native fallback |
|---|---|---|
| clarify + requirements | `superpowers:brainstorming` | host agent clarifies via `AskUserQuestion` wizard (2-4 questions) + writes per the `requirements.md` template |
| executable plan | `superpowers:writing-plans` | host agent breaks down Tasks per the `design.md` template (Goal/Arch/Stack + `## Task N` + `验证: AC-N` + `- [ ]` TDD steps) |
| execution | task-swarm (concurrent) / `superpowers:executing-plans` | host agent runs TDD in `design.md` Task order (red → green), appending `implementation-log.md` |
| acceptance | `superpowers:verification-before-completion` | host agent verifies item by item against `design.md` test points / `AC-N` + writes acceptance summary |

**How to decide**: the host agent first tries calling the matching superpowers skill via `Skill`; if unavailable, take the native branch. Do not stall or tell the user to install something just because superpowers is absent — pick up natively right away.

## 执行方式 selector (the single fixed per-spec selector, after design completes)

After design is confirmed, call `AskUserQuestion` to present **adaptive 4 options** — **show an option only if its engine is installed**:

1. **委托 task-swarm（多 agent 并发）** — requires task-swarm.
2. **superpowers subagent-driven（每 Task 派全新 subagent + 两阶段评审，推荐）** — requires superpowers.
3. **superpowers executing-plans（当前会话顺序批量 + checkpoint）** — requires superpowers.
4. **specode 自执行（顺序单 agent）** — native fallback, the only option when nothing is installed.

> Options 2/3 are both superpowers skills (built on Claude Code's native Agent/subagent capabilities), not Claude built-in workflows; their ergonomics differ (the former: clean context + per-Task review; the latter: single-session continuous batch).

When presenting, pass question / header / options **verbatim** per the `references/selectors.md` example — do not invent and do not collapse into a shorter option set. This is a single-user scenario with the PreToolUse hard-check removed, so "verbatim per the example" is enforced by this rule alone.

## Continuation (documents-as-state)

`/spec continue <slug>` (slug required; missing or nonexistent → error + suggest `/spec list` first): locate `<specsRoot>/<slug>/`, read the directory contents, and infer the phase to resume per this table:

| Directory state | Inferred phase | Resume action |
|---|---|---|
| no `requirements.md` | intake | rerun requirements (brainstorming / native clarification) |
| has `requirements.md`, no `design.md` | design | run design (writing-plans / native Task breakdown) |
| has `design.md` with unchecked `- [ ]` Tasks | executing | resume execution (task-swarm checks run state / superpowers resumes executing-plans / native resumes sequentially) |
| all Tasks in `design.md` checked | complete | run acceptance / report already complete |

`/spec list` lists every spec under `<specsRoot>` with each one's inferred phase (for looking up slugs / overview; **does not resume**); if there are no specs → suggest `/spec <request>` first.

## task-swarm handoff (zero hard dependency)

task-swarm is a **standalone plugin**; specode has **zero imports** of it and does not know its install path — all calls go through task-swarm's own `/task-swarm` command (which self-resolves its `$CLAUDE_PLUGIN_ROOT`). After the user picks "delegate":

1. Read this spec's `design.md` Task list + each Task's `**Files:**` → mechanically derive `<specsRoot>/<slug>/pipeline.yml` (task groups / `@writes` files / `needs` topology).
2. **Show the yml summary to the user** (number of task groups / same-file conflicts / topology); init only after the user confirms.
3. Invoke task-swarm's own `/task-swarm` command to drive its plan → fork → advance → writeback → resolve orchestration until done.
4. Append to `implementation-log.md` throughout; run acceptance after done.

**task-swarm not installed** (`/task-swarm` unavailable) → fall back on the spot to "specode self-execute" or the superpowers execution path, so the user is never stuck.

## Output Language

User-facing output (summaries, questions, confirmations, status, errors) must be in **Chinese (中文)**.

Keep in English / verbatim: technical names, commands, file paths, code identifiers; the contents of code blocks; this skill's own rule files (SKILL.md / references). If the request is in English, the generated spec documents may be in English; other user-facing summaries / confirmations remain in Chinese.

## Document output brevity

When writing / updating spec documents, **never** reprint the full text in chat. A report contains only: the file path (one line) + 3-8 section-title or key-change bullets + open questions (if any) + the next action. Never paste document body, full Task lists, or design rationale. The only exception is when the user explicitly asks.

## Iron rules

1. **Fixed-artifact invariant**: always produce only the 3 documents `requirements.md` / `design.md` / `implementation-log.md`, with fixed filenames, filed in `<specsRoot>/<slug>/`, independent of the execution engine; after delegating to superpowers you must run the post-relocation check.
2. **specsRoot: read config first, then ask**: call `get-root` on every start; only when missing, `AskUserQuestion` once and `set-root` to write it back, then use it silently thereafter; use the user's directory verbatim as the root, appending nothing.
3. **CLIs must go through run.sh + absolute path**: all specode CLIs go through the `run.sh` wrapper + a `$CLAUDE_PLUGIN_ROOT` (fallback `$CODEBUDDY_PLUGIN_ROOT`) absolute path; never a bare `python3 <script>`.
4. **执行方式 selector verbatim per example**: the `AskUserQuestion` question / header / options are taken verbatim from `references/selectors.md`, adaptively showing only options for installed engines; never invent / collapse.
5. **Lightweight red line**: no more locking / takeover protocol / state machine; no more status-summary footer line; no more forced code-doc sync nagging; no more paired writes of a persistent session file and spec config file; no more pending-selector markers / phase-transition CLI / log collection. Active state is inferred from the current conversation context + document existence.

## References

- `references/selectors.md` — verbatim `AskUserQuestion` example for the 「执行方式」 selector (the first-time directory-setup question is here too).
- `references/obsidian.md` — specsRoot path resolution and directory conventions.
- `references/superpowers-wiring.md` — the per-phase ↔ superpowers skill mapping, pre-instructions, and post-relocation instructions.
