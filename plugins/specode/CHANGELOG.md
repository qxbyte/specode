# Changelog — specode

specode 是 spec-driven 轻量工作流插件：requirements → design → execute → acceptance 四阶段编排 + 三份固定产物（requirements.md / design.md / implementation-log.md）。本文件记录其自身版本。

## Unreleased

## 3.1.0 (2026-06-27)

### Changed — step 2.2 injection 升级为内容摘要（P3-2 闭环 part 1）

主 `SKILL.md` step 2.2 注入命令从

```
codemap recall '<request>' --top-k 5 -o yaml
```

升级为

```
codemap recall '<request>' --top-k 5 --with-content -o yaml
```

注入格式从"wikilink 一句话摘要"升级为"完整字段表格"：

```markdown
### [[rule-coupon-mutex]] (business_rule, ranked_score=7)

**优惠券和积分互斥**

| 字段 | 值 |
|---|---|
| statement | Coupons and points can't both apply to the same order |
| why | Prevents stacking discounts beyond margin |
| exceptions | VIP ≥ 8 |
| enforcement | service layer throws / frontend disables checkbox |
```

每个 category 渲染不同字段集（rules → statement/why/exceptions/...；
pitfalls → symptom/fix/...；cases → implementation_summary/...；business
→ trigger/steps/...；modules → scope/columns/...）。

**修复闭环断点**：v3.0 注入只放了 wikilink，design phase 的 LLM
（superpowers:writing-plans / native）很可能不主动去读 yml/md，错过
关键约束。v3.1 把内容直接铺到 requirements.md 上，下游 skill 一定
能看到。

`stale` 命中（freshness_score < 0.5，由 codemap-aimemory 0.4.0 引入）
在子标题前加 ⚠️ 前缀，让用户决定是否仍要遵守过期知识。

### Added — step 3 design phase rule-acknowledgement post-check (P3-2 闭环 part 2)

`design.md` 写完后，host agent 自动扫 requirements 的
`## 已知约束 / 历史坑` 段提取所有 `[[rule-*]]`，逐一在 design.md grep
是否被显式 acknowledge 或 override。缺失时 `AskUserQuestion`：

```
设计未显式涉及以下规则，可能违背或遗漏：
- [[rule-X]] — <title>
- [[rule-Y]] — <title>

选择处理方式：
- 补充 design.md 说明如何遵守 (recommended)
- 显式声明覆盖（override rule-X: <reason>）
- 跳过（认为不适用，标记到 implementation-log）
```

用户选完后 host agent 写回 design.md 或 implementation-log。规则不再
能"悄悄遛过" design 阶段。如果 step 2.2 没召回任何 rule，post-check
自动跳过（无可校验）。

### Requirements

- **`codemap-aimemory>=0.4.0`** for `--with-content` flag + freshness
  fields. Older codemap：注入退化到 wikilink-only（v3.0 行为，依然
  能用），post-check 仍生效。

### Why this closes P3-2

P3-2 的设计目标是 "design 阶段强制规则校验"。要做到这点，前置条件
是 design phase 真的看到了规则**内容**（v3.0 wikilink-only 注入
不够）。v3.1 两个改动是缺一不可的双臂：
- step 2.2 内容注入 → 让 LLM 看见规则的具体约束
- step 3 post-check → 让"规则没被处理"不能静悄悄发生

到此 specode 闭环 "知识 → spec → design → 实施" 真正闭合。

## 3.0.1 (2026-06-26)

### Added — specode-distill step 4 pre-check (P2-2)

`skills/specode-distill/SKILL.md` step 4 now starts with a pre-step
that queries the project's existing knowledge base for relevant rules
and pitfalls **before** the LLM forms breakdown proposals:

```bash
codemap recall --from-spec "<specsRoot>/<slug>/requirements.md" \
               --project "<project_root>" \
               --types rules,pitfalls \
               --top-k 5 \
               --output json
```

Each hit is surfaced to the user as a short context bullet
`- [[<knowledge_id>]] (<type>, score=<n>) — <title> · <summary>`. The
host agent then forms proposals **with awareness of**:

- existing `rule-*` statements (don't propose contradictory new rules)
- existing `pit-*` symptoms (link via `seen_again_in` if this spec
  re-touches the same area; treat as risk if proposed code path
  matches a known failure pattern)

Proposed knowledge candidates now pre-fill `related_knowledge` with
any recall hits judged relevant.

Requires **codemap-aimemory>=0.3.6** (the `--from-spec` flag). If
`codemap recall` is unavailable (codemap-aimemory not installed or
older), the pre-step is silently skipped — proposals fall back to
spec-only context. No hard dependency.

### Why this closes P2-2

The AI-EDS roadmap defined P2-2 as "spec-distill writes rules with
awareness of historical pitfalls / cases". Until now the breakdown
step in step 4 only had the current spec's documents in context, so
the LLM had no way to know it was about to propose a rule that
contradicted last quarter's hard-won pitfall. The pre-step closes
that gap by injecting the cross-project knowledge that already lives
in `.ai-memory/knowledge/` — produced by prior runs of either
specode-distill itself or task-swarm's auto ingest.

## 3.0.0 (2026-06-26)

### Added — specode-distill 子 skill（spec-distill 迁入 specode 并改造为单 spec 模型）

specode 是 spec 全生命周期的入口（requirements → design → execute →
acceptance），把"知识沉淀"也纳入其中 → specode 成为 single source of
truth，闭环更紧。

新增 `skills/specode-distill/`：

- 5 步流程：解析 project_root → 准备 yml + md 目录 → 读 spec 全文 →
  AskUserQuestion 拆分提议 → 同时写 yml + md 双产
- 写到 spec 自己的 `project_root`（绝对路径从 `requirements.md`
  frontmatter 读），**严格 per-spec**，彻底消除原 spec-distill 跨项目
  混淆问题（一个 vault 内多项目 spec 沉到不同 project_root）
- 双产物：
  - `<project_root>/.ai-memory/knowledge/{rules,business,modules,cases,pitfalls}/*.yml`
    （机器源，给 `codemap recall` 和未来 embedding indexer）
  - `<project_root>/knowledge-base/{rules,business,modules,cases,pitfalls}/*.md`
    （人读 + embedding 源，保留散文/ascii/表格结构）
- 同 stem、同 knowledge_id；同次 LLM 一次性产 yml + md

新增 slash command：`/specode:specode-distill <slug>`。

主 SKILL.md step 6 acceptance 末尾新增 `AskUserQuestion` 提示：
*"是否立即沉淀本次需求知识？"* — "是"自动调 specode-distill；"否"输出
后续手动命令提示。不强制；refusal 不影响 spec 状态。

### Schema

5 类 yml schema + 5 类 md 模板的完整定义在
`skills/specode-distill/references/doc-template.md`：

- `rules/rule-*` — 业务规则 / 全局机制（statement / why /
  trigger_conditions / exceptions / enforcement）
- `business/biz-*` — 业务流程 / 功能页（trigger / end_state / steps
  with branches / data_flow / ui_constraints）
- `modules/mod-*` — 表 / 字段 / 调用链 / 模块地图（scope=table
  with columns/enum/shard，或 scope=call_chain）
- `cases/case-*` — 历史案例（implementation_summary / changed_files /
  key_decisions / bugs_encountered / lessons / review_findings /
  acceptance_status）每个 spec 必产 1 篇
- `pitfalls/pit-*` — 可复用坑点（symptom / root_cause / fix /
  prevention / affects / first_seen_in / seen_again_in）

### 砍掉的东西（v1/v2 spec-distill 有 → v3 没有）

| 移除 | 原因 |
|---|---|
| `scan` 子命令（vault-wide 列待沉淀） | 单 spec 模型无 "vault 全局待沉淀" 概念 |
| `<vault>/00-Index/_system/spec-distill-state.yml` | 不再需要全局 state；每个 spec 写自己项目 |
| `<vault>/00-Index/_system/spec-distill-report.yml` | 同上 |
| 按"系统"分组（`<vault>/10-Work/知识库/<系统>/`） | 替换为按"项目"分组（`<project_root>/knowledge-base/`） |
| `MEMORY.md` / `wiki-log.md` | v2 已废 |
| `--vault <path>` 标志 | 不再适用——输入只是 `<specsRoot>/<slug>/` 与 spec 自己的 `project_root` |
| Python 辅助脚本 `kn_scan.py` | 纯 LLM-driven 流程；无脚本需要 |

### Breaking changes

- **install dependency change**：obsidian-wiki **不再是 AI-EDS 工作流必装**。
  之前依赖 `/spec-distill sync` 的用户改用 `/specode:specode-distill <slug>`。
- 配套 obsidian-wiki **2.0.0** 同步移除 `skills/spec-distill/` 子目录。
- 配套 task-swarm **0.6.0** 同步加 `knowledge-base/*.md` 双产。
