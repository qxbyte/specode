---
name: specode
description: Specification-driven workflow. All hooks are advisory injections — never blocking. Activates only when the user explicitly invokes `/specode:spec`, `/specode:continue`, `/specode:status`, `/specode:end`, or explicitly asks to use spec mode. Every active-spec turn must respect the phase order, selector format, code-doc sync reminders, and the status footer.
---

# specode — Spec-Mode 工作流

文件优先的规范驱动工作流。`requirements.md` / `bugfix.md` / `design.md` / `tasks.md` / `implementation-log.md` 是事实源；代码改动总是滞后于文档落地。所有 hook 都是**提示式注入**，永远不阻断；hook 注入失败或缺失时，本 SKILL.md 的硬约束仍然完整有效。

## Activation Guard

只在以下任一情况激活：

- 用户当前输入包含 `/specode:spec`、`/specode:continue`、`/specode:status`、`/specode:end`。
- 用户显式说"使用 spec 模式" / "use spec mode"。
- 当前会话的 `~/.specode/sessions/<session_id>.json` 中 `mode=active` 或 `mode=readonly`。

`mode=ended` 或 sessions 文件不存在且无触发条件 → **不要激活**，按普通对话处理。

## Session Lifecycle

持久会话是**唯一**模式（无 `--persist` 标志）。所有写操作必须同时更新 `<spec-dir>/.config.json` + `~/.specode/sessions/<session_id>.json` 两处；CLI 用 tempfile + `os.replace` + `os.fsync` 保证原子性；任一写失败 → CLI 整体 exit 1 + 回滚 + 你在 chat 如实报告，**禁止把 in-memory 半成功状态当成已落地**。

### CLI 调用规约（强制）

所有 specode CLI **必须**通过 `run.sh` 包装调用，脚本路径用 `$CLAUDE_PLUGIN_ROOT`（fallback `$CODEBUDDY_PLUGIN_ROOT`）拼绝对路径——**禁止**假设 cwd 在 scripts 目录，**禁止**裸 `python3 <脚本名>` 调用：

```bash
sh "${CLAUDE_PLUGIN_ROOT:-${CODEBUDDY_PLUGIN_ROOT}}/scripts/run.sh" \
   "${CLAUDE_PLUGIN_ROOT:-${CODEBUDDY_PLUGIN_ROOT}}/scripts/<name>.py" \
   <verb> <args...>
```

`run.sh` 自动探测 `python3 → python → py` 三档解释器并 exec 透传参数；任何 `python3 spec_session.py ...` 形式的裸调用在大多数 cwd 都会 `No such file or directory`。下表中的脚本名是简写，**实际 Bash 工具调用必须套用上面模板**。

四个命令的 CLI 展开：

| 命令 | 解析 → 关键 CLI 调用 |
|---|---|
| `/specode:spec <需求>` | **优先** `-n <slug> <需求>`：slug 直接用作 spec 目录名；**兼容** `<名称>：<内容>` / 纯 `<需求>`（主代理推导 slug）→ `spec_init.py --name <slug> --requirement-name "<显示名>" --source-text "<需求>" --session <session_id>` |
| `/specode:continue [slug]` | 无 slug：`spec_session.py list-specs` 列表 → 用户回编号；有 slug：`spec_session.py acquire --spec <dir> --session <id>`（LockHeld → `takeover-options` 选择器）→ `continue` + `load` → 状态摘要 + 状态行 footer → end turn |
| `/specode:end` | `spec_session.py end --session <id>`（释锁 + mode=ended） |
| `/specode:status` | `spec_session.py status --session <id>` 或 `spec_status.py` |

→ 完整 phase 子步骤、`/continue` 接管流程详见 `references/workflow.md`。

### session_id 的获取

- `SessionStart` hook 注入当前 `session_id`；`UserPromptSubmit` hook 每轮重复注入避免遗忘。
- 调任何 specode CLI 时必须传 `--session <session_id>`。
- 永远**不要** invent session_id、不要从用户输入解析、不要在 chat echo 完整 ID（状态行只取前 8 位）。

## Status Footer

active spec 期间，**每一次响应末尾**必须额外输出状态行，与正文空一行隔开：

```text
─── spec-mode ─── spec: <slug> | session: <session_id 前 8 位> | phase: <phase> | /specode:end 退出
```

只读模式追加 `[只读]` 字段。状态行是机器友好格式（`─── spec-mode ───` 三符号包裹），不允许装饰、不允许 emoji。当本 turn 输出 selector 时，状态行放在 selector **之前**，再空一行接 selector。`mode=ended` 或不在 spec 模式 → **不**输出状态行。

### 新 spec 创建 / 接管的当 turn（hook 尚未刷新）

`/specode:spec <需求>`（`spec_init.py` 成功）、`/specode:continue [slug]`（`acquire`+`load`+`continue` 成功）这两类**当前 turn 内**：sessions/<id>.json 已经被 CLI 改成 `mode=active` + `pending_selector=<对应 selector>`，但 hook 已经在 user-prompt 提交时跑过了、本轮**不会再注入** footer / selector 提醒。主代理**必须主动**完成：

1. chat 简报 2-3 行报告创建 / 接管结果（slug / phase / spec_dir 关键路径）。
2. 按本节 §Status Footer 规则**主动**输出状态行 footer。
3. 按 §Selectors 规则**主动**调 `AskUserQuestion` 呈现对应 `pending_selector`（spec 入口是 `workflow-choice`；continue 接管 ended 会到 `workflow-choice` 或文档 phase 对应 selector，详见 `references/workflow.md`）。

**严禁**说 "使用 `/specode:continue` 进入下一阶段"、"你可以使用 ... 推进"、"下一步请输入 ..." 等让用户再输命令的引导——**spec 已在 active 模式，流程由 selector 推进，不需要用户再输命令**。`/specode:spec` / `/specode:continue` 是**持续流程的入口**，进入之后整条 phase 链由 selector + hook + phase-transition 自动推进，用户只通过 selector 选项做决策、通过 chat 给反馈、通过 `/specode:end` 退出。

下一轮 user-prompt 起 hook 会自动接上 selector / footer / 文档优先 / 模式提醒注入；本规则只 cover **首 turn**（spec_init / acquire 完成的那个 turn）。

## Spec 文档生成（主代理直接写，不 fork subagent）

4 份核心 spec 文档（`requirements.md` / `bugfix.md` / `design.md` / `tasks.md`）由**主代理本身**生成，**不** fork subagent。统一规则：

1. **Read 模板骨架**：`${CLAUDE_PLUGIN_ROOT}/assets/templates/<phase>.md`（4 份模板已就绪；章节大纲 / EARS SHALL 写法 / traceability 标签格式见 `references/templates.md`）
2. **按 `source_text`（用户原始需求）填空**：spec 的 `source_text` 字段（`<spec-dir>/.config.json.source_text`）是用户输入的需求原文，是 single-source-of-truth；按需求展开 SHALL / 设计决策 / 任务粒度，**严禁 hallucinate** "通用 X 系统应该有的需求"。需求模糊时进入 §Pre-requirements Clarification 走 `clarification-wizard`，不要凭空 invent
3. **Write 到 `<spec-dir>/<phase>.md`**：原子覆盖（spec_init 已经创建过空模板，主代理重新 Write 即可），写完按 §Document Output Brevity 报路径 + 3-8 条变更要点 + 未决问题

### 模板章节铁律（0.10.26+）

「填空」是**章节正文**的填空——不是**章节标题**的填空。Read 模板时把所有 `## ` 二级标题视作**结构骨架**，Write 时必须：

- **`## ` 二级标题逐字保留**：不允许改名、合并、拆分、调整顺序、新增不在模板里的章节。`### ` 三级标题里以 `需求 N` / `阶段 N: …` 这种为模板的"动态前缀"——可按需重复（一份需求文档可以有 `### 需求 1` / `### 需求 2` / …），但前缀本身（"需求 "/"阶段 N: "）不可改。
- **可选段可整段删，但不可只留标题留空**：模板里标了 `（可选）` 的二级章节（如 requirements 的 `## 五、非功能 / 约束（可选）`、bugfix 的 `## 九、验收要点（可选）`）若本次不写就**连标题带正文一起删**；只保留 `## X` 标题留空、或写"待补充 / 暂无"——同样算违规。
- **正文不限**：自然语言叙事 / 表格 / Mermaid 图 / EARS 句都行，按 `source_text` 实际内容铺；只是别动 `## ` 标题集合。

**后置兜底**：每次 phase-transition、acceptance 都会跑 `spec_lint.py rule_template_structure`，对 4 份文档做章节集合比对——缺 mandatory / 多 unknown 章节都会报 `[WARN][tmpl]`，hook 把 WARNING 注入下一轮，主代理需要立即修。详细规则与原因见 `references/templates.md` §模板章节铁律。

**前置提醒**：主代理对 4 份核心文档 Write 时，PreToolUse hook 会注入该 phase 的 mandatory/optional/dynamic 名单到上下文——读到这条注入就把名单当 checklist 用，写之前先把章节骨架敲好，再填正文。

理由：0.10.11 起 `spec-writer` subagent 删除（subagent 拿不到主代理的 SKILL 上下文 + 用户原始需求 + 流程状态，hallucinate 通用模板内容）。主代理直接写质量更高、上下文连续、流程更顺。0.10.23 起模板从"机器验收文档"改写为"需求/缺陷描述"，章节结构是模板**唯一的强约束面**——铁律的引入就是为了把这块约束从"模板正文里的说教"（被证明零约束力）搬到 SKILL / lint / hook 三处真正起作用的地方。

`implementation-log.md` 同样由主代理直接追加（发生设计偏离 / 关键决策时）。

## Selectors

每个 phase-gate 节点必须**调用宿主内置 `AskUserQuestion` 工具**呈现选择器；工具自动渲染上下键导航 + 回车提交 + ESC 取消 + "Other" 自定义输入。具体退化路径（自己输出 markdown 列表让用户回复编号、自加 `Type something` 保留位等）见下方 §「看到 hook 注入…」的反例列表。

### `AskUserQuestion` 工具语义（重要 / 关乎流程连续性）

`AskUserQuestion` 是**同步阻塞工具**——调用它后宿主渲染选择器、等用户选项确定后**作为 tool result 返回给你**（你看到的不是 user prompt，是 tool output）。**同一 turn 内继续处理**，无需 end turn：

1. 调 `AskUserQuestion` → 工具阻塞等用户选项
2. 拿到 user 选项 → **同一 turn 内**按 selector 模板的「**用户选定后流程**」段继续推进（每个 selector 模板末尾都有这段）
3. 推完一个 phase 子步骤（写文档 / `phase-transition` / 呈现下一 selector）后**才** end turn 等下一轮 user prompt

**严禁**拿到选项后只 chat 一句 "已选择 X，请下一轮输入 `/specode:continue`" 就 end turn —— `/specode:spec` / `/specode:continue` 是**持续流程的入口**，进入之后整条 phase 链由 selector + hook + phase-transition 自动推进。**用户只通过 selector 选项做决策、通过 chat 给反馈、通过 `/specode:end` 退出**，不需要重复输入命令推进流程。"命令"在 specode 里是流程入口而不是回合触发器。

### 呈现 selector 时禁止 invent / 简化选项

调 `AskUserQuestion` 呈现 selector 时**必须**用 `_selectors.py` 中 `SELECTOR_PROMPTS[<key>]` 的 `question` / `header` / `options[*].label` / `options[*].description` **逐字**传参（索引见 `references/selectors.md` §8 总览表），**禁止**自己改写成 "任务清单已就绪，下一步？" / "开始编码" 这种简化版——hook 注入的 selector 模板里有固定的 question 文本与 N 个固定 label / description，模型读到 "**用户选定后流程**" 段后续要做的是「按这个模板传参调工具」，不是「自己想一个更简短的选择器」。

实际反例：选定 `doc-confirm-design` 后切到 tasks phase，hook 下一轮会注入 `tasks-execution` selector 模板（3 个固定选项：用独立 task-swarm plugin 执行 / 顺序执行 / 暂停或调整 tasks.md）；如果同一 turn 内主代理主动呈现，**必须查 `_selectors.py` SELECTOR_PROMPTS['tasks-execution']** 拿到 3 个固定选项原文，不要 invent 成 2 选项简化版。

### 0.10.27+：selector 参数硬约束（PreToolUse 阻断）

「禁止 invent / 简化选项」从软约束（仅 SKILL 文本提醒）升级为**机器阻断**：

- **PreToolUse hook 拦截 AskUserQuestion** 调用：当 `pending_selector` 存在时，hook 会按 `_selector_skeleton.py:SELECTOR_OUTLINES` 对应条目 verbatim 比对你传入的 `questions` / `options[*].label` / `multiSelect`：
  - **固定 selector**（10 个）：`labels` 集合必须**完全相等**——缺一个 / 多一个 / hallucinate 一个（典型反例：把 `workflow-choice` invent 成 "TDD / RAPID / TASK_SWARM"）→ `exit 2` 阻断 + stderr 显示正确名单
  - **动态 selector**（仅 `clarification-wizard`）：`questions` 数组 2-4 个、每个 `multiSelect=false`、每个 `options ≥ 2`，labels 内容你可以自由生成
- **UserPromptSubmit hook 前置注入** cheat sheet：每轮 `pending_selector` 存在时，hook 把 fixed 的 verbatim 名单 / dynamic 的结构约束作为 `additionalContext` 注入到上下文 —— 看到这条注入就把它当 checklist 直接传参，**不要凭主代理判断改写或翻译**。
- **`description` 字段**：cheat sheet 只列 labels；description 详见 `_selectors.py SELECTOR_PROMPTS[<key>]`，逐字复制对应 description，禁止改写。

PreToolUse 阻断时 stderr 会指出：哪个 label 缺失 / 哪个是未知 hallucinate / 正确集合是什么。修复方式是**重新调一次 `AskUserQuestion`** 传 verbatim 参数，不是绕开 hook。

### phase-transition 不退出 spec 模式

`spec_session.py phase-transition` 切换 spec 的**内部 phase**（intake→requirements→design→tasks→implementation→acceptance→iteration），spec 仍然在 `mode=active`，session 仍然持锁，hook 继续每轮注入「📝 文档优先」「🔄 代码-文档同步」「🪧 状态行 footer」「⛔ 仍处于 spec 模式」四条提醒。**只有 `/specode:end`** 才让 session `mode=ended`、释锁、停 hook。

**严禁**说 "Spec 流程完成！现在退出 spec 模式，开始编码实现" / "spec 已完成" —— `tasks-execution` 选 "用独立 task-swarm plugin" / "顺序执行" 后是 `phase-transition → implementation`，**仍在 spec 模式**，主代理改代码前后必须按 §Code-Doc Sync Reminders 同步 `tasks.md` / `implementation-log.md` / `design.md`。

「spec 流程完成 / 退出 spec 模式」判断**只有一条**才成立：
- 用户主动输入 `/specode:end`

注意：`acceptance-gate` 选「验收通过，进入 iteration」**只是把 phase 切到 iteration 默认停留态**，**不**自动呈现 `iteration-scope`、**不**退出 spec 模式——spec 仍 `mode=active`，session 仍持锁，hook 仍按轮注入四条提醒，直到用户 `/specode:end`。`iteration-scope` 仅在用户后续 turn **显式**提出迭代调整意图时由主代理主动呈现。

三种类型映射到 `AskUserQuestion`：

| 类型 | `AskUserQuestion` 参数形态 | 何时用 |
|---|---|---|
| **A 单列单选** | `questions=[1 question]` + `multiSelect=false` | 一个问题、互斥选项、单选。绝大多数 phase-gate。 |
| **B wizard** | `questions=[2-4 question]` + 每个 `multiSelect=false` | 一组无依赖子问题打包；**仅用于需求澄清问答**。 |
| **C 复选框多选** | `questions=[1 question]` + `multiSelect=true` | 非互斥选项可同时勾选。**仅 iteration-scope 一个场景**。 |

`AskUserQuestion` 工具铁约束（详见工具自身文档）：
- 一次调用 `questions` 数组 **1-4 项**（B 类型 wizard 即占用全部 4 个 slot）。
- 每个 question 的 `options` **2-4 项**；超过 4 项请收敛或拆 wizard。
- `header` 是 chip-tab 短标签（≤12 字符）。

→ 8 个场景（11 keys）的完整 `AskUserQuestion` 调用模板详见 `references/selectors.md`；常量库实现在 `spec_session/_selectors.py` 的 `SELECTOR_PROMPTS` 字典。

### 8 个固定场景

| 场景 key | 类型 | 触发 phase | header |
|---|---|---|---|
| `project-root-choice` | A | spec 创建后选项目实现目录 | 项目目录 |
| `workflow-choice` | A | 进入 requirements 前 | 工作流选择 |
| `clarification-wizard` | B | intake，写需求前 | 需求澄清 wizard |
| `clarification-done` | A | intake 澄清结束 | 澄清完成? |
| `doc-confirm-{requirements,bugfix,design}` | A | 对应文档生成后 | 需求/设计/缺陷确认 |
| `tasks-execution` | A | tasks.md 生成后（含「需要调整」回退） | 执行方式 |
| `takeover-options` | A | `/specode:continue` LockHeld | 接管选项 |
| `acceptance-gate` | A | acceptance 完成 | 验收门 |
| `iteration-scope` | C | iteration 子循环开始 | 迭代范围 |

### 看到 hook 注入"必须呈现 X 选择器"时的硬约束

- 当前 turn **唯一**正确动作 = 调用 `AskUserQuestion` 工具（按提示词给出的 questions / options 逐字传参）→ 工具返回后 turn 自然结束。
- 类型与场景映射固定——不允许自行变换类型（如把 A 改 C）。
- 没看到 hook 提示但自己判断到了 phase-gate（如 hook 失败）→ 仍应按上表查类型并调 `AskUserQuestion`。
- **绝对不允许**的退化路径：
  - ❌ 在 chat 输出 markdown 列表 + "请回复 1/2/3" 让用户回复编号；
  - ❌ 加 `Type something` / `Chat about this` / `AWAITING_USER_CHOICE` 等历史保留位（工具内置 Other / ESC）；
  - ❌ 在 selector 之外多写"也可以聊聊"之类的兜底文本；
  - ❌ 在 `AskUserQuestion` 调用前没在 chat 给出 1-3 行上下文摘要（让用户知道这次选什么）。
- 工具调用前在 chat 可以写一段 ≤8 行的简报（如 doc-confirm 时列 3-8 条关键变更要点）；工具调用本身就是 end turn 触发器，不需要 sentinel。

→ 完整调用模板详见 `references/selectors.md`。

## Code-Doc Sync Reminders

### Spec 文档清单

| 文档 | 何时更新 |
|---|---|
| `requirements.md` / `bugfix.md` | 需求 / 验收标准 / 缺陷范围调整 |
| `design.md` | 架构 / 接口 / 数据模型决策 |
| `tasks.md` | 任务范围 / 状态推进 `[ ]` → `[~]` → `[x]`；末尾自带 `## 测试要点` 节，主代理在 tasks phase 按 SHALL 补几行，供测试人员参考 |
| `implementation-log.md` | 实施期间记录设计偏离 / 关键决策（可选；≥30 字） |

→ 5 份文档的章节模板与 EARS SHALL 写法详见 `references/templates.md`。

### Document-first 响应约束

1. 看到「📝 文档优先提醒（输入侧）」+ 用户输入含需求 / 设计 / 任务 / 验收调整 → 本 turn **优先 Edit 对应文档**，再处理代码。
2. 看到「🔄 代码-文档同步提醒（输出侧）」+ 本 turn 触碰过 Write/Edit 源码 → turn 结束前补齐文档；无法当 turn 补齐则在 chat 显式承诺下一轮第一件事补齐，并立刻做到。
3. 没看到提醒（hook 失败 / 无 active spec）→ 仍保持 document-first 纪律。**这是硬约束，不依赖 hook 触发**。

## Help Fast-path

`/specode:spec -h` / `--help` 由 hook 注入完整帮助文本，要求逐字打印。同样的 fast-path 适用于 `--vault-status` / `--detect-vault` / `--sync-status`：hook 给出预渲染输出，模型只负责 verbatim print，**禁止补充解释**。

## Workflow Selection

进入 requirements 前由 `workflow-choice` 选择器决定走哪条流程：

- **Requirements-first**：行为优先，先 EARS SHALL，再补技术设计。
- **Technical Design-first**：架构约束已知，先 design.md 框架，再反推需求。
- **Bugfix**：缺陷修复，用 `bugfix.md`（Current / Expected / Unchanged）替代 `requirements.md`。

→ 三档判定细则详见 `references/workflow.md` §3。

## Phase Order

`intake → requirements/bugfix → design → tasks → implementation → acceptance → iteration`

每个 phase 切换通过 `spec_session.py phase-transition --from <p> --to <p2>`，自动更新 sessions.phase + 对应 `pending_selector`。

**进入 acceptance phase 时主代理必须调一次 `spec_lint.py --spec <spec-dir>`**（通过 §CLI 调用规约的 run.sh 模板），把 traceability / log / EARS / tmpl 四类 WARNING 列给用户参考，再呈现 `acceptance-gate` 选择器。lint 是 advisory，所有 WARNING `exit 0`，**不阻断**验收决策；但 `[WARN][tmpl]` 章节集合漂移意味着主代理在写文档时背离了模板骨架，验收前最好先回去把章节结构改齐（见 §模板章节铁律）。

→ 每个 phase 的输入 / 产出文档 / 子步骤详见 `references/workflow.md`。

## Document Root Resolution

三层解析（无 fallback；详见 `references/obsidian.md`）：

1. `--root <p>` 或 `SPECODE_ROOT` env（最高优先级）
2. `~/.config/specode/config.json.obsidianRoot`
3. 自动检测已安装 Obsidian vault → `<vault>/spec-in/<os>-<user>/specs`

三层全 miss → `spec_init.py` exit 3 + 引导提示；**不**回退到 cwd / `~/specs` / 项目目录。

`/specode:continue` 查找 spec 时**禁止 Grep 项目目录**——spec 不在项目里。正确流程：`spec_vault.py status` + `spec_session.py list-specs`，详见 `references/obsidian.md` §5.1。

### 首次使用 / auto-detect 命中时的确认（强制）

`spec_init.py` 第 3 层（Obsidian 自检测）是 **silent fallback**——一旦命中
就直接拿来当 `doc_root`，不向用户呈现"我用了哪个 vault"。首次使用时这会让
用户莫名其妙地看到 spec 落在 Obsidian 目录里，跟自己直觉的 cwd / 项目内
位置不一致（典型 case：用户在 git repo 下输入 `/specode:spec ...`，预期 spec
在项目内或被询问，结果 silent 写进了某个 Obsidian vault）。

因此 **commands/spec.md 在调 `spec_init.py` 之前必须先调 `spec_vault.py status`
确认 source**：

- `source = env` 或 `source = config` → 已显式配置，直接调 `spec_init.py`
- `source = auto` 或 `source = none` → **禁止直接调 `spec_init.py`**，按以下
  确认流程走：

  1. **调 `AskUserQuestion`** 三选（中文 label / description）：
     - `"使用检测到的 <doc_root>（持久化到 config，下次不再问）"`
     - `"改用其他绝对路径（你提供，将持久化到 config）"`
     - `"中止本次创建"`
  2. 用户选定后：
     - 前两个选项 → 调 `spec_vault.py set --vault <path>` 写入
       `~/.config/specode/config.json.obsidianRoot`，下次 `source` 就变成
       `config`、不再触发本流程
     - 选"中止" → end turn，**不调** `spec_init.py`
  3. 持久化成功后再进入常规 `spec_init.py` 流程

这样首次使用时用户**显式知道并同意** spec 文档落点，避免 silent fallback
带来的认知 mismatch；后续会话因 config 已写，全程沉默自动用，不打扰。

## Multi-Window + Lock

不同窗口可并行不同 spec；同一 spec 同时只一个会话持锁（lock 字段持有者键 = `session_id`，30 分钟无 heartbeat 视为 stale）。

每次 spec 文档写入前三重校验：specId 匹配 / spec_dir 在 documentRoot 下 / `verify-lock` 返回 ok。`/specode:continue` 命中 LockHeld → 呈现 `takeover-options` 选择器（强制接管 / 只读查看 / 取消）。

→ 锁状态机与接管流程详见 `references/lock-protocol.md`。

## Pre-requirements Clarification（铁律）

**核心约束**：在 `requirements.md` / `bugfix.md` / `design.md` 任何一份**首次生成之前**，对源需求里**任何**不明确的地方——范围边界、行为细节、数据模型、UX 交互、验证规则、验收口径——主代理**必须**主动提出来与用户讨论；**严禁**凭主代理自己的判断假设/补全/invent。

### 触发条件

`workflow-choice` 用户选定工作流后（"Requirements first" / "Technical Design first" / "Bugfix" 任一），**先**做歧义自检：

- 通读 `<spec-dir>/.config.json.source_text`（用户原始需求）+ 用户最近 turn 在 chat 里的补充；
- 自问：要把这份需求落成 EARS SHALL 条款（或 bugfix 的 Current/Expected）/ 写出 design 架构，**有没有任何**会让我编一条规则填空的问题？典型阻塞维度：
  - **scope**：边界在哪？哪些场景包含/排除？
  - **behavior**：触发条件是什么？正常/异常路径如何分？
  - **UX**：交互是同步阻塞还是异步反馈？文案/提示哪里给？
  - **data**：字段类型、唯一性约束、默认值、迁移口径？
  - **validation**：长度上限、格式、特殊字符处理、空值？
  - **acceptance**：怎么算"做完了"？测试用例颗粒度？
- 若 **≥1 个**阻塞维度回答不出来 → 触发 `clarification-wizard`。

### 必须呈现 wizard 的强制场景

- 源需求是**单句口语化描述**（"加个登录功能"/"做个 todo app"）→ 几乎必有 ≥2 个阻塞维度，**默认必呈现**；
- 源需求包含**含糊措辞**（"等"/"诸如此类"/"差不多"/"先简单做下"/"以后再说"）→ 必呈现；
- 历史 turn 用户已经主动列了多个需求点但未给细节 → 必呈现；
- 任何"主代理一边写 SHALL 一边自己脑补 X 是 Y 类型 / Z 是默认值"的冲动 → 都是必呈现信号。

### 唯一例外（允许跳过 wizard）

用户在当前会话**明确放权**才可跳过：
- 显式说"由你决定"/"你看着办"/"随便填"/"按通用做法"/"先 MVP，细节后面再说"等同类表达；
- 或在更早 turn 已给过明确的放权指示（如『需求很粗，你直接按业界默认实现』）。

放权范围**只覆盖用户讲过的部分**；超出范围的歧义仍要先问。**禁止**把用户没说话当成默认放权——沉默 ≠ 同意你 invent。

### 落地动作

- 满足触发条件 → 调 `AskUserQuestion` 呈现 `clarification-wizard`（类型 B，一次性 2-4 个阻塞性子问题，模板见 `_selectors.py` SELECTOR_PROMPTS['clarification-wizard']）；**不写**任何 spec 文档。
- 用户答完 → 立即呈现 `clarification-done`（类型 A）决定再问一轮 / 进入 requirements 生成。
- 跳过 wizard（用户已放权 / 无歧义）→ 在 chat 显式声明放权范围或"已自检无阻塞性歧义"，再走 `phase-transition --to <requirements|bugfix|design>`。
- 写文档时遇到**新**冒出来的歧义点（自检漏掉的）→ **停写**，回头补一轮 wizard；不要边写边猜。

### 反例（违反铁律）

- ❌ "我看用户没说密码强度要求，就按 8 位字母数字混合写吧" → 必须先问。
- ❌ "用户说'添加登录'，我先按邮箱+密码方案写 requirements" → 是不是邮箱登录？是不是密码方案？必须先问。
- ❌ "我把'通常应该有的功能'都写进 SHALL，用户不要的再删" → SHALL 是 ground truth，不是脑暴清单。

→ wizard 详细出题策略详见 `references/workflow.md` §intake；模板见 `_selectors.py` SELECTOR_PROMPTS['clarification-wizard']。

## 任务执行（implementation 阶段）

`tasks-execution` 选择器有三条出路：

- **用独立 task-swarm plugin 执行**：task-swarm 已拆为独立 plugin（不再内置于 specode）。若用户已安装，提示其用该 plugin 的 `/task-swarm` 命令把本 spec 的 `tasks.md` 交给它做多 coder 并发 + reviewer/validator 编排；specode 自身不再 fork 任何 task-swarm subagent。
- **顺序执行**：`phase-transition → implementation`，单 agent 按 `tasks.md` checkbox 顺序逐个推进。
- **暂停 / 调整 tasks.md**：回退到 tasks phase。

无论哪条，主代理改代码前后都必须按 §Code-Doc Sync Reminders 同步 `tasks.md` / `implementation-log.md` / `design.md`，**仍在 spec 模式**直到 `/specode:end`。

## Output Language

User-facing 输出（摘要、问题、确认、状态、错误）——**中文**。

Exceptions（保留英文 / 原样）：技术名、命令、文件路径、代码标识符；代码块内容；本 skill 自身的规则文件（SKILL.md / references）。需求若是英文，生成的 spec 文档可英文；其他 agent 输出（摘要、确认）仍中文。

## Document Output Brevity

写 / 更新 spec 文档时**绝不**在 chat reprint 全文。报告只含：

- 文件路径（一行）
- 3–8 条章节标题或关键变更 bullets
- 未决问题（如有）
- 下一步动作

never paste 文档正文、EARS SHALL 全集、代码块、完整任务列表、设计 rationale。用户显式要求才例外。

## References

- `references/workflow.md` — phase 序列、三档工作流、phase-gate 输出顺序、`/specode:continue` 完整流程
- `references/lock-protocol.md` — 锁状态机、接管三选项、只读模式、被驱逐窗口行为
- `references/obsidian.md` — vault 三层解析、目录约定、`list-specs` 查找流程
- `references/selectors.md` — 三类选择器骨架 + 8 场景常量库 + 输出格式约束
- `references/templates.md` — 5 份文档模板、EARS SHALL 写法、traceability 规范
- `references/iteration.md` — iteration 子循环、文档累积规则

## Session Logging（0.10.0+）

specode 自带**会话日志收集**，默认开启。日志内容：每个 hook 触发、主代理工具调用（Bash / Read / Write / Edit 等）的 tool_input / tool_response、specode CLI 调用的 cmd / argv / exit_code、session phase / lock 状态变化。**用途**：排查"主代理为什么走偏 / 选错 selector / 漏写文档"等问题时回溯现场，配合截图反馈给开发者。

- **存储位置**：`~/.specode/logs/<session_id>.jsonl`（每行一个 JSON event）
- **关闭**：`export SPECODE_LOG=off` 临时关 / 编辑 `~/.config/specode/config.json` 设 `"logging": false` 永久关
- **隐私**：默认 redact 黑名单（`password / api_key / token / secret / authorization / cookie` 等键名匹配 → 占位 `<redacted>`）；字符串字段超 500 字符自动截断；可在 config 加 `redact_keys` 列表扩展
- **回放**：`sh "$CLAUDE_PLUGIN_ROOT/scripts/run.sh" "$CLAUDE_PLUGIN_ROOT/scripts/spec_log.py" replay --session <id>` 按时序打印 events
- **占用查询**：`spec_log.py status` 输出当前 `~/.specode/logs/` 大小；超过 100MB 会提示手动清理 `rm -rf ~/.specode/logs/`

日志收集任何异常都吞并，绝不阻断业务流程。

## Iron Rules

1. **持久会话是唯一模式**——`/specode:end` 是退出口；不退出 hook 永远继续注入。
2. **文档优先**——需求 / 设计 / 任务调整必须先 Edit 对应文档，再代码或解释。
3. **强制双写 + 原子写**——`/specode:spec` / `/specode:continue` / `/specode:end` 任何写入失败视为整命令失败；不接受 in-memory 半成功。
4. **selector 由你按骨架生成 + 必须以 sentinel 结尾 + end turn**——hook 只注入"该呈现哪个"，文本由你写。
5. **状态行 footer 每轮必输**——缺失视为流程违规；hook 不会因此阻断，但用户与下一轮上下文都能察觉。
6. **CLI 调用必须走 `run.sh` 包装 + `$CLAUDE_PLUGIN_ROOT` 绝对路径**——见 §Session Lifecycle "CLI 调用规约"；任何 `python3 spec_session.py ...` 裸调用一律视为流程违规，发现立即换模板重试，不要在错误路径上循环。
7. **`requirements.md` / `bugfix.md` / `design.md` / `tasks.md` 4 份核心文档由主代理直接生成**——Read `${CLAUDE_PLUGIN_ROOT}/assets/templates/<phase>.md` 骨架 + 按 `source_text` 填空 + Write 到 `<spec-dir>/<phase>.md`。`implementation-log.md` 同样由主代理追加。详细规则与 spec-writer subagent 已删除的原因见 §Spec 文档生成。
8. **文档头 `Status` / `Review Status` 字段不允许主代理手改**——这些字段反映 phase / 评审状态，由 `phase-transition` CLI 与 selector 流程驱动改变。主代理写完 `requirements.md` 把 `Status: Requirements Draft` 改成 `Requirements Complete` 是越权（这是 selector 走完后才该发生的事）；保持模板默认值不动。文档**正文**该怎么写还是怎么写，只是别动 frontmatter 状态字段。
