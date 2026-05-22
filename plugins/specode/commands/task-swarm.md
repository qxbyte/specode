---
description: 多 agent 并发执行 tasks.md（state.json 单一事实源；主代理按 plan→fork→advance 循环驱动）
argument-hint: "[<spec-dir>/tasks.md] [--max-parallel N] [--max-rounds N]"
---

/specode:task-swarm $ARGUMENTS

## ⛔ 强制前置阅读（不可跳过）

本文件**只列**入口路由 + 关键禁止项。所有实操细节都在 `references/task-swarm.md`：

- §1 角色 / 并发度
- §2 文件冲突 / group 切分（`@writes` 不相交 + `@depends-on` 拓扑）
- §3 Phase 状态机（reviewer / p0-fix / validator / v-fix 转换规则）
- §4 子代理产物 schema（coder `result.md` / reviewer `review.md` / validator `validation.md`）
- §5 tasks.md writeback 格式（line-safe diff / 修复状态标签）
- §6 `on-task-completed` hook 提醒矩阵
- §7 信息流总览
- §8 死循环保护（连续 3 轮同 fail 签名 → `failed-deadloop`）
- §9 CLI 接口速查

**在调任何 `task_swarm.py` 子命令之前**（包括 init / plan / advance / writeback / resolve），
必须先 Read `references/task-swarm.md` 至少扫一遍 TOC + §3 + §9。本文件下面的 3 步路由
**只够回答"现在该调哪条 CLI"**，不够回答"plan 输出怎么解析 / advance 失败时该 retry
还是 fork / writeback 越界怎么办"——这些细节都在 references 里。**禁止凭印象推**。

如果对任何一步流程仍不确定，**先 Read references 对应章节再动手**，不要边猜边跑。

---

按以下 3 步路由。**禁止**主代理直接 `task_swarm.py init`、**禁止**根据用户裸输入 invent `<spec_dir>`。task-swarm 是 tasks phase + `tasks-execution` selector 选中 task-swarm 路径后的下游编排，不是用户裸触发的入口（详见 SKILL.md §Task-Swarm + `references/task-swarm.md`）。

## 第一步：前置校验（必做）

调 `spec_session.py read-session --session <id>` 拿当前 session 状态：

```sh
sh "${CLAUDE_PLUGIN_ROOT:-${CODEBUDDY_PLUGIN_ROOT}}/scripts/run.sh" \
   "${CLAUDE_PLUGIN_ROOT:-${CODEBUDDY_PLUGIN_ROOT}}/scripts/spec_session.py" \
   read-session --session <id>
```

必须全部满足：

- `mode == "active"`（不是 idle / ended / readonly）
- `active_spec_dir` 非空（init 的 `--tasks` 必须用此值 + `/tasks.md`，**禁止 invent**）
- `phase == "tasks"`
- `pending_selector == "tasks-execution"` 且用户已选 task-swarm 路径

任一不满足 → **不要** init，在 chat 引导用户先到 tasks phase 跑 `tasks-execution` selector 选 task-swarm 路径，end turn。

详见 SKILL.md §「Task-Swarm / `/specode:task-swarm` 前置校验」。

## 第二步：init

校验通过后用 step 1 拿到的 `active_spec_dir`：

```sh
sh "${CLAUDE_PLUGIN_ROOT:-${CODEBUDDY_PLUGIN_ROOT}}/scripts/run.sh" \
   "${CLAUDE_PLUGIN_ROOT:-${CODEBUDDY_PLUGIN_ROOT}}/scripts/task_swarm.py" \
   init --tasks "<active_spec_dir>/tasks.md" --session <id>
```

- `--tasks` 是 **tasks.md 的绝对路径**（不是 spec 目录），用 step 1 的 `active_spec_dir + /tasks.md`
- init 报 `tasks.md 中未解析出任何 ## 阶段 N: 段` → 格式不对，**回到 `tasks-execution` 选「需要调整 tasks.md」**让主代理按 SKILL.md §「Spec 文档生成」重写
- 拿到 `{run_id, run_dir, groups}` 后转第三步

## 第三步：7 步循环（plan → fork → advance → writeback → resolve）

按下面 7 步循环驱动，**所有** `task_swarm.py` 子命令套同一 run.sh 包装模板：

1. `init`（第二步已做）
2. `plan --run <run_id>` 拿下次 fork 列表
3. `fork`：同 message 发 N 个 Task block（按 `plan.fork` 逐字拷贝，**不要**凭印象自创 agent_key——
   `coder-fix-xxx` / `coder-session-fix` 等自定义命名**全部禁止**，必须用 plan 给的 `coder-vfix-g{N}-r{R}-f{I}` 等规范名）
4. **等齐 subagent 返回（advance 前置强约束，违反必出乱）**：
   - **必须**先在主代理 UI 看 "Waiting for N teammates" 区域，**所有** fork 出去的 Task 都 ✓ completed 才能进 step 5；
     **任何 ⠙ streaming / ⠴ running Bash 的就不能 advance**。
   - **不要**凭口头报告判定完成——包括 team-lead / 其他平台 agent 说"已修复 STATUS"/"已完成"。
     **只有** subagent 自己的 Task tool 返回 ✓ completed 才算数。
   - PostToolUse hook 注入的"plan 提醒"**不是**"立即 advance"指令——它只是告知"这个 Task 完成了"，
     advance 仍要等齐**所有** in-flight Task。
   - 不确定时调 `task_swarm.py plan --run <run_id>`，若返回 `action: coding-waiting` / `p0-fix-waiting` /
     `v-fix-waiting` / `v-fix-waiting`，**禁止** advance，回到等待。

   **常见误判**：
   - "team-lead 说改完了" ≠ subagent 真完成（team-lead 修补可能是直接 Edit outbox，绕过 subagent 工作）
   - "f0 跑了 30 个 tool 看起来快完了" ≠ completed（最后写盘可能还没刷）
   - "其他 4 个都 ✓ 了最后 1 个估计也快" ≠ 可以提前——advance 之后没回头路
5. `advance --run <run_id> --phase <p> --round <n>` 推进 state
6. `writeback --run <run_id> --group <N>`（validator pass 后回写 tasks.md，line-safe diff，越界 exit 1）
7. `resolve --run <run_id>`（所有 group 完成 → 回到 spec-mode acceptance phase）

完整规格全部在 `references/task-swarm.md`，本文件不再重复展开：

- §1 角色 / 并发度（reviewer / validator 单实例，coder N 并发）
- §2 文件冲突 / group 切分（`@writes` 不相交 + `@depends-on` 拓扑）
- §3 Phase 状态机（reviewer advisory 只触发一次 p0-fix；validator 阻塞循环 fix→validator 直到 pass）
- §4 子代理产物 schema（coder `result.md` / reviewer `review.md` / validator `validation.md`）
- §5 tasks.md 写回格式（含修复状态标签）
- §6 `on-task-completed` hook 提醒矩阵
- §7 信息流总览
- §8 死循环保护（连续 3 轮同 fail 签名 → `failed-deadloop`，停循环报告用户）
- §9 CLI 接口速查（含所有子命令完整调用样例）

## heartbeat（长流程必做）

主代理每 5 分钟 / 每完成一个 subagent 后调用（保证 spec 锁不被 stale 回收）：

```sh
task_swarm.py heartbeat --run <run_id>
spec_session.py heartbeat --spec <dir> --session <id>
```

## advance 报 "result.md 缺 STATUS / 解析失败" 的正确应对

这是 0.10.13 (user-login) / 0.10.17 (login-page) 两次事故的根源——必须按这套走，不要自创修补。

### 错误做法（已知反模式）

- ❌ team-lead / 主代理 / 任何外部 agent **直接 Edit `agents/<key>/outbox/result.md`** 把 STATUS 补上
- ❌ 主代理基于"已修复 STATUS"口头报告**直接 advance**
- ❌ 凭印象判定"subagent 应该已经把代码改了，只是 result.md 格式不对"
- ❌ 给同一个 P0 fork 一个**新名字的 agent**（如 `coder-fix-session-validation`）绕开命名规则——
  task_swarm 永远等不到这个 agent 的 result（不在 `in_flight` 列表），且会跟原 `coder-p0fix-g{N}-r{R}-f{I}` 并发改同一文件

**为什么错**：STATUS 缺失多半意味着 **subagent 提前退出 / 工作未完成**——代码改动可能根本没刷到磁盘。
手补 STATUS 后 advance 通过，下游 reviewer/validator 拿到的是**半成品代码**，必然 fail，进入 v-fix 循环，
浪费资源 + 污染状态机 + 多 agent 并发改同文件互相覆盖。

### 正确做法

1. **保留**残缺的 `result.md`（作为证据，不要 Edit 它）
2. 调 `task_swarm.py status --run <run_id>` 查看 `coder_in_flight` / `p0_in_flight` / `vfix_in_flight`，
   确认该 agent 是不是还在 in_flight
3. **如果 in_flight**（subagent 还在跑）：
   - 等 subagent 真完成（看 teammates UI ✓ completed）
   - 一直 ⠙ streaming 不收尾（>10 分钟）→ esc 取消那个 Task + 报用户决定 abort 还是重 fork
4. **如果不在 in_flight 但 result.md 残缺**（subagent 已退出但产物不合规）：
   - **重新 fork 该 agent**（用**同一个** agent_key，比如还叫 `coder-p0fix-g1-r1-f0`）
   - fork 前先 `rm -rf agents/<key>/outbox/*` 确保干净重跑（不要让旧残物干扰）
   - **禁止**起新名字（`coder-fix-xxx` 不在 state 的 in_flight 里，task_swarm 永远等不到）
5. 重 fork 都不行（subagent 反复无法产出合规 result.md）→ 报告用户 + 准备 abort run

**永远不要**：让 team-lead 或主代理代笔补 STATUS。绕过 subagent 工作的"修补"是把状态机推向更深的失序。

## 异常出口

- coder STATUS=`failed`/`blocked`、writeback 越界、`failed-deadloop` → 停循环、向用户报告并等用户介入，**不要**自动 retry。详见 `references/task-swarm.md` §3 / §8。
