<p align="right"><a href="./README.md">English</a> | <strong>中文</strong></p>

# pluginhub

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./README.zh-CN.md#许可证)
[![specode](https://img.shields.io/badge/specode-5.0.1-blue.svg)](./plugins/specode/.claude-plugin/plugin.json)
[![task-swarm](https://img.shields.io/badge/task--swarm-0.10.1-blue.svg)](./plugins/task-swarm/.claude-plugin/plugin.json)
[![obsidian-wiki](https://img.shields.io/badge/obsidian--wiki-2.0.0-blue.svg)](./plugins/obsidian-wiki/.claude-plugin/plugin.json)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-compatible-8A2BE2)](https://github.com/qxbyte/pluginhub#installation)
[![CodeBuddy](https://img.shields.io/badge/CodeBuddy-2.97.1%2B-1E90FF)](https://github.com/qxbyte/pluginhub#installation)
[![Tests](https://img.shields.io/badge/pytest-233%20cases-success)](./plugins/task-swarm/tests)

> qxbyte 面向 CLI 编码代理（Claude Code / CodeBuddy）的插件 marketplace。

**pluginhub** 是一个插件 marketplace：`marketplace add` 一次，之后即可安装其中任意插件。后续会有更多插件加入。

## 插件一览

| 插件 | 版本 | 做什么 |
| --- | --- | --- |
| **specode** | 5.0.1 | 轻量**规格驱动工作流**——编排外壳，每个阶段委托给 [superpowers](https://github.com/obra/superpowers) 技能（一等公民原生降级），每条规格固定产出 3 份文档。**v5.0.1**：`distill` skill 改为 `user-invocable: false`（隐藏裸 `/distill` 与重复的 `/specode:distill`，只留命令一条）；distill 收敛为纯 **md-only**（移除已死的 `--format yml|both` 与 `codemap knowledge write` 路径）；清理全部 `.ai-memory`/codemap 文档残留，并从 requirements 模板删除已废弃的 recall 段。**v5.0.0 BREAKING**：命令去掉冗余 `specode-` 前缀——`/specode:spec` / `/specode:continue` / `/specode:list` / `/specode:distill`（原 `/specode:specode-*`）；`distill` skill 目录与 `name` 同改为 `distill`；编排内核 skill `specode` 改为 `user-invocable: false`，斜杠菜单不再显示裸 `/specode`（仍经命令自动激活）。AI-EDS 时代保留至 v4.0.0 的能力：项目级 `CLAUDE.md` / `AGENT.md` filesystem 扫描注入「## 项目级约束」段（痛点 #14 方案 D）、SessionStart cache 与 marketplace drift 提示（M8）、autonomous-mode defaults（5 schema key + 5 个 `SPECODE_*` env var + `read-defaults` / `write-default` / `reset-default` verb，M1+M9）。**v4.0.0 BREAKING**：拔除记忆注入工程——P3-1 `codemap recall` 注入 / P3-2 rule-acknowledgement post-check / acceptance 后自动 distill 全部砍掉；round 1/2 baseline 实验证明 recall 注入未 net 节省 token。`distill` skill v4 完全重写为**仅手动**Obsidian 整理器——`/specode:distill <slug>` 默认 md-only 写到 `/Volumes/External HD/Obsidian/Notes/11-KnowledgeBase/<slug>/`，不再写 `.ai-memory/`。如需 v3 行为：`git checkout backup/specode-v3.4.0-task-swarm-v0.9.2`。 |
| **task-swarm** | 0.10.1 | 由 `pipeline.yml` 驱动的**多 agent 编排**：语义任务组 + 跨组并发、fork coder、按组 reviewer + validator 循环。**v0.10.1**：编排内核 skill `task-swarm` 改为 `user-invocable: false`，斜杠菜单不再显示裸 `/task-swarm`（命令 `/task-swarm:swarm` 不变）。AI-EDS 时代保留至 v0.10.0 的能力：frontmatter-first `project_root` + registry-based run 查找（0.7.x）、coder/reviewer/validator `task.md` 中「## 项目级约束（必读）」段 + `_PROJECT_AGENT_DOCS.md` inbox sentinel（0.7.3+0.7.4）、lifecycle group + `init` dedupe（`--on-existing` flag）+ `run.pipeline_end_validator`（0.8.0+0.8.1）、M2 `run-loop` 自动驱动器（0.8.1）、task.md 「## 开发纪律 (范式参考)」段列出 superpowers skill 名作为范式标识（0.9.0–0.9.2）。**v0.10.0 BREAKING**：拔除记忆注入工程——删 `_ingest_lessons.py` + `cmd_resolve` 自动 ingest + `--no-ingest` flag，`cmd_resolve` 不再写 `<project_root>/.ai-memory/knowledge/cases\|pitfalls/*.yml`。如需 v0.9.x 行为：`git checkout backup/specode-v3.4.0-task-swarm-v0.9.2`。详见 [`plugins/task-swarm/`](./plugins/task-swarm)。 |
| **obsidian-wiki** | 2.0.0 | 维护 Obsidian LLM-Wiki：确定性结构层（Home 树 / README / 分区页）、SpecIn → knowledge-base 蒸馏 + MEMORY、内容养护（lint / ingest / curate）、统一编排器。通用代码 + 按 vault 配 `.wiki/config.json`。详见 [`plugins/obsidian-wiki/`](./plugins/obsidian-wiki)。 |

`## 安装` 覆盖整个 marketplace；其余章节（能力亮点、使用、项目结构）记录的是 **specode**（旗舰插件）。**task-swarm** 的文档见 [`plugins/task-swarm/`](./plugins/task-swarm) 下的源码与 `CHANGELOG`。

## 能力亮点

- **编排外壳，不是重型引擎。** specode 把每个阶段委托给成熟的 superpowers 技能（`brainstorming` → `writing-plans` → `subagent-driven-development` / `executing-plans` → `verification-before-completion`），自身只管规格生命周期、文档落盘和 task-swarm 衔接。
- **原生降级，一等公民。** 没有 superpowers？specode 用 `AskUserQuestion` 向导 + 顺序 TDD 自己跑澄清 / 规划 / 执行 / 验收循环，原生路径与 superpowers 路径地位相同，不是凑数的备选。
- **3 份固定文档，固定命名，固定位置。** 每条规格产出 `requirements.md` / `design.md` / `implementation-log.md`，统一落在 `<specsRoot>/<slug>/` 下，无论用哪种引擎生成内容。缺陷修复用 `requirements.md` 散文描述，不单独建 `bugfix.md`。
- **文档即状态。** 无持久状态文件，无锁，无状态行 footer，无日志。"我在哪个阶段？"由已存在的文档以及 `design.md` 中 `- [ ]` 勾选进度推断得出。
- **单一自适应选择器。** `design.md` 确认后，`AskUserQuestion` 选择器动态呈现最多 4 条执行路径——仅展示当前已安装引擎对应的选项：委托 task-swarm / superpowers subagent-driven / superpowers executing-plans / specode 自执行。
- **首次使用问一次目录。** 第一次使用时，specode 询问你的文档管理目录，将其**原样**作为规格根目录持久化到 `~/.config/specode/config.json.specsRoot`，之后不再询问。
- **单个轻量 hook。** 仅一个 `SessionStart` 提醒式 hook，告知代理 specode 可用，不阻断，无逐轮机制。
- **并发执行是独立插件。** 选"委托 task-swarm"后，specode 读取 `design.md` 派生 `pipeline.yml`，零 import 衔接独立的 **task-swarm** 插件。
- **项目级约束沿链路传递。** specode + task-swarm（AI-EDS v0.9 痛点 #14 方案 D，保留至 v4.0.0 / v0.10.0）扫 `<project_root>` 根 / 直接父目录 / 任何被 `@writes` 触达的子目录里的 `CLAUDE.md` / `AGENT.md` / `AGENTS.md` / `CODEBUDDY.md`，把命中的**绝对路径**（不复制内容）同步注入 `requirements.md` 的「## 项目级约束」段 + 每个 coder / reviewer / validator `task.md` 的「## 项目级约束（必读）」段。`_PROJECT_AGENT_DOCS.md` inbox sentinel 强化硬约束。修掉「独立 subagent 进程看不到主 agent 自动加载的指南文件」这个静默漏点。
- **autonomous mode / CI 友好（opt-in）。** 设 `SPECODE_INTERACTIVE=false` + 相关 `SPECODE_PROJECT_ROOT` / `SPECODE_EXECUTION_MODE` / `SPECODE_AUTO_DISTILL` / `SPECODE_SPECS_ROOT_DEFAULT` env var（或 `resolve_root.py write-default --key X --value Y` 持久化），原本会在 CI / 长跑场景阻塞的每个 `AskUserQuestion` 都会 silently 跳过用 default。schema default 是 `interactive=true`，**默认行为零变化**——只 opt-in 用户走 autonomous 路径。
- **无记忆注入（v4.0.0 / v0.10.0 BREAKING）。** AI-EDS 时代的记忆注入管线（specode P3-1 `codemap recall` + P3-2 rule-check + acceptance auto-distill，加 task-swarm `cmd_resolve` auto-ingest 写 `.ai-memory/knowledge/*.yml`）在 baseline 实验（3 case）证明 recall 注入未 net 节省 token 后被完全移除。specode 4.0.0 是纯 spec-orchestration 外壳；task-swarm 0.10.0 是纯 multi-agent 执行器；两者都不读写 `.ai-memory/knowledge/`。如需在 Obsidian wiki 中保存按 spec 整理的知识，手动跑 `/specode:distill <slug>` — 默认 md-only 写到 `/Volumes/External HD/Obsidian/Notes/11-KnowledgeBase/<slug>/`。如需 v3.4.0 / v0.9.2 行为：`git checkout backup/specode-v3.4.0-task-swarm-v0.9.2`。

## 安装

> 📌 **marketplace 的名字是 `pluginhub`（仓库名），不是 `qxbyte`（owner 名）。**
> 所有安装 / 卸载命令都用 `<plugin>@pluginhub`（如 `specode@pluginhub` / `task-swarm@pluginhub`）。写成 `@qxbyte` 会报 `Marketplace "qxbyte" not found`。本地 cache 路径也按 marketplace 名挂在 `~/.claude/plugins/cache/pluginhub/<plugin>/<version>/`——排查"装了哪个版本"时常用到。

### GitHub（推荐）

两个 CLI 均支持，插件清单通用。CodeBuddy 已在 2.97.1 上验证。

```sh
# CodeBuddy
codebuddy plugin marketplace add https://github.com/qxbyte/pluginhub
codebuddy plugin install specode@pluginhub

# Claude Code
claude plugin marketplace add https://github.com/qxbyte/pluginhub
claude plugin install specode@pluginhub
```

如需完整的 superpowers 加持体验，请额外安装 **superpowers** 插件。如需多 agent 并发执行，请从同一 marketplace 额外安装 **task-swarm**（**无需**再 `marketplace add`）——装了它 specode 会在执行阶段委托给它，没装则 specode 顺序自执行：

```sh
# Claude Code
claude plugin install task-swarm@pluginhub
# CodeBuddy
codebuddy plugin install task-swarm@pluginhub
```

specode 不依赖这两者，原生降级路径开箱即用。

### 一次性会话（仅 Claude Code）

```sh
claude --plugin-url https://github.com/qxbyte/pluginhub/archive/refs/heads/main.zip
```

### 本地开发

```sh
git clone https://github.com/qxbyte/pluginhub.git
claude    --plugin-dir ./specode/plugins/specode
codebuddy --plugin-dir ./specode/plugins/specode

# 想用委托式多 agent 执行就把 task-swarm 也挂上
claude --plugin-dir ./specode/plugins/specode --plugin-dir ./specode/plugins/task-swarm
```

### 卸载

```sh
claude plugin uninstall specode@pluginhub
claude plugin uninstall task-swarm@pluginhub   # 若已安装
claude plugin marketplace remove pluginhub
# 可选：清理用户级配置（含旧 ~/.specode 状态）
rm -rf ~/.specode ~/.config/specode
```

### 升级

```sh
# Claude Code
claude plugin update specode@pluginhub
claude plugin marketplace update pluginhub

# CodeBuddy
codebuddy plugin update specode@pluginhub
codebuddy plugin marketplace update pluginhub
```

## 使用

specode 只有三条命令。

### 1. 新建规格

```sh
/specode:spec <需求>
```

先 `cd` 到你的项目目录——specode 以当前终端 cwd 作为项目根（无需额外指定）。**首次运行**时会询问一次文档管理目录并记住它。之后代理依次走完流水线：

1. **需求阶段** — 澄清 + 写 `requirements.md`（通过 `superpowers:brainstorming`，或原生 `AskUserQuestion` 向导）。
2. **设计阶段** — 生成可执行计划 `design.md`（通过 `superpowers:writing-plans`，或原生任务分解）。
3. **执行方式选择器** — 从自适应 4 个选项中选择执行路径（详见上方亮点）。
4. **执行阶段** — 以 TDD 方式跑完计划，追加写入 `implementation-log.md`。
5. **验收阶段** — 对照 `design.md` 测试点和 `requirements.md` 的 `AC-N` 验收条件检查，然后由你确认接受。

所有输出以 3 份固定文档落在 `<specsRoot>/<slug>/` 下。

### 2. 续接规格

```sh
/specode:continue <slug>
```

`<slug>` 为必填。specode 定位到 `<specsRoot>/<slug>/`，根据已存在的文档（以及 `design.md` 中的 `- [ ]` 进度）推断当前阶段，从那里继续。不知道 slug？用 `/specode:list` 查找。

### 3. 列出规格

```sh
/specode:list
```

列出 `<specsRoot>` 下所有规格及其推断阶段，仅供概览，不会自动续接。

## 项目结构

```
.claude-plugin/marketplace.json   marketplace 清单（specode + task-swarm）
plugins/specode/
  .claude-plugin/plugin.json      插件清单（version 2.0.0）
  hooks/hooks.json                1 个提醒式 SessionStart hook
  commands/spec.md        /specode:spec（新建）
  commands/continue.md    /specode:continue <slug>
  commands/list.md        /specode:list
  scripts/
    resolve_root.py               specsRoot 解析 + 持久化 + list
    spec_hooks.py                 SessionStart 规范注入
    run.sh / run.cmd              python3 → python → py 解释器探测
  skills/specode/
    SKILL.md                      编排外壳（全部行为规范）
    references/
      selectors.md                执行方式选择器逐字示例
      obsidian.md                 specsRoot 路径解析 + 惯例
      superpowers-wiring.md       阶段 ↔ superpowers 技能映射
  assets/templates/               requirements.md / design.md /
                                  implementation-log.md 种子模板
  tests/                          hermetic pytest 测试套件（resolve_root.py）
```

配套的 **task-swarm** 插件（`plugins/task-swarm/`）是独立的多代理编排器，specode 可选择性地将执行阶段交由它负责；详见其自身的 README 和 `CLAUDE.md`。

## 贡献

参见 [`CONTRIBUTING.md`](./CONTRIBUTING.md)，其中涵盖：runtime 仅限标准库、`run.sh` CLI 调用契约、提醒式 hook 规则、hermetic 测试规范以及发版流程。

## 许可证

MIT
