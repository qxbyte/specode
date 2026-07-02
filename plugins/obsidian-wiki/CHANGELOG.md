# Changelog — obsidian-wiki

obsidian-wiki 是维护 Obsidian LLM-Wiki 的多 agent 插件（从独立 skills 仓迁入并重打包）。本文件记录其自身版本。

## Unreleased

### Fixed — 清理 2.0.0 spec-distill 剥离后的文档残留

2.0.0 删除了 `skills/spec-distill/`（含 `kn_scan.py`），但大量文档没同步：
`wiki-orchestrate` 仍会尝试运行已不存在的 `kn_scan.py`，README / AGENTS 仍宣传
「四个 skill」。本次全部对齐到三 skill 现实：

- `README.md` / `AGENTS.md`：「四个 skill」→「三个 skill」，删 spec-distill 行与
  `kn_scan.py` 调用示例，补「已剥离、迁往 specode `/specode:distill`」迁移说明。
- `wiki-orchestrate/SKILL.md`：编排序「结构→沉淀→策展」→「结构→策展」；体检从
  三方改两方（删 `kn_scan.py` 调用与 spec-distill-report）；删「知识沉淀」执行阶段、
  wiki-log 行模板与 `knowledge.spec_in_candidates` 残留。
- `wiki-orchestrate/references/sub-skills.md`：删 §2 spec-distill 整节（wiki-curate
  升为 §2），「三个」→「两个」。
- `wiki-orchestrate/references/decision-guide.md`：删 kn_scan 信号行、「知识沉淀」
  默认阶段与「项目落哪个系统」判断点。
- `wiki-curate/SKILL.md` + references（writing-conventions / note-templates /
  readonly-dirs-policy / karpathy-llm-wiki）、`wiki-struct/SKILL.md`：spec-distill
  职责描述改为「遗留产物只读；新沉淀走 specode `/specode:distill`」，并删除指向已
  删除文件（`spec-distill/references/*.md`）的死链接。

## 2.0.0 (2026-06-26)

### BREAKING — spec-distill 已剥离

spec-distill 作为 "对接 specode 沉淀知识"的工具，本质不属于"Obsidian
vault 维护"工具集，曾在 v1/v2 期间临时寄放在本插件内。v2.0 将其完整
迁移到 **specode 内子 skill specode-distill**（slash command 改为
`/specode:specode-distill <slug>`），并对触发模型做了根本性调整：
单 spec 触发、写到 spec 自己的 project_root，彻底消除 v1/v2 spec-distill
依赖 vault 全局 scan 时的跨项目混淆问题。

obsidian-wiki **本体仍然存在**，剩余三件套：

- `wiki-struct` — 维护 Obsidian Home 树 / 各一级目录 README / 00-Index
  分区页的受管块
- `wiki-curate` — Karpathy 方法论的内容向 ingest / curate / lint
- `wiki-orchestrate` — 只读体检 → 行动计划 → 编排上面两个

如果你之前依赖 v1/v2 spec-distill：

1. 安装最新 specode 3.0+（`/plugin install specode`）。
2. 用 `/specode:specode-distill <slug>` 替代 `/spec-distill sync`。
3. 知识不再写到 `<vault>/10-Work/知识库/<系统>/`，而是写到每个 spec
   的 `<project_root>/.ai-memory/knowledge/` + `<project_root>/knowledge-base/`。
4. vault 内 `00-Index/_system/spec-distill-state.yml` 与
   `spec-distill-report.yml` 不再被维护——可以保留作为历史档案，也
   可以删除。

### 移除

- `skills/spec-distill/`（整个子目录）
- `scripts/kn_scan.py`（连同 17 个单测）— 单 spec 模型不需要全局扫描

## 1.1.0 (2026-06-25)

### BREAKING: spec-distill 完全重写输出层（v2）

为接入 AI-Enterprise-Delivery-System 四层记忆模型（L0/L1 由
`codemap-aimemory>=0.3.2` 在 `<project_root>/.ai-memory/` 下写；L2/L3
由本 skill 写），spec-distill 抛弃所有 markdown 输出，改产纯 yml 知识：

- **目标位置**：`<project_root>/.ai-memory/knowledge/{rules,business,
  modules,cases,pitfalls}/<id>.yml`（不在 vault 内，不再按"系统"分层）。
- **废弃产物**：v1 的 `10-Work/知识库/<系统>/<知识点>.md` /
  `MEMORY.md` / `00-Index/_system/wiki-log.md` 一律不再写。
- **vault 内仅保留两个状态文件**：
  - `00-Index/_system/spec-distill-state.yml` — sync 完成后追加的已沉淀
    spec 索引（`{spec_id: {project_root, synced_at, new_count}}`）。
  - `00-Index/_system/spec-distill-report.yml` — scan 命令覆盖式产出
    （pending / done 列表 + counts）。

### sync 流程变化

- **project_root 解析**：优先级 `--project <abs>` → spec 的
  `requirements.md` 顶部 YAML frontmatter `project_root` 字段（由 specode
  v2 写入）→ 报错请求用户指定。**不再猜测**。
- **拆分启发式 → 五类目录映射**（5 维 + cases/pitfalls 额外两类）：
  - 业务流程 / 功能页 → `business/biz-*.yml`
  - 表/字段 / 调用链 → `modules/mod-*.yml`
  - 机制 / 规则 → `rules/rule-*.yml`
  - 本次实现（每个 spec 必产 1 篇）→ `cases/case-*.yml`
  - 可复用坑点 → `pitfalls/pit-*.yml`
- 同 ID 升级规则：`updated_at` 推进、`version` +1、`related_requirements`
  追加；不重写已有结构性字段。

### references 重组

- `references/doc-template.md` — 完全重写为 5 类 yml schema 模板
  （公共字段 + 类型特异字段）。
- `references/breakdown-heuristics.md` — 5 维启发式保留，开头加 5 维 → 5
  类目录映射表，"拆分流程"步骤补 `category` + `knowledge_id` 要求。
- `references/memory-rules.md` — **删除**（不再维护 MEMORY.md）。

### scripts/kn_scan.py 重写

- 抛弃 v1 的"读各系统 MEMORY 表反向解析"逻辑。
- 改为读 `<vault>/00-Index/_system/spec-distill-state.yml`（JSON-as-YAML，
  零外部依赖），与 SpecIn 源目录做差集得 pending / done。
- 输出 `spec-distill-report.yml`（之前是 `.md`）。
- 17 个新单测覆盖 discovery / state / scan / report 四组路径，全部通过。

### 配合 specode 改造

本 PR 同步更新 specode v2.0.0（plugin.json 不变）：

- `assets/templates/requirements.md` 顶部加 YAML frontmatter，含
  `spec_id` / `project_root` / `created_at`。
- `skills/specode/SKILL.md` "requirements" phase 流程：写 requirements.md
  前必须用 `AskUserQuestion` 让用户确认 `project_root`（默认 `git
  rev-parse --show-toplevel` 或 cwd），把确认值写入 frontmatter；下游
  spec-distill v2 从此 frontmatter 读 `project_root`。

## 1.0.1 (2026-06-20)

首个发布。维护 Obsidian LLM-Wiki（Karpathy 方法论：Sources 只读 / Wiki LLM 写 / Schema 规约）的四个 skill + 家目录多库配置注册表。

### 四个 skill（`skills/`）

- **wiki-struct** — 确定性重写 Home 总览树 / 各一级目录 README / `00-Index` 分区页的"受管块"（只改 marker 之间），产出结构体检报告。
- **spec-distill** — 把 SpecIn 里 specode 生成的需求文档逐项目提炼成细粒度知识库笔记（`10-Work/知识库/<系统>/`）并维护 MEMORY；替换原 kn-indexer，跨平台。
- **wiki-curate** — 内容向 ingest / curate / lint + Karpathy 三层方法论 doctrine（写作规范、只读红线、笔记模板）。
- **wiki-orchestrate** — 统一编排：只读体检 → 行动计划 → 按「结构 → 沉淀 → 策展」调用上面三个。

### 设计

- **代码通用、零结构硬编码**：每个库的结构配置存**家目录多库注册表** `~/.config/obsidian-wiki/`（`vaults.json` 记各库 path+active，`configs/<名>.json` 存结构），按 vault keying；未注册则回退库内 `<vault>/.wiki/config.json`。
- `lib/registry.py`：`list` / `resolve` / `register` / `set-active`；`$OBSIDIAN_WIKI_CONFIG_DIR` 可覆盖配置根。
- 脚本 Python 3 标准库、UTF-8、零外部依赖；`--vault` 必填；共享 `lib/wikicommon.py`。
- **多 agent**：Claude Code / Copilot CLI / CodeBuddy 原生发现 `skills/`；Codex CLI 走根 `AGENTS.md`（脚本照跑，LLM 流程内联读 SKILL.md）。
- 全 5 套件单测通过；家目录配置与库内回退等价性已验证。
