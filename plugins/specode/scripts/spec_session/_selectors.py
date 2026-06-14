'''spec_session package 内部实现：SELECTOR_PROMPTS 字典 + _fill_selector 模板填充。

`SELECTOR_PROMPTS` 是 11 个 phase-gate selector 的提示词常量库。
hook 注入时按 key 取出对应模板字符串、用 _fill_selector 填入 <slug> / <phase> 等
上下文占位符后 emit 到 additionalContext，让主代理按格式调 AskUserQuestion。

byte-identical 守卫：tests/test_selectors_drift.py 用 regex 解析本文件，把
`SELECTOR_PROMPTS: dict[str, str] = {...}` 字典字面量与 references/selectors.md
逐字对比。新增 / 改 selector 时务必同步 selectors.md，否则 drift test fail。

不要直接运行本文件。stdlib-only。
'''
from __future__ import annotations

from typing import Optional


SELECTOR_PROMPTS: dict[str, str] = {
    "project-root-choice": """## 选择器节点：项目实现目录选择

**目的**：spec 刚创建（pending_selector=project-root-choice），在选工作流之前
**先**确定 coder / 实现 agent 写代码时用哪个目录作为项目根（`project_root`）。
spec 文档目录（`<spec_dir>`）只放 `.md` 文档和实现产物之外的状态，**不是**代码根。

**上下文**：active spec=<slug>，phase=intake。
- 用户启动 Claude Code 的 cwd：`<invocation_cwd>`
- cwd/slug 子目录：`<cwd_subdir>`

**前置动作（chat 简报，≤3 行）**：写一句
"spec 已创建。代码将写到 project_root，**不是** spec 文档目录。
请选择项目目录（cwd 在已有项目里迭代 / cwd/slug 新项目子目录 / 自定义）。"

**调用 `AskUserQuestion` 工具**，**直接传**下列结构（label/description 不要翻译）：

questions:
  - question: "代码写到哪个目录？project_root 决定 coder / 实现 agent 的 cwd"
    header: "项目目录"
    multiSelect: false
    options:
      - label: "cwd（在已有项目里迭代）"
        description: "代码写到 <invocation_cwd>。适用：已 cd 到目标 repo 后启动。"
      - label: "cwd/slug（新项目子目录）"
        description: "代码写到 <cwd_subdir>。适用：cwd 是父目录，要新建项目子目录。"
      - label: "自定义路径"
        description: "用 Other 输入绝对路径。适用：项目目录跟 cwd 完全无关。"

**约束**：
- 调用工具后立即 end turn 等用户选择。
- 不要在 chat 输出 markdown 列表 / 不要让用户回复编号。

**用户选定后流程（同一 turn 内继续，不要 end turn 让用户输命令）**

拿到选项后**本 turn 内**按选项走，调 `spec_session.py set-project-root` CLI 写入：

- 选 "cwd（在已有项目里迭代）" → 调
  `sh "$PLUGIN_ROOT/scripts/run.sh" "$PLUGIN_ROOT/scripts/spec_session.py" set-project-root --spec <spec_dir> --session <id> --root "<invocation_cwd>"`
  （`$PLUGIN_ROOT` 即 `${CLAUDE_PLUGIN_ROOT:-${CODEBUDDY_PLUGIN_ROOT}}`）
- 选 "cwd/slug（新项目子目录）" → 同上但 `--root "<cwd_subdir>"`，CLI 会 mkdir -p 自动创建。
- 选 "自定义路径"（Other 文本）→ 拿用户输入的绝对路径作 `--root`。**禁止**接受相对路径；若用户给的是相对，请先扩展为绝对。

CLI 成功后：
1. `.config.json.project_root` 已写入，`pending_selector` 推进到 `workflow-choice`
2. 立即调 `AskUserQuestion` 呈现 `workflow-choice` selector（不要 end turn 让用户再输命令）
3. 简报一句"已设 project_root=<选定路径>，下一步选工作流"

CLI exit 1（路径不存在 / 不是目录 / 无权限）→ 报错给用户，重新呈现本 selector。
""",
    "workflow-choice": """## 选择器节点：工作流选择

**目的**：用户刚运行 /specode:spec <需求>，已进入 intake 阶段。
在写 requirements.md / bugfix.md / design.md 之前，先决定走哪条 spec 工作流。

**上下文**：active spec=<slug>，phase=<phase>。

**前置动作（chat 简报，≤2 行）**：写一句"接到需求《<source_text_head>...》，请选择工作流。"

**调用 `AskUserQuestion` 工具**，参数完全按下列结构（直接传入，不要翻译/重写选项）：

questions:
  - question: "工作流选择 —— 决定走哪条 spec 流程？"
    header: "工作流选择"
    multiSelect: false
    options:
      - label: "Requirements first"
        description: "行为优先的新特性：先把 SHALL 写清楚，再补技术设计。"
      - label: "Technical Design first"
        description: "架构约束已知的新特性：先把 design.md 框架定下来，再反推 requirements。"
      - label: "Bugfix"
        description: "缺陷修复 / 回归测试：用 bugfix.md（Current/Expected/Unchanged）替代 requirements.md。"

**约束**：
- 调用工具后立即 end turn 等待用户选择。
- 不要在 chat 输出 markdown 列表 / 不要让用户回复编号。
- 宿主工具自动提供 "Other" + ESC 取消，**禁止**自己加 "Type something" / "Chat about this" 保留位。

**用户选定后流程（同一 turn 内继续，不要 end turn 让用户输命令）**

拿到 AskUserQuestion 选项后**先做歧义自检**（SKILL.md §「Pre-requirements Clarification（铁律）」），再决定下一步：

**Step A — 歧义自检（必做）**：通读 `<spec-dir>/.config.json.source_text` + 用户最近 turn 的补充，按 scope / behavior / UX / data / validation / acceptance 六维自问"要写 SHALL 或 design 时，是否任一维度需要我编一条规则填空？"

- **有阻塞性歧义且用户未明确放权** → 立即调 `AskUserQuestion` 呈现 `clarification-wizard`（类型 B，2-4 个子问题），**不**做 phase-transition、**不**写任何文档；用户答完 → 呈现 `clarification-done` 决定再问 / 进入文档生成。
- **无歧义** 或 **用户已明确放权**（说过"由你决定"/"按业界默认"/"先 MVP" 等）→ 在 chat 显式声明"已自检无阻塞性歧义"或"用户已放权 X 部分"，再进 Step B。

**Step B — 按工作流选项生成文档**：

- 选 "Requirements first" → 调 `phase-transition --from intake --to requirements` → 按 SKILL.md §「Spec 文档生成」生成 `requirements.md` → 报路径 + 3-8 条变更要点 → 立即调 `AskUserQuestion` 呈现 `doc-confirm-requirements` selector → end turn 等用户对文档做决策
- 选 "Technical Design first" → 同上但 `--to design` + 生成 `design.md` + 呈现 `doc-confirm-design`
- 选 "Bugfix" → 同上但 `--to bugfix` + 生成 `bugfix.md` + 呈现 `doc-confirm-bugfix`
- "Other"（用户文字输入）→ 按用户文字调整，必要时重新呈现 selector

**写文档过程中冒出新歧义** → 立即**停写**，回到 Step A 补一轮 wizard，不要边写边 invent。

详细 phase 链见 `references/workflow.md` §2-§5；澄清铁律完整定义见 SKILL.md §「Pre-requirements Clarification（铁律）」。
""",
    "clarification-wizard": """## 选择器节点：需求澄清问答（wizard）

**目的**：需求有歧义，必须在写 requirements.md / bugfix.md 之前**一次性**收齐
影响 scope / behavior / UX / data / validation / acceptance 的 2-4 个阻塞性澄清点。

**上下文**：active spec=<slug>，phase=intake。
源需求摘要：<source_text_head>

**前置动作（chat 简报，≤3 行）**：写一句"为避免 invent 业务规则，需要先确认 N 个关键点，请逐一回答。"

**调用 `AskUserQuestion` 工具一次**，`questions` 数组传 **2-4 个 question 对象**
（每个 question 都是独立的 chip-tab，每个 multiSelect=false）。子问题与选项**由你结合源需求摘要 + 用户最近输入 + assets/templates 章节结构自行生成**——不要凭空 invent 业务规则。

参数格式示例（替换为你针对当前需求生成的具体子问题）：

questions:
  - question: "<具体决策点 1 标题，必须是'是/否/选哪条'问题>"
    header: "<≤12 字 chip 标签>"
    multiSelect: false
    options:
      - label: "<选项 A>"
        description: "<一句话解释 + trade-off>"
      - label: "<选项 B>"
        description: "<一句话解释 + trade-off>"
  - question: "<具体决策点 2>"
    header: "<chip 标签>"
    multiSelect: false
    options:
      - label: "<选项 A>"
        description: "..."
      - label: "<选项 B>"
        description: "..."
  # 最多 4 个 question

**约束**：
- 每个子问题必须是"是/否/选哪条"具体问题；禁止开放式叙述（"你怎么想"）。
- 子问题之间**无依赖**——若有依赖应拆成两次 wizard。
- 决策点 ≥ 5 个 → 只保留最阻塞的 4 个，其余记入 requirements.md "待确认问题" 节。
- inputs 不足以构成阻塞决策点 → **不调本工具**，直接进 `clarification-done`。
- 工具自动提供 "Other"，**不要**手工加 "Type something" / "Chat about this" 保留位。
- 调用工具后立即 end turn。

**用户选定后流程（同一 turn 内继续）**

收齐子问题答案后**本 turn 内**：

- 在 chat 简报 "已记录用户 N 个澄清回答"
- 立即调 `AskUserQuestion` 呈现 `clarification-done` selector 判断是否进入 requirements/bugfix 生成
- end turn 等 `clarification-done` 决策
""",
    "clarification-done": """## 选择器节点：需求澄清是否完成？

**目的**：上一轮 wizard 用户已回答；判断是否进入 requirements.md / bugfix.md 生成，
还是再发一轮 wizard 继续澄清。

**上下文**：active spec=<slug>，phase=intake。

**前置动作（chat 简报，≤2 行）**：写一句"已记录用户的 N 个澄清回答，请确认下一步。"

**调用 `AskUserQuestion` 工具**：

questions:
  - question: "需求澄清是否完成？"
    header: "澄清完成?"
    multiSelect: false
    options:
      - label: "进入下一阶段（推荐）"
        description: "用户回答已覆盖所有阻塞项，可开始写 requirements.md / bugfix.md。"
      - label: "继续澄清"
        description: "还有未解决的歧义，再发一轮 wizard。"

**约束**：
- 调用工具后立即 end turn。
- 不要复述选项 / 不要让用户回复编号。

**用户选定后流程（同一 turn 内继续）**

- 选 "进入下一阶段" → 按 spec workflow（看 `<spec-dir>/.config.json.workflow`）调 `phase-transition --from intake --to <requirements|design|bugfix>` → 按 SKILL.md §「Spec 文档生成」生成对应文档 → 报路径+摘要 → 立即呈现 `doc-confirm-<phase>` selector
- 选 "继续澄清" → 重新调 `AskUserQuestion` 呈现 `clarification-wizard` 收新一轮澄清点
""",
    "doc-confirm-requirements": """## 选择器节点：requirements.md 文档确认

**目的**：requirements.md 已生成 / 更新；让用户确认是否进入 design phase，
或者先看全文 / 继续修改。

**上下文**：active spec=<slug>，phase=<phase>。
刚生成的文档：<spec_dir>/requirements.md

**前置动作（chat 简报，≤8 行）**：列出 3-8 条**关键变更要点**（文件路径 + 章节增量 + 未决问题）。
绝对不要 reprint 文档全文。

**调用 `AskUserQuestion` 工具**：

questions:
  - question: "requirements.md 已生成。下一步？"
    header: "需求确认"
    multiSelect: false
    options:
      - label: "确认（推荐）"
        description: "文档内容符合预期，进入设计（design）环节。"
      - label: "查看全文"
        description: "在 chat 完整 echo 该文档（不进入设计环节）。"
      - label: "继续沟通"
        description: "文档需要修改，告诉你具体怎么改。"

**约束**：
- 调用工具后立即 end turn。
- 简报必须在工具调用**之前**输出。

**用户选定后流程（同一 turn 内继续）**

- 选 "确认" → 调 `phase-transition --from requirements --to design` → 按 SKILL.md §「Spec 文档生成」生成 `design.md` → 报路径+摘要 → 立即呈现 `doc-confirm-design` selector
- 选 "查看全文" → 在 chat 完整 echo `requirements.md`（无任何额外解释）→ 重新调 `AskUserQuestion` 呈现 `doc-confirm-requirements` selector
- 选 "继续沟通" → end turn 等用户文字反馈 → 下一 turn 按反馈 Edit `requirements.md` → 报变更要点 → 重新呈现 `doc-confirm-requirements`
""",
    "doc-confirm-bugfix": """## 选择器节点：bugfix.md 文档确认

**目的**：bugfix.md 已生成 / 更新；让用户确认是否进入 design phase，
或者先看全文 / 继续修改。

**上下文**：active spec=<slug>，phase=<phase>。
刚生成的文档：<spec_dir>/bugfix.md

**前置动作（chat 简报，≤8 行）**：列出 3-8 条关键变更要点
（Current / Expected / Unchanged 段落增量 + 复现步骤 + 影响范围）。

**调用 `AskUserQuestion` 工具**：

questions:
  - question: "bugfix.md 已生成。下一步？"
    header: "缺陷确认"
    multiSelect: false
    options:
      - label: "确认（推荐）"
        description: "文档内容符合预期，进入设计（design）环节。"
      - label: "查看全文"
        description: "在 chat 完整 echo 该文档（不进入设计环节）。"
      - label: "继续沟通"
        description: "文档需要修改，告诉你具体怎么改。"

**约束**：
- 调用工具后立即 end turn。
- 简报必须在工具调用**之前**输出。

**用户选定后流程（同一 turn 内继续）**

- 选 "确认" → 调 `phase-transition --from bugfix --to design` → 按 SKILL.md §「Spec 文档生成」生成 `design.md` → 报路径+摘要 → 立即呈现 `doc-confirm-design` selector
- 选 "查看全文" → 在 chat 完整 echo `bugfix.md` → 重新呈现 `doc-confirm-bugfix`
- 选 "继续沟通" → end turn 等用户反馈 → 下一 turn 按反馈 Edit `bugfix.md` → 重新呈现 `doc-confirm-bugfix`
""",
    "doc-confirm-design": """## 选择器节点：design.md 文档确认

**目的**：design.md 已生成 / 更新；让用户确认是否进入 tasks phase，
或者先看全文 / 继续修改。

**上下文**：active spec=<slug>，phase=<phase>。
刚生成的文档：<spec_dir>/design.md

**前置动作（chat 简报，≤8 行）**：列出 3-8 条关键变更要点
（架构图变化 + 接口签名 + 数据模型字段 + 风险 / 偏离）。

**调用 `AskUserQuestion` 工具**：

questions:
  - question: "design.md 已生成。下一步？"
    header: "设计确认"
    multiSelect: false
    options:
      - label: "确认（推荐）"
        description: "文档内容符合预期，进入任务拆分（tasks）环节。"
      - label: "查看全文"
        description: "在 chat 完整 echo 该文档（不进入任务拆分环节）。"
      - label: "继续沟通"
        description: "文档需要修改，告诉你具体怎么改。"

**约束**：
- 调用工具后立即 end turn。
- 简报必须在工具调用**之前**输出。

**用户选定后流程（同一 turn 内继续）**

- 选 "确认" → 调 `phase-transition --from design --to tasks` → 按 SKILL.md §「Spec 文档生成」生成 `tasks.md`（独立 task-swarm plugin 兼容格式：`## 阶段 N:` + `- [ ] N.M ... @writes:... _需求：x.y_`）→ 报路径 + 任务计数 + 主要阶段摘要 → 立即呈现 `tasks-execution` selector
- 选 "查看全文" → 在 chat 完整 echo `design.md` → 重新呈现 `doc-confirm-design`
- 选 "继续沟通" → end turn 等用户反馈 → 下一 turn 按反馈 Edit `design.md` → 重新呈现 `doc-confirm-design`
""",
    "tasks-execution": """## 选择器节点：任务执行选择（合并 0.9.2 旧 doc-confirm-tasks）

**目的**：tasks.md 已生成；让用户在一个选择器里同时完成「确认 tasks.md」+「选择执行方式」+「回退（需要调整）」+「暂不 coding」。0.9.3 起废弃单独的 doc-confirm-tasks 选择器，「需要调整 tasks.md」作为本选择器的回退出口。

**上下文**：active spec=<slug>，phase=tasks。
required 任务数：<n_required>，optional 任务数：<n_optional>。

**前置动作（chat 简报，≤8 行）**：
- 列出**任务计数**（required N 个，optional M 个）
- 列出**主要阶段**与 traceability（`_需求：x.y_` 标签）
- 标注同文件冲突的 stage

**调用 `AskUserQuestion` 工具**：

questions:
  - question: "tasks.md 已生成。怎么执行？"
    header: "执行方式"
    multiSelect: false
    options:
      - label: "用 task-swarm plugin 执行（独立）"
        description: "task-swarm 已拆为独立 plugin；若已安装，用其 `/task-swarm` 命令把本 spec 的 `tasks.md` 交给它（多 coder 并发 + 每个任务组 reviewer/validator）；自动委托衔接见后续里程碑。"
      - label: "顺序执行（同时处理 optional）"
        description: "单 agent 逐个推进 required + optional 任务，[ ] → [~] → [x]。如需只跑 required，可在 Other 输入说明。"
      - label: "暂停 / 调整 tasks.md"
        description: "tasks 不符合预期需要调整，或暂不开始 coding（Other 输入说明具体哪种）。"

**约束**：
- 3 个选项；细化需求（如只跑 required / 跳过某 optional）走 "Other" 输入。
- 调用工具后立即 end turn。
- 简报必须在工具调用**之前**输出。

**用户选定后流程（同一 turn 内继续）**

- 选 "用 task-swarm plugin 执行（独立）" → 提示用户调用独立 task-swarm plugin（手动）
- 选 "顺序执行" → 调 `phase-transition --from tasks --to implementation` → 单 agent 按 `tasks.md` checkbox 顺序逐个推进
- 选 "暂停 / 调整 tasks.md" → end turn 等用户反馈：若是调整 → 下一 turn Edit `tasks.md` → 重新呈现本 selector；若是暂停 → 留在 tasks phase，随时 `/specode:end` 退出或后续 `/specode:continue <slug>` 续接
""",
    "takeover-options": """## 选择器节点：接管选项

**目的**：/specode:continue <slug> 命中 LockHeld；让用户选择强制接管 / 只读查看 / 取消。

**上下文**：active spec=<slug>，phase=<phase>。
锁持有者: <other_id_short>（前 8 位），最近 heartbeat: <last_heartbeat>。

**前置动作（chat 简报，≤2 行）**：写一句"spec '<slug>' 已被 <other_id_short> 在 <last_heartbeat> 持有，请选择处理方式。"

**调用 `AskUserQuestion` 工具**：

questions:
  - question: "该 spec 已被其他会话窗口持有，怎么处理？"
    header: "接管选项"
    multiSelect: false
    options:
      - label: "强制接管"
        description: "驱逐对方锁，本会话成为新锁主；对方下一次写操作会被 verify-lock 拒绝。"
      - label: "只读查看"
        description: "不持锁，加载文档进入只读模式；所有 Edit/Write 在 SKILL.md 层面被劝阻。"
      - label: "取消"
        description: "不接管，关闭本次 /specode:continue。"

**约束**：
- **不给"（推荐）"标记**——让用户根据对方是否仍活跃自己判断。
- 调用工具后立即 end turn。

**用户选定后流程（同一 turn 内继续）**

- 选 "强制接管" → 调 `acquire --force --spec <dir> --session <id>` → `load` → `continue` → 报告 "已强制接管：<slug>" + 状态行 footer
- 选 "只读查看" → **跳** `acquire`（不持锁）→ `load --spec <dir>` 拿数据 → 写 `sessions/<id>.json.mode=readonly` → 报告 "已只读加载：<slug>（持锁者：<other_id>）" + footer（含 `[只读]` 标记）
- 选 "取消" → end turn，不调任何 CLI
""",
    "acceptance-gate": """## 选择器节点：验收门

**目的**：acceptance phase；tasks.md 全部 `[x]` 完成后，判断是否通过验收进入 iteration，或者回到 requirements / design / tasks 继续修改。

**上下文**：active spec=<slug>，phase=acceptance。
任务完成度：<n_done>/<n_total>。

**前置动作（chat 简报，≤3 行）**：
- 列出 tasks.md 完成度（done/total）。
- 调用 `spec_lint.py --spec <spec_dir>` 把 WARNING 列出来（traceability / log / EARS 三类，如有）。
- 若 tasks.md 末尾 `## 测试要点` 章节存在，简述本次需要测试人员关注的要点；测试要点是参考信息，不参与验收门判定。

**调用 `AskUserQuestion` 工具**：

questions:
  - question: "验收结论？"
    header: "验收门"
    multiSelect: false
    options:
      - label: "验收通过，进入 iteration（推荐）"
        description: "所有任务完成；如有后续调整走 iteration 子循环。"
      - label: "继续修改"
        description: "仍有未完成任务 / lint WARNING 需处理，回到 requirements / design / tasks 调整。"

**约束**：
- n_done == n_total 时推荐选 1；否则**移除"（推荐）"标记**。
- 调用工具后立即 end turn。

**用户选定后流程（同一 turn 内继续）**

- 选 "验收通过，进入 iteration" → 调 `phase-transition --from acceptance --to iteration` → 在 chat 用 1-2 行告知"已进入 iteration（已交付常驻态），如需新一轮调整请直接提出（如『加个 X 功能』『改一下 Y 需求』），或 `/specode:end` 退出 spec 模式" → **end turn**。**不要**自动呈现 `iteration-scope`——它只在用户后续显式提出迭代调整时才呈现。
- 选 "继续修改" → end turn 等用户文字反馈 → 下一 turn 根据反馈判断回到哪个 phase：改需求 → `phase-transition --to requirements`；改设计 → `--to design`；改任务 → `--to tasks`；改实现 → 留 implementation phase Edit 代码 + 更新 `tasks.md`
""",
    "iteration-scope": """## 选择器节点：iteration 调整范围（多选）

**目的**：用户在 iteration 默认停留态**显式**提出了新一轮调整意图（如"加个 X 功能"/"改下 Y 需求"/"重跑下测试"）；确定本轮 iteration 调整哪些文档/动作。

**触发条件（必须满足之一才可呈现）**：
- 用户当前 turn 在 chat 里明确表达了下一轮迭代/调整意图；
- **不**在 `acceptance-gate` 选「验收通过」后自动呈现——验收通过只切 phase 到 iteration，end turn 等用户提；
- **不**在 `/specode:continue` 一个 phase=iteration 的 spec 时自动呈现——恢复后停在 chat 等用户提。

**上下文**：active spec=<slug>，phase=iteration。

**前置动作（chat 简报，≤2 行）**：用 1-2 行复述用户提出的调整意图（如"你提到要加 X 功能 + 调整 Y 验收标准，请勾选本轮调整范围"），让用户确认 selector 选项与意图对得上。

**调用 `AskUserQuestion` 工具**，注意 **multiSelect=true**：

questions:
  - question: "本轮 iteration 要调整哪些文档/动作？（可多选）"
    header: "迭代范围"
    multiSelect: true
    options:
      - label: "改 requirements"
        description: "新增 / 修改 EARS SHALL 条款。"
      - label: "改 design"
        description: "架构 / 接口 / 数据模型调整。"
      - label: "改 tasks"
        description: "新增任务或调整已有任务范围。"
      - label: "重跑测试"
        description: "不改文档，重新验证当前实现。"

**约束**：
- multiSelect=true（**唯一**使用类型 C 复选框的场景）。
- 允许用户全不选（视为本轮 iteration 取消）；ESC 等价。
- 调用工具后立即 end turn。

**用户选定后流程（同一 turn 内继续）**

iteration-scope 是多选（multiSelect=true），用户可勾选 1-4 项或全不选。按 phase 序列从前往后依次处理勾选项（同一 turn 内串行 phase-transition + 文档生成 + 对应 `doc-confirm-*` selector）：

- 勾 "改 requirements" → `phase-transition --from iteration --to requirements` → 按 SKILL.md §「Spec 文档生成」修订 `requirements.md` → 呈现 `doc-confirm-requirements`（修订版）
- 勾 "改 design" → `--to design` + 修 `design.md` → 呈现 `doc-confirm-design`
- 勾 "改 tasks" → `--to tasks` + 修 `tasks.md` → 呈现 `tasks-execution`
- 勾 "重跑测试" → 留 iteration phase，执行 `tasks.md` 末尾验证命令 / `## 测试要点` 节中的检查项 + 报告结果
- 全不选 / ESC → 视为本轮 iteration 取消，留 acceptance phase，告知用户随时 `/specode:end` 或再次进入 acceptance-gate
""",
}


def _fill_selector(key: str, ctx: dict[str, str]) -> Optional[str]:
    tpl = SELECTOR_PROMPTS.get(key)
    if not tpl:
        return None
    out = tpl
    for k, v in ctx.items():
        out = out.replace(f"<{k}>", str(v))
    return out
