---
description: Use when 准备生成或修订 requirements.md / bugfix.md / design.md / implementation-log.md。详述这几份文档的章节模板、EARS SHALL 写法、traceability 规范。
---

# Spec Document Templates

spec 文档的**写作约束 + EARS / traceability 规范**。完整章节骨架的
**单一事实源**是 `${CLAUDE_PLUGIN_ROOT}/assets/templates/<phase>.md`——主
代理按 SKILL.md §「Spec 文档生成」Read 那份骨架 + 按 `source_text` 填空。
本文件**不重复骨架**，只列每份文档独有的写作约束。

## 0. 命名约定

| 文件 | 用途 | 骨架文件 | 互斥关系 |
|---|---|---|---|
| `requirements.md` | 需求-first / design-first 工作流的需求文档 | `assets/templates/requirements.md` | 与 `bugfix.md` 互斥 |
| `bugfix.md` | bugfix 工作流的问题描述 | `assets/templates/bugfix.md` | 与 `requirements.md` 互斥 |
| `design.md` | 技术设计文档（含测试策略 / 正确性属性 / 验收映射，是 implementation 的单一事实源） | `assets/templates/design.md` | — |
| `implementation-log.md` | 实现记录（spec_init 预生成空骨架，主代理实现期间追加） | `spec_init.py:FALLBACK_TEMPLATES`（无独立模板文件） | — |

> M4 起 specode 不再产 `tasks.md`：implementation 阶段直接读 `design.md` 实现，
> 或委托独立 task-swarm plugin（主代理读 design.md 生成 pipeline.yml）。

每份文档头部固定四行 metadata（骨架已含；**主代理不要手改 `Status` /
`Review Status` 字段**——这些由 `phase-transition` CLI + selector 流程驱动）：

```text
Spec Type: <Feature | Bugfix>
Workflow: <requirements-first | design-first | bugfix>
Status: <Requirements Draft | Bug Analysis Draft | Design Draft | Tasks Draft | Implementation Log>
Review Status: <unreviewed | reviewed | accepted>
```

## 0.5 模板章节铁律（0.10.26+，强约束）

**结构骨架是模板唯一的强约束面**。Write 3 份核心文档（requirements / bugfix /
design）时章节标题必须严格对齐 `assets/templates/<phase>.md`，由
`spec_lint.py rule_template_structure` 后置兜底，PreToolUse hook 在 Write 时前置注入名单。

### 两类章节

| 类别 | 来源 | 行为约束 |
|---|---|---|
| **mandatory** | 模板里**没有** `（可选）` 标记的 `## ` 二级标题 | 必须**逐字保留**；缺失即 `[WARN][tmpl]` |
| **optional** | 模板里**标了** `（可选）` 的 `## ` 二级标题（如 requirements 的 `## 五、非功能 / 约束（可选）`、bugfix 的 `## 九、验收要点（可选）`） | 可**整段删除**；不可只保留标题留空、或写"待补充 / 暂无" |

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

只有 optional 可以「不写」：

- optional 整节删（连 `## ` 标题一起删）：合规
- optional 只删正文留标题、或写"待补充"：违规（`[WARN][tmpl]` 不会直接报，但
  SKILL §Spec 文档生成段视为"违反铁律"）

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

- SHALL 必须按 `<需求编号>.<条目编号>` 编号（如 `1.1` / `2.3`）—— design.md
  「正确性属性」的 `**验证：需求 x.y**` 用同一编号系统 traceback。
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
正确性属性 / 风险 / 待确认问题。

- M4 起 `design.md` 是 implementation 的**单一事实源**：implementation 阶段直接
  按 design.md 实现，或委托独立 task-swarm plugin（主代理读 design.md 生成
  pipeline.yml）。不再产 `tasks.md`，所以任务拆分 / 测试要点都收敛到 design.md。
- 「正确性属性」必须显式写 `**验证：需求 x.y**`，把每条 design 属性映射回
  requirements.md / bugfix.md 编号——这是验收的 traceability 入口。
- 「测试策略」节给出单元 / 集成 / 端到端 / 回归测试方向，供实现与验收参考。

## 4. `implementation-log.md` 写作约束

spec_init 预生成空骨架（来自 `spec_init.py:FALLBACK_TEMPLATES`，无独立模板文件）
——主代理实现期间按 `## YYYY-MM-DD` 分日期追加，每天记录任务进度 / 设计偏离 / 关键决策。

- 自由式格式；每条记录 **≥30 字**（`spec_lint.py` 检查；过短报 WARNING）。
- 按日期分节（`## YYYY-MM-DD`），每天追加。
- 记录三类内容：
  1. **任务进度**：某项实现完成 / blocker。
  2. **设计偏离**：实现期间偏离 design.md 的决策（必须**同 turn** Edit
     design.md 同步）。
  3. **关键决策**：选型 / 安全性 / 性能取舍。
- 缺关键文件引用（路径 / 行号 / 函数名）→ WARNING。
- log 是「轻量级补救手段」 —— 如果同 turn 改了代码但实在没法重写
  design.md，至少在 log 里记一行；**空 log 等于没改过**（下一会话看不到）。

## 5. EARS 四种 SHALL 写法

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

## 6. traceability 规范（`**验证：需求 x.y**`）

- 编号系统 = `requirements.md` / `bugfix.md` 的"需求 1 > 验收标准 1.1"路径。
- M4 起 traceability 收敛到 `design.md`：「正确性属性」节每条属性须显式写
  `**验证：需求 x.y**`，把 design 行为映射回需求编号，作为验收 traceback 入口。
- 多需求覆盖一条属性时用全角顿号「、」分隔（如 `**验证：需求 1.1、1.2**`）。

## 7. Document Style 总则

- 章节结构稳定（见 §0.5 模板章节铁律 + 各 `assets/templates/<phase>.md` 骨架），
  不要随意改 H2 标题；H3 仅 `### 需求 N` 等动态扩展允许。
- 中文叙述；技术名 / 命令 / 路径 / 函数名 / 变量名保持英文原样。
- 禁止使用「假设」/「Assumptions」节 —— 用 `待确认问题` 节主动问。
- 禁止使用模糊措辞（"大概"、"可能"、"应该差不多"）—— 不确定就走澄清 wizard。
- iteration 子循环里旧节不动，按规则追加（详见 `references/iteration.md`）。

## 8. 跨文档引用

- phase 序列与 `doc-confirm-*` 选择器 → `references/workflow.md`。
- 选择器三种类型与场景常量 → `references/selectors.md`。
- iteration 子循环的文档累积规则 → `references/iteration.md`。
- 各文档与文档优先纪律的关系 → SKILL.md §Code-Doc Sync Reminders。
