# Changelog — task-swarm

task-swarm 是从 specode 拆出的独立多 agent 编排 plugin。本文件记录其自身版本；specode 的变更见仓库根 `CHANGELOG.md`。

## Unreleased

## 0.4.0 (2026-06-19)

### Changed (BREAKING) — 命令叶子改名 `task-swarm` → `swarm`（→ 0.4.0）

原命令文件 `commands/task-swarm.md` 调用形态是 `/task-swarm:task-swarm`（插件名与命令名重复）。改命令文件名为 `commands/swarm.md`,调用形态变为 `/task-swarm:swarm`(菜单显示 `/swarm (task-swarm)`)。命名空间前缀 `task-swarm:` 来自插件名,去不掉,但去掉了重复。

- `commands/task-swarm.md` → `commands/swarm.md`(`git mv`,内容不变)。
- 同步更新引用:`skills/task-swarm/SKILL.md`(`/task-swarm:swarm` 触发提示 + `commands/swarm.md` 模板路径)、`references/task-swarm.md`(协议归属命令 + deadloop 重跑指引)、`scripts/task_swarm.py`(API surface 注释)、`tests/test_standalone_smoke.py`(读 `commands/swarm.md`)。
- **迁移**:旧 `/task-swarm:task-swarm` 不再存在;改用 `/task-swarm:swarm`。
- 注:`references/task-swarm.md` 等**文件名**不变(那是协议文档,与命令叶子名无关)。

### Fixed — `run.sh` 包装路径在 `$CLAUDE_PLUGIN_ROOT` 为空时 127

与 specode 同源 bug:`$CLAUDE_PLUGIN_ROOT` 只对 hook/MCP 子进程导出,skill 发出的 Bash 调用里为空,旧写法 `${CLAUDE_PLUGIN_ROOT:-${CODEBUDDY_PLUGIN_ROOT}}` 展开成 `/scripts/run.sh` → `Exit 127`(执行记录里靠硬编码 `TS_ROOT=.../task-swarm/0.3.1` 绕过)。

- `commands/swarm.md`(init + heartbeat 模板 + 7 步循环说明)改为带兜底的 resolver:env var 命中则用,否则 `find` 出 cache 里最新版本(`sort -V | tail -1`),**不写死版本号**;用 `find` 而非 shell glob(zsh 下不匹配的 glob 会中止)。task-swarm 无 hooks,故无需保留裸 env-var 形态。

## 0.3.1 (2026-06-18)

> 死代码清理 + 去重，**无行为变更**（纯瘦身，net -600 余行非测试代码）。

- 删 `_writeback.py`（`writeback_tasks_md` 等自 M3 起已是死代码：只剩 `cli.py` 死 import + 单元测试，主路径不调用）及其测试 `test_task_swarm_writeback.py`（9 例）。
- 删 `spec_log.py`（会话日志收集，仅 CLI 入口/出口各调一次且有 fallback；与 specode 1.0.1 删同款一致）；移除 `cli.py` 仅为日志而存在的 `_log_wrap_main` 包装。
- 去重：`_now_iso` / `_atomic_write_text` 此前各定义 3 处，统一到 `_state.py` 由其它模块 import；`_outbox.py` 中英文冒号解析提取 `_after_colon` helper。
- CLI 命令集 / pipeline.yml schema / state.json 结构 **均无变化**。

## 0.3.0 (2026-06-15)

首发版本。task-swarm 自 specode 拆出（specode 0.11.0），独立可运行的多 agent 编排器：pipeline.yml 声明式编排 + 语义任务组跨组并发 + per-组 reviewer/validator 循环。

### Added -- 独立 plugin + 解耦（M1）

- 从 specode 摘出 state machine / outbox / prompt / writeback / cli 等，自带 `task_swarm.py` launcher + `run.sh`/`run.cmd` 包装。
- 状态根 `<workdir>/.task-swarm/runs/<run_id>/`，不依赖任何 specode session / 锁。
- stdlib-only（运行时无第三方依赖）。

### Added -- YAML 声明式编排 + 独立 SKILL（M2）

- **pipeline.yml** 成为唯一编排输入（受限 YAML 子集，自写 stdlib parser + schema 校验）。
- 自带 `SKILL.md`：主代理 = orchestrator + planner，读需求/design → 生成 pipeline.yml → 驱动 swarm。零 specode 依赖。
- `init → plan → fork → advance → writeback → report` 完整流程；`report` 从 state.json 按需渲染。
- 移除 markdown 路径耦合，收敛 yml 单轨（0.3.0 起 `--tasks` 已删）。

### Added -- 语义组下沉 + 跨组并发（M3）

- reviewer/validator 从「文件冲突批次」下沉到「语义任务组」（pipeline.yml 的 `task_group`），每组一个独立子状态机。
- **调度层**（`_schedule`，纯函数）：`needs` 拓扑 + `writes` 不相交 → 跨组并发；`plan` 返回多组 `schedule` + `actions`，主代理同 message fork 多组 coder（总并发受 `max_parallel`）。
- `advance --group <gid>` / `writeback --group <gid>` per-group 推进；agent_key 绑 gid（`coder-{gid}-s{n}` / `reviewer-{gid}` / `validator-{gid}`）。
- validator 默认跨组并发 + `--serial-validation` 逃生口（测试有共享资源时全局串行）。

### Added -- specode 委托模式接口（M4）

- `init` 接可选 `--spec-id` / `--spec-dir` 作回溯标注（被 specode 委托时用）；行为/state 不变，不反向依赖 specode。
- 被 specode 的 `delegated` 阶段委托时，resolve 后由调用方主代理（按 specode SKILL）决定下一步。

### 设计要点

- **state.json 单一事实源**；report 是其纯函数视图。
- **死循环保护**：validator 连续 3 轮同 fail 签名 → `failed-deadloop`。
- **C 模型**：主代理驱动 plan→fork→advance 循环，CLI 只守机械完整性（schema / agent_key / advance 产物 / 原子写禁手改），不压主代理思考。
