# Changelog — task-swarm

task-swarm 是从 specode 拆出的独立多 agent 编排 plugin。本文件记录其自身版本；specode 的变更见仓库根 `CHANGELOG.md`。

## Unreleased

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
