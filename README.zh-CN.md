<p align="right"><a href="./README.md">English</a> | <strong>中文</strong></p>

# specode

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./README.zh-CN.md#许可证)
[![Version](https://img.shields.io/badge/version-0.10.21-blue.svg)](./plugins/specode/.claude-plugin/plugin.json)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-compatible-8A2BE2)](https://github.com/qxbyte/specode#installation)
[![CodeBuddy](https://img.shields.io/badge/CodeBuddy-2.97.1%2B-1E90FF)](https://github.com/qxbyte/specode#installation)
[![Tests](https://img.shields.io/badge/pytest-152%20cases-success)](./plugins/specode/tests)

> 面向 CLI 编码代理（Claude Code / CodeBuddy）的规格驱动工作流插件。

specode 把一句话需求变成一条「文档优先」的纪律化交付链路。代理被牵着走过
固定的 phase 流水线 —— **requirements → design → tasks → implementation
→ acceptance**，五份 Markdown 文档（`requirements.md` / `bugfix.md` /
`design.md` / `tasks.md` / `implementation-log.md`）是唯一事实源。
每个 phase-gate 由你在 chat 里通过选择器决定下一步；中间过程由提醒式
hook 把代理钉在轨道上，**永不阻断**工具调用。

如果你见过 LLM 代理跑着跑着就飘、跨窗口丢上下文、合上未审过的代码 ——
specode 就是给它套的轨道。

## 能力亮点

- **Document-first 纪律**：每条需求都先落到 spec 文档再动代码。Hook 在
  写代码前后都会提醒代理读 / 改文档。
- **提醒式 Hook，永不阻断**：7 个 hook 全部 `exit 0`，只往模型上下文
  注入提示（状态行 footer、phase 选择器、文档-代码同步提醒、静默续锁
  心跳），不会中途打断工具调用，不再有「hook 拒绝」的意外。
- **会话状态绑定 `session_id`**：每个宿主 session 拥有独立状态文件
  `~/.specode/sessions/<session_id>.json`（原子写）。同时开三个窗口
  也不会混在一起。
- **Phase-gate 选择器**：每个决策点由代理按三种骨架（A 单选 / B
  wizard / C 复选）渲染 11 个固定场景之一 —— 你选方向，代理执行。
- **task-swarm —— 内置的并发实现编排器**：`tasks.md` 确认后，task-swarm
  扇出多个 **coder** 子代理并发干活（按 `@writes` 文件写冲突自动切
  group、按 `@depends-on` 排拓扑），再让单实例 **reviewer** 提
  建议（P0 触发一次修复）和单实例 **validator** 做最终判定（pass/fail
  二元，fail 会循环修到 pass）。连续 3 轮同 fail 触发死循环保护。
- **Obsidian 感知的文档根**：三层解析（env > config > 自动探测
  Obsidian vault），spec 落进你的知识库，而不是散在各 project 目录。
- **active 期间每个 turn 都有状态行 footer**：永远知道自己在哪里：
  ```
  ─── spec-mode ─── spec: <slug> | session: <前 8 位> | phase: <p> | /specode:end 退出
  ```
- **每个 session 的 JSONL 日志**：用来排查「代理为什么走偏」，默认
  屏蔽敏感字段、字符串自动截断到 500 字符。
- **主代理直接写 spec 文档**：不 fork subagent —— 主代理读
  `assets/templates/<phase>.md` 模板骨架、按用户原始需求填空，全程
  保留上下文与对话状态（0.10.11 之前用过 `spec-writer` subagent，
  因为拿不到主代理上下文容易 hallucinate 通用模板内容，故移除）。

## 安装

### GitHub（推荐）

两个 CLI 都行，插件清单通用。CodeBuddy 已在 2.97.1 上验证。

```sh
# CodeBuddy
codebuddy plugin marketplace add https://github.com/qxbyte/specode
codebuddy plugin install specode@specode

# Claude Code
claude plugin marketplace add https://github.com/qxbyte/specode
claude plugin install specode@specode
```

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
# 可选：清理用户级状态
rm -rf ~/.specode ~/.config/specode
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

### 1. 首次使用：绑定文档根

spec 文档落在 `<doc_root>/specs/<slug>/`。绑定一次即可长期记住：

```sh
/specode:spec --set-vault <路径>     # 绑定 Obsidian vault
/specode:spec --set-root <路径>      # 任意目录都行（等价）
/specode:spec --detect-vault         # 列出已检测到的 vault
/specode:spec --vault-status         # 查看当前文档根 + 解析来源
```

未绑定时 specode 会自动探测 Obsidian vault，没有就会在创建 spec 时
问你。

### 2. 新建 spec

```sh
/specode:spec -n <slug> <需求>       # 推荐：显式 slug
/specode:spec <需求>                 # 或让代理推导 slug
/specode:spec <名称>: <需求>         # 或同时指定显示名 + 需求
```

`-n` 保留 slug 原文（允许 Unicode：中文 / 日文 / emoji 都行），只禁
文件系统危险字符。不带 `-n` 的写法让代理推导 slug，方便但结果不可预知。

创建成功后代理会**连续**呈现两个选择器：

1. **project-root-choice**：代码写到哪个目录（与文档目录解耦）。
2. **workflow-choice**：从 `requirements.md` 起步，还是走 `bugfix.md`
   缺陷修复流程等。

之后每个 turn 都以状态行 footer 收尾，phase-gate 处由代理弹选择器
让你决定下一步。

### 3. 管理会话

```sh
/specode:continue [slug]    # 恢复当前 session 或切到指定 spec
/specode:status             # 查看 mode / phase / lock / pending selector
/specode:end                # 结束 session（文档保留）
```

状态按宿主 `session_id` 隔离，每个终端窗口各自一条线。

### 4. task-swarm：并发跑 tasks

`tasks.md` 确认后，在 `tasks-execution` 选择器里选 `task-swarm` 路径，
编排器接管：

```
init  →  plan  →  fork（N 个 coder）  →  advance  →  writeback  →  resolve
                ↑                                    ↓
                └────────── reviewer / validator ────┘
```

- **coder** 并发执行，按 `@writes` 文件冲突自动切 group。
- **reviewer** 每个 group 单实例；只有带证据标签（`[req:x.y]` /
  `[security]` / `[contract]`）的 P0 才触发一轮 `p0-fix`，其余 advisory。
- **validator** 每个 group 单实例；`fail` 进入 `v-fix` 循环直到 `pass`，
  连续 3 轮同 fail 触发死循环保护。
- 可在 `tasks-execution` 选择「task-swarm + 人工验收（跳过 validator）」
  → 加 `--skip-validator` 走人工验收。

`/specode:task-swarm` 是入口；完整状态机规格见
`references/task-swarm.md`。

### 5. 查看 session 日志

specode 默认把每个 session 的事件流写到
`~/.specode/logs/<session_id>.jsonl`（含 hook 触发、主代理工具调用、
phase / lock 变化），用于排查「代理为什么跳过 phase / fork 错 agent /
选错 selector」：

```sh
sh "$CLAUDE_PLUGIN_ROOT/scripts/run.sh" \
   "$CLAUDE_PLUGIN_ROOT/scripts/spec_log.py" replay --session <id>
```

默认 redact 黑名单（`password / api_key / token / …`），字符串字段
自动截断到 500 字符。可通过 `~/.config/specode/config.json.redact_keys`
扩展黑名单。

### 6. 全局 bypass（仅调试）

```sh
SPECODE_GUARD=off   # 让所有 hook 立刻 exit 0
SPECODE_LOG=off     # 让 session 日志不写入
```

## 项目结构

```
.claude-plugin/marketplace.json   单插件 marketplace 清单
plugins/specode/
  .claude-plugin/plugin.json      插件清单
  hooks/hooks.json                7 个提醒式 hook handler
  commands/                       /specode:spec, :continue, :end,
                                  :status, :task-swarm
  agents/                         task-swarm-{planner,coder,
                                  reviewer,validator}
  scripts/                        spec_vault / spec_init /
                                  spec_session / spec_lint /
                                  spec_status / task_swarm*
  skills/specode/                 SKILL.md + references/
  assets/templates/               文档模板
  tests/                          152 个 pytest 用例
```

## 贡献

参见 [`CONTRIBUTING.md`](./CONTRIBUTING.md)：runtime 仅限标准库、
hook 安全契约（提醒式、永不 `exit 2`）、测试规范。

## 许可证

MIT
