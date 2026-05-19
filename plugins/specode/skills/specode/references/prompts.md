# Selectors — 选择器场景常量库的参考视图

每个 phase-gate 节点必须输出**结构化文本选择器**（不是自由叙述）。本文件给出全部 8 个固定场景的标题、选项标签、推荐项、触发 phase；以及三种类型的统一文本骨架。

模型在每个 phase-gate 按 §1-§3 任一类型骨架生成文本；`UserPromptSubmit` hook 在合适时机注入"必须呈现 X 选择器"提示（含场景 key 与具体选项标签），具体内容见 §4 场景常量库。

> ⚠️ 本文件**不再**包含 `spec_choice.py` 命令示例、`[spec-mode:non-interactive]` sentinel、TTY curses 模式说明 ——这些是 0.5.0 之前的旧路径，0.6 已彻底删除。所有选择器都由模型直接输出文本，sentinel 改为 `AWAITING_USER_CHOICE`。

## 1. 类型 A — 单列单选（single-select）

适用：一个问题，互斥选项，单选。绝大多数 phase-gate 用 A。

文本骨架：

```text
=== <选择器标题> ===
当前阶段：<phase>
<1-2 行上下文，如：spec 名 / 刚生成的文档路径 / 摘要>

1. <选项 1 标签>
 <一句话说明>
2. <选项 2 标签>（推荐）
 <一句话说明>
3. <选项 3 标签>
 <一句话说明>
4. Type something
 自定义回复
5. Chat about this
 就这个选择器讨论，不下决定

请回复选项编号或选项名称。
AWAITING_USER_CHOICE
```

约束：

- 「（推荐）」**至多一个**；无强推荐时全部不带括号。
- 正式选项 **2–5 个**（过多说明问题没切清楚，重新拆问题）。
- 末两个保留位**必须**在：`Type something`（自定义文本逃生口）+ `Chat about this`（讨论不下决定）。
- 选项标签用中文动词式短语（`确认` / `查看全文` / `继续沟通` / `强制接管` / `只读查看` / `取消` / `进入下一阶段`），≤8 字。
- 每个选项必须有一行说明。
- 最后一行必须是 `AWAITING_USER_CHOICE` 单独成行。

## 2. 类型 B — 多项串行决策（wizard）

适用：写需求文档前的"需求澄清"——多个**相互独立**但需在同一轮全部回答的子问题。每个子问题是一个 chip-tab；用户在每个 tab 单选后 Submit。

**仅用于 `clarification-wizard` 一个场景。其他 phase-gate 不用类型 B**。

文本骨架：

```text
=== <wizard 标题> ===
当前阶段：<phase>
本 wizard 共 <N> 个决策点，全部确认后 Submit。

▼ 决策点 1/<N>：<子问题 1 标题>
 <1-2 行子问题说明>
 1.1 <选项 A>
 <一句话说明>
 1.2 <选项 B>（推荐）
 <一句话说明>
 1.3 <选项 C>
 <一句话说明>

▼ 决策点 2/<N>：<子问题 2 标题>
 <1-2 行子问题说明>
 2.1 <选项 A>
 <一句话说明>
 2.2 <选项 B>
 <一句话说明>

...

▼ 决策点 <N>/<N>：<子问题 N 标题>
 N.1 <选项 A>
 N.2 <选项 B>
 N.3 Type something

请按格式回复，每行一个决策点：
 1: 1.2
 2: 2.1
 3: N.3 "<自定义文本>"

或回复 `Chat about this` 就 wizard 整体讨论而不下决定。
AWAITING_USER_CHOICE
```

约束：

- 决策点之间**无依赖** —— 若有依赖应拆成两次 wizard（前者 Submit 后再下一个）。
- 决策点个数 **2–5**；每个决策点 **2–4** 个互斥选项。
- 每个决策点末项保留 `Type something`。
- wizard 整体保留 `Chat about this` 作为"先讨论不下决定"逃生口。
- 子问题必须是"是 / 否 / 选哪条"具体问题；不能是开放式叙述。
- 选项之间互斥；如果发现要"可多选"，则该决策点拆错了类型——回到正文继续叙述，不放进 wizard。

## 3. 类型 C — 复选框多选（multi-select）

适用：多个**非互斥**的组合方案，用户可同时勾选多项。

**当前 `iteration-scope` 是唯一使用类型 C 的场景**；其他 phase-gate 不用类型 C。

文本骨架：

```text
=== <选择器标题> ===
当前阶段：<phase>
<1-2 行上下文>

请勾选适用项（可多选）：

 [ ] 1. <选项 1 标签>
 <一句话说明>
 [ ] 2. <选项 2 标签>
 <一句话说明>
 [ ] 3. <选项 3 标签>
 <一句话说明>
 [ ] 4. Type something
 自定义补充

回复格式：
 - 单项：`2`
 - 多项：`1,3` 或 `1 3`
 - 全不选：`none`
 - 自定义：`4 "<自定义文本>"`
 - 整体讨论而不下决定：`Chat about this`

AWAITING_USER_CHOICE
```

约束：

- 至少允许"全不选" —— 多选场景下"不选任何项"是合法答案。
- 选项个数 **2–6**（超过 6 拆 wizard）。
- 不写「（推荐）」标记 —— 多选场景没有"推荐组合"，由用户判断。
- 末项保留 `Type something`。
- 回复格式说明必须固定四行（单项 / 多项 / 全不选 / 整体讨论），格式与上面骨架一致。

## 4. 8 个固定场景常量库

每个场景由 hook 通过 `pending_selector` 字段触发。hook 注入的 `additionalContext` 提示告诉模型"该呈现哪个场景的哪种类型"，模型按 §1–§3 骨架生成文本。

下面列出每个场景的：key / 类型 / 触发 phase / 标题 / 选项标签（**逐字使用**）/ 推荐项。

### (1) `workflow-choice` — 类型 A

- 触发 phase：进入 requirements 前（`intake` 末段或 `clarification-done=1` 后）。
- 标题：**工作流选择**
- 上下文示例：`active spec: <slug>（phase=<phase>）。你即将进入需求/设计文档生成，先决定走哪条工作流。`
- 选项（逐字使用）：
 1. **Requirements first**
 行为优先的新特性：先把 SHALL 写清楚，再补技术设计。
 2. **Technical Design first**
 架构约束已知的新特性：先把 design.md 框架定下来，再反推 requirements。
 3. **Bugfix**
 缺陷修复 / 回归测试：用 bugfix.md（Current/Expected/Unchanged）替代 requirements.md。
- 推荐项：无（让用户主动选）。
- 保留位：4. `Type something` + 5. `Chat about this`。

### (2) `clarification-wizard` — 类型 B

- 触发 phase：`intake`，需求有歧义、写 requirements / bugfix 之前。
- 标题：**需求澄清（共 N 个决策点）**
- 上下文示例：`active spec: <slug>（phase=intake）。源需求摘要：<source-text 前 60 字>。`
- 决策点内容**由你结合用户输入 + `references/templates.md` 章节结构自行生成**（hook 只给框架占位）。每个决策点应锁定 scope / behavior / UX / data / validation / acceptance 之一的阻塞问题。
- 决策点个数 2–5；每点 2–4 个互斥选项。
- 每点末项保留 `Type something`；wizard 整体保留 `Chat about this`。
- 一个决策点都没有（需求足够清晰）→ **不输出 wizard**，直接跳到 `clarification-done`。

### (3) `clarification-done` — 类型 A

- 触发 phase：`intake`，澄清结束（用户刚回答完 wizard）。
- 标题：**需求澄清是否完成？**
- 上下文示例：`active spec: <slug>（phase=intake）。用户刚刚回答了上一轮 wizard 的澄清问题。`
- 选项（逐字使用）：
 1. **进入下一阶段**（推荐）
 用户回答已经覆盖所有阻塞项，可开始写 requirements.md / bugfix.md。
 2. **继续澄清**
 还有未解决的歧义，再发一轮 wizard。
- 推荐项：**1**。
- 保留位：3. `Type something` + 4. `Chat about this`。

### (4) `doc-confirm-*` — 类型 A（4 个变体共享模板）

key 取值：`doc-confirm-requirements` / `doc-confirm-bugfix` / `doc-confirm-design` / `doc-confirm-tasks`。

- 触发 phase：对应文档刚生成 / 更新后（同一 turn）。
- 标题：**<文档名> 文档确认**（例：`requirements.md 文档确认`）。
- 上下文示例：`active spec: <slug>（phase=<phase>）。刚生成/更新的文档：<spec_dir>/<doc-filename>。关键变更摘要：• <3-8 条要点>`。
- 选项（逐字使用）：
 1. **确认**（推荐）
 文档内容符合预期，进入下一 phase。
 2. **查看全文**
 先在 chat 完整 echo 该文档（不进入下一 phase）。
 3. **继续沟通**
 文档需要修改，告诉你具体怎么改。
- 推荐项：**1**。
- 保留位：4. `Type something` + 5. `Chat about this`。
- 选 2 → 完整 echo 文档后**再次**呈现同一 selector + end turn。
- 选 3 → 接收反馈 → 同 turn 改文档 → 重出摘要 + selector。

### (5) `tasks-execution` — 类型 A

- 触发 phase：`tasks.md` 确认后（紧接 `doc-confirm-tasks=1`）。
- 标题：**任务执行选择**
- 上下文示例：`active spec: <slug>（phase=tasks）。tasks.md 已确认。required 任务数：<n_required>，optional 任务数：<n_optional>。`
- 选项（逐字使用）：
 1. **开始 required**
 仅执行 required 任务，逐个推进 `[ ]` → `[~]` → `[x]`。
 2. **开始 required + optional**
 required 完成后顺带处理 optional 任务。
 3. **用 task-swarm 多 agent 并发**
 委派给 task-swarm 编排器，多 coder 并发 + reviewer + validator。
 4. **暂不 coding**
 文档已落地但暂不开始实现。`/specode:end` 关闭会话。
- 推荐项：**1**。
- 保留位：5. `Type something` + 6. `Chat about this`。

### (6) `takeover-options` — 类型 A

- 触发 phase：`/specode:continue <slug>` 命中 LockHeld（exit 4）。
- 标题：**该 spec 已被其他窗口持有**
- 上下文示例：`active spec: <slug>（phase=<phase>）。锁持有者: claude_session_id=<other-id 前 8 位>, 最近 heartbeat: <iso>`。
- 选项（逐字使用）：
 1. **强制接管**
 驱逐对方窗口的锁，本会话成为新锁主；对方下一次写操作会被 verify-lock 拒绝。
 2. **只读查看**
 不持锁，加载文档进入只读模式；所有 Edit/Write 在 SKILL.md 层面被劝阻。
 3. **取消**
 不接管，关闭本次 `/specode:continue`。
- 推荐项：**无**（让用户根据对方是否仍活跃自己判断）。
- 保留位：4. `Type something` + 5. `Chat about this`。

### (7) `acceptance-gate` — 类型 A

- 触发 phase：`acceptance` 阶段最后一项 checklist 跑完。
- 标题：**验收结论**
- 上下文示例：`active spec: <slug>（phase=acceptance）。acceptance-checklist.md 已填写。已通过：<n_pass>，未通过 / 待复核：<n_fail>。`
- 选项（逐字使用）：
 1. **验收通过，进入 iteration**（推荐）
 所有 SHALL 已满足；如有后续调整走 iteration 子循环。
 2. **继续修改**
 仍有未达标项，回到 requirements / design / tasks 调整。
- 推荐项：**1**（当 `n_fail=0` 时）；其他情况无推荐。
- 保留位：3. `Type something` + 4. `Chat about this`。

### (8) `iteration-scope` — 类型 C

- 触发 phase：iteration 子循环开始。
- 标题：**本轮 iteration 调整范围**
- 上下文示例：`active spec: <slug>（phase=iteration）。`
- 选项（逐字使用）：
 1. **改 requirements**
 新增 / 修改 EARS SHALL 条款。
 2. **改 design**
 架构 / 接口 / 数据模型调整。
 3. **改 tasks**
 新增任务或调整已有任务范围。
 4. **重跑测试**
 不改文档，重新验证当前实现。
- 推荐项：无（多选场景不写推荐）。
- 保留位：5. `Type something`。
- 回复格式（**必含**四行）：
 - 单项：`2`
 - 多项：`1,3` 或 `1 3`
 - 全不选：`none`（视为本轮 iteration 取消）
 - 整体讨论而不下决定：`Chat about this`
- 允许"全不选"（视为本轮 iteration 取消）。

## 5. 响应格式约束（铁律）

无论哪种类型，输出选择器的 turn 都必须：

1. **正文 + 状态行 footer 先写**：先把 phase-gate 上下文（文档路径 / 摘要 / 关键变更要点）写完，空一行接状态行 footer（详见 SKILL.md §Status Footer）。
2. **空一行接选择器骨架**：选择器作为独立段，按 §1 / §2 / §3 对应类型骨架。
3. **结尾 sentinel**：选择器段最后一行**必须**是 `AWAITING_USER_CHOICE` 单独成行；前面不要有空格、不要加修饰、不要包代码块。
4. **保留位必须留**：
 - 类型 A：末尾 `Type something` + `Chat about this`。
 - 类型 B：每决策点末项 `Type something` + wizard 整体末段 `Chat about this`。
 - 类型 C：末尾 `Type something` + 回复格式中的 `none` + `Chat about this`。
5. **立即 end turn**：输出 `AWAITING_USER_CHOICE` 之后不再添加任何内容。
6. **不允许把 selector 拆成两轮**：上下文 / 状态行 / selector 必须同一 turn。
7. **不允许跳过 selector 直接进下一步**：哪怕 hook 漏了注入提示，phase-gate 也必须按本文件 §4 场景表呈现 selector。

## 6. Plan-mode 澄清问答示例

用 `clarification-wizard`（类型 B）一次性问完 3 个澄清点。**这是格式样例，不要直接照抄到真实输出**——子问题与选项由你结合用户输入决定。

```text
（正文：spec 名 / 源需求摘要 / 已确认事项概览）

─── spec-mode ─── spec: dark-mode | session: a1b2c3d4 | phase: intake | /specode:end 退出

=== 需求澄清（共 3 个决策点） ===
当前阶段：intake
源需求摘要：用户希望在应用里支持夜间模式，自动跟随系统。

本 wizard 共 3 个决策点，全部确认后 Submit。

▼ 决策点 1/3：颜色主题切换粒度
 应用是仅支持"亮 / 暗"两档，还是允许用户在系统设置之外再单独切换？
 1.1 仅跟随系统
 系统亮则亮、暗则暗，用户在应用内无切换入口。
 1.2 跟随系统 + 应用内手动覆盖（推荐）
 默认跟随系统；用户可在 Settings 选"始终亮 / 始终暗 / 跟随系统"。
 1.3 完全用户控制
 不跟随系统；用户在应用内手动选。
 1.4 Type something

▼ 决策点 2/3：自定义颜色范围
 允许用户自定义主题色吗？
 2.1 不允许，固定两套色板
 2.2 允许选预设色板（≤6 个）
 2.3 允许完全自定义 RGB
 2.4 Type something

▼ 决策点 3/3：是否影响图表 / 图片
 应用中的图表、图标、嵌入图片是否一并切换？
 3.1 一并切换（含图表反色、图标变体）
 3.2 仅切换 UI 颜色，图表 / 图片不动
 3.3 Type something

请按格式回复，每行一个决策点：
 1: 1.2
 2: 2.2
 3: 3.1

或回复 `Chat about this` 就 wizard 整体讨论而不下决定。
AWAITING_USER_CHOICE
```

## 7. Forbidden Phrasing

下列措辞**禁止**出现在面向用户的输出中：

- "够了" / "差不多" / "应该可以了" —— 口语化，改用选择器的正式选项。
- "随便选一个" / "看你" —— 必须给具体推荐项或问具体问题。
- "我猜……" / "我假设……" —— 禁止猜测；走类型 B wizard 澄清。
- "稍等" / "我来想一下" —— 直接输出结果或结束 turn 等回复，不要中间填充语。

## 8. 跨文档引用

- 类型 A / B / C 在 phase-gate 的输出顺序（正文 → 状态行 → selector → sentinel）→ `references/workflow.md` §10 Phase-gate 输出顺序。
- 状态行 footer 模板 → SKILL.md §Status Footer。
- 文档优先纪律与 6 份文档清单 → SKILL.md §Code-Doc Sync Reminders；模板章节 → `references/templates.md`。
- `/specode:continue` 接管完整流程 → `references/lock-protocol.md` §6。
