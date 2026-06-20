# Changelog — obsidian-wiki

obsidian-wiki 是维护 Obsidian LLM-Wiki 的多 agent 插件（从独立 skills 仓迁入并重打包）。本文件记录其自身版本。

## Unreleased

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
