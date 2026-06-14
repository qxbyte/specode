---
description: Use when 准备生成或修订 requirements.md / bugfix.md / design.md / tasks.md / implementation-log.md。详述 5 份文档的章节模板、EARS SHALL 写法、traceability 规范。
---

# Spec Document Templates

5 份 spec 文档的**写作约束 + EARS / traceability 规范**。完整章节骨架的
**单一事实源**是 `${CLAUDE_PLUGIN_ROOT}/assets/templates/<phase>.md`——主
代理按 SKILL.md §「Spec 文档生成」Read 那份骨架 + 按 `source_text` 填空。
本文件**不重复骨架**，只列每份文档独有的写作约束。

## 0. 命名约定

| 文件 | 用途 | 骨架文件 | 互斥关系 |
|---|---|---|---|
| `requirements.md` | 需求-first / design-first 工作流的需求文档 | `assets/templates/requirements.md` | 与 `bugfix.md` 互斥 |
| `bugfix.md` | bugfix 工作流的问题描述 | `assets/templates/bugfix.md` | 与 `requirements.md` 互斥 |
| `design.md` | 技术设计文档 | `assets/templates/design.md` | — |
| `tasks.md` | 任务拆分 + 进度 + traceability + 末尾 `## 测试要点`（tasks phase 按 SHALL 顺手补给测试人员参考） | `assets/templates/tasks.md` | — |
| `implementation-log.md` | 实现记录（可选；spec_init 不预生成，主代理首次记录时再 Write） | — | — |

每份文档头部固定四行 metadata（骨架已含；**主代理不要手改 `Status` /
`Review Status` 字段**——这些由 `phase-transition` CLI + selector 流程驱动）：

```text
Spec Type: <Feature | Bugfix>
Workflow: <requirements-first | design-first | bugfix>
Status: <Requirements Draft | Bug Analysis Draft | Design Draft | Tasks Draft | Implementation Log>
Review Status: <unreviewed | reviewed | accepted>
```

## 0.5 模板章节铁律（0.10.26+，强约束）

**结构骨架是模板唯一的强约束面**。Write 4 份核心文档时章节标题必须严格对齐
`assets/templates/<phase>.md`，由 `spec_lint.py rule_template_structure` 后置兜底，
PreToolUse hook 在 Write 时前置注入名单。

### 三类章节

| 类别 | 来源 | 行为约束 |
|---|---|---|
| **mandatory** | 模板里**没有** `（可选）` 标记的 `## ` 二级标题 | 必须**逐字保留**；缺失即 `[WARN][tmpl]` |
| **optional** | 模板里**标了** `（可选）` 的 `## ` 二级标题（如 requirements 的 `## 五、非功能 / 约束（可选）`、bugfix 的 `## 九、验收要点（可选）`） | 可**整段删除**；不可只保留标题留空、或写"待补充 / 暂无" |
| **dynamic** | 模板里以"动态前缀"开头的标题（目前只有 tasks.md 的 `## 阶段 N: …`） | 可按需重复 N 次；前缀本身（"阶段 "/数字/`:`）不可改 |

`### ` 三级标题不在本铁律覆盖范围（如 requirements 的 `### 需求 1` / `### 需求 2`
可自由扩展）。

### 五条禁令

1. **禁止改名**：`## 一、背景 / 目标 / 范围` 不许改成 `## 背景` / `## 目标与范围`。
2. **禁止合并**：`## 五、非功能 / 约束（可选）` + `## 六、依赖与风险（可选）`
   不许合并成 `## 五、非功能与风险（可选）`。
3. **禁止拆分**：`## 四、需求详述` 不许拆成 `## 四、用户需求` + `## 五、系统需求`。
4. **禁止调序**：mandatory 之间不许互换位置（即使顺序校验未启用，未来可能加）。
5. **禁止新增**：不许凭主代理判断添加 `## 八、随便发挥的一节` 这种未在模板里的章节。

### 何时可以删

只有 optional / dynamic 可以「不写」：

- optional 整节删（连 `## ` 标题一起删）：合规
- optional 只删正文留标题、或写"待补充"：违规（`[WARN][tmpl]` 不会直接报，但
  SKILL §Spec 文档生成段视为"违反铁律"）
- dynamic 写 0 个：合规（虽然实际上 tasks.md 至少要 1 个阶段才能交给任务执行）

### 两道闸门

| 时机 | 机制 | 失败行为 |
|---|---|---|
| **写之前**（前置） | PreToolUse hook 注入当前 phase 的 mandatory/optional/dynamic 名单 | advisory：把名单当 checklist 用 |
| **写之后**（后置） | `spec_lint.py rule_template_structure` 比对 `## ` 集合 | `[WARN][tmpl]` 缺 mandatory / 多 unknown；hook 自动注入下一轮 |

详细常量字典见 `scripts/spec_session/_template_skeleton.py:TEMPLATE_OUTLINES`；
模板改动后跑 `scripts/_gen_template_outline.py` 重生常量；
`tests/test_template_outlines_drift.py` 守住常量与模板的一致性。

## 1. `requirements.md` 写作约束

骨架见 `assets/templates/requirements.md`。章节：简介 / 词汇表 / 需求 / 边界
情况 / 非功能需求 / 待确认问题。

- SHALL 必须按 `<需求编号>.<条目编号>` 编号（如 `1.1` / `2.3`）—— tasks.md
  的 `_需求：x.y_` 用同一编号系统 traceback。
- 「待确认问题」节是给"用户回头要确认"用的；澄清 wizard 解决不了的可延后项
  写在这里。
- 避免使用「假设」/「Assumptions」节—— 用 `待确认问题` 主动问，不要假设。

## 2. `bugfix.md` 写作约束

骨架见 `assets/templates/bugfix.md`。章节：问题摘要 / 复现步骤 / 当前行为 /
期望行为 / 保持不变的行为 / 影响范围 / 证据 / 约束 / 待确认问题。

- `当前行为` 用 `WHEN ... THE ... [错误行为]`（**不带** SHALL；因为不是期望）。
- `期望行为` 用标准 `WHEN ... SHALL ...`。
- `保持不变的行为` 用 `WHEN ... SHALL CONTINUE TO ...` —— bugfix 专用 EARS
  写法。
- 调研代码后再写「根因」相关结论；**不要**在 bugfix.md 里凭空断言根因（根因
  写在 design.md）。

## 3. `design.md` 写作约束

骨架见 `assets/templates/design.md`。章节：概述 / 架构（现有 + 目标）/ 组件
与接口 / 数据模型 / 流程 / 错误处理 / 安全与隐私 / 性能与可靠性 / 测试策略 /
正确性属性 / 风险 / 变更历史 / 待确认问题。

- 「正确性属性」必须显式写 `**验证：需求 x.y**`，把每条 design 属性映射回
  requirements.md / bugfix.md 编号。
- 「测试策略」是策略不是计划 —— 具体任务在 tasks.md 里。
- 「变更历史」节是 iteration 子循环的累积入口，**首次落地时也保留空节标题**，
  方便后续追加。

## 4. `tasks.md` 写作约束

骨架见 `assets/templates/tasks.md`。**采用独立 task-swarm plugin 兼容格式**：顶层
`## 阶段 N: 标题` 段对应一个 stage（task-swarm fork 粒度）；每条具体任务
`- [ ] N.M 任务 @writes:文件 @reads:文件 @depends-on:N _需求：x.y_`。

- **顶层段落必须用 `## 阶段 N: 标题`** 格式（独立 task-swarm plugin 的解析器据此
  切 stage；不符合会报 `tasks.md 中未解析出任何 ## 阶段 N: 段`）。
- **每条具体任务编号 `N.M`**（不能仅 `N`），任务行末必须带 `_需求：x.y_`
  或 `_需求：可选_` traceability。
- **`@writes`**（task-swarm 据此切 group 避免并发冲突）；**`@reads`** 可选；
  **`@depends-on:N`** 可选（不写则仅靠 `@writes` 冲突切 group）。
- 可选任务把 `[ ]` 改 `[*]`；checkpoint 任务把标题写成 `检查点 —— ...`。
- 文件路径直接写裸路径（不用反引号；task-swarm 按裸路径切分）。
- 「验收」节固定四行（顺序、措辞与骨架一致），不要改写。
- 同一 stage 内多条任务并入 single coder 顺序执行；要拆 coder 必须把它们分
  到不同 stage（不同 `## 阶段 N: ...` 段）。

详细切 group 规则与 `@depends-on` 语义由独立 task-swarm plugin 的文档说明。

### 4.1 任务标记语义

```
[ ] pending [~] in progress [x] completed
[-] skipped [*] optional
```

推进规则：
- 开始一个任务 → `[ ]` → `[~]`。
- 该任务对应验证通过 → `[~]` → `[x]`。
- 跳过任务 → `[-]` + 在 chat / log 说明原因。
- 可选任务：用户选 `开始 required` 时不动；选 `开始 required + optional` 时
  也走 `[ ] → [~] → [x]` 流程。

### 4.2 `## 测试要点` 节填充提示

tasks phase 生成 tasks.md 时，按 requirements.md / bugfix.md 的 SHALL
**顺手**补几行：

- 每行格式 `触发场景 → 预期结果（需求 X.Y）`（不带 checkbox；这一节是参考
  清单而非任务清单）。
- **触发场景**：测试人员可执行的具体动作。
- **预期结果**：SHALL 后的期望行为。
- **需求 X.Y**：requirements.md 的 SHALL 编号。

非硬纪律——SHALL 模糊或拿不准时可以留 `_待补充_` 占位；后续 acceptance 时
可以补。**不要把这一节当成验收门**——验收只看 tasks.md 是否全 `[x]`。

iteration 子循环按需追加新行，详见 `references/iteration.md`。

## 5. `implementation-log.md` 写作约束

无 spec_init 预生成骨架——首次记录时主代理 Write，按 `## YYYY-MM-DD` 分日期。
每天追加任务进度 / 设计偏离 / 关键决策三类内容。

- 自由式格式；每条记录 **≥30 字**（`spec_lint.py` 检查；过短报 WARNING）。
- 按日期分节（`## YYYY-MM-DD`），每天追加。
- 记录三类内容：
  1. **任务进度**：任务 x.y 完成 / blocker。
  2. **设计偏离**：实现期间偏离 design.md 的决策（必须**同 turn** Edit
     design.md 同步）。
  3. **关键决策**：选型 / 安全性 / 性能取舍。
- 缺关键文件引用（路径 / 行号 / 函数名）→ WARNING。
- log 是「轻量级补救手段」 —— 如果同 turn 改了代码但实在没法重写
  design.md / tasks.md，至少在 log 里记一行；**空 log 等于没改过**（下一
  会话看不到）。

## 6. EARS 四种 SHALL 写法

```text
WHEN [condition/event], THE [system/component] SHALL [expected behavior].
WHILE [state], THE [system/component] SHALL [expected behavior].
IF [condition], THEN THE [system/component] SHALL [expected behavior].
WHEN [condition], THE [system/component] SHALL CONTINUE TO [existing behavior].
```

含义：

| 写法 | 含义 | 用于 |
|---|---|---|
| `WHEN ... SHALL ...` | 事件触发型 | 一般行为 |
| `WHILE ... SHALL ...` | 状态持续型 | 持续行为（如"登录态下持续刷新 token"） |
| `IF ... THEN ... SHALL ...` | 条件型 | 分支行为 |
| `WHEN ... SHALL CONTINUE TO ...` | 不变行为 | bugfix.md 专用，断言修复后某行为不变 |

`spec_lint.py` 检查每条 SHALL：缺动词 / 缺 trigger（WHEN/WHILE/IF）→ WARNING。

## 7. traceability 规范（`_需求：x.y_`）

- 写法：`_需求：1.1_`、`_需求：1.1、1.2_`、`_需求：2.3、可选_`。
- 编号系统 = `requirements.md` / `bugfix.md` 的"需求 1 > 验收标准 1.1"路径。
- 编号 `可选` 用于 optional 任务。
- 多需求覆盖一个任务时用全角顿号「、」分隔。
- `spec_lint.py` 检查每条具体子任务（不含 checkpoint / 顶层任务）：缺
  traceability 或编号在 requirements.md 中找不到 → WARNING。

## 8. Document Style 总则

- 章节结构稳定（见 §0.5 模板章节铁律 + 各 `assets/templates/<phase>.md` 骨架），
  不要随意改 H2 标题；H3 仅 `### 需求 N` / `### 任务 N.M` 等动态扩展允许。
- 中文叙述；技术名 / 命令 / 路径 / 函数名 / 变量名保持英文原样。
- 禁止使用「假设」/「Assumptions」节 —— 用 `待确认问题` 节主动问。
- 禁止使用模糊措辞（"大概"、"可能"、"应该差不多"）—— 不确定就走澄清 wizard。
- iteration 子循环里旧节不动，按规则追加（详见 `references/iteration.md`）。

## 9. 跨文档引用

- phase 序列与 `doc-confirm-*` 选择器 → `references/workflow.md`。
- 选择器三种类型与场景常量 → `references/selectors.md`。
- iteration 子循环的文档累积规则 → `references/iteration.md`。
- 5 份文档与文档优先纪律的关系 → SKILL.md §Code-Doc Sync Reminders。
