---
description: Use when 准备调 AskUserQuestion 呈现 phase-gate selector，或对 selector 选项 / 文案 / 类型 / Other 兜底有疑问。详述 8 个固定场景模板与三类骨架。
---

# Selectors — `AskUserQuestion` 调用规范

每个 phase-gate 节点必须**调用宿主内置 `AskUserQuestion` 工具**呈现选择器；工具自身渲染 chip-tabs / 选项列表 / 上下键导航 / 回车提交 / ESC 取消 / "Other" 自定义输入 UI。模型只负责传参，**绝不**自己输出 markdown 列表让用户回复编号。

本文件给出 8 个固定场景的**类型骨架 + 总览索引**；完整模板文本是 `spec_session/_selectors.py` 的 `SELECTOR_PROMPTS` 字典字面量（按 key 查找）。`doc-confirm-tasks` 已合并进 `tasks-execution`（见总览表 §A4 行）。

---

## 类型 → AskUserQuestion 参数形态

| 类型 | `questions` 数组 | `multiSelect` | UI 形态 |
|---|---|---|---|
| **A 单列单选** | 1 个 question | `false` | 一个问题 + N 个互斥选项；用户上下键选 + 回车 |
| **B wizard（多项串行决策）** | 2-4 个 question | 每个都 `false` | 顶部 chip-tabs（每个 question 一个 tab）+ 每 tab 单选；全部填完才能 Submit |
| **C 复选框多选** | 1 个 question | `true` | 一个问题 + N 个非互斥选项 + checkbox UI |

公共参数约束（来自 `AskUserQuestion` 工具本身）：
- `questions`: 1-4 项
- 每个 question 的 `options`: 2-4 项
- `question`: 完整问句，结尾建议带 `?`
- `header`: ≤12 字符 chip 短标签
- `description`: 选项的一句话说明（描述含义 / trade-off）
- `preview`: 可选；为有具体 artifact 对比的场景（mockup / 代码片段 / 配置）添加 markdown 渲染预览。**不要**为简单问题写 preview。

公共禁区：
- ❌ 在 selector 文本之外添加 "请回复编号"、"请输入选项名称"、`AWAITING_USER_CHOICE` 等措辞。
- ❌ 手工加 `Type something` / `Chat about this` / `Submit` 等保留位选项——`AskUserQuestion` 工具自动提供 "Other" + ESC。
- ❌ 选项数超过 4 → 收敛 / 重新拆问题；不要硬塞。
- ❌ `multiSelect=true` 配 `preview`（工具仅支持单选时 preview）。

---

## 类型变体 A+：单选 + 预览（side-by-side 布局）

类型 A 的视觉增强变体——为每个 option 额外传 `preview` 字段后，宿主 UI 自动切到**左右分栏**布局：左侧垂直选项列表，右侧 monospace 渲染当前焦点选项的 preview 内容（markdown，支持多行）。用户在选项间上下移动时，右侧 preview 实时切换，方便**逐项对比具体 artifact**。

**何时考虑**：

- 让用户在多份 UI mockup / 代码片段 / 配置 / 示意图之间挑一份。
- 文字描述不够直观、需要"看东西做选择"。

**何时不要用**：

- 简单偏好题（label + description 已经说清楚）——徒增视觉负担。
- 多选场景（`multiSelect=true`）—— 工具仅在单选时支持 preview。
- 候选不存在可视差异（仅取舍而无具象差别）。

**调用形态**：

```text
questions:
  - question: "<具体问题>?"
    header: "<≤12 字>"
    multiSelect: false
    options:
      - label: "<选项 A 名>"
        description: "<选项含义/trade-off>"
        preview: |
          <多行 markdown / ASCII mock / 代码片段 / 配置示例>
      - label: "<选项 B 名>"
        description: "..."
        preview: |
          <对应的另一份 artifact>
```

**当前状态**：8 个固定场景**均未启用** A+ 形态；本节是模板留档，待将来出现"让用户视觉对比 artifact"的 phase-gate 时按本骨架填空即可。如果新增固定场景使用 A+，应同步在 `spec_session.py SELECTOR_PROMPTS` 内加常量并补到下方 8 场景表里。

---

## 8 个固定场景常量库

下列 8 个固定场景（11 个 key，其中 `doc-confirm-{requirements,bugfix,design}`
共享 3 个变体）的**完整提示词文本**是 hook 注入时的运行时常量，单一事实源为
`plugins/specode/scripts/spec_session/_selectors.py` 的 `SELECTOR_PROMPTS`
字典。本文件仅给总览 + 链接，不再 reprint 模板原文——重复维护两份会导致
drift 和歧义。

| § | key | 类型 | 触发 phase | header | _selectors.py 行号 |
|---|---|---|---|---|---|
| §A0 | `project-root-choice` | A | spec 创建后选项目目录 | 项目目录 | L19 |
| §A1 | `workflow-choice` | A | 进入 requirements 前 | 工作流选择 | L68 |
| §A2 | `clarification-done` | A | intake 澄清结束 | 澄清完成? | L157 |
| §A3 | `doc-confirm-requirements` | A | requirements.md 生成后 | 需求确认 | L187 |
| §A3 | `doc-confirm-bugfix` | A | bugfix.md 生成后 | 缺陷确认 | L222 |
| §A3 | `doc-confirm-design` | A | design.md 生成后 | 设计确认 | L257 |
| §A4 | `tasks-execution` | A | tasks.md 生成后（含调整回退） | 执行方式 | L292 |
| §A5 | `takeover-options` | A | `/specode:continue` LockHeld | 接管选项 | L332 |
| §A6 | `acceptance-gate` | A | acceptance 完成 | 验收门 | L365 |
| §B1 | `clarification-wizard` | B | intake，写需求前 | 需求澄清 wizard | L107 |
| §C1 | `iteration-scope` | C | iteration 子循环开始 | 迭代范围 | L398 |

### 阅读模板的方式

完整 `question` / `header` / `options[*].label` / `options[*].description`
原文都在 `SELECTOR_PROMPTS[<key>]` 字符串字面量里——Python triple-quoted
string，markdown 语法直接渲染可读。运行时 hook 命中 `pending_selector`
后会把对应字典值拿出来做占位符替换（`<slug>` / `<phase>` / `<spec_dir>` /
`<source_text_head>` 等）后 emit 到 `additionalContext`，主代理读到该模板
后**逐字**作为 `AskUserQuestion` 参数。

### 调模板时必读的硬约束（与具体 key 无关）

1. **不要**翻译 / 重写 / 简化 `question` 或 `options[*].label` /
   `options[*].description`——主代理读到 hook 注入的 YAML 块，作为
   `AskUserQuestion` 参数**逐字**传入。
2. **不要**在 selector 之外加 `Type something` / `Chat about this` /
   `请回复编号` 等保留位——工具内置 "Other" + ESC。
3. **不要**自行变换类型（如把 A 改 C）—— 类型与 key 的映射在
   上方表格中固定。
4. 每个 selector 模板末尾都有 **「用户选定后流程」** 段，描述
   "user 点完选项后**同一 turn 内**继续做什么"——必须读完那段再决定下一步。

### Drift 守卫

`tests/test_catalog.py` 与 `tests/test_selectors_drift.py` 共同保证：
- `_selectors.py` 的 `SELECTOR_PROMPTS` 字典 11 个 key 与本表 11 行一一对应；
- 本表每个 key 在 `_selectors.py` 中实际存在。

不再做"selectors.md ```text 块与字典字面量 byte-identical"全文对账——单一
事实源就是 `_selectors.py`，本表是它的目录索引。


## hook 注入与模板替换

`UserPromptSubmit` 的 `on-user-prompt` hook 在 `sessions/<id>.json.pending_selector` 命中某 key 时，把 `SELECTOR_PROMPTS[key]` 拿出来做字符串替换（`<slug>` / `<phase>` / `<spec_dir>` / `<source_text_head>` 等），包入 `additionalContext` 注入。

实际注入文本采用三段式 YAML 缩进格式（**目的** / **上下文** / **前置动作** / 工具参数 / **约束** / **用户选定后流程**）。

模型看到注入后**唯一动作**：

1. 在 chat 写 hook 提示中"前置动作"要求的简报内容（doc-confirm 类型必须含 3-8 条变更要点；接管类型必须含锁持有者信息）。
2. 调 `AskUserQuestion` 工具，参数按 hook 给的 YAML 块**逐字**翻译为工具参数（不要翻译选项 label / description）。
3. 工具返回后按用户选择推进下一步（调对应 CLI 子命令）。

绝不允许：
- ❌ 把模板里的 questions / options 翻译 / 重写 / 加减项。
- ❌ 工具调用之外另开 chat 输出"也可以告诉我..."。
- ❌ 跳过工具直接做下一步（即使你"觉得"用户的意图明确）。

---

## 自主判断（hook 失败时）

按上面 8 个场景对照表选 key → 用对应模板直接调 `AskUserQuestion`。hook 是**提醒**而非**触发**——hook 失效时仍要按本文规范走。
