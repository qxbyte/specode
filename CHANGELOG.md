# Changelog

## Unreleased

## 0.10.22 (2026-05-26)

### Refactored — `spec_session.py` 拆分 + 两大 CLI 子目录化

**两步走的纯重构，无行为变化。**

#### 第一步（B1）：spec_session.py 拆成 5 个 `_ss_*.py` sibling

`spec_session.py` 从 2360 行的"什么都装"模块拆成薄入口 + 5 个 sibling：

| 模块 | 承载 |
|---|---|
| `_ss_io.py` | 原子写、session+spec config 读写、锁工具、共享常量（`VALID_PHASES` / `STALE_LOCK_SECONDS`） |
| `_ss_selectors.py` | `SELECTOR_PROMPTS` 字典 + `_fill_selector` |
| `_ss_reminders.py` | reminder 模板字符串 + help 文本渲染 |
| `_ss_business.py` | 所有 `cmd_*` 业务命令 + `_update_session_for_spec` |
| `_ss_hooks.py` | 所有 `hook_on_*` + `_safe_hook` + task-swarm plan 提醒辅助 |

#### 第二步：两大 CLI 子目录化 + 同名 launcher

`scripts/` 顶层从 19 个 `.py` 收敛到 7 个 + 2 个 package 目录。`spec_session`
和 `task_swarm` 各自从「下划线前缀 fake namespace」升级为真子目录包：

```
scripts/
├── spec_session.py            # ~40 行薄 launcher（utf-8 reconfigure + sys.path + main 转发）
├── spec_session/              # package（_io / _selectors / _reminders / _business / _hooks / _catalog / cli）
├── task_swarm.py              # ~25 行薄 launcher
├── task_swarm/                # package（_state / _parse_md / _outbox / _prompt / _writeback / cli）
└── （其余 5 个独立 CLI：spec_init / spec_lint / spec_log / spec_status / spec_vault）
```

文件改名规则：`_ss_io.py` → `spec_session/_io.py`，`task_swarm_state.py` →
`task_swarm/_state.py` 等（去前缀、加 `_` 标记 internal）。

**外部 API surface 100% 不变**：
- 文件名 `spec_session.py` / `task_swarm.py` 保留——`hooks/hooks.json`、`commands/*.md`、`tests/conftest.py:run_script` 都按这些名字拼绝对路径调用。Python 的 `FileFinder` 在同一 path entry 下 package 优先于 module，launcher 自己被 exec 不走 import 系统，所以同名文件 + 同名目录共存安全。
- `spec_status.py:25` 的 `from spec_session import read_session, read_spec_config, _session_short, _is_lock_stale` 仍可解析（`spec_session/__init__.py` 从 `_io` re-export 这 4 个符号）。
- `tests/test_selectors_drift.py` SCRIPTS 路径 → `spec_session/_selectors.py`；4 个 `test_task_swarm_*.py` 的直接 import → `from task_swarm._<X> import ...`。

**包内规范**：
- 包内 import 用 absolute 形式（`from spec_session._io import ...`），出错信息清晰。
- 包内文件需要找顶层 sibling 脚本时，统一 `_THIS_DIR = Path(__file__).resolve().parents[1]`（= `scripts/`），让旧用法 `_THIS_DIR / "task_swarm.py"` / `_THIS_DIR.parent / ".claude-plugin"` 语义一致。

219 项原有测试 + 18 项新 catalog 测试 = 237 全绿；无 schema 变化、无 hook 行为变化、外部用户无需任何 install / config 改动。

### Added — `on-user-prompt-catalog` hook：reference 关键词触发提示

新 advisory hook，注册到 `hooks.json` `UserPromptSubmit` 数组第 3 位。激活
门：仅 `mode=active` 触发，`idle / readonly / ended` 一律静默。

**机制**：
- 每个 `references/*.md` 文件首部新增 YAML frontmatter `description: Use when …`（"何时该读"而非"内容是什么"，superpowers 风格）。
- `spec_session/_catalog.py` 维护一份预编译关键词正则字典 `CATALOG`（含中英文双语 pattern，例如 `lock / takeover / 接管` → `lock-protocol`，`task-swarm / @writes / reviewer` → `task-swarm` 等 8 个 key）。
- 每轮 user prompt 触发：扫文本、把命中的 reference 列出来 + 嵌入对应 description，作为 `additionalContext` 注入。

**目的**：specode 从"全程监考"扩展为"全程监考 + 定向激活"双模并存。
主代理看到注入后自己决定是否真要 Read 对应 reference；hook 永远 advisory，
不阻断。

**新 drift 守卫**：
- `tests/test_catalog.py::test_catalog_keys_have_matching_reference_files` —— `CATALOG` key 必须对应真实 `references/<key>.md`
- `tests/test_catalog.py::test_every_catalog_referenced_file_has_description_frontmatter` —— 每份 referenced 文件必有非空 `description` 字段

性能：每次调用纯预编译正则匹配 + 最多 8 次小文件读，远低于
UserPromptSubmit 80ms 预算。

## 0.10.21 (2026-05-23)

### Fixed — writeback line-safe 算法对多行 `reproduce_cmd` 报"越界"

**用户痛点（login-page 现场）**：validator-g1-r3 pass，`reproduce_cmd` 含多行（`cd C:\Users\qiang\login-page` + 空行 + `# 验证 P0...` + `node -e "..."`）。`task_swarm.py writeback` 报错：

```
writeback 越界：line 49
原: '## 阶段 5: 集成测试'
新: '# 1. 验证 Vite 构建成功（前端无编译错误）'
```

根因：`task_swarm_writeback.py:_format_findings_block` 把 multi-line `reproduce_cmd` 直接拼进 `f"> ✅ validator pass: \`{cmd}\`"` 的 inline backtick——这个字符串作为单元素追加进 `out` 列表。后续 `"\n".join(new_lines + block_lines)` 写入 tasks.md，**`cmd` 内部的 `\n` 被保留**，文件实际多了几行非 `>` 前缀的内容（如 `# 验证 P0 修复`、`node -e "..."`）。`_verify_line_safe` 行级对齐时发现新行不属于"checkbox toggle"也不"以 `>` 开头"，报"越界"。

修复 `task_swarm_writeback.py:_format_findings_block`：

```python
if "\n" in cmd:
    out.append(f"> ✅ validator{round_text} pass，复现命令：")
    out.append("> ```")
    for cmd_line in cmd.splitlines():
        out.append(f"> {cmd_line}" if cmd_line else ">")
    out.append("> ```")
else:
    cmd_text = f": `{cmd}`" if cmd else ""
    out.append(f"> ✅ validator{round_text} pass{cmd_text}")
```

多行 cmd 用 `> ```fenced` ` 块，每行加 `> ` 前缀（包括空行用 `>`）→ 完全满足 `_verify_line_safe` 的"允许多出 `> ` 前缀或空行"规则。单行 cmd 仍 inline。

### Changed — PreToolUse hook 对 `tasks.md` 从软提醒升级为强阻断

**用户痛点（login-page 现场）**：上面 writeback 报越界后，主代理**手工 Edit tasks.md** 把 1-4 阶段所有 `[ ]` 改成 `[x]`——破坏 state.json 与 tasks.md 行号一致性，后续 writeback 永远过不去。0.10.13 PreToolUse hook 当时对 tasks.md 给的是**软提醒**（"本提醒不阻断当前工具调用"），主代理见 writeback 失败就绕过 CLI 自己改。

修复 `spec_session.py:hook_on_pre_tool_use`：

旧（软提醒，可忽略）：

```python
text = "## ⚠ 检测到正在直接 Edit/Write tasks.md ..."
_emit_hook_additional_context(text, hook_event_name="PreToolUse")
```

新（强阻断，exit 2 + stderr 详细原因）：

```python
sys.stderr.write(
    f"specode 阻断：主代理不得直接 Edit/Write `tasks.md` ...\n"
    "若 writeback 本身报越界，请保留现场报告用户，让 task-swarm 算法层修，\n"
    "**不要**手工抹平。\n"
)
sys.exit(2)
```

现在 `tasks.md` 跟 `.task-swarm/runs/*/state.json` / `agents/*/outbox/*` 同等待遇——active spec + task-swarm 进行中时主代理一律不能直接 Edit/Write，必须走 `task_swarm.py writeback` CLI。

### Tests

- 新增 `test_writeback_handles_multi_line_reproduce_cmd`：触发 multi-line reproduce_cmd writeback 全流程，断言不报越界 + tasks.md 包含 `> ```` 块 + 每行带 `> ` 前缀
- 新增 `test_on_pre_tool_use_blocks_edit_of_tasks_md`：active spec + task_swarm_run_id 进行中 → Edit tasks.md → exit 2 + stderr 含 `task_swarm.py writeback` 引导
- 全套 pytest **219/219 PASS**

## 0.10.20 (2026-05-23)

### Added — `--skip-validator` 人工验收模式：task-swarm 跳过 validator/v-fix

**用户痛点**：login-page 现场显示一轮 validator 跑下来要花 25-50k tokens + 大量 Bash 测试，多轮 v-fix 循环下成本高昂。用户希望有"task-swarm 但不启动 validator"的选项——多 coder 并发 + reviewer + p0-fix 仍走，但跳过 validation/v-fix 循环；代码正确性由用户**事后人工核验**，有问题再跟模型常规对话沟通。

实现：

1. **`task_swarm_state.py` `StateMachine`**：加 `skip_validator: bool = False` 字段，load/to_dict 同步。
2. **`task_swarm.py cmd_init`**：加 `--skip-validator` argparse flag；写入 state.json；events_append init 事件含 `skip_validator` 字段。
3. **`task_swarm.py cmd_advance`**：两处分支改造：
   - review phase advance：`if sm.p0_pending: begin_p0_fix ...; elif sm.skip_validator: begin_writeback（直接进 writeback）; else: begin_validation`
   - p0-fix phase advance：`if sm.skip_validator: begin_writeback; else: begin_validation`
4. **`task_swarm_writeback.py`**：
   - `GroupFindings` 加 `skip_validator: bool = False` 字段
   - `_format_findings_block` 优先检查 skip_validator——若 True 写 "`> ⏭️ validator 已跳过（人工验收模式）—— 代码正确性由用户人工核验`"，否则走原有 pass/fail/deadloop 分支
5. **`task_swarm.py cmd_writeback`**：构造 `GroupFindings` 时把 `sm.skip_validator` 传入
6. **`spec_session.py` SELECTOR_PROMPTS["tasks-execution"]** 4 个选项重新组织：
   - "task-swarm + validator 自动验收（推荐）"
   - "task-swarm + 人工验收（跳过 validator）"（新）
   - "顺序执行（同时处理 optional）"
   - "暂停 / 调整 tasks.md"（合并原"需要调整" + "暂不 coding"）
7. **`commands/task-swarm.md`** 第二步 init 提及 `[--skip-validator]` flag + 触发条件
8. **`references/selectors.md` A4** drift-sync byte-identical

**新模式流程**：
```
init --skip-validator → coding → review → p0-fix → writeback → next group
                                             （跳过 validation / v-fix）
```

用户使用：
1. tasks.md 生成后呈现 `tasks-execution` selector
2. 选「task-swarm + 人工验收（跳过 validator）」
3. 主代理调 `task_swarm.py init --tasks <p> --session <id> --skip-validator`
4. 流程按 full 模式跑 coding → review → p0-fix（行为不变）
5. **p0-fix 完成后状态机直接进 writeback**（不 fork validator）
6. writeback 把 tasks.md `[ ]` → `[x]`，注释块写"⏭️ validator 已跳过"
7. 用户人工 review 代码 → 有问题跟模型常规对话沟通调整

### Tests

- 新增 `test_init_skip_validator_flag_persists_to_state`：验证 flag 写入 state.json
- 新增 `test_init_without_flag_defaults_to_full_mode`：默认兼容
- 新增 `test_skip_validator_review_no_p0_skips_validation`：无 P0 直接 writeback
- 新增 `test_skip_validator_p0_fix_done_skips_validation`：p0-fix 完直接 writeback
- 新增 `test_skip_validator_writeback_writes_skipped_note`：writeback 注释含"validator 已跳过"
- 更新 `test_tasks_execution_snapshot` 预期 4 个新选项
- 全套 pytest **217/217 PASS**

## 0.10.19 (2026-05-23)

### Added — `commands/task-swarm.md` 加术语区分节「reviewer 分级 vs validator fail」

**用户痛点（login-page 现场）**：validator-g1-r2 报 fail（子任务 1.5 响应式设计未完成），主代理输出"判定为 fail，因为 1 个 P1 问题（响应式设计）仍然存在"——把 validator 的子任务核验失败误称为 reviewer 的 P1 等级。用户看到"P1"自然问"这个 P1 到底需不需要修"——因为按 reviewer 分级体系 P1 是 advisory，**不阻塞 pipeline**。

但实际上 validator 跟 reviewer 是**两个完全不同的裁判**：

- **reviewer 路径是尝试性修复**：p0-fix 只给"带证据标签的 P0"一次修复机会，不论结果都进 validation；P1/P2/无标签 P0 不修。
- **validator 路径是循环验证**：fail 就必须 v-fix 修到 pass，没有"P1 可跳过"概念，**没有任何"建议性"**。

主代理混淆术语的后果：用户被误导以为 1.5 是"建议项"可以跳过；或者把 reviewer P0 误当 validator fail 一直循环修。

修复 `commands/task-swarm.md` 加新节「术语区分」：

1. **4 行对比表**：P0（带证据标签）/ P0（不带证据标签）/ P1·P2 / validator fail，列出来源 + 是否触发 fix loop + 具体策略
2. **关键差异说明**：reviewer 是"尝试性修复"（一次性），validator 是"循环验证"（修到 pass）
3. **主代理正确措辞示范**：✓ "子任务 1.5 未完成" vs ✗ "1 个 P1 问题"
4. **用户问"能不能跳过"时的回答**：按设计不能，跳过的唯一办法是 abort run + 改 tasks.md 移除该任务

放在"advance 报 STATUS 缺失的正确应对"节之前，跟其他易混淆场景集中在一起。

**对照源码确认**：
- "P0 不带证据标签自动降级 advisory" 在 `task_swarm_outbox.py:280-286` 真实装
- "p0-fix 不再 review 直接进 validation" 在 `references/task-swarm.md §3 line 61` 明确写过
- "validator fix_targets 不带 P0/P1 标签" 在 `references/task-swarm.md §4.3 line 175` 明确写过

新节是把分散在 references / 代码里的事实**集中到 commands 一处**，让主代理读 commands 时就能正确分辨，不必再去 references 拼。

### Tests

- 纯文档改动，无 Python 代码路径影响
- 全套 pytest **212/212 PASS**

## 0.10.18 (2026-05-23)

### Fixed — `commands/task-swarm.md` 第 4 步软提示导致主代理提前 advance + team-lead 代笔补 STATUS

**用户痛点（login-page 事故现场）**：主代理在 `coder-p0fix-g1-r1-f0` 还 ⠙ streaming 时就调 `advance --phase p0-fix`，依据是 team-lead 报告"已修复 result.md STATUS line"。advance 看磁盘上 STATUS 合法 → 返回 `ok:true` 进入 validation → validator 验出 P0 还在（f0 实际没修完）→ 主代理 fork 自定义命名的 `coder-fix-session-validation`（违反 task_swarm 命名规则）→ 同时**两个 agent 并发改 session.js**，状态机进一步崩坏。

事后看 state.json：`phase=v-fix`、`failed_status=failed`、`vfix_in_flight=[coder-vfix-g1-r2-f0]`（task_swarm 期待的 agent 没被 spawn，只有目录壳），teammates UI 显示 2 个 streaming agent 在改同文件。

根因三层：

1. **commands/task-swarm.md 第 4 步措辞 "等齐 subagent 返回（PostToolUse hook 注入提醒，可读可忽略）"** —— "可忽略"等于告诉模型可以不等
2. **team-lead 代笔补 STATUS 反模式没明确禁止** —— 主代理凭口头报告判定完成
3. **自定义命名 agent 绕开 task_swarm in_flight 规则没明确禁止** —— validator fail 后主代理另起 `coder-fix-xxx` 而不用 plan 给的 `coder-vfix-g{N}-r{R}-f{I}`

修复 `commands/task-swarm.md`：

#### 第 4 步全文重写为强约束

旧：`4. 等齐 subagent 返回（PostToolUse hook 注入提醒，可读可忽略）`

新：完整约束（节选）：

> - **必须**先在主代理 UI 看 "Waiting for N teammates" 区域，**所有** fork 出去的 Task 都 ✓ completed 才能进 step 5；**任何 ⠙ streaming / ⠴ running Bash 的就不能 advance**。
> - **不要**凭口头报告判定完成——包括 team-lead / 其他平台 agent 说"已修复 STATUS"/"已完成"。**只有** subagent 自己的 Task tool 返回 ✓ completed 才算数。
> - PostToolUse hook 注入的"plan 提醒"**不是**"立即 advance"指令。
> - 不确定时调 `task_swarm.py plan --run <run_id>`，若返回 `action: *-waiting`，**禁止** advance。
>
> **常见误判**：
> - "team-lead 说改完了" ≠ subagent 真完成
> - "f0 跑了 30 个 tool 看起来快完了" ≠ completed
> - "其他 4 个都 ✓ 了最后 1 个估计也快" ≠ 可以提前；advance 之后没回头路

step 3 也加了一句明确禁止自定义 agent_key：

> `coder-fix-xxx` / `coder-session-fix` 等自定义命名**全部禁止**，必须用 plan 给的 `coder-vfix-g{N}-r{R}-f{I}` 等规范名

#### 新节「advance 报 result.md 缺 STATUS / 解析失败的正确应对」

放在「异常出口」前。明确列出 4 条错误做法（手补 STATUS / 凭口头报告 advance / 凭印象判定 / 起新名字 agent）+ 正确做法 5 步（保留残缺 result.md / 查 in_flight 状态 / 等 subagent 真完成 / 用同一 agent_key 重 fork / 多次失败报用户 abort）。

核心断言：

> STATUS 缺失多半意味着 subagent 提前退出 / 工作未完成——代码改动可能根本没刷到磁盘。手补 STATUS 后 advance 通过，下游 reviewer/validator 拿到的是半成品代码，必然 fail。

### 未做的事

- **未修 task_swarm.py advance 加 subagent lifecycle 检查**：stdlib-only 脚本跨不到 Claude Code/codebuddy 框架的 Task spawn API，没法验证"所有 spawn 的 Task 是否真已退出"。约束只能在主代理文档层做。
- **未扩展 PreToolUse hook 拦截 subagent outbox 写**：team-lead 是独立 subagent，它的 session_id 不在 specode `~/.specode/sessions/` 里，hook 静默放行——这是 0.10.13 hook 的设计盲区，但扩展拦截会误伤合法 subagent 的正常 outbox 写（coder 写 result.md 本来就该走 Edit），暂不动。

### Tests

- 纯文档改动，无 Python 代码路径影响
- 全套 pytest **212/212 PASS**

## 0.10.17 (2026-05-23)

### Changed — `commands/task-swarm.md` 顶部加强制前置阅读指引（修软提示无效问题）

**用户痛点**：模型读 `commands/task-swarm.md` 后跑 task-swarm 流程，**明知**有 `references/task-swarm.md` 这份详细规格（commands 已有多处 "详见 references/task-swarm.md" 软提示），但**主动选择只读 commands**。模型内心戏证据：

> "我应该读取 commands/task-swarm.md，因为它可能包含命令的具体用法。"

结果：模型按 commands 81 行的简化路由开始干，遇到 plan 输出解析 / advance 失败 / writeback 越界等细节就凭印象推——这是 0.10.13 user-login 事故里 r2/r3 漂移 + 主代理手工 Edit state.json 的反模式根源之一。

根因：现有 "详见 references/task-swarm.md" 措辞太弱（line 8 / 57-67 / 80 都有），模型当作背景资料而非必读项。

修复：`commands/task-swarm.md` 顶部加 **⛔ 强制前置阅读** 节，明确：

1. 列出 references/task-swarm.md 的 9 个章节 TOC（让模型知道里面有什么）
2. **指令式**前置要求："**在调任何 `task_swarm.py` 子命令之前**（包括 init / plan / advance / writeback / resolve），必须先 Read references/task-swarm.md 至少扫一遍 TOC + §3 + §9"
3. 明确 commands 文件的边界："本文件下面的 3 步路由**只够回答'现在该调哪条 CLI'**，不够回答 plan 输出怎么解析 / advance 失败该 retry 还是 fork / writeback 越界怎么办"
4. 兜底约束："**禁止凭印象推**；如果对任何一步仍不确定，先 Read references 对应章节再动手"

放置在 frontmatter 后、3 步路由前，最显眼位置。

**未改 commands/spec.md 和 commands/continue.md**：用户只反馈 task-swarm 这一处遇到问题，其他 commands 没有真实证据需要同等强化。等出现实际 case 再说，避免预防性过度设计。

### Tests

- 纯文档改动，无 Python 代码路径影响
- 全套 pytest **212/212 PASS**

## 0.10.16 (2026-05-23)

### Fixed — slug 强制 ASCII 与 0.10.14 文档"保留原文不做翻译"自相矛盾（中文 slug 被静默换成英文）

复现：用户在 codebuddy 跑 `/specode:spec -n 登录页面 帮我做一个简单的登录页面`。主代理按 0.10.14 4a 路径调 `spec_init.py --name 登录页面 ...`，CLI 报错"非法 slug"（exit 3）。主代理**自动 fallback 到 4b 推导**，把 slug 换成 `login-page` 再调一次（成功）——但用户不知道目录名被偷偷换了。

根因有两层：

1. **代码层**：`spec_init.py:174` 的 `SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")` 强制 ASCII 小写+数字+短横线，跟 0.10.14 commands/spec.md 4a 承诺的"保留用户原文，不做翻译/推导"自相矛盾。这条 ASCII 限制是早期跨 OS 文件系统兼容性的历史包袱，但现代 Python 3 + Windows 10+/macOS/Linux 都支持 UTF-8 路径，已无必要。
2. **流程层**：主代理在 SLUG_RE 失败后**静默 fallback 推导**，没让用户知情。用户用 `-n` 形式就是想精确控制目录名，自动换成英文 = 欺骗用户。

修复：

1. **`spec_init.py:174` SLUG_RE 放宽**：

   ```python
   # 0.10.16+：允许 Unicode（中文/日文/emoji 等），仅禁文件系统危险字符
   SLUG_RE = re.compile(
       r'^[^<>:"/\\|?*\s\x00-\x1f.\-]'
       r'[^<>:"/\\|?*\s\x00-\x1f]{0,79}$'
   )
   ```

   拒：`< > : " / \ | ? *`（Windows 禁字符）、控制字符 `\x00-\x1f`、任何空白（避免 shell 转义麻烦）；首字符额外拒 `.`（隐藏文件）、`-`（CLI flag 歧义）。新增 `_WIN_RESERVED` set 拒 Windows 保留名（`CON` / `PRN` / `AUX` / `NUL` / `COM1-9` / `LPT1-9`）。新增 `_slug_invalid_reason(slug)` 返回用户可读的拒绝原因（替代单一错误消息）。

2. **`commands/spec.md` 4a 加分支**：

   > spec_init.py exit 3（slug 非法）时：**禁止**主代理**静默 fallback 到 4b 推导**——用户用了 `-n` 形式就是想精确控制目录名，自动换成英文 slug 是欺骗用户。正确做法：把 CLI stderr 报给用户让用户重选，仅当用户明确说"你帮我想一个"时才走 4b 推导。

3. **`references/workflow.md` step 0** 同步说明 + 例 2（中文 slug）。

例 2（新支持）：

```
/specode:spec -n 登录页面 帮我做一个简单的登录页面
  → --name 登录页面
  → --requirement-name "登录页面"（非 ASCII slug 复用原文做显示名）
  → --source-text "帮我做一个简单的登录页面"
  → specs/登录页面/ 目录被创建
```

### Added — `/specode:spec -h` 帮助文本顶部加「用法」节

之前 help 只有"会话与锁 / 工作流 / 会话日志"三节，没列实际 CLI 用法。0.10.14/0.10.15 加了 `-n <slug>` 显式语法和 `project-root-choice` selector，help 没跟上。本版本在 `HELP_OUTPUT_TEMPLATE` 顶部加「用法」节（5 行简表）：

```
用法：
  /specode:spec -n <slug> <需求>     推荐：显式指定 spec 目录名（slug 直接用作 specs/<slug>/）
  /specode:spec <需求>                兼容：主代理从 <需求> 推导 slug（结果不可预知）
  /specode:continue [slug]            接管已有 spec（无 slug 时列表选）
  /specode:end                        退出当前 spec 模式
  /specode:status                     查看会话与 spec 状态
```

工作流流程图保持原样——`project-root-choice` 是 selector 自动引导的内部步骤，用户不必在 help 里看到字段名。

### Tests

- 重写 `test_spec_init_rejects_invalid_slug` 为 parametrize 11 case：`evil/path` / `bad\\slash` / `bad<x>` / `bad:colon` / `bad*star` / `has space` / `.hidden` / `CON` / `nul` / `trailing.` / 空 slug 全部 exit 3
- 新增 `test_spec_init_accepts_unicode_and_extended_ascii_slug` parametrize 7 case：`user-login` / `UserLogin` / `登录页面` / `ログイン` / `auth_v2` / `spec.with.dots` / `user-1.0.0` 全部 exit 0，且磁盘 spec_dir.name == 用户原文
- 全套 pytest **212/212 PASS**

## 0.10.15 (2026-05-22)

### Added — `project_root`：spec 文档目录与代码实现目录解耦

**用户痛点**：在 user-login 事故中，task-swarm coder subagent 把 `npm install` / `src/App.tsx` / `database/migrations/` 全写到了 spec 文档目录 `<doc_root>/specs/user-login/` 下，污染了 vault。根因：`render_coder_prompt` 生成的 task.md 上下文段里**只有 `spec_dir` 字段，没有项目实现根目录概念**，subagent 看到 `@writes:src/services/auth-service.ts` 这种相对路径就拿 spec_dir 当根。

修复路径：**spec 文档目录与代码实现目录解耦**——`spec_dir` 只放 `.md` 文档和 `.task-swarm/` 状态，代码实际写入到 `project_root`（绝对路径，由用户在 spec 创建后通过 selector 选定）。

实现：

1. **`spec_init.py`**：
   - 写 `.config.json` 时记录 `invocation_cwd = os.getcwd()`（用户启动 Claude Code 时的目录，供 selector 渲染用）
   - `pending_selector` 默认改为 `project-root-choice`（替代 `workflow-choice`）
   - 新增 `project_root: null` 字段（待 `set-project-root` CLI 写入）

2. **`spec_session.py` SELECTOR_PROMPTS["project-root-choice"]**（新 selector）：
   - 三选项：`cwd（在已有项目里迭代）` / `cwd/slug（新项目子目录）` / `自定义路径`
   - 每个选项 description 带具体路径（hook 注入时填入 `<invocation_cwd>` / `<cwd_subdir>`）
   - 用户选定后由主代理调 `set-project-root` CLI 写入

3. **`spec_session.py` `cmd_set_project_root`**（新 CLI）：
   - `set-project-root --spec <dir> --session <id> --root <abs-path>`
   - 校验：lock holder 必须是 current session；`--root` 必须绝对路径；不存在则 mkdir -p；存在但非目录 exit 1
   - 写 `.config.json.project_root` + 把 `pending_selector` 推进到 `workflow-choice`，session 同步

4. **`task_swarm_prompt.py` `_context_block`** + 各 `render_*_prompt`：
   - context block 加 `- project_root: <path>` 行（fallback 文本明确"未设置时用 spec_dir"）
   - `render_coder_prompt` 新增 `## 项目根目录与路径规约` 段：明确"`@writes/@reads` 相对 `project_root`，**严禁**写到 `spec_dir`，Bash 命令请先 `cd` 到 `project_root`"
   - reviewer / validator 也注入 project_root（跑测试时 cd 用）

5. **`task_swarm.py`** 调用方：新增 `_resolve_project_root(sm)` helper 读 `spec_dir/.config.json.project_root`；6 处 `render_*_prompt` 调用全部传入。

6. **`commands/spec.md`** 第四步「成功后必做」：从直接呈现 `workflow-choice` 改成**两步走**——先 `project-root-choice` selector → 用户选 → 主代理调 `set-project-root` CLI → 再 `workflow-choice` selector。两步都不 end turn。

7. **`references/selectors.md`** drift-sync 新增 `A0 project-root-choice` 节，byte-identical 与 SELECTOR_PROMPTS 一致。

**向后兼容**：老 spec（pre-0.10.15）的 `.config.json` 没有 `project_root` 字段，`_resolve_project_root` 返回 `None`，render_*_prompt 输出 fallback 文本（"⚠ project_root 未设置；fallback 用 spec_dir"），不阻断流程。用户可手动调 `set-project-root` 补字段。

**用户使用流程**：

```
/specode:spec -n user-login 添加用户登录功能
  → spec_init.py 创建 spec + 写 invocation_cwd
  → 主代理呈现 project-root-choice selector（3 选项含具体路径）
  → 用户选「cwd（在已有项目里迭代）」
  → 主代理调 set-project-root --root <cwd>
  → CLI 写 project_root + 推 pending_selector → workflow-choice
  → 主代理立即呈现 workflow-choice selector
  → ...
```

### Tests

- 新增 5 个 `test_set_project_root_*`：成功路径 + 自动 mkdir + 拒绝相对路径 + 拒绝非目录 + 拒绝非 lock-holder
- 新增 `test_on_user_prompt_project_root_choice_emits_with_cwd_context`：hook 注入 selector 时填充 invocation_cwd / cwd_subdir
- 新增 `test_coder_prompt_includes_project_root_from_spec_config` + `test_coder_prompt_fallback_when_project_root_unset`：覆盖 project_root 注入 task-swarm prompt 的两条路径
- 更新 3 个测试预期：spec_init 后 pending_selector 是 `project-root-choice` 而非 `workflow-choice`，集成测试加 set-project-root 调用步骤
- selectors.md drift test 自动 cover `project-root-choice` byte-identical
- 全套 pytest **195/195 PASS**

## 0.10.14 (2026-05-22)

### Added — `/specode:spec -n <slug> <需求>` 显式指定 spec 目录名

用户痛点：当前 `/specode:spec <需求>` 走"主代理推导英文 slug"路径——推导结果对用户不可预知（如用户想要 `refund`，主代理可能推成 `order-refund-flow`）。即使用前缀形式 `<名称>：<内容>`，左侧也只是 `requirement_name`（中文显示名），slug 仍是主代理推。用户无法精确控制 `<doc_root>/specs/<slug>/` 的目录名。

`spec_init.py` 的 CLI 层早就支持 `--name <slug>`（line 230，必填），bug 在文档/指引层始终引导主代理"推导"。本版本在 4 处文档加入显式 `-n` / `--name` 路径作为**推荐形式**：

- `commands/spec.md`：argument-hint 加 `-n <slug> <需求>` 在最前；第四步拆成 4a（显式 `-n`，推荐）+ 4b（推导，兼容）
- `skills/specode/SKILL.md` 路由表第一行：标注"优先 `-n <slug>`"
- `skills/specode/references/workflow.md` §1.1：加 step 0「显式 slug」，明确"有 `-n` 时跳过 step 1+2 的前缀解析与推导"

`requirement_name` 默认从 slug 推：短横线 → 空格 + 首字母大写（如 `user-login` → `User Login`）。

例：
- `/specode:spec -n user-login 添加用户登录功能` → `--name user-login --requirement-name "User Login" --source-text "添加用户登录功能"`
- `/specode:spec --name dark-mode 加个深色主题切换` → `--name dark-mode --requirement-name "Dark Mode" --source-text "加个深色主题切换"`

旧形式（纯 `<需求>` / `<名称>：<内容>`）保留兼容，但 workflow.md 明确"推导结果对用户不可预知；若用户在意目录名应引导改用 `-n` 形式"。

### Tests

- 无新增测试：`spec_init.py --name` 一直是必填字符串参数，无需在 CLI 层验证；本次纯文档改动，不影响代码路径。
- 全套 pytest **186/186 PASS**

## 0.10.13 (2026-05-22)

### Fixed — task-swarm v-fix prompt 写到 `r{round+1}`，但 state 命名是 `r{round}`（导致 "产物文件不存在" 死锁）

复现：`/specode:spec ...` 走到 task-swarm → validation round 1 fail → 进 v-fix。`begin_v_fix` 把 `sm.round` 从 1 升到 2，并把 `vfix_in_flight = ["coder-vfix-g1-r2-f*"]`（用当前 round 命名，正确）。但 `task_swarm.py:_materialize_prompts_v_fix` 调 `render_coder_prompt(round_=sm.round + 1)` —— 多 +1 一次 → 磁盘 task.md 写到 `agents/coder-vfix-g1-r3-f*/task.md`。

后果链：

1. plan_next 输出的 fork hint（`L572: r{sm.round+1}`，**这里也 +1，因为它在 begin_v_fix 之前调用，sm.round 还是旧值**）刚好等于磁盘文件名 → 主代理按 hint fork `coder-vfix-g1-r3-f*` subagent → 产物落在 r3 目录
2. 下一次 `advance --phase v-fix` 时，cmd_advance 按 `vfix_in_flight = [r2-*]` 找 `agents/coder-vfix-g1-r2-f*/outbox/result.md` → 全部不存在 → 报 "产物文件不存在"
3. 主代理面对 state（r2）与磁盘（r3）不一致，**判定为 "naming mismatch" 然后手工 Edit `state.json`** 抹平差异 → 状态机被人为污染 → 后续 phase 持续走错 → 最终 `validator-g1-r2` subagent spawn 后无人回收产物 → Claude Code 界面无限刷 "Waiting for 1 teammate..."

修复：`task_swarm.py:818` 把 `round_=sm.round + 1` 改成 `round_=sm.round`。理由：`_materialize_prompts_v_fix` 是 cmd_advance 在 `begin_v_fix` **之后**调用的，`sm.round` 已经自增过；`begin_v_fix` 写 `vfix_in_flight` 用的也是 `sm.round`（state.py:385）。在已自增的 round 上再 +1 = 多 +1 一次。同理 plan_next L572 / L583 因为是 begin_v_fix 之前调用，仍保留 `+1`，这是对的。

回归测试：新增 `test_v_fix_prompt_files_match_state_in_flight` —— 触发 validation fail → begin_v_fix 后断言 `state.vfix_in_flight` 每个 agent_key 对应的 `agents/<key>/task.md` 必须存在。旧 bug 下这个 test 直接挂。

### Added — PreToolUse hook 阻断主代理直接 Edit/Write task-swarm 受控路径

事故还原显示：上面 Bug A 触发"state 跟磁盘不一致"时，主代理推理"这是 naming mismatch 我需要手工修 state.json"，连续 5 次 Edit `state.json`（清 `vfix_in_flight` 列表 / 把 `failed_status: "failed"` 改成 `null` / 把 `completed_at` 写未来时间戳 / events 追加伪造 `completed` 事件），还 Edit 了 subagent 的 `outbox/result.md` 手工补 STATUS 行。这些"修补"全是**绕过 task_swarm.py 状态机契约**的反模式，导致状态污染雪崩。

加防护：`hook_on_pre_tool_use` 检测 tool_input.file_path 是否落在以下三类受控路径下，命中则 `sys.exit(2)`（PreToolUse 阻断）并把拒绝原因写 stderr：

| 路径模式 | 拒绝原因 |
|---|---|
| `.task-swarm/runs/*/state.json` | state 唯一事实来源，只能 `task_swarm.py advance` 改 |
| `.task-swarm/runs/*/agents/*/task.md` | task_swarm.py 为 subagent 生成的 prompt，改了 subagent 也不会重读 |
| `.task-swarm/runs/*/agents/*/outbox/*` | subagent 产物，手工补 STATUS = 伪造工作 |

stderr 详细说明 why + 正确路径 hint（如"重新 fork subagent 或汇报 task_swarm.py 解析 bug"）。仅在 `mode==active` 且 `task_swarm_run_id` 已绑定时生效，非 task-swarm 场景零开销。原 `tasks.md` 直写软提醒保留（不阻断）。

### Tests

- 新增 `test_v_fix_prompt_files_match_state_in_flight`（Bug A 回归）
- 新增 5 个 `test_on_pre_tool_use_*` 覆盖 state.json / agent task.md / outbox 阻断 + 正常源码 Edit 通行 + idle session 不拦截
- 全套 pytest **186/186 PASS**

## 0.10.12 (2026-05-22)

### Fixed — `/specode:end` 之后模型仍在响应末尾输出 `─── spec-mode ───` 状态行（banner 残留）

复现：`/specode:spec ...` → 走若干 turn → `/specode:end`（CLI 返回 `ok:true`）→ 后续任意 turn 模型仍输出 `─── spec-mode ─── spec: ... | /specode:end 退出` 状态行。

根因：`hook_on_user_prompt` 在 `mode in ("idle","ended")` 时静默 early-return，**不注入任何反向消息**。但此前 N 个 turn 已反复注入 `STATUS_FOOTER_TEMPLATE`（"请在本次响应正文之后**额外**输出一行 ─── spec-mode ─── ..."）与 `SPEC_MODE_CONTINUE_REMINDER`（"下一 turn 必须继续遵守 ... 通过 /specode:end 才能正式退出"）。`/specode:end` 提交那一 turn mode 仍是 active，hook 最后一次注入照常进行；end 之后下一 turn hook 安静停止，但模型 context 里堆积的"必须输出 footer / 下一 turn 必须继续遵守"指令仍生效，凭惯性继续输出 banner。

修复：

1. 新增 `SPEC_MODE_ENDED_REMINDER` 模板：明确告知模型"已退出，作废此前所有 spec-mode 指令，**不要**再输出 `─── spec-mode ───` footer"
2. `cmd_end` 设 `post_end_reminder_pending=True`；同时**对齐 `end.md` 文档**清掉 `active_spec_slug` / `active_spec_dir` / `spec_id` / `phase` / `task_swarm_run_id`（此前实现只改 `mode/ended_at/lock_state/pending_selector`，违反文档约定）
3. `hook_on_user_prompt` 在 `mode=="ended" and post_end_reminder_pending` 时注入提醒并清标志；其他 `ended/idle` 路径维持原静默

行为：end 后**第 1 turn** 模型收到明确反向指令 → **第 2 turn 起** hook 完全静默 → banner 不再出现。

### Changed — `doc-confirm-*` selector option description 用具体环节名替代「下一 phase」

`requirements.md / bugfix.md / design.md` 三份文档确认 selector 的「确认（推荐）」和「查看全文」option description 此前都用泛化"进入下一 phase / 不进入下一 phase"。每个 selector 的下一阶段实际固定：

- `doc-confirm-requirements` → 进入设计（design）环节
- `doc-confirm-bugfix` → 进入设计（design）环节
- `doc-confirm-design` → 进入任务拆分（tasks）环节

同步更新 `references/selectors.md`（drift test byte-identical cover）。

`workflow-choice` 的"进入下一阶段"保留泛化（next 按 workflow 动态选 requirements/design/bugfix 三选一，无法静态命名）。

### Tests

- 扩展 `test_end_sets_mode_ended_and_releases_lock` 覆盖 `active_spec_*` 字段清零 + `post_end_reminder_pending` 标志
- 新增 `test_on_user_prompt_post_end_reminder_emits_once_then_clears`（hook 单元，覆盖第 1 turn 注入 + 第 2 turn 静默）
- 重写集成测试 `test_after_end_user_prompt_emits_nothing` → `..._emits_one_shot_then_nothing`
- 全套 pytest **180/180 PASS**

## 0.10.11 (2026-05-22)

### Removed — `spec-writer` subagent；4 份核心 spec 文档改由主代理直接生成

复现：用户跑 `/specode:spec 在 git 目录做登录页面` → 走到 requirements phase →
主代理 fork `spec-writer` agent 写 requirements.md → spec-writer 各种 Glob/Read
找不到 `assets/templates/` 模板（实际找的是不存在的 `.template.md` 后缀）→
hallucinate 18 条通用登录页面 SHALL + 408 行 design.md（JWT/HTTPS/CSRF/2FA），
跟用户原始需求"在 git 目录做登录页面"完全脱节。

根因：subagent 设计反模式 —— 每个 subagent 是独立 LLM 调用 + 新 context window，
**拿不到主代理上下文**（不读 SKILL.md / 不知道用户原始 `source_text` / 不知道
流程状态）。即使模板路径正确，subagent 仍按通用模板填空，内容不贴合用户具体
需求。主代理本身就有完整 SKILL + 流程上下文 + source_text，直接写质量更高。

修复（用户授权我自决方案）：

1. **删除** `plugins/specode/agents/spec-writer.md`
2. **`SKILL.md` 加 §「Spec 文档生成」（单一规则来源）**：主代理 Read
   `${CLAUDE_PLUGIN_ROOT}/assets/templates/<phase>.md` 作骨架 + 按
   `<spec-dir>/.config.json.source_text` 填空 + Write 到 `<spec-dir>/<phase>.md`
3. **`SKILL.md` Iron Rule 7 改写**：移除 "必须 fork spec-writer subagent" 约束
4. **31 处 `fork spec-writer` 引用全部替换** 成 "主代理按 SKILL.md §「Spec 文档生成」走"：
   - `spec_session.py SELECTOR_PROMPTS` 6 selector 的「用户选定后流程」段
   - `references/selectors.md` 同步 6 处（byte-identical，drift test cover）
   - `references/workflow.md` 4 处 phase 流程
   - `references/templates.md` 顶部说明 + 6 处分散提及
   - `commands/task-swarm.md` 1 处 cross-ref
   - `scripts/spec_init.py` 1 处 docstring
   - `assets/templates/tasks.md` 1 处 ## 测试要点 说明
5. **`assets/templates/` 4 份模板（requirements.md / bugfix.md / design.md / tasks.md）保留**
   作为主代理 Read 的骨架来源

### Changed — `commands/spec.md` + `commands/continue.md` 进一步变薄（commands 薄 / SKILL 厚）

按用户指导原则 "命令中不要设置过多流程，只列关键必要内容，让模型与 skill 对接流程"：

- **`spec.md` 第四步「成功后必做」**：从 3 件事详细描述压缩成「按 SKILL.md
  §Status Footer「新 spec 创建/接管的当 turn」走」一句话引用 + 保留关键
  禁止项（"严禁 hallucinate '请下一轮输入 /specode:continue'"）
- **`continue.md`** 大幅瘦身：删除详细 5 步描述，改成「按 `references/workflow.md`
  §9.1 / §9.2 走 N 步」+ 关键禁止项（"禁止跳过 selector 直接 acquire"、"禁止
  Grep 项目目录"、"LockHeld 禁止直接 --force"）

commands 现在只列入口路由 + 关键不可漏的约束（hallucinate 防御）；业务流程
全部 link 到 SKILL.md / `references/workflow.md`。模型从入口跳到 SKILL 拿详
细规则，避免 commands 跟 SKILL 双份维护漂移。

### 测试

- drift test 11/11 PASS（selectors.md 与 SELECTOR_PROMPTS byte-identical）
- 全套 pytest **179/179 PASS**

## 0.10.10 (2026-05-22)

### Fixed — selector 选定后流程缺失 + 主代理 hallucinate "退出 spec 模式" / invent 简化 selector

承接 0.10.9 修好 `/specode:spec` 创建后引导 hallucinate 之后，又发现两类同源问题：

**1. selector 选定后流程缺失**

复现：用户跑 `/specode:spec <需求>` → workflow-choice 选 "Requirements first"
→ 主代理只 chat 一句 "已选择 Requirements first" + "请下一轮输入
`/specode:continue` 继续，或直接提出你的需求细节" → end turn。**没**调
`phase-transition` / **没** fork spec-writer / **没**生成 requirements.md /
**没**呈现 doc-confirm-requirements selector。

证据：
- `references/workflow.md` §2:105 明确说 "用户选完 → 调 phase-transition
  → 进入对应 phase"；§3.1 写了 fork spec-writer → 生成 requirements.md →
  呈现 doc-confirm-requirements 4 步
- selector 模板末尾约束段都是 "调用工具后立即 end turn 等待用户选择" —— 这条
  历史措辞误导主代理：把 `AskUserQuestion` 当作 "end turn 触发器"，拿到 user
  选项后只 chat ack 一句就 end turn 让用户输新命令推进
- 但 `AskUserQuestion` 是**同步阻塞工具**——它返回 user 选项作为 tool result，
  主代理在**同一 turn 内**继续处理，**不应该** end turn

**2. 主代理 hallucinate "退出 spec 模式" + invent 简化 selector**

复现：tasks 完成后主代理输出 "Spec 流程完成！现在退出 spec 模式，开始编码实现"
+ 用 "任务清单已就绪，下一步？ → 开始编码" 这种 **invent 的简化 selector**
（不是 tasks-execution 模板的 4 个固定选项：用 task-swarm / 顺序执行 / 需要
调整 / 暂不 coding）。

证据：
- `spec_session.py:_auto_pending_selector` line 926-945 phase=tasks → 设
  `pending_selector=tasks-execution`，模板有 4 个固定选项
- `phase-transition` 是 spec 内部 phase 切换（intake→requirements→...→
  implementation→acceptance→iteration），**不**退出 spec 模式；**只有**
  `/specode:end` 才退出
- 但 SKILL.md 没明确"phase-transition 不退出 spec"，也没明确"呈现 selector
  时禁止 invent / 简化"，主代理因此 hallucinate

修复（commands 薄 / SKILL 厚原则）：

**SELECTOR_PROMPTS / selectors.md（10 个 selector 各加「用户选定后流程」段）**

每个 selector 模板末尾约束段后新增 `**用户选定后流程（同一 turn 内继续）**`
段，列出**每个选项**的下一步动作（phase-transition target / fork agent /
下一个 selector 等）。注意用 `**bold**` 而非 `### H3`——避免被 drift test
的 H3/H4 regex 误识别为 selector 边界。

`spec_session.py SELECTOR_PROMPTS` 与 `references/selectors.md` 同步修改，
`test_selectors_drift.py` 11/11 通过保证 byte-identical。

**SKILL.md §Selectors 顶部加 3 个子节**

1. **`AskUserQuestion` 工具语义（重要 / 关乎流程连续性）**：澄清
   `AskUserQuestion` 是同步阻塞工具，拿到选项后**同一 turn 内**按 selector
   "用户选定后流程" 段继续；**严禁** "已选择 X，请下一轮输入 /specode:continue"
   就 end turn—— `/specode:spec` / `/specode:continue` 是持续流程入口而非
   回合触发器
2. **呈现 selector 时禁止 invent / 简化选项**：必须用 SELECTOR_PROMPTS /
   selectors.md 模板 question / label / description 逐字传参，**禁止** invent
   简化版（如 "任务清单已就绪，下一步？ / 开始编码"）
3. **phase-transition 不退出 spec 模式**：`phase-transition` 是 spec 内部
   phase 切换，spec 仍 mode=active 持锁；**只有** `/specode:end` 才退出；
   **严禁** "Spec 流程完成！现在退出 spec 模式，开始编码实现" 这类话——
   implementation phase 期间 hook 继续注入 4 条提醒（文档优先 / 代码-文档
   同步 / 状态行 footer / 仍处于 spec 模式），主代理改代码前后必须按
   §Code-Doc Sync Reminders 同步 tasks.md / implementation-log.md / design.md

pytest **179/179 PASS**（drift test 11/11 + 全套 168 不变）。

## 0.10.9 (2026-05-22)

### Fixed — `/specode:spec` 创建后 hallucinate 引导 + 漏状态行 footer

复现：用户跑 `/specode:spec <需求>`，主代理输出 "Spec 已创建成功" 详情后接
"你可以使用 `/specode:continue` 进入下一阶段继续推进"，且**漏了**状态行
footer。

证据：
- `spec_init.py:400-408` 只输出纯 JSON，无任何 "/specode:continue 进入下一阶段"
  引导（全 repo `grep` "使用 /specode:continue 进入" 命中 0 次）
- `hook_on_user_prompt` 注入 footer (line 1550)、但只在 user-prompt 提交时跑；
  用户输 `/specode:spec` 时 session 还是 idle / new，**没**注入 footer 提醒
- `hook_on_stop` 只 emit `CODE_DOC_SYNC_STOP` + `SPEC_MODE_CONTINUE_REMINDER`
  （文字提醒"下一 turn 要 footer"），**不 emit `STATUS_FOOTER_TEMPLATE` 本身**
- → `spec_init.py` 把 session 改成 mode=active + pending_selector=workflow-choice
  之后，本 turn hook 已经跑过、不会重新注入 footer / selector；commands/spec.md
  第四步没规定"成功后主代理本 turn 必做 footer + selector + 禁止 hallucinate
  让用户输命令的引导"——主代理因此漏 footer 又 hallucinate `/specode:continue`

修复（commands 薄 / SKILL 厚原则）：

1. **`commands/spec.md` 第四步加「成功后必做」子节**：明确 `spec_init` exit 0 后
   本 turn 必做 3 件事——
   - chat 简报 2-3 行（slug / phase / spec_dir），**禁止**说 "使用
     `/specode:continue` 进入下一阶段" / "你可以使用 ... 推进" / "下一步请
     输入 ..." 等让用户再输命令的引导
   - 输出状态行 footer
   - 立即调 `AskUserQuestion` 呈现 `workflow-choice` selector

2. **`SKILL.md §Status Footer` 加「新 spec 创建 / 接管的当 turn」子节**：统一
   覆盖 `/specode:spec`（spec_init 完成）和 `/specode:continue [slug]`
   （acquire+load+continue 完成）两类首 turn 场景，规定 hook 未刷新时主代理
   必须主动 chat 简报 + footer + selector，**严禁** "持续流程被打断"类的
   命令引导。`/specode:spec` 和 `/specode:continue` 是持续流程的入口，进入
   之后整条 phase 链由 selector + hook + phase-transition 自动推进。

`spec_session.py` / `spec_init.py` 不动，是引导文档层修复。pytest 179/179 通过
（修改的是 .md 文件，不影响测试）。

audit 同源风险（其他 commands）：

- `continue.md`（0.10.5 重构后）：step 5 已要求 footer；SKILL.md 新子节覆盖
  主动 selector，无需 commands 再补
- `end.md`：mode=ended 不输 footer，by-design
- `status.md`：active 期间应输 footer（SKILL.md §Status Footer），轻微风险
- `task-swarm.md`：init 后立即 plan→fork，by-design

## 0.10.8 (2026-05-21)

### Fixed — `spec-in/<os>-<username>/specs` device 段从未被代码实现

`references/obsidian.md` §0-§1 + `SKILL.md:158` 明确约定 spec 文档应该落在
`<vault>/spec-in/<os>-<username>/specs/<slug>`（让同一 vault 在多设备 / 多用户
共享时各 device 的 spec 互不串扰、避免锁串扰、避免文件冲突），但
`spec_vault.py:resolve_doc_root` **从未实现 `device_segment`**——`auto` /
`config-obsidianRoot` 命中后直接返回 vault 根，spec_init 拼出来变成
`<vault>/specs/<slug>`，少了关键的 `spec-in/<device>/` 整层。

复现：

- `~/.config/specode/config.json` 不存在、`SPECODE_ROOT` 未设
- `Documents\Notes/.obsidian/` 存在 → auto-detect 命中
- 跑 `/specode:spec <需求>` → spec_dir 落在 `Documents\Notes\specs\<slug>`
  而非约定的 `Documents\Notes\spec-in\windows-qiang\specs\<slug>`

修复（`spec_vault.py`）：

1. 加 `_device_segment()` 函数（`platform.system()` + `getpass.getuser()`），
   返回 `windows-qiang` / `macos-alice` / `linux-bob` 这种规范化串。
2. `resolve_doc_root` 内部按字段语义分场景追加 `spec-in/<device>` 段：

   | source   | 来源                                | 追加 device 段？ |
   |----------|-------------------------------------|------------------|
   | override | `--root` 参数                       | 否（用户给什么用什么） |
   | env      | `SPECODE_ROOT` 环境变量             | 否               |
   | config   | `config.json.rootOverride`          | 否               |
   | config   | `config.json.obsidianRoot`/`docRoot`| **是**           |
   | auto     | Obsidian auto-detect                | **是**           |
   | none     | 三层全 miss                         | —                |

3. `cmd_set` 之前 `--vault` 和 `--root` 都写 `obsidianRoot`（导致 `rootOverride`
   字段在代码里实际从未被使用，文档与运行时不一致）。修正为：

   - `--vault <p>` → 写 `obsidianRoot`（`resolve_doc_root` 追加 device 段）
   - `--root <p>` → 写 `rootOverride`（不追加）
   - 互斥：写其中一个字段时清掉另一个 + 清掉 legacy `docRoot`
   - 输出的 `doc_root` 用 `resolve_doc_root()` 重算，反映 device 段

`spec_init.py` / `spec_session.py list-specs` call site **不动**（仍
`<doc_root>/specs/<slug>`，但 `doc_root` 现在已含 `spec-in/<device>`，最终
路径自动变成 `<vault>/spec-in/<device>/specs/<slug>`）。

### Changed — `spec_vault.py` set 字段语义对齐 obsidian.md

`cmd_set` 现在区分 `obsidianRoot` (`--vault`) 与 `rootOverride` (`--root`) 两个
互斥字段，跟 `references/obsidian.md` §1 描述对齐。已经用旧版本 `set --root`
写过 config 的用户字段名是 `obsidianRoot`，跑过一次新版 `set --root` 会自动
迁移成 `rootOverride`（同时清掉旧 `obsidianRoot`）。

### Added — 4 个 doc_root device 段测试

`tests/test_spec_vault.py` 新增覆盖：

- `test_status_with_root_override_no_device_suffix`：`rootOverride` 命中不追加
- `test_root_override_takes_precedence_over_obsidian_root`：两字段并存时
  `rootOverride` 胜出
- `test_set_root_writes_root_override_no_device_suffix`：`set --root` 写
  `rootOverride` 字段且不追加 device 段
- `test_set_vault_then_root_replaces_field`：连续 `set --vault` 后 `set --root`
  字段切换 + 互斥清理

更新现有 3 个测试以反映新 schema（`test_status_with_config_only` /
`test_set_vault_writes_config_and_status_reflects_config` 现在断言路径含
`spec-in/<device>` 段）。

pytest 全套 **179/179 PASS**（从 0.10.7 的 176 → 179，3 个净新增）。

### Notes — 升级影响

旧版本生成的 spec 目录（在 `<vault>/specs/<slug>` 下，缺 `spec-in/<device>`）
**不会被自动迁移**。升级到 0.10.8 后：

- 新 `/specode:spec` 命令会按约定路径创建（`<vault>/spec-in/<device>/specs/<slug>`）
- `/specode:continue` 调 `list-specs` 时也会看新路径，找不到旧路径下的 spec
- 如需保留旧 spec 内容，手动 `mv <vault>/specs/<slug>` 到
  `<vault>/spec-in/<device>/specs/<slug>` 并更新对应 `sessions/<id>.json` 的
  `active_spec_dir` 与 `<vault>/.active-specode.json` pointer 字段

## 0.10.7 (2026-05-21)

### Changed — `/specode:spec -h` help 删去「命令一览」节

命令清单在 `SKILL.md` / `commands/*.md` / README 已有详细说明且会随版本演进，
help 文本内重复列一份反而容易过时（0.10.4 / 0.10.5 加 doc_root 确认步骤、
task-swarm 前置校验时都需要同步改 help）。help 改为只展示版本号 + 会话与锁 /
工作流概要 / 日志开关，命令细节让用户查 SKILL.md。

无业务行为变化。`spec_session.py:HELP_OUTPUT_TEMPLATE` 删除 13 行（line 614-628）。
hook 测试 17/17 通过。

## 0.10.6 (2026-05-21)

### Fixed — `references/selectors.md` 与 `SELECTOR_PROMPTS` 漂移

Audit 发现 selector 模板有 3 处真 drift：
- `workflow-choice`：selectors.md 缺 "**调用 `AskUserQuestion` 工具**" 后的
  "**，参数完全按下列结构（直接传入，不要翻译/重写选项）**" 子句；约束段
  "立即 end turn" 缺 "等待用户选择"、"工具" 缺 "宿主"、"ESC" 缺 "取消"。
- `doc-confirm-bugfix` / `doc-confirm-design`：selectors.md §A3 把这两个变体
  压缩成表格列差异（line 178-181），没给完整 `\`\`\`text` 块，结果文档跟运行时
  无法逐字对比；spec_session.py 实际模板的简报句格式也跟表格描述对不齐。
- §A3 H3 标题里残留 `doc-confirm-tasks`（0.9.3 起已废弃合并进 `tasks-execution`）。

修法：selectors.md 跟运行时（`spec_session.py SELECTOR_PROMPTS`）对齐——
- 补 `workflow-choice` 缺失措辞
- §A3 重构为「H3 分组介绍 + H4 三个 key 各带完整 `\`\`\`text` 块」结构
  （`doc-confirm-requirements` / `doc-confirm-bugfix` / `doc-confirm-design`）
- H3 标题去掉 `tasks` 残留

`spec_session.py` 不动（运行时是注入的实际真相，selectors.md 跟它走）。

### Added — `test_selectors_drift.py` 防回归

`plugins/specode/tests/test_selectors_drift.py` 在 pytest 阶段自动比对两边：
- `test_keys_match`：runtime selector key 集合必须与 selectors.md `### / ####`
  反引号标题命中的 key 集合一致；orphan（一边有一边没）直接 fail
- `test_byte_identical[<key>]`：parametrize 10 个 selector，每个 key 的
  `\`\`\`text` 块内容必须与 `SELECTOR_PROMPTS[key]` `strip()` 后逐字相等

跑了一遍：11/11 passed，全套 pytest 176/176 passed（165 + 11 新增）。

未来改 selector 措辞 / 增删 selector，pytest 自动 fail 提醒同步两边。

## 0.10.5 (2026-05-21)

### Fixed — `/specode:continue` 跳过 selector 直接 acquire / `/specode:task-swarm` 缺前置校验

承接 0.10.3 / 0.10.4 在 `/specode:spec` 上修好的"commands 直接给 CLI 命令 → 主代理 bypass SKILL 业务规则"反模式，本次 audit 发现 `continue.md` 和 `task-swarm.md` 同源：

**`continue.md`（类型 1，同源 / 高严重度）**
旧版「## 立即调用」行 22-26 直接给 `acquire --spec <dir> --session <id>` 完整模板，
主代理见命令就跑，**跳过** `references/workflow.md` §9 要求的 5 步流程
（list-specs 报告 → `AskUserQuestion` 让用户选 ≤4 项 → LockHeld → `takeover-options`
selector → acquire → load）。无 slug 时主代理还会 invent `<dir>`。

修复：重写为两步路由
- 第一步（无 slug）：先确认 doc_root（接 SKILL.md §「首次使用 / auto-detect 命中时的确认」）→ `list-specs` → 空列表引导 `/specode:spec` / 非空 chat 1-2 行摘要 + `AskUserQuestion` 单列单选（≤4，按 `last_heartbeat_at` 取最近）→ 用户选定后转第二步
- 第二步（有 slug）：解析 `spec_dir` → `acquire`（exit 4 `LockHeld` → **禁止**直接 `--force`，先 `takeover-options` selector 让用户选）→ `load` → `continue` → 报告 + 状态行 footer

**`task-swarm.md`（类型 2，弱同源 / 中严重度）**
旧版行 8-12「## 立即调用」直接给 `task_swarm.py init --tasks <spec_dir>/tasks.md`，
`<spec_dir>` 占位符**鼓励主代理 invent 路径**而不去读 `sessions/<id>.json` 拿
`active_spec_dir`；缺 phase / `pending_selector` 前置校验，用户裸输
`/specode:task-swarm` 时主代理无前置检查直接 init。

修复：拆 3 步
- 第一步（前置校验，必做）：先 `read-session` 拿状态，强制满足 `mode=active` /
  `active_spec_dir` 非空 / `phase=tasks` / `pending_selector=tasks-execution` 且
  已选 task-swarm 路径
- 第二步（init）：用 step 1 的 `active_spec_dir + /tasks.md`，禁止 invent
- 第三步（7 步循环）：保留 sketch，详细规格全部指向 `references/task-swarm.md`

同时 SKILL.md §Task-Swarm 补「`/specode:task-swarm` 前置校验（强制）」小节，
是 commands/task-swarm.md 第一步引用的业务规则单一来源。

### Changed — commands/task-swarm.md 大幅精简（commands 薄 / references 厚）

原 task-swarm.md 132 行重复了 `references/task-swarm.md` 的 5 段内容（Phase 状态机
ASCII 图 / 7 步循环展开 / 文件冲突 / 详细异常处理 / 命令调用样例）。精简到 ~70 行，
只保留 commands 路由层职责（前置校验 / init / 7 步 sketch + heartbeat / 异常出口
摘要），详细规格全部 link 到 `references/task-swarm.md` §1-§9 单一来源。

设计原则延续 0.10.4：commands 薄（路由 + 边界引导）、SKILL / references 厚（业务规则
+ 协议详解）。commands 不重复细节，边界 case 指章节，业务流程改动只动 SKILL / references。

## 0.10.4 (2026-05-21)

### Fixed — 新建 spec 时 silent fallback 到 Obsidian vault（首次使用确认缺失）

承接 0.10.3 修好 `/specode:spec -h` fast-path 旁路后，又一个 `commands/spec.md`
引导主代理调 CLI 而 bypass 业务规则的 case：用户在 git repo 下输入
`/specode:spec 在 git 目录下创建一个项目，用来做一个登录页面`，主代理直接
`sh ... spec_init.py --name login-page ...`，spec 文档**silent 落到**
`C:\Users\qiang\Documents\Notes\specs\login-page`（Obsidian vault 自检测命中），
没有任何确认。

证据：
- `~/.config/specode/config.json` 不存在，`SPECODE_ROOT` 未设
- `Documents\Notes\.obsidian/` 存在 → `spec_init.py` 走第 3 层 silent fallback
- `spec_vault.py status` 返回 `{"source": "auto", "doc_root": "Documents\\Notes"}`
- 主代理 chain-of-thought 截图：直接解析 slug + 调 CLI，没问 doc_root

根因：与 0.10.3 同源——`commands/spec.md` 旧版第二步「## 立即调用」直接给
`sh spec_init.py ...` 命令，主代理照执行，**SKILL.md § Document Root Resolution
只讲了"三层全 miss → exit 3"，没规则约束"第 3 层命中（非全 miss）也应先确认"**。
spec_init.py 实现是 silent 用了。

修复（双管齐下）：

1. `SKILL.md § Document Root Resolution` 加新子章节
   **「首次使用 / auto-detect 命中时的确认（强制）」**：明确 `source = auto`
   或 `none` 时**禁止**直接调 `spec_init.py`，必须先 `AskUserQuestion` 三选
   （接受检测到的 vault + 持久化 / 改用其他绝对路径 + 持久化 / 中止），
   用户选定后 `spec_vault.py set --vault <p>` 持久化，下次自动用、不再问。

2. `commands/spec.md` 重构为 **4 步路由**（依次匹配 `$ARGUMENTS` 形态）：
   - 第一步：fast-path（`-h` / `--help` / `--vault-status` / `--detect-vault` /
     `--sync-status`，hook 已注入模板）→ verbatim print
   - 第二步：set 命令（`--set-vault <p>` / `--set-root <p>`，hook **不**拦截）
     → 调 `spec_vault.py set --vault <p>`，end turn
   - 第三步：新建 spec 前必做 —— 调 `spec_vault.py status`，按 SKILL.md
     新规则做 doc_root 确认
   - 第四步：`spec_init.py` 创建 spec

   修正 0.10.3 commands/spec.md 第一步把 `--set-vault` / `--set-root` 误列入
   fast-path 旗标的 bug（hook 实际不拦截这俩，主代理按"等 hook"会卡住）。
   set 命令现在有独立第二步，调 `spec_vault.py set` 后 end turn。

设计原则：commands 薄（路由 + 边界引导）、SKILL 厚（业务规则）。commands 不
重复 SKILL 里的细则，只在边界 case 指向 SKILL 章节，让业务流程在 SKILL.md
单一来源维护。

## 0.10.3 (2026-05-21)

### Fixed — `/specode:spec -h` fast-path 被 commands/spec.md 引导旁路

0.10.2 修复了 hook emit `UnicodeEncodeError` 之后，`hook_on_user_prompt`
能正确向主代理 `additionalContext` 注入完整 fast-path 模板（含 verbatim
print 指令 + HELP CONTENT BEGIN/END + `specode v0.10.2 ...` 完整 help
body，验证 stdout 2598 字节，session log 无 `hook_exception`）。但主代理
**仍然不按 fast-path 走**，而是 `sh ... spec_init.py -h`，把 spec_init.py
自己的 argparse help 当成 specode help 输出。

根因：`commands/spec.md` 顶部「## 立即调用」标题 + `sh ... spec_init.py ...`
代码块**视觉优先级压倒**原本藏在底部 bullet 第 3 项的"fast-path 参数由 hook
拦截"备注。主代理看到 `-h` 时按"立即调用"分支执行，调起 spec_init.py。

修复：把 fast-path 分支前置成「## 第一步」，明确 `-h` / `--help` /
`--vault-status` / `--detect-vault` / `--sync-status` / `--set-vault` /
`--set-root` **不要调任何 CLI**，**禁止** `sh ... spec_init.py -h` 等，
只 verbatim 输出 hook 注入内容；常规需求降为「## 第二步」。

证据链：
- CodeBuddy 缓存 0.10.2 已正确部署（plugin.json + scripts/utf-8 reconfigure
  + run.sh alias stub 检测均在位）。
- 最新 session log（`615f599c-...jsonl`）中 `hook_on_user_prompt` 后再无
  `hook_exception`（0.10.2 emit 修复有效）。
- 用真实 session id 跑 `prompt="/specode:spec -h"` → hook stdout 2598 字节
  完整 fast-path JSON，含 `specode v0.10.2` 完整 help。
- 主代理 chain-of-thought 截图：先说 "According to the system reminder hook,
  I should output the help content verbatim ..."，紧接调 `sh spec_init.py -h`
  ——证明主代理同时收到 hook 注入与 commands 引导，按 commands 走。

## 0.10.2 (2026-05-21)

### Fixed — Windows 上 hook 注入彻底失效（两个连续根因）

1. **Launcher 命中 Microsoft Store alias stub**（commit `fb2ef14`）——
   `plugins/specode/scripts/run.sh` / `run.cmd` 探测 `python3` 时会命中
   `%LOCALAPPDATA%\Microsoft\WindowsApps\python3.exe`（0 字节 App Execution
   Alias stub，跑起来只打印 "Python was not found" 并 exit 49），
   `spec_session.py` 根本没被执行 → CodeBuddy 启动报
   `Hook SessionStart [warning]`，后续所有 hook 全部空跑。
   修复：`run.sh` 新增 alias stub 路径检测跳过；`run.cmd` 优先级改成
   `py → python3 → python`（`py.exe` 不受 alias 影响）。

2. **emit 阶段 UnicodeEncodeError 被 `_safe_hook` 吞并**（commit `6b0a06f`）——
   Windows pipe stdout 默认 fallback 到 locale 编码（中文 Windows 为
   `cp936/gbk`），无法编码 emoji `📝/🪧/⛔`（来自
   `DOC_PRIORITY_REMINDER_ACTIVE` / `STATUS_FOOTER_TEMPLATE` /
   `SPEC_MODE_CONTINUE_REMINDER` 模板）。`_emit_hook_additional_context`
   写入时抛 `UnicodeEncodeError`，被 `_safe_hook` 装饰器的
   `except BaseException` 吞掉 → hook exit 0、stdout 空 → CodeBuddy 拿不到
   `additionalContext` → 主代理收不到 fast-path / session_id / selector /
   footer / 文档优先提醒。
   修复：`spec_session.py` / `spec_init.py` 顶部
   `sys.stdout / stderr.reconfigure(encoding="utf-8", errors="replace")`，
   绕过 text-mode encoding。

### Fixed — 测试套件跨平台支持（Windows pytest 165/165）

测试代码硬编码 macOS 路径、`.read_text()` 默认 locale 解码、`subprocess.run`
不指定 encoding、`fake_home` 未隔离 `APPDATA` 等多个跨平台问题：

- `tests/conftest.py` + 6 个 `tests/test_task_swarm_*.py`：`SCRIPTS_DIR`
  从硬编码 `/Users/xueqiang/Git/specode/...` 改成
  `Path(__file__).resolve().parents[1] / "scripts"`。
- `conftest.run_script` + `test_task_swarm_cli.py` + `test_task_swarm_hook.py`：
  `subprocess.run` 加 `encoding="utf-8"`，env 设 `PYTHONUTF8=1` /
  `PYTHONIOENCODING=utf-8`，让子进程 pathlib 与 stdio 同时 utf-8。
- `conftest.fake_home`：monkeypatch `APPDATA` / `LOCALAPPDATA` 到
  `tmp_path`，防止用户真实 Obsidian 安装漏到 `spec_vault.detect` 测试。
- 6 个 test 文件的 `.read_text()` 加 `encoding="utf-8"`：解决 utf-8 写入的
  `.config.json` / `sessions/*.json` 被默认 cp936 解码失败。
- `test_spec_session_hooks::test_on_user_prompt_help_fastpath`：
  `"specode v0.6"` 断言改成 `"specode v"`，兼容 0.10.1+ 动态版本号。

无业务行为变化。Windows 上 `pytest` 从 109 fail → 165/165 全过。

## 0.10.1 (2026-05-20)

### Changed — `/specode:spec -h` help 文本

`plugins/specode/scripts/spec_session.py` 内 `HELP_OUTPUT_TEXT` 改为模板：

- 版本号不再硬编码为 `v0.6`，改为运行时从 `.claude-plugin/plugin.json`
  读 `version` 注入（失败降级 `unknown`），后续 bump 不再需要手动改 help。
- 新增「会话日志（v0.10.0+）」段，简述 logs/ 默认行为、env / config
  双开关优先级、`spec_log.py status / replay` 用法，作为新用户从 help
  入口直达日志能力的导航。

无业务行为变化；纯文档/渲染层调整。

## 0.10.0 (2026-05-20)

### Added — Session 日志收集（默认开启，可关）

新增 `plugins/specode/scripts/spec_log.py` 模块 + 双 hook 通配监听
+ 各 CLI 入口集成，全程收集 spec 模式期间的事件流，便于排查
"主代理为什么走偏 / 漏 fork spec-writer / 选错 selector" 等问题。

收集的事件类型：

- `hook_invoked` —— 每个 hook（SessionStart / UserPromptSubmit /
  Stop / SessionEnd / PostToolUse Task / PreToolUse Edit|Write|MultiEdit /
  on-heartbeat-quiet）触发时
- `tool_pre` / `tool_post` —— 主代理每次 Bash / Read / Write / Edit /
  Task 等工具调用前后（PreToolUse `*` + PostToolUse `*` 全通配新 hook）
- `cli_call` / `cli_exit` —— specode 自身 CLI（spec_session /
  spec_init / spec_status / task_swarm）被调用前后的 cmd / argv / exit_code
- `hook_exception` —— hook 内部异常 trace（被 _safe_hook 吞并的，仍记日志）

**存储**：`~/.specode/logs/<session_id>.jsonl`（每行一个 JSON event；
无 session_id 的事件落 `_orphan.jsonl`）。

**双开关**（默认开启）：

```sh
# 临时关闭（仅当前 shell）
export SPECODE_LOG=off

# 永久关闭：编辑 ~/.config/specode/config.json 加
#   { "logging": false }
```

env 优先于 config；env 可取 `off / false / 0 / no` 关闭，`on / true / 1 / yes` 强制打开。

**隐私保护**（默认）：

- 字段名 redact 黑名单：`password / passwd / pwd / api_key / apikey /
  token / access_token / refresh_token / secret / client_secret /
  authorization / auth / cookie / private_key / ssh_key` 命中即替换为
  `<redacted>`。可在 config 加 `redact_keys: ["custom_key", …]` 扩展。
- 字符串字段超 500 字符自动截断（后缀 `...<truncated>`）。
- 递归深度 >8 → `<deep_truncated>`。

**回放 + 状态查询**：

```sh
# 按时序打印一个 session 的事件流
sh "$CLAUDE_PLUGIN_ROOT/scripts/run.sh" \
   "$CLAUDE_PLUGIN_ROOT/scripts/spec_log.py" replay --session <id>

# 占用查询（输出 enabled / switch_source / 文件数 / 总字节）
sh "$CLAUDE_PLUGIN_ROOT/scripts/run.sh" \
   "$CLAUDE_PLUGIN_ROOT/scripts/spec_log.py" status
```

**rotation 策略**：不自动切片；超过 100MB 时 status 命令提示手动清
（`rm -rf ~/.specode/logs/`）。session-bound 写入即可控制大小。

**异常隔离**：日志收集任何异常都吞并（spec_log 内部 try/except + 各
集成点用 contextlib.suppress 包裹），绝不阻断业务流程。失败时主代理
看不到日志写入痕迹，但 spec / hook / CLI 本身行为完全一致。

### Changed — hooks.json 新增 2 个全通配 hook

`PostToolUse "*"` matcher 和 `PreToolUse "*"` matcher 各加一条 hook，
分别调 `spec_session.py on-log-post-tool-use / on-log-pre-tool-use`。
这两个新 hook 仅落日志，不注入 additionalContext，不影响主代理行为。
原有 `PreToolUse Edit|Write|MultiEdit` 和 `PostToolUse Task` matcher
保持不变（继续走 `on-pre-tool-use / on-task-completed` 的 advisory
注入逻辑）。

### Changed — 文档（SKILL.md / CONTRIBUTING.md / README × 2）

- SKILL.md 加 §Session Logging 节，列出存储位置 / 双开关 / 隐私 /
  回放 / 占用查询。
- CONTRIBUTING.md 加 §Debugging with session logs 节，给开发者
  排查问题用 replay 的命令示例 + 新 hook/CLI 子命令应在入口加
  `_log_event` 的约定。
- README / README.zh-CN 「Global bypass」节加 `SPECODE_LOG=off`；
  各自新增 Session logging / 会话日志收集 小节简述用法 + 关闭方式。

### Tests

165 pass (152 previous + 13 new in `test_spec_log.py`)：write_event /
disabled-via-env / disabled-via-config / redact-default-keys /
redact-extended-via-config / truncate-long-string / replay /
replay-missing / status × 3 / hook-invocation-writes-log /
cli-call-writes-log. 原 152 个测试 0 个破——日志收集是完全 backward-
compatible 的纯加项。

### Migration

无需迁移。0.10.0 启动后会开始往 `~/.specode/logs/` 写日志；不想要的
按上面方式关掉。已有 sessions / specs / 锁 / state.json 全部不变。

```sh
# Adjust the CLI name for whichever host you use (claude / codebuddy).
claude plugin marketplace update specode
claude plugin update specode
```

## 0.9.3 (2026-05-20)

### Added — 2 条新 Iron Rule（SKILL.md）

0.9.2 真实跑测时观察到主代理在 `/specode:spec` 后多处违纪：自己 Write
requirements.md（应该 fork spec-writer）+ 写完后又 Edit 改文档头
`Status: Requirements Draft → Complete`（不该越权改 phase 状态）。
现有 6 条 Iron Rule 没有强约束这两点，本版补：

- **Iron Rule 7**：`requirements.md` / `bugfix.md` / `design.md` /
  `tasks.md` 4 份核心文档必须 fork `spec-writer` subagent 写。主代理
  用 Write / Edit 直接写这 4 份文档视为流程违规。subagent 的工具白
  名单（无 Bash）是物理隔离边界，绕过它就是绕过 review/validator
  兜底。`implementation-log.md` 例外，主代理可以直接追加。
- **Iron Rule 8**：文档头 `Status` / `Review Status` 字段不允许主代
  理手改。这些字段反映 phase / 评审状态，由 `phase-transition` CLI
  与 selector 流程驱动改变。主代理写完 requirements.md 把
  `Status: Requirements Draft` 改成 `Requirements Complete` 是越权
  （这是 selector 走完后才该发生的事）；保持模板默认值不动。

### Changed — `doc-confirm-tasks` 合并入 `tasks-execution`（8→7 个选择器）

0.9.2 真实跑测时观察到 tasks phase 走两步选择器（先 doc-confirm-tasks
确认 tasks.md、再 tasks-execution 选执行方式）冗余且易出错——主代理
在第一步把标准 3 选项「确认 / 查看全文 / 继续沟通」简化成 2 选项
「确认，继续 / 需要调整」，漏掉了 task-swarm 路径。

本版合并为一步：

- 废弃 `SELECTOR_PROMPTS["doc-confirm-tasks"]`，把「需要调整」作为
  `tasks-execution` 的回退出口。tasks-execution 现 4 选项：
  - 用 task-swarm 多 agent 并发（推荐）
  - 顺序执行（同时处理 optional）
  - 需要调整 tasks.md
  - 暂不 coding
- 不再区分「开始 required」vs「开始 required + optional」——默认两
  种执行方式都把 optional 一起跑；要只跑 required 走 Other 输入。
- `phase=tasks` 的 `pending_selector` 推导从 `"doc-confirm-tasks"`
  改为 `"tasks-execution"`。
- 同步：SKILL.md 8 场景表 → 7 场景表；selectors.md §A4
  `tasks-execution` 模板镜像 + 表格删 doc-confirm-tasks 行；
  workflow.md §3.3 / §5 流程改一步出图；test_selector_prompts.py
  删 test_doc_confirm_tasks_snapshot；test_spec_session_hooks.py
  pending_selector fixture 改 "tasks-execution"。

### Changed — tasks.md 模板统一为 task-swarm 兼容格式

0.9.2 真实跑测时观察到主代理选「用 task-swarm 多 agent 并发」后
`task_swarm.py init` 报 `tasks.md 中未解析出任何 ## 阶段 N: 段`，
被迫主代理自己 Write 覆盖 tasks.md（违反新 Iron Rule 7）。根因：
spec-writer 生成的 tasks.md 用 `- [ ] 1. 阶段标题 / - [ ] 1.1 子任务`
嵌套格式，但 `task_swarm.py parse_md.py` 期望 `## 阶段 N: 标题` 顶层
段 + `- [ ] N.M ... @writes:... _需求：x.y_`。两边对不齐。

本版统一为 task-swarm 兼容格式（顺序执行也兼容——task-swarm 标签被
顺序执行 agent 当作注释忽略）：

- `assets/templates/tasks.md` 完整重写：顶层 `## 阶段 N: ...`
  + `- [ ] N.M ... @writes:... _需求：x.y_` + 格式约定头部说明。
- `spec_init.py FALLBACK_TEMPLATES["tasks.md"]` 同步。
- `references/templates.md §4` 模板示例 + 约束规则改写。
- `agents/spec-writer.md phase=tasks` 子工作流明示新格式 + 不符合时
  应回到 `tasks-execution` 选「需要调整」让 spec-writer 重写（**不
  许主代理 Write 覆盖**，呼应 Iron Rule 7）。

### Changed — `commands/task-swarm.md` 立即调用段澄清

0.9.2 真实跑测时主代理调 `task_swarm.py` 时漏 `init` 子命令、把
spec 目录传给 `--tasks`（应该传 tasks.md 绝对路径）。立即调用段示例
原本用 `<abs>` 太抽象，本版改为 `<spec_dir>/tasks.md`，并在「注意」
块明示：`init` 子命令必传、`--tasks` 是 tasks.md 路径而非 spec 目录、
不符合格式时回到 selector 让 spec-writer 重写。

### Tests

152 pass（down from 153；删除 `test_doc_confirm_tasks_snapshot`
随 selector 合并；其余 fixture / 断言同步更新）。

### Migration

无需迁移。`tasks-execution` 推荐项变成「task-swarm 多 agent 并发」，
但仍保留「顺序执行」「需要调整」「暂不 coding」三个出口。已经写好的
旧格式 tasks.md（无 `## 阶段 N:` 段）在选 task-swarm 时会报错；主
代理按新 Iron Rule 7 + tasks-execution 「需要调整」入口让 spec-writer
重写即可，不要手改。

```sh
# Adjust the CLI name for whichever host you use (claude / codebuddy).
claude plugin marketplace update specode
claude plugin update specode
```

## 0.9.2 (2026-05-19)

### Removed — `DESIGN.md` 与 `IMPLEMENTATION-AUDIT.md` 从仓库移除

两份文档都不再作为项目产物维护：

- `DESIGN.md`（1515 行 / ~78KB）是 v0.5 → v0.8 重建期的设计文档，
  写给设计者 / 维护者读，不是最终用户文档。0.8.0 / 0.9.x 系列演进
  后部分章节已与代码漂移（如 §3.3 sessions schema 字段名、§3.9
  spec_lint 规则数量），全文同步代价过高。
- `IMPLEMENTATION-AUDIT.md`（327 行 / ~26KB）是 v0.7.0 时点的一次性
  对账表，行号引用大多因为代码演进失效，且没有持续维护价值。

历史信息仍可通过 `CHANGELOG.md` + git log 回溯。当前真实代码状态
看 `SKILL.md` + `references/*.md`（与代码同步演进）。

随之清理：

- `plugins/specode/commands/status.md` —— 引用 `DESIGN.md §3.3` 改为
  指向 SKILL.md §Session Lifecycle。
- `plugins/specode/scripts/spec_session.py` —— `HELP_OUTPUT_TEXT`
  末尾的 "DESIGN.md §3" 引用改为 "SKILL.md 与 references/"。
- `plugins/specode/skills/specode/references/task-swarm.md` —— 章节
  标题里 `（§11.X）` 全部去掉，开头 "对应 DESIGN.md §11" 删除。
- `plugins/specode/scripts/*.py`（9 个文件）—— 所有 docstring / 注释
  里指向 `DESIGN.md` 的 `§X.Y` 章节引用改为指向具体的
  `references/*.md` 章节号，或简化为指向 SKILL.md。
- `plugins/specode/commands/task-swarm.md` —— 3 处 `§11.X` 引用
  对齐到 `references/task-swarm.md §X`。
- `plugins/specode/skills/specode/references/selectors.md` —— 历史
  反 pattern 列表里 `请按 §3.7.X 类型骨架输出` 改为 `请按
  selectors.md 类型骨架输出`。

### Changed — `CONTRIBUTING.md` 规范化重写

- 删除头部过时的 0.6.0 note（提到 75 tests / 4 hooks / 6 references，
  现在都不准确）。
- 测试数字从 "75 tests" 更新到 "153 tests"，覆盖范围描述同步扩大
  （加 task-swarm 全套 + selector_prompts + 集成 + 兼容性回归）。
- 新增 **CLI invocation contract** 整节：明确所有 CLI 必须走
  `run.sh` 包装 + `${CLAUDE_PLUGIN_ROOT:-${CODEBUDDY_PLUGIN_ROOT}}`
  完整路径模板（0.8.0 起的硬要求，避免主代理裸调对 cwd 失败）。
- 新增 **On-disk schema fields** 整节：约束新写入用中性字段名
  （`session_id` / `holder`，不再用 `claude_session_id`），读侧
  必须三键 fallback；schema 字段命名变更走 minor 还是 major 的
  semver 取决于是否带 read-side fallback。
- semver 表加 hook event names 与 persisted schema fields 到
  "API surface" 范围；schema rename + fallback 明示走 minor。
- release 流程加 step 3 "pytest 一次"，明示双宿主 CLI 命令等价。
- 全文去掉 v0.6 字样，去掉 host-specific 措辞。

### Removed — `.gitignore` 加强

补 `.pytest_cache/` 与 `.claude/` 两条防御性 ignore（目前都未被
追踪，但 `git add -A` 可能在未来误抓）。

### Tests

153 pass，无净变化。本版仅 docs 删除 / docstring 调整 / `.gitignore`
更新，无代码逻辑变化。

### Migration

无需迁移。如果你之前 fork 了仓库且依赖 `DESIGN.md` 做参考，请改
看 Obsidian 备份或对应版本的 git tag。

```sh
# Adjust the CLI name for whichever host you use (claude / codebuddy).
claude plugin marketplace update specode
claude plugin update specode
```

## 0.9.1 (2026-05-19)

### Changed — `tasks.md ## 测试要点` 降权为"参考清单"

0.9.0 在把 acceptance-checklist.md 折叠进 tasks.md 时过度强调了
新 `## 测试要点` 节——把它包装成「跟随式更新铁律」、acceptance-gate
验收硬条件、`DOC_PRIORITY_REMINDER` 每轮注入提示、spec-writer 5 处
「同 turn 更新」、workflow.md §3.2 整章纪律……约 50 处分布在 12
个文件，与节点本身只是「给测试人员一份验证清单参考」的实际地位
严重不匹配。

本版降权：

- **`acceptance-gate` selector**（`spec_session.py` 与
  `selectors.md` 镜像）—— 验收推荐只看 `tasks.md` 是否全 `[x]`，
  测试要点降为"chat 简报里顺带提一下"的参考信息，不参与判定。
- **`DOC_PRIORITY_REMINDER_ACTIVE`**（hook 每轮注入文本）—— 删
  "同 turn 更新测试要点"那一行，文档清单里加一句注解说明 tasks.md
  末尾有这一节即可。
- **SKILL.md** —— 5 份文档列表 / 文档表格里不再标"同 turn 重写
  测试要点"硬纪律；tasks.md 行改为「spec-writer 在 tasks phase
  按 SHALL 补几行供测试人员参考」。
- **`references/workflow.md`** —— 删 §3.2 整章
  「tasks.md 测试要点跟随式更新（铁律）」；删 §3.1 / §4 / §5
  各处「同 turn 更新测试要点」步骤；§7 acceptance phase 不再
  要求"逐行跑测试要点 + 全 [x] 才推荐验收通过"，回到只看 tasks.md
  完成度；§9.2 持续沟通模式不再强调测试要点；流程图去掉
  「测试要点跟随式更新」列。后续 §3.3 / §3.4 重编号为 §3.2 / §3.3。
- **`references/templates.md`** —— 删 §4.2 整节「填充规则」；§4
  tasks.md 模板的 `## 测试要点` 示例从带 `[ ]` 改成纯 bullets
  （表明非待办清单）；`## 验收` 节删「测试要点全部跨过」那行；
  增设 §4.2「填充提示」短节说明 spec-writer 在 tasks phase
  按 SHALL 顺手补几行即可，模糊时可留 `_待补充_`。
- **`agents/spec-writer.md`** —— 删整个「## tasks.md 测试要点
  同 turn 更新」section；phase=requirements / phase=bugfix 流程
  里删「同 turn 更新测试要点」步骤；phase=tasks 加一句「填末尾
  `## 测试要点` 节，按 SHALL 补几行供测试人员参考」。
- **`references/iteration.md`** —— iteration 期间不再要求改测试
  要点；累积规则降为「按需追加」；ASCII 示例从 `[ ] / [x]` checkbox
  改成纯 bullets。
- **README / README.zh-CN / DESIGN / IMPLEMENTATION-AUDIT** —— 顶层
  描述去掉「跟随式」「同 turn 更新」措辞。

### 不变（保留）

- `assets/templates/tasks.md` 模板里的 `## 测试要点` 节本身保留
- `spec_init.py FALLBACK_TEMPLATES["tasks.md"]` 里的 `## 测试要点`
  节本身保留（格式从 `- [ ]` 改回纯 bullets）
- `obsidian.md` 目录树里的 `tasks.md ← 末尾自带 ## 测试要点 章节`
  说明保留（信息性）
- `spec-writer agent` 在 tasks phase 仍负责按 SHALL 顺手补充
  测试要点行（但作为 tasks 文档的一部分，不是独立铁律）

### Tests

153 pass（无净变化）。本版仅 docs/prompts 文字调整，无代码逻辑改变。

### Migration

无需迁移。`acceptance-gate` 推荐判定从「tasks.md 全 [x] + 测试要点
全跨过」简化为「tasks.md 全 [x]」——对已经在用 0.9.0 的用户来说，
验收门只会变得**更容易**通过，不会出现"以前能过、现在卡住"的情形。

```sh
# Adjust the CLI name for whichever host you use (claude / codebuddy).
claude plugin marketplace update specode
claude plugin update specode
```

## 0.9.0 (2026-05-19)

### Removed — `acceptance-checklist.md` retired, test points moved into `tasks.md`

Spec document count dropped from 6 to 5. The standalone
`acceptance-checklist.md` (which existed to give QA reviewers a
verification checklist parallel to `tasks.md`) has been folded into
a new `## 测试要点` section at the end of `tasks.md`. Reasons:

- The checklist file duplicated information that already had a home
  in `tasks.md` (`_需求：x.y_` traceability tags).
- Maintaining two parallel docs encouraged drift — one would update
  while the other lagged, and the `spec_lint` `checklist-lag` rule
  papered over a symptom rather than fixing the duplication.
- A single `## 测试要点` section keeps the QA-facing artifact next
  to the engineering-facing tasks it validates, so changes propagate
  in one Edit.

Acceptance phase now decides "passed" based on `tasks.md` being all
`[x]` plus every test-point line in `## 测试要点` being crossed
(`[x]` or `[-]` with reason), instead of a separate checklist table.

**Changes**:

- `spec_init.py` — drops the `acceptance-checklist.md` template
  string and its write step; `tasks.md` template now ships with a
  `## 测试要点` section.
- `spec_session.py` — `SELECTOR_PROMPTS["acceptance-gate"]`
  rewritten (lists `n_done/n_total` + `n_fail` instead of pass/fail
  count, and prompts the model to run `spec_lint.py` first); the
  6-doc list in `spec_doc_names` (`list-specs`) shrinks to 5; the
  document-first reminder text drops the checklist line.
- `spec_lint.py` — `rule_checklist_lag` removed (3 rules remain:
  traceability / log / EARS).
- `agents/spec-writer.md` — the "same-turn rewrite of
  `acceptance-checklist.md`" iron rule becomes "same-turn update of
  the `## 测试要点` section in `tasks.md`".
- `SKILL.md` — 6→5 doc list; new line under §Phase Order instructing
  the model to invoke `spec_lint.py` once when entering acceptance.
- `references/workflow.md` — §3.2 retitled and rewritten as
  "tasks.md 测试要点 跟随式更新（铁律）"; acceptance phase steps
  (§7) now include the `spec_lint` call and reference test-point
  rows rather than checklist rows.
- `references/templates.md` — §5 (`acceptance-checklist.md` template)
  removed entirely; `tasks.md` template (§4) gains the `## 测试要点`
  section + a new §4.2 with the fill rules; subsequent sections
  renumbered (§6→§5, §7→§6, …).
- `references/iteration.md` — iteration-time accumulation rules now
  describe appending lines to `## 测试要点` instead of rewriting a
  checklist table.
- `references/obsidian.md` — spec directory tree drops the
  checklist file.
- `references/selectors.md` — A6 `acceptance-gate` constant
  rewritten to mirror the new `SELECTOR_PROMPTS["acceptance-gate"]`.
- README / README.zh-CN / DESIGN / IMPLEMENTATION-AUDIT updated to
  reflect the 5-doc list and the new acceptance criterion.

### Added — `spec_lint.py` wired into acceptance phase

`spec_lint.py` existed as a standalone tool since 0.6.0 but no
hook/command/agent ever invoked it. Now SKILL.md §Phase Order and
the `acceptance-gate` selector text both instruct the main agent
to call it once when entering acceptance and list any
traceability / log / EARS warnings in the chat preamble. Lint is
still advisory (`exit 0`), never blocking.

### Removed (cont.)

- `spec_lint.rule_checklist_lag` and the 1 corresponding pytest
  case in `test_spec_lint.py` (`test_lint_checklist_lag_warns`).
  5 cases remain: clean-spec + trace + log + ears + all-bad
  multi-fire.
- `acceptance-checklist.md` entry from `test_spec_init.py`
  `DOC_FILENAMES` (6→5).

### Tests

153 pass (down from 154; the deleted `checklist-lag` case is the
only loss — clean/trace/log/ears/all-bad coverage of the 3
surviving rules stays).

### Migration

**Existing specs created before 0.9.0** keep their
`acceptance-checklist.md` file on disk — no auto-delete. Treat
those as historical artifacts; copy the still-useful lines into
the new `## 测试要点` section in `tasks.md` and delete the file
manually if you no longer need it. New specs created from 0.9.0
onward never get the file.

```sh
# Adjust the CLI name for whichever host you use (claude / codebuddy).
claude plugin marketplace update specode
claude plugin update specode
```

## 0.8.1 (2026-05-19)

### Changed — `references/prompts.md` renamed to `references/selectors.md`

The file name `prompts.md` was too generic for a document whose
content is "AskUserQuestion selector specification + 8 fixed scenario
constant library". `selectors.md` matches the file's own title
("Selectors — AskUserQuestion 调用规范") and aligns with the
single-word file naming convention used by the other references
(`workflow.md`, `templates.md`, `iteration.md`, …).

Renamed via `git mv` so history follows. All 23 in-repo references
were updated (SKILL.md, 5 cross-references in `references/*.md`,
DESIGN.md, IMPLEMENTATION-AUDIT.md). Earlier `CHANGELOG.md` entries
that mention `prompts.md` were **left untouched** because they
reflect the actual file name at the time of those releases.

### Added — type variant A+ registered (single-select + preview)

`references/selectors.md` now documents the **A+ variant**: when an
option carries a `preview` field, the host UI auto-switches to a
side-by-side layout (vertical option list on the left, monospace
markdown preview on the right that updates as the user moves the
focus). Single-select only — `multiSelect=true` rejects `preview`.

Currently **no fixed scenario uses A+** — this is template-only,
registered ahead of any phase-gate that needs visual artifact
comparison (UI mockups / code snippets / config variants). If a
future scenario adopts A+, add the constant to
`spec_session.py SELECTOR_PROMPTS` and append it to the 8-scenario
table below the variant note.

### Tests

154 pass; no test changes.

### Migration

None.

## 0.8.0 (2026-05-19)

### Changed — host-neutral wording + sessions schema field rename

Two coordinated cleanups so the plugin reads as host-agnostic and the
on-disk schema uses neutral key names.

**1. Description neutralization across docs and code.** All
user-facing wording that singled out one host CLI was reworded to
neutral terms ("host CLI" / "宿主" / "CLI agent"). Affected files:

- `README.md` / `README.zh-CN.md` — install section lists CodeBuddy
  before Claude Code; tagline says "for CLI coding agents".
- `SKILL.md` + 6 `references/*.md` — "Claude Code 内置 X 工具" → "宿主
  内置 X 工具"; "Claude 窗口" / "Claude 会话" → 中性词。
- `DESIGN.md` / `CHANGELOG.md` / `CONTRIBUTING.md` /
  `IMPLEMENTATION-AUDIT.md` — same treatment.
- `plugin.json` / `marketplace.json` description fields drop the
  "(Claude Code + CodeBuddy)" suffix.
- `spec_session.py` `HELP_OUTPUT_TEXT`, hook context strings, error
  messages neutralized.

Technical contracts retained verbatim because they are platform-
injected, not stylistic: `CLAUDE_PLUGIN_ROOT` env var (with the
existing `:-${CODEBUDDY_PLUGIN_ROOT}` fallback), `.claude-plugin/`
directory name (plugin discovery protocol), the `claude plugin …`
install commands users actually type.

**2. Sessions / state.json schema: `claude_session_id` → `session_id`.**
All write sites now produce the new key. Read sites are
backwards-compatible:

- `read_session()` (`spec_session.py:135`) auto-migrates legacy files
  by copying `claude_session_id` → `session_id` in-memory; the next
  write lands the new key on disk.
- `StateMachine.load()` (`task_swarm_state.py:149`) does the same for
  `~/.specode/runs/<run_id>/state.json` (renames the dataclass field
  too: `sm.claude_session_id` → `sm.session_id`).
- Lock holder reads (`list-specs`, `on-heartbeat-quiet`) fall back
  through `holder → session_id → claude_session_id` in priority
  order. The lock field's actual persisted key has always been
  `holder`; the rename does not touch `<spec-dir>/.config.json`.

No manual migration needed. Existing `~/.specode/sessions/*.json`
and `state.json` files keep working; they get rewritten in the new
schema on the next mutating CLI call.

### Changed — command md files carry copy-pasteable CLI templates

Every command md under `plugins/specode/commands/` now opens with an
**「立即调用」** section that embeds the full `sh
"${CLAUDE_PLUGIN_ROOT:-${CODEBUDDY_PLUGIN_ROOT}}/scripts/run.sh"
"${CLAUDE_PLUGIN_ROOT:-${CODEBUDDY_PLUGIN_ROOT}}/scripts/<name>.py"
<args>` template the model should execute. Motivation: a recent
session showed the model looping six times on bare `python3
spec_session.py …` invocations against the wrong cwd, because the
command md only listed `/specode:continue $ARGUMENTS` and the model
never consulted SKILL.md for the wrapper rule before retrying.

SKILL.md also gained a "**CLI 调用规约（强制）**" subsection and an
Iron Rule explicitly banning bare `python3` invocations.

### Added — backwards-compat regression tests

Two new tests pin the auto-migration behavior so future refactors
can't quietly drop legacy support:

- `test_read_session_migrates_legacy_claude_session_id`
  (`tests/test_spec_session_business.py`).
- `test_load_migrates_legacy_claude_session_id`
  (`tests/test_task_swarm_state.py`).

### Removed

- `migrate-from-spec-mode.sh` — one-shot migration script for users
  upgrading from 0.1.0's `spec-mode` plugin name. Long past its
  usefulness window; deleted.

### Tests

154 pass (152 previous + 2 new compat regressions). All existing
fixtures updated to write the new `session_id` key directly.

### Migration

None. Plugin cache update sufficient:

```sh
# Adjust the CLI name for whichever host you use (claude / codebuddy).
claude plugin marketplace update specode
claude plugin update specode
```

## 0.7.3 (2026-05-19)

### Changed — all selector references unified to YAML three-section format

Following 0.7.2 (which rewrote SELECTOR_PROMPTS to the three-section
+ YAML format), this release brings the two **dynamic selectors** in
`references/obsidian.md` and the **8 static scenarios** in
`references/prompts.md` to the same format so every selector
reference across the plugin is visually identical.

Two dynamic selectors updated:

- **§3 multi-vault selection** (when `spec_vault.py detect` finds >1
  vault and no `obsidianRoot` is set yet) — was Python-call form;
  now three-section YAML.
- **§5.1 `/specode:continue` no-slug spec picker** (when
  `spec_session.py list-specs` returns >0 specs) — was Python-call
  form; now three-section YAML. Empty list still skips the tool and
  prompts the user to run `/specode:spec <requirement>` instead.

The 8 static scenarios in `prompts.md` (workflow-choice,
clarification-{wizard,done}, doc-confirm-{requirements,bugfix,design,
tasks}, tasks-execution, takeover-options, acceptance-gate,
iteration-scope) were rewritten from Python-call form to **byte-for-
byte the same YAML three-section format as SELECTOR_PROMPTS**, with
the same wrapper section structure (目的 / 上下文 / 前置动作 / 工具参数 /
约束). The previous "Python-call form and YAML form are equivalent"
caveat is removed — there is now only one format.

A worked example with three clarification points (login UX scenario)
was added to §B1 to give the model a concrete reference for wizard
construction.

### Tests

- All 152 tests pass; no test changes required (snapshots already
  match the new format after 0.7.2).

### Migration

None. Plugin cache update sufficient:

```sh
claude plugin marketplace update specode
claude plugin update specode
```

## 0.7.2 (2026-05-19)

### Changed — SELECTOR_PROMPTS rewritten to three-section + YAML format

All 11 entries in `spec_session.py SELECTOR_PROMPTS` have been rewritten
to a **three-section + YAML-indented** format that matches the
"directly paste into the host CLI and the tool fires" prompt style
the maintainer validated in another window.

Each constant now has the same structure:

```
## 选择器节点：<scenario>

**目的**：<why this selector is appearing now; what user just did>

**上下文**：active spec=<slug>, phase=<phase>, <other dynamic fields>

**前置动作（chat 简报，≤N 行）**：<what to write to chat BEFORE calling the tool>

**调用 `AskUserQuestion` 工具**：

questions:
  - question: "<full question>"
    header: "<≤12 char chip>"
    multiSelect: <true|false>
    options:
      - label: "<option A>"
        description: "<rationale / trade-off>"
      - label: "<option B>"
        description: "..."

**约束**：<scenario-specific dos and don'ts>
```

Why this change:
- The previous wrapper text ("必须呈现「X」选择器（类型 A 单列单选）...") was diagnostic / declarative — the model still had to translate it into tool arguments mentally.
- The new format **is itself a paste-and-fire tool prompt** — the YAML block can be lifted as-is into the model's mental model of the `AskUserQuestion` call.
- Three sections make purpose / pre-action / call / constraints visually separate, so the model can't skip the chat briefing before tool call (doc-confirm-* constants explicitly require 3-8 bullets of summary).

What this changes in behavior:
- doc-confirm-* now explicitly mandates a chat briefing **before** the tool call (file path + 3-8 change bullets + open questions).
- takeover-options explicitly forbids the "（推荐）" marker (user must judge based on other holder's liveness).
- acceptance-gate conditionally moves the "（推荐）" marker (only when `n_fail=0`).
- tasks-execution explicitly notes the 4 options have saturated the tool ceiling; Other for custom.
- iteration-scope explicitly flags `multiSelect: true` as the **only** Type C usage in the protocol.

`references/prompts.md` updated with a note that the Python-call form (`AskUserQuestion(questions=[...])`) and the YAML-indented form (used by the hook) are **semantically equivalent** — both mean "call the tool with these arguments".

### Tests

- `test_selector_prompts.py` snapshot assertions updated to match new
  format (assert `选择器节点：`, `AskUserQuestion`, `multiSelect: false|true`,
  YAML `options:` / `label:` markers, `Type something` + `Other` in
  forbidden-list).
- All 152 tests pass.

### Migration

None. Existing sessions / specs unaffected; hooks behavior otherwise
unchanged. Plugin cache update sufficient:

```sh
# Adjust the CLI name for whichever host you use (claude / codebuddy).
claude plugin marketplace update specode
claude plugin update specode
# restart the host CLI
```

## 0.7.1 (2026-05-19)

### Changed — selector protocol switched to AskUserQuestion

The 11 entries in `spec_session.py SELECTOR_PROMPTS` have been
rewritten to instruct the model to call the host CLI's built-in
**`AskUserQuestion`** tool instead of emitting a markdown list with
a `AWAITING_USER_CHOICE` sentinel and asking the user to reply with
a number.

The three selector types map to `AskUserQuestion` parameters as
follows:

- **Type A (single-select)** — `questions=[1 q]` + `multiSelect=false`
- **Type B (wizard)** — `questions=[2-4 q]`, each `multiSelect=false`
  (each question shows as its own chip-tab)
- **Type C (multi-select)** — `questions=[1 q]` + `multiSelect=true`

Why this changes things:

- The host tool renders arrow-key navigation + Enter to
  submit + ESC to cancel + auto-provided "Other" for free-text
  input. The user never types a number.
- The historical reserved positions `Type something` / `Chat about
  this` / `Submit` are deleted from the selector text — "Other" and
  ESC are provided by the tool.
- The `AWAITING_USER_CHOICE` sentinel is removed everywhere it
  drove turn termination — calling the `AskUserQuestion` tool is
  itself a turn terminator.
- `references/prompts.md`, `SKILL.md` §Selectors, and the
  multi-vault selector in `references/obsidian.md` §3 all now
  describe selectors as `AskUserQuestion(questions=[...])`
  invocations with explicit Python-style parameter blocks.
- `references/workflow.md` §9.1 (`/specode:continue` with no slug)
  and §10 (phase-gate output order) updated; the model no longer
  outputs a numbered list and waits for a reply — it calls the
  tool.

The historical wording (`AWAITING_USER_CHOICE` / "请回复编号" /
`Type something` / `Chat about this`) is now listed as **forbidden
phrasing** in `references/prompts.md`'s compat section so the model
can recognize and reject it if encountered in older docs.

### Tests

- `tests/test_selector_prompts.py::test_workflow_choice_snapshot`
  updated to assert `AskUserQuestion` / `multiSelect` / `"label"`
  fields appear, and that `Type something` / `Other` appear in the
  forbidden-list section.
- All 152 tests pass (75 v0.6 + 77 task-swarm = 152; no new tests
  introduced in 0.7.1).

### Migration

No state migration needed. Existing `~/.specode/sessions/<id>.json`
files are unaffected. Hooks behavior is otherwise unchanged.

## 0.7.0 (2026-05-19)

### Added

- **task-swarm multi-agent orchestrator** (was originally targeted at
  a separate v0.7). Six new scripts:
  - `task_swarm.py` (1333 lines) — CLI: `init` / `status` / `plan` /
    `advance` / `writeback` / `heartbeat` / `resolve`.
  - `task_swarm_state.py` — StateMachine + `state.json` atomic
    persistence + deadloop detection (3 consecutive same fail
    signatures → group failed-deadloop, no infinite loop).
  - `task_swarm_parse_md.py` — `tasks.md` parser + group splitting
    by `@writes` file-conflict (no two stages in the same group
    touch overlapping files).
  - `task_swarm_outbox.py` — strict schema validators for coder
    `result.md` / reviewer `review.md` (with evidence tags) /
    validator `validation.md` (with fix targets).
  - `task_swarm_writeback.py` — line-safe `tasks.md` writeback;
    refuses any diff outside `[ ] → [x]` checkbox toggle + `> `
    annotation block append.
  - `task_swarm_prompt.py` — prerendered prompts for coder /
    reviewer / validator subagents at every phase / round.
- **`on-task-completed` hook (PostToolUse matcher=Task)** — when a
  subagent returns during a task-swarm run, calls
  `task_swarm.py plan` and injects the next-step advice into
  `additionalContext` (9 state matrix per §11.6). Never blocks.
- **`on-heartbeat-quiet` hook (UserPromptSubmit, second handler)** —
  silently renews the spec lock on every user turn when
  `mode=active`. Never injects `additionalContext`.
- **`on-pre-tool-use` hook (PreToolUse matcher=Edit|Write|MultiEdit)** —
  when in a task-swarm run and the target is the active spec's
  `tasks.md`, injects an advisory reminding the model to go through
  `task_swarm.py writeback` instead of direct edits. Never blocks.
- **`spec_session.py list-specs --root <path>`** — replaces the
  removed `spec_choice.py` discovery flow for `/specode:continue`
  with no slug; returns a JSON of all specs in the doc root with
  lock state / phase / mtime so the model can present a
  numbered-list selector without Grep'ing the project directory.
- **`spec-writer` agent** (already in 0.6) and **four task-swarm
  agents** (planner / coder / reviewer / validator, already
  shipping; tool isolation unchanged).
- **References** added: `task-swarm.md` (full protocol incl.
  §11.1–§11.7 spec) and `task-swarm-example.md` (3-stage / 8-task
  worked example showing group split + traceability + annotation
  block format).
- **77 new tests** for the task-swarm pipeline; **152 tests total**
  (75 v0.6 + 77 v0.7) all passing.

### Changed

- **`SKILL.md` slimmed from ~335 lines to ~194 lines** — heavy
  detail moved to references; SKILL.md is now an activation contract
  + dispatch table, not a manual.
- **`/specode:continue` flow corrected** — model is now explicitly
  forbidden from Grep'ing the project directory; must go through
  `spec_vault.py status` → `spec_session.py list-specs`. See
  `references/obsidian.md` §5.1.
- **Multi-vault selection UI** now follows §3.7.1 Type A skeleton
  with `AWAITING_USER_CHOICE` sentinel and `Type something` /
  `Chat about this` reserved positions (was a freer list before).
- **All version-difference wording removed** from runtime docs
  (commands / agents / skills / references) — features are
  documented as "what works", not "what is new in vX".

### Removed

Nothing further. All deletions from 0.5.0 remain: `spec_guard.py`,
`spec_sync.py`, `bash_guard.py`, `task_swarm_guard.py`, all INV-1
through INV-11, `spec_choice.py`, sentinel short-circuit, audit
log, telemetry.

### Hook inventory (final)

| Event | Handler | Behavior |
|---|---|---|
| `SessionStart` | `on-session-start` | Initializes sessions file; emits session_id reminder |
| `UserPromptSubmit` | `on-user-prompt` | Fast-path / selector / doc-first / status-footer / mode reminder |
| `UserPromptSubmit` | `on-heartbeat-quiet` | Silently renews lock on every active turn |
| `PreToolUse` | `on-pre-tool-use` | Reminds (never blocks) on direct `tasks.md` edits during task-swarm runs |
| `Stop` | `on-stop` | Code-doc sync reminder + spec-mode continuation reminder |
| `PostToolUse` (matcher=Task) | `on-task-completed` | task-swarm next-step advice |
| `SessionEnd` | `on-session-end` | Writes mode=ended + releases lock as fallback |

All hooks `exit 0`. `SPECODE_GUARD=off` short-circuits all of them.

## 0.6.0 (2026-05-19)

### Added — full re-implementation on the 0.5.0 skeleton

0.5.0 stripped the project back to a skeleton. 0.6.0 rebuilds the runtime
**without** any of the previous INV / exit-2 enforcement, on top of a new
"advisory hooks + selector prompts + session-bound state" foundation.

- **Session lifecycle bound to host `session_id`.** New per-session state
  file at `~/.specode/sessions/<session_id>.json` with fields
  `mode` (active / readonly / ended), `active_spec_slug`, `phase`,
  `lock_state`, `pending_selector`, ... — all writes are atomic
  (tempfile + `os.replace` + `os.fsync`) and rolled back on partial
  failure. `<spec-dir>/.config.json` lock field uses `holder` as the
  persisted key.
- **Persistent session is the only mode** — `--persist` flag removed.
  `/specode:spec <requirement>` always creates a persistent session;
  `/specode:end` writes `mode=ended` and hooks immediately stop
  injecting.
- **Four v0.6 hooks, all advisory (`exit 0`, never block):**
  - `SessionStart` → `on-session-start` — initializes sessions file +
    injects `session_id` reminder.
  - `UserPromptSubmit` → `on-user-prompt` — overlays up to 5 segments
    based on `mode`: fast-path interception (`/specode:spec -h` / 
    `--vault-status` / `--detect-vault` / `--sync-status`), selector
    prompt (per `pending_selector`), document-first reminder, status
    footer template, and spec-mode continuation reminder.
  - `Stop` → `on-stop` — injects code-doc sync reminder (output side)
    and spec-mode continuation reminder when `mode=active`.
  - `SessionEnd` → `on-session-end` — writes `mode=ended` + releases
    any lock the dying session still holds (forgiveness fallback if
    user forgot `/specode:end`).
- **Selector text is generated by the model, not the script.** Three
  selector types (A single-select / B wizard / C multi-select) match
  the three reference screenshots shipped by the project. The hook
  injects an `additionalContext` constant telling the model *which*
  type and scenario to render; the model formats the text per the
  skeletons in `references/prompts.md`. 11 fixed scenario constants
  shipped in `spec_session.py SELECTOR_PROMPTS` (workflow-choice,
  clarification-wizard, clarification-done, doc-confirm-{requirements,
  bugfix,design,tasks}, tasks-execution, takeover-options,
  acceptance-gate, iteration-scope).
- **Status footer** required on every active-spec turn:
  `─── spec-mode ─── spec: <slug> | session: <8-prefix> | phase: <p> | /specode:end 退出`
  (readonly mode adds `[只读]` segment).
- **Document-first discipline as advisory hooks**, replacing the
  exit-2 INV-1 / INV-2 enforcement entirely:
  - `on-user-prompt` injects "📝 文档优先提醒（输入侧）" listing the
    six spec docs, asking the model to check whether the current
    input warrants a doc edit *before* code.
  - `on-stop` injects "🔄 代码-文档同步提醒（输出侧）" asking the
    model to self-check whether the just-finished turn left a
    code change without a matching doc update.
- **`/specode:spec -h` fast-path** — hook intercepts the prompt and
  injects the full help text into `additionalContext` for the model
  to verbatim-print, replacing the prior unstable "model reads
  references/help-output.md" path.
- **Six core scripts** (stdlib-only): `spec_vault.py` (3-tier doc
  root resolution + Obsidian vault detection), `spec_init.py` (spec
  scaffolding with forced double-write of sessions + .config.json
  and rollback), `spec_session.py` (1500 LOC — business commands,
  hook subcommands, SELECTOR_PROMPTS), `spec_lint.py` (4 advisory
  rules), `spec_status.py`, plus `run.sh` / `run.cmd` launchers.
- **`spec-writer` agent** — new agent for document generation with
  tools `Read, Write, Edit, Grep, Glob` (no Bash; physical
  isolation prevents the agent from touching code, locks, or
  phase transitions).
- **SKILL.md and 6 references rewritten** for the new model:
  `workflow.md`, `lock-protocol.md`, `obsidian.md`, `prompts.md`
  (selector scenarios constant library), `templates.md` (six doc
  templates + EARS SHALL), `iteration.md`.
- **75 pytest tests** covering 3-tier vault resolution, init &
  rollback, business lock state machine, four hooks across mode
  matrix, SELECTOR_PROMPTS snapshot, lint rules, and end-to-end
  event chain. All passing.

### Removed

Nothing further beyond the 0.5.0 skeleton removal. **INV-1 through
INV-11 and `spec_choice.py` remain gone** and are not coming back —
their goals are now served by advisory hook injections plus model
self-discipline guided by SKILL.md.

### Global bypass

`SPECODE_GUARD=off` short-circuits all hooks to `exit 0` with no
output and no state writes. Reserved for debugging.

### Compatibility

- **Plugin commands**: `/specode:spec`, `/specode:continue`,
  `/specode:end`, `/specode:status`, `/specode:task-swarm`
  (placeholder, v0.7).
- **State migration**: nothing automatic. Users coming from 0.4.x
  who still have `~/.specode/sessions/*.json` in the old schema
  should run `/specode:end` once (which will write the new schema
  with `mode=ended`) or remove the file. New schema is written
  starting from the next `SessionStart`.

## 0.5.0 (2026-05-18)

### Removed (breaking — please read)

This release strips the plugin back to a skeleton. Every runtime
enforcement and helper introduced from 0.1.0 through 0.4.0 has been
removed; what remains is the plugin shell and the agent role docs.

- **All hook handlers removed.** `plugins/specode/hooks/` (both
  `hooks.json` and the `hooks-probe.json` diagnostic) is deleted. The
  6 hook events (SessionStart / UserPromptSubmit / PreToolUse /
  PostToolUse / Stop / SessionEnd) no longer fire any plugin code.
- **All invariants removed.** INV-1 through INV-11 (CDSG hard-deny,
  CDSG advisory, eviction guard, acceptance follow-mode, status-block
  injection, phase gate, subagent_type prefix, subagent @writes
  boundary, tasks.md writeback, outbox schema, non-interactive Bash
  guard) no longer exist as code paths.
- **All scripts removed.** `plugins/specode/scripts/` is deleted —
  `spec_guard.py`, `spec_session.py`, `spec_init.py`, `spec_sync.py`,
  `spec_choice.py`, `spec_state.py`, `spec_status.py`, `spec_lint.py`,
  `spec_vault.py`, `spec_telemetry.py`, `task_swarm.py`,
  `task_swarm_*.py`, `bash_guard.py`, `run.sh`, `verify_local.sh`.
- **Tests removed.** `plugins/specode/tests/` is deleted in full.
- **Skill references removed.** `plugins/specode/skills/specode/references/`
  (workflow / commands / prompts / lock-protocol / templates / iteration /
  obsidian / help-output / task-swarm / task-swarm-example /
  sample-analysis) is deleted.
- **SKILL.md** rewritten as a short skeleton describing the spec-mode
  activation contract; the iron rules referencing INV / hooks /
  scripts are gone.
- **`/task-swarm` command** rewritten as a placeholder; the 7-step
  CLI-driven orchestrator protocol it used to host is removed.

### Kept

- `.claude-plugin/marketplace.json` + `plugins/specode/.claude-plugin/plugin.json`
- `plugins/specode/commands/` — entry stubs for `/spec`, `/continue`,
  `/end`, `/status`, `/task-swarm`
- `plugins/specode/skills/specode/SKILL.md` — skeleton
- `plugins/specode/agents/` — task-swarm planner / coder / reviewer /
  validator role docs (descriptive only; the orchestrator that
  dispatched them is gone)
- Top-level docs (`README.md` / `README.zh-CN.md` / `CHANGELOG.md` /
  `CONTRIBUTING.md` / `DEV.md` / `migrate-from-spec-mode.sh`) are
  retained and updated to reflect the new skeleton state.

### Migration

No automatic migration. Reinstall on top of the new version to drop
the hooks; user runtime state under `~/.specode/` and
`~/.config/specode/` is untouched and can be removed manually:

```sh
rm -rf ~/.specode ~/.config/specode
```

If you were relying on any 0.4.x behaviour (CDSG advisories, INV-11
non-interactive Bash guard, task-swarm orchestrator), pin to
`specode--v0.4.0` until the runtime is rebuilt.

## 0.4.0 (2026-05-18)

### Changed (behavior change — please read)

- **CDSG downgraded to advisory.** INV-1 / INV-2 / INV-4 / INV-6 no
  longer block the tool call when violated. Instead they record a
  sticky advisory on `.sync-ledger.json` (new field
  `pending_advisories`) and inject it into the next
  `UserPromptSubmit` status block. Rationale: the previous hard-deny
  caused legitimate work (e.g. P0 hot-fixes during task-swarm coder
  rounds) to be interrupted mid-stride while the model retried
  permutations to satisfy the rule. Advisory keeps the drift signal
  visible without breaking flow.
  - Auto-clear: editing any spec doc drops INV-1/2/4 advisories
    (the drift those warned about is being addressed).
  - Manual dismiss: `python3 scripts/spec_sync.py dismiss-advisories
    [--inv INV-1,INV-2]`
  - Visible in: ledger `pending_advisories[]`, status block in next
    turn, and `spec_sync.py status` output.
  - **Data-safety INVs unchanged**: INV-3 / INV-7 / INV-8 / INV-9
    remain hard-enforced (`exit 2`). They protect against actual data
    corruption (evicted writes, bad subagent dispatch, subagent
    boundary breach, tasks.md non-writeback edit).

### Added

- **INV-11 — Non-interactive Bash guard.** New `bash_guard.py` with two
  layers of defense against agent Bash hanging on TTY prompts:
  - **PreToolUse hard-deny** of 14 known interactive command patterns:
    `npm create` (no `--yes`), `npx` (no `--yes`), `npm init` (no `-y`),
    `yarn create`, `pnpm create`, `git rebase -i`, `git add -p/-i`,
    `git commit` (no `-m`/`-F`/`--amend --no-edit`), TUI editors/pagers
    (`vim`/`nano`/`less`/`top`/`man`/...), interactive shells (`bash -i`,
    `python -i`), bare REPLs (`python3` alone), `ssh` without
    `BatchMode`, `gh pr create` without `--title`/`--body`, `apt install`
    without `-y`. Each denial includes a ready-to-paste non-interactive
    rewrite.
  - **PostToolUse hang signature scan** of Bash stdout/stderr tail
    (4 KiB) for ~17 known prompt strings (`Ok to proceed?`, `[Y/n]`,
    `password:`, `确认吗`, etc.) plus exit code 124 (`timeout` kill).
    When detected, injects an `additionalContext` advisory into the
    next turn telling the model the previous command hung and not to
    retry the same form.
  - Hooks: `hooks.json` PreToolUse matcher extended from
    `Edit|Write|MultiEdit|Task` → `+Bash`; PostToolUse from
    `Edit|Write|MultiEdit` → `+Bash`. INV-11 works without an active
    spec session (Bash hangs are universal, not spec-bound).
  - 55 new unit tests in `tests/test_bash_guard.py` (positive +
    negative samples per rule, hang signature detection).

- **`/spec --dismiss-advisories` CLI** (`spec_sync.py dismiss-advisories`)
  — clears all sticky advisories or `--inv INV-1,INV-6` for a subset.

- **SKILL.md Iron Rule #9** — Non-interactive Bash discipline. Lists
  the safe forms (`npm create xxx -- --yes`, `git commit -m`, etc.)
  the model should default to before the hook ever has to deny.

### Migration

Users on 0.3.x upgrading to 0.4.0:

- Code paths that previously expected `exit 2` from INV-1/2/4/6 now
  see `exit 0` plus a sticky advisory. Re-tune any local automation
  that grepped `~/.specode/audit/*.log` for `deny-INV-1` —
  the new audit string is `advisory-INV-1`.
- `pending_advisories[]` field appears in `.sync-ledger.json` on first
  hook fire after upgrade. Older ledgers without the field continue
  to work (defaulted to `[]`).
- No spec session needs to be re-created.
- `freeform` mode meaning subtly shifted: previously "INV-1 bypass,
  INV-2 still enforced"; now "INV-1 silenced (no advisory recorded
  either); INV-2/4/6 still raise advisories." Effectively quieter.

## 0.3.2 (2026-05-18)

### Fixed

- **`spec_choice.py` hang under CodeBuddy Bash** — observed a single
  Stop-gate selector running for 1h16m, with multiple zombie selectors
  accumulating per spec session (one per phase gate). Root cause: TTY-only
  `input()` / curses paths blocked indefinitely when stdin was a pipe
  without EOF (CodeBuddy harness behavior). Both paths are now deleted —
  the script always emits options + `AWAITING_USER_CHOICE` sentinel and
  exits 0. Physically cannot block on stdin. `--no-curses` flag kept as
  a no-op for back-compat.

### Added

- **CI static guard against blocking stdin reads** — new
  `tests/test_no_blocking_io.py` tokenizes every runtime script under
  `scripts/` and fails on any `input()` / `raw_input()` /
  `sys.stdin.read*` / `getpass.getpass(` not explicitly whitelisted
  with a `# stdin-block: <reason>` comment marker. Prevents future
  regressions of the hang class.
- **`tests/test_spec_choice.py`** — 9 subprocess-driven tests with
  `timeout=3s` so a hang is a regression.
- **SKILL.md Iron Rule #8 — selector via `spec_choice.py` only.**
  Every phase-gate selector MUST be produced by running the exact
  `spec_choice.py` command from `references/prompts.md` and relaying
  its stdout verbatim. Hand-rolling silently drops newer options the
  script knows about (real observed regression: 任务执行 selector
  rendered as 3 options because the model wrote them from memory,
  dropping `用 task-swarm 多 agent 并发`).
- **SKILL.md Document Output Brevity rule** — when writing or updating
  a spec doc, do not reprint the full content in chat. Report only:
  file path, 3-8 section bullets, open questions, next action.

### Notes

- `scripts/spec_guard.py` legitimately reads stdin (hook payload from
  the host CLI, bounded JSON + immediate close) — annotated
  with `# stdin-block: hook entry point` to satisfy the new scanner.

## 0.3.1 (2026-05-18)

### Added

- **Local-only telemetry** (`~/.specode/telemetry.jsonl`): opt-in via
  `SPECODE_TELEMETRY=on`, append-only single file so `grep` / `jq` stay
  trivial. **Absolutely no remote upload** — purely for the user's own
  inspection of flow execution.
  - Events: `spec.init` / `spec.phase_transition` / `spec.end` /
    `inv.violation` (INV-1..9, with `spec_slug` + `phase`) /
    `swarm.run_start` / `swarm.stage_round` / `swarm.stage_done` /
    `swarm.writeback` / `swarm.run_end`.
  - Records carry `spec_slug` / `cwd` / `run_id` so you can aggregate per
    spec or per project.
  - Size cap defaults to 50 MB (overridable via
    `SPECODE_TELEMETRY_MAX_BYTES`); rotates to `telemetry.jsonl.0` once.
  - All IO errors are swallowed — telemetry never breaks a hook.
- `python3 scripts/spec_state.py telemetry-summary [--days N] [--json]`
  aggregates the telemetry file locally: counts per event, INV violations
  top-list, per-spec phase-transition / violation totals, and task-swarm
  average rounds per converged/failed stage.

### Fixed

- **task-swarm fork description now carries scope** (`[validator-fail-fix]`
  / `[advisory]` / `[re-run]`). Previously a checkpoint stage's r2 coder
  was labelled `阶段 N coder-r2: <title>` with no scope, and the
  orchestrator commonly improvised a description like "修复 N 个 P0" off
  the validator outbox — reading as if the reviewer had triggered a fix
  loop (reviewer is advisory and never does). With scope baked in, the
  Task UI now reads e.g. `阶段 5 coder-r2 [validator-fail-fix]: ...` and
  `commands/task-swarm.md` explicitly tells the orchestrator to copy
  `<json.description>` verbatim.
- **validator agent now forbidden from using P0/P1 severity labels** in
  fix guidance (`agents/task-swarm-validator.md`). Those tags are
  reviewer terminology; validator fail is itself blocking. This prevents
  the orchestrator from observing "(P0)" markers in validator output and
  carrying them into the fork description.

## 0.3.0 (2026-05-18)

### Added

- **Task-Swarm control inversion (CLI-driven orchestrator)**: the main model
  no longer drives the state machine in long context — it now follows a tiny
  `init → loop(next → fork → parse → advance) → writeback → done` protocol
  while all determinism (round counting, convergence, dead-loop detection,
  outbox parsing, tasks.md write-back) lives in Python scripts.
  - New CLI: `scripts/task_swarm.py` with 7 sub-commands
    (`init` / `next` / `parse` / `advance` / `writeback` / `status` / `resolve`).
  - New modules: `task_swarm_state.py` (state machine + round tracking),
    `task_swarm_parse_md.py` (stage-aggregated dispatch from tasks.md),
    `task_swarm_outbox.py` (schema-checked result/review/validation parsing),
    `task_swarm_prompt.py` (pre-rendered subagent prompts), and
    `task_swarm_writeback.py` (line-safe tasks.md edits — checkbox toggle +
    `> ` notes only).
  - Per-run workspace under `.task-swarm/runs/<run_id>/` with predictable
    `agents/stage-N-{role}[-rN]/` layout — easy to inspect, replay, or clean.
- **INV-7 / INV-8 / INV-9 / INV-10** hooks (task-swarm period only):
  - **INV-7** — `Task` calls must use `subagent_type` prefixed with
    `specode:task-swarm-`; otherwise the hook denies (prevents accidental
    fall-back to `general-purpose`, which would bypass tool-whitelist
    isolation).
  - **INV-8** — subagents may only write files declared in their `@writes`
    block (or under their own `outbox/`); any out-of-bound write is denied.
  - **INV-9** — during a task-swarm run, edits to `tasks.md` must go through
    the `writeback` sub-command; direct `Edit`/`Write` is diffed and rejected
    unless the change is purely checkbox toggles + `> ` annotations.
  - **INV-10** — subagent outbox files must pass a schema check (required
    sections, `STATUS:` line, judgment field); `parse` surfaces a
    `schema-error` which the orchestrator handles by retrying instead of
    advancing on garbage.
  - Hook implementation: `scripts/task_swarm_guard.py` + extensions in
    `scripts/spec_guard.py`. Matcher now also covers the `Task` tool.
- **Independent reviewer / validator rounds**: `--reviewer-rounds N` (default
  **1**) and `--validator-rounds N` (default **3**). Rationale —
  reviewer is an LLM reading code (subjective, prone to corrective spirals);
  validator runs commands (objective failure signal, deserves more retries).
  `--max-rounds N` remains as a fallback default for both.
- **Reviewer P0 evidence tags**: every P0 finding must carry one of
  `[req:x.y]` / `[security]` / `[contract]`. Untagged P0s are auto-downgraded
  to `advisory_p0` (logged for audit, but do not count toward `p0_count` and
  do not trigger a coder fix round). If every P0 in a review is untagged, the
  judgment flips from `p0` to `approved` and the stage converges directly.
  This stops cheap-prose reviewers from forcing infinite fix loops.
- Help-output (`/spec -h`) now surfaces `--freeform` and `--strict`.

### Changed

- Reviewer "exit fix loop" behavior is now **advisory**, not hard-block.
  When a reviewer round reports the same P0s as the previous round, the
  orchestrator records the loop signal and stops the stage with a
  `failed` mark via the same loop-detection path as validator, instead
  of a separate hard-stop branch. Keeps loop handling symmetric across
  roles.
- `references/task-swarm.md` rewritten as a **design spec** (why the
  state machine exists, how iron rules are upheld) — the runtime model
  reads `commands/task-swarm.md` for the actual 7-step protocol.
- `agents/task-swarm-reviewer.md` updated to require P0 evidence tags
  and the loop-detection self-report convention.
- `agents/task-swarm-coder.md` clarified the fix-round contract (only
  touch P0-listed locations or validator-fail repair guidance; no scope
  creep).

### Fixed

- Long-context drift on round counting: the main model no longer
  computes round numbers or convergence in prompt — all of that lives
  in `task_swarm_state.py` and is checked by tests.
- Outbox format drift: `task_swarm_outbox.py` validates against a
  schema instead of relying on the main model to "eyeball" review.md /
  validation.md.

### Tests

- 6 new test files (`test_task_swarm_cli.py`, `test_task_swarm_guard.py`,
  `test_task_swarm_hook_integration.py`, `test_task_swarm_outbox.py`,
  `test_task_swarm_parse_md.py`, `test_task_swarm_prompt.py`,
  `test_task_swarm_state.py`). Total suite now **135 tests**.

### Migration

No user action required — `/task-swarm`, `/spec`, `/continue`, `/status`,
`/end` slash commands are unchanged; subagent names are unchanged;
`~/.specode/` state schema is unchanged. The orchestrator protocol is
**internal** to the plugin: the main model loads it from
`commands/task-swarm.md` automatically on plugin update.

If you had pinned `0.2.0`, the only behavior change on bumping to
`0.3.0` is that reviewer P0s without `[req:x.y]` / `[security]` /
`[contract]` evidence tags will no longer trigger coder fix rounds —
they become advisory. Audit logs continue to record them.

## 0.2.0 (2026-05-17)

### Renamed (breaking-ish — see Migration)

- Plugin renamed: **`spec-mode` → `specode`**. All identifiers follow:
  - plugin / skill name (manifests, frontmatter, namespace `specode:*`)
  - directory tree (`plugins/specode/`, `skills/specode/`)
  - env vars (`SPEC_MODE_ROOT` → `SPECODE_ROOT`, `SPEC_MODE_GUARD` → `SPECODE_GUARD`)
  - runtime state (`~/.spec-mode/` → `~/.specode/`,
    `~/.config/spec-mode/` → `~/.config/specode/`)
  - vault index file (`.active-spec-mode.json` → `.active-specode.json`)
- The slash command `/spec` itself is unchanged (it was never `/spec-mode`).

### Added

- **Task-Swarm Mode**: a third option in the "任务执行" selector that delegates
  task execution to specialized subagents shipped with the plugin
  (`specode:task-swarm-coder`, `-reviewer`, `-validator`, `-planner`).
- Reviewer and validator subagents are spawned with **no Edit/Write tools** —
  enforces anti-self-approval at the tool layer (not just prompt-level).
- Stage-aggregated dispatch: one coder per top-level tasks.md stage (covering
  all its leaf subtasks), one reviewer per stage, validator reuses the
  built-in "检查点" tasks. Cuts subagent count from naive `N×3` to roughly
  `N` for a spec with `N` stages.
- **Convergence loop per stage**: each stage runs `coder → reviewer → validator`
  in a loop. Reviewer must classify findings as P0 (blocking) / P1 / P2; any
  P0 triggers a focused coder fix round + re-review. Validator fail triggers
  another coder fix round + mandatory re-review + re-validate. Default
  `--max-rounds 3` per loop; reviewer/validator self-report "same finding as
  previous round" to short-circuit infinite loops. tasks.md `[x]` is only
  written when both loops converge cleanly; intermediate rounds only append
  `> 第 N 轮…` progress notes under the affected subtask.
- New command `/task-swarm <spec-dir>/tasks.md` for manual triggering of
  task-swarm mode outside the standard selector flow.
- New plugin subdirectory `agents/` carrying the 4 task-swarm subagents.
  The host CLI auto-registers these (namespaced as `specode:task-swarm-*`).
- New references:
  - `references/task-swarm.md` — full protocol (single authority for editing
    behavior, subagent contract, write-back rules, loop semantics, iron-rule
    interaction)
  - `references/task-swarm-example.md` — sample tasks.md showing stage
    layout, `@swarm:*` labels, and expected subagent count
- New `migrate-from-spec-mode.sh` — one-shot migration script for users
  upgrading from 0.1.0; handles state dirs, vault index file rename,
  stale plugin install detection, and `SPEC_MODE_*` env var detection.
  Supports `--dry-run`.
- README: new `Uninstall` section (en + zh) covering plugin uninstall,
  marketplace removal, optional state cleanup, cache GC behavior, and
  temporary disable/enable.
- CONTRIBUTING: new `Release` section documenting semver bump rules
  (with examples), pre-release checklist, cutting a release, re-tagging
  caveats, and post-release verification.

### Changed

- `references/prompts.md` task execution selector now lists 4 options
  (added `用 task-swarm 多 agent 并发` before `暂不 coding`).
- `references/workflow.md` §7.1 documents the task-swarm delegation flow
  and how it co-exists with lock / INV-4 / phase-gate iron rules.
- `references/help-output.md` now lists `/task-swarm` in the cheat sheet.
- `SKILL.md` References section links the two new task-swarm docs.
- README (en + zh): new Task-Swarm Mode section.

### Fixed

- **P0 — subagent_type must be plugin-prefixed**: dispatching with the
  bare name `Task(subagent_type="task-swarm-coder", ...)` is rejected by
  the host CLI with `"Agent type not found"`. All 13 references in
  `commands/task-swarm.md` and `references/task-swarm.md` now use the
  fully-qualified `specode:task-swarm-coder` (and `-reviewer` /
  `-validator` / `-planner`). The `agents/*.md` frontmatter `name` is
  intentionally left as the bare form — the plugin loader applies the
  namespace automatically. Without this fix, task-swarm mode would have
  failed on the first Task dispatch.
- Doc improvements (from LLM-perspective review of `task-swarm.md`):
  - role mapping table gains a `职责` column documenting what each role
    actually does, plus a note that `planner` is rarely needed in the
    specode + task-swarm flow (specode tasks phase already does splitting)
  - 5-tier precedence rules for `@swarm:*` subtask labels (`skip` always
    wins > `full` > `coder-only` > heuristic); conflicts → INFO log;
    unknown tag → WARN log
  - typed pseudocode signatures in the 4e/4f convergence loops:
    `@dataclass ReviewResult` / `ValidationResult`, typed `fork_reviewer`
    / `fork_coder_fix_round` / `fork_validator` / `fork_reviewer_quick_check`

### Migration

Users upgrading from 0.1.0:

```sh
./migrate-from-spec-mode.sh --dry-run    # preview
./migrate-from-spec-mode.sh              # apply
claude plugin marketplace remove spec-mode
claude plugin marketplace add https://github.com/qxbyte/specode
claude plugin install specode@specode
```

If you had `SPEC_MODE_ROOT` / `SPEC_MODE_GUARD` exported in your shell rc,
rename them to `SPECODE_ROOT` / `SPECODE_GUARD`. The migration script
detects and prints reminders for these.

## 0.1.0 (2026-05-15)

### Phase 1 — bootstrap

- Initial plugin skeleton.
- `plugin.json` consumed by the host CLI's plugin loader.
- `hooks/hooks.json` wiring SessionStart / UserPromptSubmit / PreToolUse /
  PostToolUse / Stop / SessionEnd → `scripts/spec_guard.py`.
- `scripts/spec_guard.py`: dispatch entry, audit-log every event, all
  handlers return ok. Supports `SPECODE_GUARD=off` global bypass.

### Phase 2 — state layer + injection + short-circuit

- `scripts/spec_state.py`: read-only probe against existing
  `.active-specode.json` / per-spec `.config.json`. Owns
  `~/.specode/{sessions,.any-active}`. CLI: status / sync-sentinel /
  demo-activate / demo-deactivate.
- `spec_guard.py`: SessionStart writes the host-session record;
  UserPromptSubmit injects a status block via
  `hookSpecificOutput.additionalContext` when a spec is active; other
  handlers fast-exit when no active spec.
- `hooks/hooks.json`: shell short-circuit on `$HOME/.specode/.any-active`
  for the non-session hooks so Python doesn't even start when idle.

### Phase 3 — Code-Doc Sync Guard (CDSG)

- `scripts/spec_sync.py`: tasks_files extraction (FILE: lines + Affected
  Files section + glob), path classification (spec-doc / project-code /
  outside), `.sync-ledger.json` + per-turn ledger, legality checks. CLI:
  status / freeform / extract.
- `spec_guard.py`:
  - `UserPromptSubmit` refreshes turn_id, re-extracts tasks_files, mirrors
    freeformMode into ledger, extends the injected status block (mode /
    turn / tasks_files count).
  - `PreToolUse` enforces INV-1 (Code-Doc Sync) on project-code edits.
  - `PostToolUse` appends changes to ledger turn_code/doc_changes.
  - `Stop` enforces INV-2 (turn conservation) and INV-4 (acceptance-
    checklist follow-mode). Resets turn on pass.
- `SKILL.md`: three new dispatch entries for `--freeform` / `--strict` /
  `--sync-status`.

Hard-decision compliance (design doc §13):
- 1A: freeform does NOT exempt INV-2.
- 2A: `implementation-log.md` counts as a doc change for INV-2.

### Phase 4 — INV-3 + INV-6

- `spec_sync.py`: `check_verify_lock` (delegates to `spec_session._verify`;
  denies on `evicted`, allows on `ok`/`not_held`/`stale_lock` for backward
  compat); `check_phase_gate` against `PHASES_FORBID_CODE = {intake,
  requirements, bugfix, design, tasks}`.
- `spec_guard.py` `PreToolUse`:
  - spec-doc edits → INV-3 verify-lock first.
  - project-code edits → INV-6 phase gate (absolute; freeform does NOT
    exempt), then INV-1.
  - outside edits → pass through.

### Phase 5 — CodeBuddy static adapter

- `hooks/hooks.json`: env var fallback to
  `${CLAUDE_PLUGIN_ROOT:-${CODEBUDDY_PLUGIN_ROOT}}`.
- `adapters/codebuddy/README.md`: open items + suggested wrapper script if
  CodeBuddy doesn't honor `${VAR:-fallback}` expansion inside hook command
  strings.

### Phase 6 — tests + docs + stub

- `tests/` with 19 pytest cases (unit + integration). Covers all six
  invariants, freeform behavior, glob matching, lock states, phase gate
  matrix.
- `README.md` rewritten as full reference (rules, architecture, install,
  usage, performance, bypass, CodeBuddy note, tests).
- `CONTRIBUTING.md`: stdlib-only runtime rule, test conventions.
