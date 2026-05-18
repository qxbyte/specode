<p align="right"><a href="./README.md">English</a> | <strong>中文</strong></p>

# specode

面向 **Claude Code** 与 **CodeBuddy** 的规格驱动工作流插件。

承担约束的工作流规则由 Claude Code hooks 强制——也就是 harness 实际执行的确定性 shell 命令——而不是依赖模型在上下文里"记住并遵守"指令。

## 强制保证（Invariants）

只要 spec 处于激活状态，下列规则即由 **harness 检查**。0.4.0 起 INV 分两级：

- **advisory**（流程纪律）：违反时在 ledger 写一条 sticky 提醒，下轮 `UserPromptSubmit` 状态块显示；工具调用照样放行。改任一 spec 文档自动清除 INV-1/2/4；手动清除运行 `/spec --dismiss-advisories`。
- **enforced**（数据/契约保护）：违反时硬拒（exit 2），防止数据丢失、被驱逐覆盖写、subagent 派单错、subagent 越界写。

| ID | 规则 | Hook | 等级 |
|---|---|---|---|
| **INV-1** | 编辑源码需 `tasks.md` 列表覆盖、同轮 doc 编辑、或 `freeform` 模式 | `PreToolUse` | **advisory** |
| **INV-2** | 触碰源码的 turn 应在结束前至少触碰一份 spec 文档 | `Stop` | **advisory** |
| **INV-3** | 当前会话已被其他窗口驱逐时，spec 文档写入被拒 | `PreToolUse` | **enforced** |
| **INV-4** | `requirements.md` / `bugfix.md` 编辑应同轮更新 `tasks.md ## 测试要点` | `Stop` | **advisory** |
| **INV-5** | 每个用户 turn 注入状态块（`spec / phase / lock / turn / advisories`） | `UserPromptSubmit` | 注入 |
| **INV-6** | 实现前阶段（intake / requirements / bugfix / design / tasks）禁止源码编辑 | `PreToolUse` | **advisory** |
| **INV-7** | task-swarm 运行期间 `Task` 工具的 `subagent_type` 必须 `specode:` 前缀 | `PreToolUse` | **enforced** |
| **INV-8** | subagent 写出 `@writes` 边界的文件被拒 | `PreToolUse` | **enforced** |
| **INV-9** | task-swarm 期间 `tasks.md` 编辑必须经 `writeback`（line-safe diff） | `PreToolUse` | **enforced** |
| **INV-11** | 会卡死在 TTY 的 `Bash` 命令（`npm create`、`git commit` 无 `-m`、`vim` 等）被拒，附非交互改写建议；`PostToolUse` 还会扫描输出中的交互提示特征，命中即注入 advisory | `PreToolUse` + `PostToolUse` | **enforced** + advisory |

INV-1 与 INV-2 共同构成 **Code-Doc Sync Guard (CDSG)** —— 0.4.0 起降为 advisory（0.3.x 仍为硬拒）。

## 项目结构

```
.claude-plugin/marketplace.json   ← 单插件 marketplace 清单
plugins/specode/
  .claude-plugin/plugin.json      ← 插件清单
  hooks/hooks.json                ← 6 个事件处理器，挂哨兵 shell 短路
  hooks/hooks-probe.json          ← 诊断探针（重新验证时替换上去）
  skills/specode/               ← skill 内容（SKILL.md + references）
  commands/                       ← /spec, /continue, /status, /end
  scripts/
    spec_guard.py                 ← hook 入口；分发 + 审计日志
    spec_state.py                 ← 只读状态探测 + 哨兵 + Claude 会话登记
    spec_sync.py                  ← INV-1/2/3/4/6 逻辑；ledger；阶段闸门；glob 匹配
    spec_session.py               ← 锁 + 阶段 + active-pointer 模型
    spec_init.py / spec_lint.py / spec_status.py / spec_choice.py / spec_vault.py
  tests/                          ← 19 个 pytest 用例（单元 + 集成）
```

## 安装

### 通过 GitHub（推荐）

```sh
# Claude Code
claude plugin marketplace add https://github.com/qxbyte/specode
claude plugin install specode@specode

# CodeBuddy（已在 2.97.1 上验证）
codebuddy plugin marketplace add https://github.com/qxbyte/specode
codebuddy plugin install specode@specode
```

两个 harness 都会克隆 marketplace、定位到 `plugins/specode/` 下的插件，然后自动加载 `hooks/`、`skills/`、`commands/`。后续升级用 `claude plugin update specode` 或 `claude plugin marketplace update specode`。

### 一次性会话（仅 Claude Code）

```sh
claude --plugin-url https://github.com/qxbyte/specode/archive/refs/heads/main.zip
```

仅当前会话生效，不持久化任何状态。

### 本地开发

```sh
git clone https://github.com/qxbyte/specode.git
claude    --plugin-dir ./specode/plugins/specode
codebuddy --plugin-dir ./specode/plugins/specode
```

加载后：

```
/help                              # 列出 /specode:* 系列命令
/reload-plugins                    # 修改插件文件后重新加载
```

Hook 行为日志写入 `~/.specode/audit/<date>.log`（UTC）。

可选的**本地 telemetry**（记录 spec 生命周期、INV 触发、task-swarm 收敛轮数等流程事件）——默认关闭，需要 `SPECODE_TELEMETRY=on` 启用。事件写入单文件 `~/.specode/telemetry.jsonl`（append-only，不上报远端，不按日切，方便 grep）。运行 `python3 scripts/spec_state.py telemetry-summary` 做本地聚合分析。

### 卸载

```sh
# 1. 先卸载插件
claude plugin uninstall specode@specode

# 2. 再移除 marketplace
claude plugin marketplace remove specode

# 3.（可选）清理用户级运行时状态（步骤 1 不会动这些）
rm -rf ~/.specode ~/.config/specode
# 想彻底清干净还可以删 vault 里的索引文件：
#   find <obsidian-vault> -name '.active-specode.json' -delete
```

注意事项：

- **顺序很重要**：必须先卸 plugin 再卸 marketplace，否则 Claude Code 下次启动会
  报 orphaned plugin 警告。
- `claude plugin uninstall` 只移除安装记录；`~/.claude/plugins/cache/specode/`
  下的缓存会在 orphan 后约 7 天自动 GC。想立刻回收磁盘：
  `rm -rf ~/.claude/plugins/cache/specode/`。
- `~/.specode/` 和 `~/.config/specode/` 是 *用户* 数据（audit 日志、会话记录、
  obsidianRoot 配置），卸载命令**故意不动**它们——这样重装时你的 spec 历史不丢。
  想从头开始就手动删。
- 只想**临时禁用**而不卸载：`claude plugin disable specode@specode`（用
  `enable` 启回来）。

## 使用

会话内（插件已加载）：

```
/specode:spec --persist <需求>            # 启动持久 spec 会话
/specode:continue [slug]                  # 恢复 / 切换 spec
/specode:status                           # 查看当前会话状态
/specode:end                              # 结束持久会话

/specode:spec --freeform                  # 放宽 INV-1（INV-2 仍然强制）
/specode:spec --strict                    # 恢复 INV-1
/specode:spec --sync-status               # 查看 ledger / 待同步项 / 上次违规
```

spec 激活后：

- 每个用户 prompt 都会被附加一段 `specode active` 状态块，标注 spec、phase、锁状态、turn id、freeform 模式
- 对项目源文件的编辑（不在 `tasks.md` 列表内的）会被拦截，除非同一轮先动了文档（INV-1）
- 触碰过代码的 turn 在停止前未触碰任何文档时会被拦下，模型必须补一条 `design.md` / `tasks.md` / `implementation-log.md`（INV-2）
- 改 `requirements.md` / `bugfix.md` 必须在同一轮更新 `tasks.md` 的 `## 测试要点` 节（INV-4）
- intake / requirements / bugfix / design / tasks 阶段绝对不允许源代码编辑——freeform **不**豁免 INV-6

## 不对称约束说明

INV-2 是**单向**的：源代码变更 ⇒ 必须有文档变更，但纯文档编辑（错别字、措辞调整）**不**强制配套代码变更。`implementation-log.md` 算作满足 INV-2 的轻量文档动作——`spec_lint.py` 对短于 30 字符或没有引用任何实际代码文件的日志条目会发出软 WARNING（防止"装饰性文档"绕规则）。

## 性能预算

| Hook | 墙钟预算 |
|---|---|
| `SessionStart` / `SessionEnd` | 总会跑 Python；<500ms |
| `UserPromptSubmit` | 仅当 `~/.specode/.any-active` 哨兵存在时跑 Python；<80ms |
| `PreToolUse` / `PostToolUse` / `Stop` | 同样的 shell 短路；运行时 <100ms |

无 spec 激活时，shell 那行 `[ ! -e ~/.specode/.any-active ]` 直接退出，Python 根本不启动 → 实际成本可忽略。

## CodeBuddy 支持

已在 CodeBuddy 2.97.1 上验证：相同的 `hooks/hooks.json` 与 `scripts/spec_guard.py` 不需任何修改即可工作。CodeBuddy 内部基于 Claude Code 2.1.142 agent，并同时注入 `CLAUDE_PLUGIN_ROOT` 与 `CODEBUDDY_PLUGIN_ROOT`，因此集成是字节级兼容的。

## 贡献

参见 [`CONTRIBUTING.md`](./CONTRIBUTING.md)：runtime 仅限标准库、hook 安全契约、测试规范。

## 许可证

MIT
