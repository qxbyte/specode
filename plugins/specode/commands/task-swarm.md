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
3. `fork`：同 message 发 N 个 Task block（按 `plan.fork` 逐字拷贝，**不要**凭印象自创 agent_key）
4. 等齐 subagent 返回（PostToolUse hook 注入提醒，可读可忽略）
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

## 异常出口

- coder STATUS=`failed`/`blocked`、writeback 越界、`failed-deadloop` → 停循环、向用户报告并等用户介入，**不要**自动 retry。详见 `references/task-swarm.md` §3 / §8。
