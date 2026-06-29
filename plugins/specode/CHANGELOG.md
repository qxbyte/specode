# Changelog — specode

specode 是 spec-driven 轻量工作流插件：requirements → design → execute → acceptance 四阶段编排 + 三份固定产物（requirements.md / design.md / implementation-log.md）。本文件记录其自身版本。

## Unreleased

## 5.0.1 (2026-06-30) — distill 收敛 md-only + 隐藏 + 全量清理 .ai-memory/codemap 残留

承接 5.0.0,把 distill 彻底收敛为「纯 md-only Obsidian 整理器」,并清掉全仓最后的记忆注入文档残留。

### Changed

- **`skills/distill/SKILL.md`**:加 `user-invocable: false` —— 斜杠菜单不再出现裸 `/distill`,也消除了「命令 + 同名可见 skill」造成的 `/specode:distill` 重复项(现只剩命令一条干净入口;Claude 仍可自动调用该 skill)。
- **distill 收敛为纯 md-only**:移除 `--format md|yml|both` flag 与 `codemap knowledge write` 写入器路径。yml 输出的唯一消费者(`codemap recall`)早在 v4.0.0 删除,yml 已无人读取,故彻底移除。

### Removed / cleaned(文档与模板里的死引用)

- **`assets/templates/requirements.md`**:删除已废弃的「## 已知约束 / 历史坑」段 —— 该段是 v4.0.0 已移除的 P3-1 codemap-recall 注入占位,SKILL 早已声明 requirements.md 不再含此段,模板未同步(会盖进每个新 spec)。
- **`skills/distill/references/doc-template.md`**:重写为 v5 md-only 模板参考 —— 删除 yml schema / `.ai-memory/knowledge/` 路径表 / codemap 写入器框架,frontmatter 对齐 SKILL 的 Obsidian 风格,保留 5 类 md 模板正文与深度标准。
- **`skills/distill/references/breakdown-heuristics.md`**:剥掉 `.ai-memory`/`codemap knowledge write`/yml 双产/supersede 框架,保留 5 维拆分方法论。
- **`commands/spec.md` / `skills/specode/references/obsidian.md` / `tests/test_project_root.py`**:`project_root` 描述去掉过时的 ".ai-memory/knowledge feeds" + "codemap recall" 消费者措辞。
- **`commands/distill.md`**:移除 `--format` flag。

全量复核:除 CHANGELOG 历史条目与「已移除 X」迁移说明外,仓库不再有把 `.ai-memory`/`codemap knowledge write`/yml-pipeline 描述成现行行为的文档。测试 233 passed。

## 5.0.0 (2026-06-30) — BREAKING: 命令去 `specode-` 前缀 + 内核 skill 隐藏

命令名 = specode 的 semver API surface。本版把命令去掉冗余的 `specode-` 前缀（插件命名空间已提供 `specode:`），并把不该被直接点的编排内核 skill 从斜杠菜单隐藏 —— 对齐 superpowers 的命名形态（无裸 `/superpowers`）。

### Changed (BREAKING — 命令重命名)

- `/specode:specode-spec` → **`/specode:spec`**（`commands/specode-spec.md` → `commands/spec.md`）
- `/specode:specode-continue` → **`/specode:continue`**（`commands/specode-continue.md` → `commands/continue.md`）
- `/specode:specode-list` → **`/specode:list`**（`commands/specode-list.md` → `commands/list.md`）
- `/specode:specode-distill` → **`/specode:distill`**（`commands/specode-distill.md` → `commands/distill.md`）
- distill skill 目录 `skills/specode-distill/` → **`skills/distill/`**，frontmatter `name: specode-distill` → `name: distill`

### Changed (斜杠菜单)

- 编排内核 skill `specode`（`skills/specode/SKILL.md`）加 `user-invocable: false` —— 裸 `/specode` 不再出现在斜杠菜单（它只应经上述命令 / 「按 spec 流程做」自然语言激活，Claude 仍可自动调用）

### Migration

- 把 `/specode:specode-X` 改成 `/specode:X` 即可，行为不变。SessionStart 提示文案、主 SKILL、references、README（EN/zh）、CLAUDE.md 已全部同步。CHANGELOG 历史条目按惯例保留旧命令名。

## 4.0.0 (2026-06-29) — BREAKING: 拔出记忆注入工程

Round 1/2 baseline 实验 (`/Volumes/External HD/Obsidian/Notes/07-Ideas/AI-Enterprise-Delivery-System/基线AB对照实验/`) 证明: 记忆注入未 net 节省 token。用户决策完全拔出, specode 专注 "spec → design → execute → acceptance 编排" 本质能力。

### Removed (specode 主 SKILL.md)

- **P3-1 codemap recall 注入段** (line 94-130): 不再调 `codemap recall ... --with-content`, requirements.md 不再含 `## 已知约束 / 历史坑` 段, 不再含 cold-start `## 相关代码地图` 段
- **P3-2 rule-acknowledgement post-check** (line 152-167): design.md 写完不再 grep `[[rule-*]]` 检查 + `AskUserQuestion` 处理偏离
- **Acceptance distill prompt sub-step** (line 179): acceptance summary 写完不再 `AskUserQuestion` 询问"是否立即沉淀"

### Preserved

- **Project-level agent docs filesystem scan** (CLAUDE.md / AGENT.md): 仍扫描 + 注入 `## 项目级约束` 段 (不涉及 `.ai-memory/`, 是纯 filesystem 扫描)
- specode 主流程 4 阶段不变 (requirements → design → execute → acceptance), 4 phase 调 superpowers 也不变
- autonomous mode 5 env (`SPECODE_INTERACTIVE` 等) 不变
- project_root frontmatter SSoT 不变

### specode-distill skill 完全重写为 v4 (md-only Obsidian organizer)

**Trigger**: 仅手动 `/specode:specode-distill <slug>`, 永不自动触发。

**Args**:
- `--target-dir <abs>` (默认 `/Volumes/External HD/Obsidian/Notes/11-KnowledgeBase/<slug>/`)
- `--format md|yml|both` (默认 `md`)

**Behavior**:
- 默认仅写 `.md` 到 `<target-dir>/<slug>/<category>/<id>.md` (Obsidian-friendly frontmatter + sections + wikilinks)
- 不调 `codemap recall` (v3 P2-2 reverse-check 已删)
- 不调 `codemap knowledge write` 默认 (仅 `--format yml|both` 时调, 写 `<target-dir>/yml-store/` 而非 spec project_root)
- 不写 `<project_root>/.ai-memory/knowledge/` (v4 完全独立于 spec 的 project_root)
- 不读 `.ai-memory/` 任何路径

### Migration

- 如需 v3 行为 (自动 recall + 自动 distill + 写 .ai-memory): `git checkout backup/specode-v3.4.0-task-swarm-v0.9.2`
- 历史 `.ai-memory/knowledge/` 内容保留不删, 用户可独立用 `codemap recall` 查询 (codemap-aimemory CLI 仍可独立装用)

## 3.3.0 (2026-06-28)

### Added — `doctor` verb in resolve_root.py (AI-EDS v0.9 痛点 #9)

新增 `resolve_root.py doctor` 子命令，检测 specode config drift：

| exit | 含义 |
|---|---|
| 0 | specsRoot 已配 + 目录存在（可能带 legacy `obsidianRoot` 警告）|
| 3 | specsRoot 未配（提示先跑 `set-root`） |
| 4 | specsRoot 配了但目录不存在（vault 被重命名 / 外置盘未挂载 / 大小写漂移 → 给出 `set-root --root <new-abs>` 可直接复制粘贴的修法）|

发现于真实试跑 2026-06-28：用户把外置盘 vault 从 `spec-in/` 重命名为 `SpecIn/`（case-sensitive 文件系统下成了两个目录），但 specode config 还指 `spec-in/`，所有下游静默走错路径。doctor 让这类漂移可一眼诊断。

### Fixed — set-root 清理 legacy obsidianRoot key (AI-EDS v0.9 痛点 #8)

`cmd_set_root` 之前只写 `specsRoot`，不删 `obsidianRoot`（specode <1.0.0 的旧 key）。读端 fallback 同时认两个键时不显问题，但其他 plugin（如 obsidian-wiki）仍直接读 `obsidianRoot` → 静默走 stale 路径，split-brain 风险（2026-06-28 真实试跑事故场景）。

修法：set-root 持久化时 `cfg.pop("obsidianRoot", None)`。doctor 在两键都存在时给 warning + 建议 re-run set-root 一次清理。

6 个 regression tests 新增 (`tests/test_set_root_cleanup_and_doctor.py`)。
specode 测试总数 27 → 33，全部通过。

## 3.2.0 (2026-06-27)

### Added — FIX-1 project_root single source of truth

`scripts/resolve_root.py` 加 3 个新 verb：

- `resolve-project-root` — 默认值推导（`git rev-parse --show-toplevel` ‖ cwd），不再要求 cwd 是 git repo（**工作区根、非 git 目录也能跑**）
- `write-project-root --spec <path> --root <abs>` — **唯一写入口**，校验绝对路径 / 目录存在 / `/Volumes` 挂载，原子写 frontmatter
- `read-project-root --spec <path>` — **唯一读入口**，缺字段 exit 3 / 值非法 exit 4

主 `SKILL.md` step 2.1/3 / `commands/specode-spec.md` step 3 / `skills/specode-distill/SKILL.md` step 1 / `references/obsidian.md` 全部改为引用这三个 verb，删除"do not ask / = cwd 不写 frontmatter"等矛盾表述。

收敛 AI-EDS ISSUE-1（文档矛盾断链）+ ISSUE-3（双写分裂）。

### Added — FIX-2 knowledge writer rewire（与 codemap-aimemory 0.4.3+ 配合）

`specode-distill` 范式翻转：从"LLM 自己写 yml"改为"LLM 产 content payload + md_body → `codemap knowledge write` 落盘"。SKILL.md / doc-template.md / breakdown-heuristics.md 全部按新流程更新。task-swarm 同样收归（见其 0.7.0）。

依赖：`codemap-aimemory >= 0.4.3`（含 `codemap knowledge` CLI）。

### Added — FIX-3d/3e consumer 更新

主 `SKILL.md` step 2.2 recall call 默认带 `--include-shared` flag（codemap-aimemory >= 0.4.4 起，opt-in 跨项目共享 knowledge）—— 未配置 `~/.config/codemap/recall.yaml shared_roots` 时是 no-op，所以**永远可以传**。

注入模板对 `source: shared` 命中加 🌐 prefix，让 reviewer 一眼区分项目本地知识 vs 团队共享知识。

依赖：`codemap-aimemory >= 0.4.4` + `codemap-semantic-index >= 0.2.0`（可选）。

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
