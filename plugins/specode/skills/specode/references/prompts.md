# Selectors — `AskUserQuestion` 调用规范

每个 phase-gate 节点必须**调用 Claude Code 内置 `AskUserQuestion` 工具**呈现选择器；工具自身渲染 chip-tabs / 选项列表 / 上下键导航 / 回车提交 / ESC 取消 / "Other" 自定义输入 UI。模型只负责传参，**绝不**自己输出 markdown 列表让用户回复编号。

本文件给出全部 8 个固定场景的 (类型 → AskUserQuestion 参数)；spec_session.py 的 `SELECTOR_PROMPTS` 字典是这些模板的运行时常量库。

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

## 8 个固定场景常量库

### A1 `workflow-choice` — 工作流选择（类型 A）

**触发**：进入 requirements 前。

```python
AskUserQuestion(questions=[{
    "question": "工作流选择 —— 决定走哪条 spec 流程？",
    "header": "工作流选择",
    "multiSelect": False,
    "options": [
        {"label": "Requirements first",
         "description": "行为优先的新特性：先把 SHALL 写清楚，再补技术设计。"},
        {"label": "Technical Design first",
         "description": "架构约束已知的新特性：先把 design.md 框架定下来，再反推 requirements。"},
        {"label": "Bugfix",
         "description": "缺陷修复 / 回归测试：用 bugfix.md（Current/Expected/Unchanged）替代 requirements.md。"},
    ],
}])
```

### A2 `clarification-done` — 需求澄清是否完成（类型 A）

**触发**：intake 阶段一轮 `clarification-wizard` 之后。

```python
AskUserQuestion(questions=[{
    "question": "需求澄清是否完成？",
    "header": "澄清完成?",
    "multiSelect": False,
    "options": [
        {"label": "进入下一阶段（推荐）",
         "description": "用户回答已覆盖所有阻塞项，可开始写 requirements.md / bugfix.md。"},
        {"label": "继续澄清",
         "description": "还有未解决的歧义，再发一轮 wizard。"},
    ],
}])
```

### A3 `doc-confirm-{requirements,bugfix,design,tasks}` — 文档确认（类型 A，4 个变体共享结构）

**触发**：对应文档生成 / 更新后。

**前置动作**：在 chat 先写 3-8 条**关键变更摘要**（文件路径 + 章节增量 + 未决问题），再调工具。

```python
# 示例：doc-confirm-requirements
AskUserQuestion(questions=[{
    "question": "requirements.md 已生成。下一步？",
    "header": "需求确认",
    "multiSelect": False,
    "options": [
        {"label": "确认（推荐）",
         "description": "文档内容符合预期，进入下一 phase。"},
        {"label": "查看全文",
         "description": "在 chat 完整 echo 该文档（不进入下一 phase）。"},
        {"label": "继续沟通",
         "description": "文档需要修改，告诉你具体怎么改。"},
    ],
}])
```

bugfix / design / tasks 三个变体仅 `question`（"bugfix.md 已生成。下一步？" 等）与 `header`（"缺陷确认" / "设计确认" / "任务确认"）替换；选项结构完全一致。

### A4 `tasks-execution` — 任务执行选择（类型 A）

**触发**：tasks.md `doc-confirm-tasks` 选"确认"之后。

```python
AskUserQuestion(questions=[{
    "question": "tasks.md 已确认，怎么执行？",
    "header": "执行方式",
    "multiSelect": False,
    "options": [
        {"label": "开始 required",
         "description": "仅执行 required 任务，逐个推进 [ ] → [~] → [x]。"},
        {"label": "开始 required + optional",
         "description": "required 完成后顺带处理 optional 任务。"},
        {"label": "用 task-swarm 多 agent 并发",
         "description": "委派给 task-swarm 编排器；多 coder 并发 + reviewer + validator 自动 fix loop。"},
        {"label": "暂不 coding",
         "description": "文档已落地但暂不开始实现；随时 /specode:end 关闭会话。"},
    ],
}])
```

### A5 `takeover-options` — 接管选项（类型 A）

**触发**：`/specode:continue <slug>` 调 `spec_session.py acquire` 返回 LockHeld（exit 4）。

**前置动作**：先在 chat 简报锁持有者 session_id 前 8 位 + 最近 heartbeat 时间。

```python
AskUserQuestion(questions=[{
    "question": "该 spec 已被其他 Claude 窗口持有，怎么处理？",
    "header": "接管选项",
    "multiSelect": False,
    "options": [
        {"label": "强制接管",
         "description": "驱逐对方锁，本会话成为新锁主；对方下一次写操作会被 verify-lock 拒绝。"},
        {"label": "只读查看",
         "description": "不持锁，加载文档进入只读模式；所有 Edit/Write 在 SKILL.md 层面被劝阻。"},
        {"label": "取消",
         "description": "不接管，关闭本次 /specode:continue。"},
    ],
}])
```

**不给"推荐"标记**——让用户根据对方是否仍活跃自己判断。

### A6 `acceptance-gate` — 验收门（类型 A）

**触发**：acceptance phase，acceptance-checklist.md 填写完毕。

```python
AskUserQuestion(questions=[{
    "question": "验收结论？",
    "header": "验收门",
    "multiSelect": False,
    "options": [
        {"label": "验收通过，进入 iteration（推荐）",
         "description": "所有 SHALL 已满足；如有后续调整走 iteration 子循环。"},
        {"label": "继续修改",
         "description": "仍有未达标项，回到 requirements / design / tasks 调整。"},
    ],
}])
```

`n_fail=0` 时推荐选 1；`n_fail>0` 时**不给推荐**。

---

### B1 `clarification-wizard` — 需求澄清问答（类型 B / wizard）

**触发**：intake 阶段，需求有歧义，必须打包多个澄清问题一次性收齐。

**关键**：`questions` 数组直接传 2-4 个 question 对象（每个 question 是一个独立的 chip-tab）。每个 question 的 `multiSelect=false`。子问题与选项**由你结合源需求摘要 + 用户最近输入 + `references/templates.md` 章节结构自行生成**——不要凭空 invent 业务规则。

```python
# 示例：登录页 spec 的澄清 wizard
AskUserQuestion(questions=[
    {
        "question": "登录失败时是否要显示具体原因？",
        "header": "失败提示",
        "multiSelect": False,
        "options": [
            {"label": "区分密码错 / 账号锁",
             "description": "对用户更友好但便于撞库探测。"},
            {"label": "统一显示\"凭据错误\"",
             "description": "更安全，避开账号枚举。"},
        ],
    },
    {
        "question": "是否需要忘记密码入口？",
        "header": "找回密码",
        "multiSelect": False,
        "options": [
            {"label": "需要（邮件链接）", "description": "标准流程；与现有邮件服务集成。"},
            {"label": "需要（短信验证）", "description": "需要短信通道；适用于移动 first。"},
            {"label": "不需要（管理员重置）", "description": "内部系统常见；用户找管理员。"},
        ],
    },
    # ... 最多 4 个
])
```

约束：
- 每个子问题必须是"是 / 否 / 选哪条"的具体问题；禁止开放式叙述（"你怎么想"）。
- 子问题之间**无依赖**——若有依赖应拆成两次 wizard。
- 决策点 ≥ 5 个 → 只保留最阻塞的 4 个，其余记入 requirements.md "待确认问题" 节。
- 如果连一个阻塞决策点都没有（需求清晰）→ **不输出 wizard**，直接跳到 `clarification-done`。

---

### C1 `iteration-scope` — 本轮 iteration 调整范围（类型 C / 多选）

**触发**：用户从 `acceptance-gate` 选了"验收通过"后进入 iteration 子循环，或显式提出迭代调整范围。

```python
AskUserQuestion(questions=[{
    "question": "本轮 iteration 要调整哪些文档/动作？（可多选）",
    "header": "迭代范围",
    "multiSelect": True,   # ← 关键：唯一一个 multiSelect=true 的场景
    "options": [
        {"label": "改 requirements",
         "description": "新增 / 修改 EARS SHALL 条款。"},
        {"label": "改 design",
         "description": "架构 / 接口 / 数据模型调整。"},
        {"label": "改 tasks",
         "description": "新增任务或调整已有任务范围。"},
        {"label": "重跑测试",
         "description": "不改文档，重新验证当前实现。"},
    ],
}])
```

允许用户全不选（视为本轮 iteration 取消）；ESC 等价。

---

## hook 注入与模板替换

`UserPromptSubmit` 的 `on-user-prompt` hook 在 `sessions/<id>.json.pending_selector` 命中某 key 时，把 `SELECTOR_PROMPTS[key]` 拿出来做字符串替换（`<slug>` / `<phase>` / `<spec_dir>` / `<source_text_head>` 等），包入 `additionalContext` 注入。模型看到注入后**唯一动作**：

1. 在 chat 写 ≤8 行上下文简报（doc-confirm 类型必须含 3-8 条变更要点；接管类型必须含锁持有者信息）。
2. 调 `AskUserQuestion` 工具，参数逐字采用 hook 给的模板。
3. 工具返回后按用户选择推进下一步（调对应 CLI 子命令）。

绝不允许：
- ❌ 把模板里的 questions / options 翻译 / 重写 / 加减项。
- ❌ 工具调用之外另开 chat 输出"也可以告诉我..."。
- ❌ 跳过工具直接做下一步（即使你"觉得"用户的意图明确）。

---

## 自主判断（hook 失败时）

按上面 8 个场景对照表选 key → 用对应模板直接调 `AskUserQuestion`。hook 是**提醒**而非**触发**——hook 失效时仍要按本文规范走。

---

## 历史措辞兼容

如果你在 SKILL.md / commands / agents 任意位置看到下列**过时词汇**，视为遗留文档，按本文规范覆盖：

- `AWAITING_USER_CHOICE` sentinel
- "请回复选项编号或选项名称"
- "Type something" / "Chat about this" 保留位
- "请按 §3.7.X 类型骨架输出"
- `spec_choice.py` 命令样例

这些词汇在运行时永远不应再出现；它们的目标都由 `AskUserQuestion` 工具替代。
