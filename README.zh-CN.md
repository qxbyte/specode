<p align="right"><a href="./README.md">English</a> | <strong>中文</strong></p>

# specode

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./README.zh-CN.md#许可证)
[![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)](./plugins/specode/.claude-plugin/plugin.json)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-compatible-8A2BE2)](https://github.com/qxbyte/specode#installation)
[![CodeBuddy](https://img.shields.io/badge/CodeBuddy-2.97.1%2B-1E90FF)](https://github.com/qxbyte/specode#installation)

> 面向 CLI 编码代理（Claude Code / CodeBuddy）的轻量级规格驱动工作流插件。

specode 1.0.0 把一句话需求变成一条「文档优先」的纪律化交付链路——但自身几乎不携带任何机制。它是一个**编排外壳**：在每个阶段（需求 → 设计 → 执行 → 验收）把重活**委托给 [superpowers](https://github.com/obra/superpowers) 技能**；若未安装 superpowers，则自动降级到同等地位的 **specode 原生路径**，插件可独立运行。每条规格最终固定产出 **3 份文档**，落进你的规格目录。

如果你见过 LLM 代理跑着跑着就飘、合上未审过的代码——specode 就是给它套的轻量轨道。

## 能力亮点

- **编排外壳，不是重型引擎。** specode 把每个阶段委托给成熟的 superpowers 技能（`brainstorming` → `writing-plans` → `subagent-driven-development` / `executing-plans` → `verification-before-completion`），自身只管规格生命周期、文档落盘和 task-swarm 衔接。
- **原生降级，一等公民。** 没有 superpowers？specode 用 `AskUserQuestion` 向导 + 顺序 TDD 自己跑澄清 / 规划 / 执行 / 验收循环，原生路径与 superpowers 路径地位相同，不是凑数的备选。
- **3 份固定文档，固定命名，固定位置。** 每条规格产出 `requirements.md` / `design.md` / `implementation-log.md`，统一落在 `<specsRoot>/<slug>/` 下，无论用哪种引擎生成内容。缺陷修复用 `requirements.md` 散文描述，不单独建 `bugfix.md`。
- **文档即状态。** 无持久状态文件，无锁，无状态行 footer，无日志。"我在哪个阶段？"由已存在的文档以及 `design.md` 中 `- [ ]` 勾选进度推断得出。
- **单一自适应选择器。** `design.md` 确认后，`AskUserQuestion` 选择器动态呈现最多 4 条执行路径——仅展示当前已安装引擎对应的选项：委托 task-swarm / superpowers subagent-driven / superpowers executing-plans / specode 自执行。
- **首次使用问一次目录。** 第一次使用时，specode 询问你的文档管理目录，将其**原样**作为规格根目录持久化到 `~/.config/specode/config.json.specsRoot`，之后不再询问。
- **单个轻量 hook。** 仅一个 `SessionStart` 提醒式 hook，告知代理 specode 可用，不阻断，无逐轮机制。
- **并发执行是独立插件。** 选"委托 task-swarm"后，specode 读取 `design.md` 派生 `pipeline.yml`，零 import 衔接独立的 **task-swarm** 插件。

## 安装

### GitHub（推荐）

两个 CLI 均支持，插件清单通用。CodeBuddy 已在 2.97.1 上验证。

```sh
# CodeBuddy
codebuddy plugin marketplace add https://github.com/qxbyte/specode
codebuddy plugin install specode@specode

# Claude Code
claude plugin marketplace add https://github.com/qxbyte/specode
claude plugin install specode@specode
```

如需完整的 superpowers 加持体验，请额外安装 **superpowers** 插件；如需多代理并发执行，请额外安装同一 marketplace 下的 **task-swarm** 插件。specode 不依赖这两者，原生降级路径开箱即用。

### 一次性会话（仅 Claude Code）

```sh
claude --plugin-url https://github.com/qxbyte/specode/archive/refs/heads/main.zip
```

### 本地开发

```sh
git clone https://github.com/qxbyte/specode.git
claude    --plugin-dir ./specode/plugins/specode
codebuddy --plugin-dir ./specode/plugins/specode
```

### 卸载

```sh
claude plugin uninstall specode@specode
claude plugin marketplace remove specode
# 可选：清理用户级配置
rm -rf ~/.config/specode
```

### 升级

```sh
# Claude Code
claude plugin update specode@specode
claude plugin marketplace update specode

# CodeBuddy
codebuddy plugin update specode@specode
codebuddy plugin marketplace update specode
```

## 使用

specode 只有三条命令。

### 1. 新建规格

```sh
/spec <需求>
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
/spec continue <slug>
```

`<slug>` 为必填。specode 定位到 `<specsRoot>/<slug>/`，根据已存在的文档（以及 `design.md` 中的 `- [ ]` 进度）推断当前阶段，从那里继续。不知道 slug？用 `/spec list` 查找。

### 3. 列出规格

```sh
/spec list
```

列出 `<specsRoot>` 下所有规格及其推断阶段，仅供概览，不会自动续接。

## 项目结构

```
.claude-plugin/marketplace.json   marketplace 清单（specode + task-swarm）
plugins/specode/
  .claude-plugin/plugin.json      插件清单（version 1.0.0）
  hooks/hooks.json                1 个提醒式 SessionStart hook
  commands/spec.md                /spec、/spec continue、/spec list
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
