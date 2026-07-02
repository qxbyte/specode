---
name: specode
user-invocable: false
description: Lightweight spec-driven workflow orchestration shell. Across the requirements → design → 「执行方式」 → execute → acceptance phases it autonomously calls mature superpowers skills to do the heavy lifting (clarification, design, TDD execution, acceptance), falling back to specode-native when superpowers is absent, and files the three fixed artifacts (requirements.md / design.md / implementation-log.md) into the user's document directory. Activates only when the user invokes `/specode:spec <request>`, `/specode:continue <slug>`, `/specode:list`, or explicitly asks to enter spec mode; otherwise behave as a normal conversation.
---

# specode — orchestration shell

specode is no longer a state machine. It is an **orchestration shell** that handles only its own distinctive value: the spec lifecycle, fixed on-disk artifacts, "documents-as-state" phase inference, the `执行方式` selector, and the task-swarm handoff bridge. The heavy lifting (clarification, design, TDD execution, acceptance) is done by **autonomously calling superpowers** skills in the matching phase; when superpowers is absent, **specode-native fallback** takes over. There is no persistent session file, no multi-window locking, no spec config file, no status-summary footer line, no forced code-doc sync nagging, and no session log collection.

## Activation Guard

Activate only in one of these cases:

- The current user input is `/specode:spec <request>`, `/specode:continue <slug>`, or `/specode:list`.
- The user explicitly says "use spec mode" / "按 spec 流程做" / equivalent.

Otherwise **do not activate**; handle as normal conversation. There is **no session file** — whether a spec is active is inferred entirely from the **current conversation context** (which slug is running this turn) plus the **documents under `<specsRoot>/<slug>/`**. No persistent state file is ever read.

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

All specode CLIs **must** be invoked through the `run.sh` wrapper with an **absolute** plugin-root path. Resolve that root robustly: prefer the host env var `$CLAUDE_PLUGIN_ROOT` (CodeBuddy: `$CODEBUDDY_PLUGIN_ROOT`), but **never assume it is set**. The host only inline-substitutes / exports `${CLAUDE_PLUGIN_ROOT}` for hooks and MCP/LSP subprocesses, and only the bare token — a CLI call emitted from *this skill body* with the `${VAR:-fallback}` form is neither substituted nor run in an env that carries the variable, so it expands **empty** and you get `sh: /scripts/run.sh: No such file or directory`. Always fall back to globbing the plugin cache, and never call a bare `python3 <script>`. Shell state does not persist between Bash calls, so prefix **every** CLI call with this self-contained resolver:

```bash
R="${CLAUDE_PLUGIN_ROOT:-$CODEBUDDY_PLUGIN_ROOT}"; [ -f "$R/scripts/run.sh" ] || R="$(find "$HOME/.claude/plugins/cache" "$HOME/.codebuddy/plugins/cache" -path '*/specode/*/scripts/run.sh' 2>/dev/null | sort -V | tail -1)"; R="${R%/scripts/run.sh}"
sh "$R/scripts/run.sh" "$R/scripts/resolve_root.py" <verb> <args...>
```

The resolver tries the env var first (works wherever the host exports it), verifies `run.sh` actually exists there, and otherwise locates the cached install with `find` and picks the newest version (`sort -V | tail -1`) — never a hard-coded version. Use `find` (not a shell glob): under zsh an unmatched glob aborts with `no matches found`, which `2>/dev/null` does not suppress; `find` stays silent on missing dirs / no match. `run.sh` auto-probes the interpreter (`python3 → python → py`) and execs through the args. The verbs match the `commands/*.md` command files:

| verb | Purpose | exit |
|---|---|---|
| `get-root [--root P]` | Resolve specsRoot (`--root` > env `SPECODE_ROOT` > config.specsRoot) | 0 ok / 3 unconfigured |
| `set-root --root <abs>` | Absolute path, persisted to `~/.config/specode/config.json.specsRoot` | 0 / 1 path not absolute |
| `list-specs [--root P]` | List spec slugs (one per line) under root: subdirs containing any fixed doc (`requirements.md` / `design.md` / `implementation-log.md`) **plus empty subdirs (intake — dir created, requirements not yet written)**; hidden dirs excluded | 0 / 3 unconfigured |
| `resolve-project-root [--cwd P]` | Compute the project_root default (`git rev-parse --show-toplevel` of cwd, else cwd) for the user to confirm | 0 |
| `write-project-root --spec <dir\|file> --root <abs>` | **Single writer** of project_root → spec's requirements.md frontmatter (validates absolute / dir exists / `/Volumes` mounted) | 0 / 1 invalid |
| `read-project-root --spec <dir\|file>` | **Single reader** of project_root from requirements.md frontmatter — all downstream skills use this | 0 / 3 missing field / 4 invalid value |
| `read-defaults [--key K] [--json]` | **v3.4.0 M1/M9**：读 autonomous-mode defaults（优先级 env > `~/.config/specode/defaults.json` > schema）。单 key 返回纯值；`--json` 或不传 `--key` 返 `{value, source}` JSON | 0 / 1 unknown key |
| `write-default --key K --value V` | **v3.4.0 M1/M9**：持久化某个 defaults key。5 个合法 key：`interactive`/`project_root_default`/`execution_mode_default`/`auto_distill`/`specs_root_default`；type + execution_mode whitelist 校验 | 0 / 1 invalid |
| `reset-default --key K \| --all` | **v3.4.0 M1/M9**：删除单 key 或 `--all` 整文件 wipe | 0 / 1 invalid |

**Autonomous-mode defaults rule（v3.4.0 / v0.9 M1/M9）🔒**：每个下面调用 `AskUserQuestion` 的地方，**必须**先 `read-defaults --key <relevant> --json` 拿 effective value + source；当 `interactive == false` 且该 key 的 `source ∈ {env, file}`（即有效值非 schema default）时，**跳过 AskUserQuestion 直接用 default**——这是 autonomous mode / CI 路径。`interactive == true`（schema default）时所有 gate 原样保留 — 默认行为零变化。Mapping：

| SKILL gate | defaults key | env var |
|---|---|---|
| 首次 specsRoot 设置 | `specs_root_default` | `SPECODE_SPECS_ROOT_DEFAULT` |
| project_root 确认（sub-step 2.1） | `project_root_default` | `SPECODE_PROJECT_ROOT` |
| 执行方式 selector（design 后） | `execution_mode_default` | `SPECODE_EXECUTION_MODE`（值：`ask` / `task-swarm` / `superpowers-subagent` / `superpowers-executing` / `specode-self`） |
| distill 末尾 prompt | `auto_distill` | `SPECODE_AUTO_DISTILL` |
| Master switch | `interactive` | `SPECODE_INTERACTIVE` |

调用模式（每个 AskUserQuestion 调用站点适用，伪代码）：

```bash
# 1) Read both keys via resolve_root.py
INTERACTIVE=$(... read-defaults --key interactive --json | jq -r '.value')
DEFAULT_INFO=$(... read-defaults --key <relevant-key> --json)
DEFAULT_VALUE=$(echo "$DEFAULT_INFO" | jq -r '.value')
DEFAULT_SOURCE=$(echo "$DEFAULT_INFO" | jq -r '.source')

# 2) Decide: skip AskUserQuestion if non-interactive + has effective default
if [ "$INTERACTIVE" = "false" ] && [ "$DEFAULT_SOURCE" != "default" ] && [ -n "$DEFAULT_VALUE" ]; then
  use "$DEFAULT_VALUE"  # silent path — autonomous / CI
else
  ask via AskUserQuestion  # original interactive path
fi
```

**project_root single-source-of-truth rule 🔒**: project_root lives in exactly one place — the spec's `requirements.md` frontmatter. specode writes it once (via `write-project-root`); every later phase and downstream skill (distill, task-swarm) obtains it via `read-project-root`. No component re-derives it from cwd / workdir / guessing.

**First-time setup flow**: `get-root` exits 3 → call `AskUserQuestion` to ask the user for the document directory (absolute path, used **verbatim** as the specs root; specode makes no assumptions about its structure and appends nothing) → after the user provides it, persist with `set-root --root <abs>` → never ask again. `project_root` is **inferred per-spec** (default: `git rev-parse --show-toplevel` of cwd, falling back to cwd itself) and **confirmed once via `AskUserQuestion`** before requirements is written — see §requirements phase. Path-resolution details are in `references/obsidian.md`.

## Flow (start → coding complete)

Each phase is annotated "if superpowers is installed, call it / otherwise go native". To decide "installed or not": **first try to call the matching superpowers skill via the `Skill` tool; if it is unavailable (skill missing / call fails), take the native branch.**

1. **specsRoot**: `get-root` (first-time setup if missing) → obtain `<specsRoot>` → `mkdir -p <specsRoot>/<slug>/` (the host agent derives the kebab-case slug from the request).
2. **requirements (clarify + requirements)** — four sub-steps, always in this order:
   1. **`project_root` confirmation (required)**: get the default via `resolve_root.py resolve-project-root` (it returns `git rev-parse --show-toplevel` of cwd, falling back to cwd) and call `AskUserQuestion` **once** with that default pre-selected to let the user confirm or override. Hold the confirmed absolute path; it's needed by sub-steps 2–3 (docs scan + 经验检索) and gets persisted to frontmatter at sub-step 4 **via `resolve_root.py write-project-root`** (the single writer — do not hand-write the frontmatter field).
   2. **Project-level agent docs scan (filesystem-only, no memory recall)**: scan the filesystem for project-level agent-instruction docs and inject them as a `## 项目级约束（CLAUDE.md / AGENT.md）` section into the requirements draft. Scan order (deduped, only existing files): (1) `<project_root>/CLAUDE.md|AGENTS.md|AGENT.md|CODEBUDDY.md`; (2) `<project_root>` 直接父目录下同 4 个文件（覆盖 monorepo workspace 根，如 `wework-ops-assistant/CLAUDE.md` 而下挂子 git repo 自身没有）;(3) 任何已经在用户描述中点名的子目录（如「ops-web 模块」）。Template — **paths only, do not copy content**:

      ```markdown
      ## 项目级约束（CLAUDE.md / AGENT.md）

      > 主 agent 的 system prompt 已自动加载下列文件；这里列出来是为了 design / 执行阶段 / 下游 task-swarm subagent 都能看见这条约束链路。**优先级高于本 spec 的其他描述**：发生冲突时以下列文件为准。

      - `<abs/path/to/CLAUDE.md>`
      - `<abs/path/to/parent/AGENTS.md>`
      ```

      为何 path-only 而非内容拷贝：主 agent 的上下文里已经有完整内容，requirements.md 复制一遍只是冗余 + 内容陈旧风险。task-swarm 0.7.3+ 渲染 task.md 时会按同样的扫描规则把这些路径塞进 coder/reviewer/validator prompt（subagent 进程不自动加载这些文件，必须用路径告知），所以 specode + task-swarm 联合保证从 requirements → design → 执行 → subagent 整条链路都看得见项目级约束。若一个文件都没扫到（典型的 fresh 项目），**整段省略**（不要写「无」之类占位）。

      > **v4.0.0 BREAKING + 新检索（philosophy 不同，勿混为一谈）**: 旧的 P3-1 codemap recall（确定性脚本把历史**内容**当事实自动注入、不省 token）已于 4.0.0 **完全移除**——不再自动从 `.ai-memory/knowledge/` 召回任何东西。**现引入一套全新的、定位优先的经验检索**（下面的 sub-step 3，规格见 `references/retrieval.md`）：注入的是**指针非事实**、由**模型判断**而非脚本召回、默认只读小索引、读 `<project_root>/knowledge-base/`（**非**旧 `.ai-memory/knowledge/`）。要手动把经验沉淀进 `knowledge-base/`，用 `/specode:distill <slug>`（见 §Acceptance 末尾的沉淀提示 + `skills/distill/SKILL.md`）。
   3. **经验检索（若 `<project_root>/knowledge-base/MEMORY.md` 存在）**: 用 sub-step 1 已确认的 `project_root`（此时 requirements.md frontmatter 尚未写，直接用持有的绝对路径，不要 `read-project-root`），按 `references/retrieval.md` 跑**两级 gated** —— Tier-1 读 `knowledge-base/MEMORY.md` 小索引、比对当前需求的页面/字段/域；命中才 Tier-2 读 ≤5 个点全文、用其前后端文件 + 调用链**定位真实代码**。命中结果贴成「**参考定位（非事实来源）**」段，仅作需求分析 / 范围界定的输入：**定位用、非事实**——指针只指向真实代码，**真实代码才是唯一事实**；**不写进 `requirements.md` 的事实结论**。`knowledge-base/MEMORY.md` 不存在（fresh 项目 / 未 distill 过）→ **静默跳过**，不报错、不写空段。引擎细节（两级触发条件 / 注入格式 / schema 契约）见 `references/retrieval.md`，此处不重述。
   4. **draft requirements**:
      - superpowers installed → call `superpowers:brainstorming` (it internally does clarification + requirements exploration + the user-approval gate).
      - not installed → **specode-native**: the host agent clarifies with an `AskUserQuestion` wizard (2-4 blocking sub-questions), then writes per the `assets/templates/requirements.md` template.
      - Relocate the artifact to `<specsRoot>/<slug>/requirements.md` (see §superpowers orchestration + relocation).
      - Write the YAML frontmatter: set `spec_id: <slug>` / `created_at: YYYY-MM-DD`, then persist `project_root` **via `resolve_root.py write-project-root --spec <specsRoot>/<slug> --root <abs from sub-step 1>`** (single validated writer; never hand-write this field).
3. **design (executable plan)**:
   - superpowers installed → call `superpowers:writing-plans` (it internally does self-review + user review).
   - not installed → **specode-native**: break down into `## Task N` + `**Files:**` + `验证: AC-N` + `- [ ]` TDD steps per the `assets/templates/design.md` template.
   - Relocate the artifact to `<specsRoot>/<slug>/design.md`.
   - **经验检索（同 requirements，定位用）**: design 同样按 `references/retrieval.md` 跑**两级 gated** —— 此 phase frontmatter 已写，用 §specsRoot resolver `resolve_root.py read-project-root --spec <specsRoot>/<slug>` 取 `project_root`；命中点的前后端文件 + 调用链用于把每个 `## Task N` 的 `**Files:**` **指向真实文件**（design 的判断仍基于真实代码，检索只缩短定位延迟）。`<project_root>/knowledge-base/MEMORY.md` 不存在 → 静默跳过。

   > **v4.0.0 BREAKING**: 旧的 P3-2 rule-acknowledgement post-check 段（grep `[[rule-*]]` 是否被 design.md 引用并 AskUser 处理偏离）**仍保持移除**——design 阶段不做任何与 `.ai-memory/knowledge/rules/` 关联的 rule 检查。上面新增的 design 检索是**定位用**（把 `**Files:**` 指向真实文件），**不引入任何「规则确认 / 偏离 gate」**——它只产出指针，不产出 must / 规则。
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
   - **沉淀提示（distill, gated by `auto_distill`）**: acceptance 写完后，按 §Autonomous-mode defaults rule 决定是否提示沉淀 —— 用 §specsRoot resolver `resolve_root.py read-defaults --key auto_distill --json` 取 effective value + source；当 `interactive == false` 且有 effective default（`source ∈ {env, file}`）时按 default **静默处理**（不打断），否则 `AskUserQuestion`「是否运行 `/specode:distill <slug>` 把本次经验沉淀进项目 knowledge-base？」。distill 仍是**用户触发的独立命令**（本体行为见 `skills/distill/SKILL.md`，Plan A 已改为项目 `knowledge-base/` primary）；这里只把入口提示重新挂回 acceptance 末尾，**不在主流程里自动跑 distill**。

   > **v4.0.0 → 重新挂回**: 4.0.0 曾把 acceptance 后的自动 distill sub-step 整体移除；现按 `auto_distill` default **把入口提示重新挂回**（见上一条 bullet，遵循既有 autonomous-mode 规则——interactive 时询问、非 interactive 有 effective default 时静默，**非无条件自动执行**）。沉淀目标是项目 `knowledge-base/`（供下次 requirements/design 检索定位），md-only 行为见 `skills/distill/SKILL.md`。

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

`/specode:continue <slug>` (slug required; missing or nonexistent → error + suggest `/specode:list` first): locate `<specsRoot>/<slug>/`, read the directory contents, and infer the phase to resume per this table:

| Directory state | Inferred phase | Resume action |
|---|---|---|
| no `requirements.md` | intake | rerun requirements (brainstorming / native clarification) |
| has `requirements.md`, no `design.md` | design | run design (writing-plans / native Task breakdown) |
| has `design.md` with unchecked `- [ ]` Tasks | executing | resume execution (task-swarm checks run state / superpowers resumes executing-plans / native resumes sequentially) |
| all Tasks in `design.md` checked | complete | run acceptance / report already complete |

`/specode:list` lists every spec under `<specsRoot>` with each one's inferred phase (for looking up slugs / overview; **does not resume**); if there are no specs → suggest `/specode:spec <request>` first.

## task-swarm handoff (zero hard dependency)

task-swarm is a **standalone plugin**; specode has **zero imports** of it and does not know its install path — all calls go through task-swarm's own `/task-swarm:swarm` command (which self-resolves its `$CLAUDE_PLUGIN_ROOT`). After the user picks "delegate":

1. Read this spec's `design.md` Task list + each Task's `**Files:**` → mechanically derive `<specsRoot>/<slug>/pipeline.yml` (task groups / `@writes` files / `needs` topology).
2. **Show the yml summary to the user** (number of task groups / same-file conflicts / topology); init only after the user confirms.
3. Invoke task-swarm's own `/task-swarm:swarm` command to drive its plan → fork → advance → writeback → resolve orchestration until done.
4. Append to `implementation-log.md` throughout; run acceptance after done.

**task-swarm not installed** (`/task-swarm:swarm` unavailable) → fall back on the spot to "specode self-execute" or the superpowers execution path, so the user is never stuck.

## Output Language

User-facing output (summaries, questions, confirmations, status, errors) must be in **Chinese (中文)**.

Keep in English / verbatim: technical names, commands, file paths, code identifiers; the contents of code blocks; this skill's own rule files (SKILL.md / references). If the request is in English, the generated spec documents may be in English; other user-facing summaries / confirmations remain in Chinese.

## Document output brevity

When writing / updating spec documents, **never** reprint the full text in chat. A report contains only: the file path (one line) + 3-8 section-title or key-change bullets + open questions (if any) + the next action. Never paste document body, full Task lists, or design rationale. The only exception is when the user explicitly asks.

## Iron rules

1. **Fixed-artifact invariant**: always produce only the 3 documents `requirements.md` / `design.md` / `implementation-log.md`, with fixed filenames, filed in `<specsRoot>/<slug>/`, independent of the execution engine; after delegating to superpowers you must run the post-relocation check.
2. **specsRoot: read config first, then ask**: call `get-root` on every start; only when missing, `AskUserQuestion` once and `set-root` to write it back, then use it silently thereafter; use the user's directory verbatim as the root, appending nothing.
3. **CLIs must go through run.sh + absolute path**: all specode CLIs go through the `run.sh` wrapper + an absolute plugin-root path resolved by the §specsRoot resolver (env var `$CLAUDE_PLUGIN_ROOT` / `$CODEBUDDY_PLUGIN_ROOT`, falling back to a cache glob — the env var is **not** reliably set in skill-driven Bash calls); never a bare `python3 <script>`, never a hard-coded version path.
4. **执行方式 selector verbatim per example**: the `AskUserQuestion` question / header / options are taken verbatim from `references/selectors.md`, adaptively showing only options for installed engines; never invent / collapse.
5. **Lightweight red line**: no more locking / takeover protocol / state machine; no more status-summary footer line; no more forced code-doc sync nagging; no more paired writes of a persistent session file and spec config file; no more pending-selector markers / phase-transition CLI / log collection. Active state is inferred from the current conversation context + document existence.

## References

- `references/selectors.md` — verbatim `AskUserQuestion` example for the 「执行方式」 selector (the first-time directory-setup question is here too).
- `references/obsidian.md` — specsRoot path resolution and directory conventions.
- `references/superpowers-wiring.md` — the per-phase ↔ superpowers skill mapping, pre-instructions, and post-relocation instructions.
- `references/retrieval.md` — 两级 gated 经验检索注入规格（requirements/design phase 调用）。
