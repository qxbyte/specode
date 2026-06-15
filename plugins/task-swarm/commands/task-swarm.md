---
description: 独立运行 task-swarm 多 agent 编排:把需求/pipeline.yml 拆成任务组、fork coder、按组跑 reviewer+validator 循环(state.json 单一事实源)
argument-hint: "[<需求文档.md | pipeline.yml>] [--max-parallel N] [--max-rounds N]"
---

## ⛔ 强制前置阅读(不可跳过)

动手前先 Read **本插件自己的** `skills/task-swarm/SKILL.md`(独立运行人格 + 7 步流程 + 兼 planner 指引)。
实操细节在 references:
- pipeline.yml 编排格式 → `references/pipeline-yaml.md`
- 角色 / 状态机 / 产物 schema / 死循环保护 / CLI 速查 → `references/task-swarm.md`(至少扫 TOC + §3 + §9)

**禁止凭印象推** plan 输出怎么解析 / advance 失败怎么办 / writeback 越界怎么办——都在 references。

## 入口路由(standalone)

参数 `$ARGUMENTS` 的第一个位置参数决定走哪条:

- **是 `pipeline.yml`(或 schema 校验能过的 yml)** → power-user 已手写编排 → 跳过 planner,直接第二步 init。
- **是需求文档**(design.md / requirements / superpowers plan / 裸 .md)→ 先做**主代理兼 planner**:
  按 SKILL.md §2 读需求 → 生成 `pipeline.yml`(需查代码库时 fork `Explore` 子 agent,你综合)→
  写到 `<项目根>/.task-swarm/pipeline.yml` → 再第二步 init。
- **无参数 / 模糊** → 在 chat 问用户要需求文档或 pipeline.yml 路径,不要 invent。

> task-swarm 独立运行:无 session / 锁概念,用户可直接触发。state 落盘 `<workdir>/.task-swarm/runs/`。

## 第二步:init

```sh
sh "${CLAUDE_PLUGIN_ROOT:-${CODEBUDDY_PLUGIN_ROOT}}/scripts/run.sh" \
   "${CLAUDE_PLUGIN_ROOT:-${CODEBUDDY_PLUGIN_ROOT}}/scripts/task_swarm.py" \
   init --pipeline "<pipeline.yml 绝对路径>" --workdir "<项目根>" \
   [--project-root "<代码根>"] [--spec-id <id>] [--skip-validator] [--serial-validation]
```

- `--pipeline`:pipeline.yml 绝对路径,**唯一输入**(语义任务组 + 组间 `needs` 依赖 + 组内 task `writes`)。
- `--workdir`:state 落盘根(state 根 = `<workdir>/.task-swarm/runs/`)。缺省 = 当前 cwd;独立模式用项目根。
- `--project-root`(可选):被改代码的根目录(缺省 = `--workdir`)。
- `--skip-validator`:人工验收模式——review/p0-fix 完成后跳过 validation/v-fix 直接 writeback。
- `--serial-validation`:跨组并发时让 **validator 全局串行**(同一时刻只跑一个组的 validation/v-fix)。测试有共享资源/端口冲突时加。
- init 报"未解析出任何任务组" → pipeline.yml 格式不对,按 `references/pipeline-yaml.md` 修正后重试。
- 拿到 `{run_id, run_dir, groups, skip_validator}` 后转第三步。

## 第三步:7 步循环(plan → fork → 等齐 → advance → writeback → resolve → report)

所有 `task_swarm.py` 子命令套同一 run.sh 包装模板:

1. `init`(第二步已做)
2. `plan --run <run_id>` 拿**多组并发调度**:返回 `{schedule:{done,running,runnable,blocked,failed}, actions:[...], serial_validation, max_parallel}`。`actions` 列出每个 runnable/待推进组的 `fork` 列表;`schedule.runnable` 是当前可起的组,`blocked` 给出原因(`needs` 未满足 / `writes` 与在跑组冲突)。
3. `fork`:同一 message 把 `actions` 里**所有 runnable 组**的 coder 一起 fork(按各 `fork[].agent_key` **逐字**拷,**禁止**自创 `coder-fix-xxx`)。总并发受 `max_parallel` 约束——超出的组会留在下一轮。
4. **等齐所有 in-flight Task ✓ completed 才能 advance**(强约束,违反必出乱):
   - 必须在 teammates UI 看到所有 fork 的 Task ✓ completed;任何 ⠙ streaming / ⠴ running Bash 都不能 advance
   - **不要**凭口头报告判定完成——只有 subagent 自己 Task tool 返回 ✓ 才算
   - 不确定时调 `plan --run <run_id>`,返回 `coding-waiting`/`p0-fix-waiting`/`v-fix-waiting` 就回到等待
5. `advance --run <run_id> --group <gid> --phase <p>`(gid 为字符串如 `g1`)推进**该组**子状态机
6. `writeback --run <run_id> --group <gid>`(finalize 本组,不写 tasks.md)
7. 全组完成 → `resolve --run <run_id>` 收尾 → `report --run <run_id>` 出报告

> plan 的 `schedule` 是并发驱动核心:主代理按 `runnable` 同 message fork 多组,`running` 是在跑组,`blocked`(needs 未满足 / writes 与在跑组冲突)等解锁后下一轮 plan 才进 runnable。

完整规格见 `references/task-swarm.md`。

## heartbeat(长流程可选)

主代理每 5 分钟 / 每完成一个 subagent 后可调,刷新 `last_activity_at`:

```sh
sh "${CLAUDE_PLUGIN_ROOT:-${CODEBUDDY_PLUGIN_ROOT}}/scripts/run.sh" \
   "${CLAUDE_PLUGIN_ROOT:-${CODEBUDDY_PLUGIN_ROOT}}/scripts/task_swarm.py" \
   heartbeat --run <run_id>
```

## 术语区分:reviewer 分级 vs validator fail(容易混)

| 概念 | 来源 | 触发 fix loop？ |
|---|---|---|
| **P0(带证据标签)** | reviewer `review.md` `## P0`,必带 `[req:x.y]`/`[security]`/`[contract]` | ✓ p0-fix(仅一轮,不 re-review,直接进 validation) |
| **P0(无证据标签)** | reviewer `## P0` 漏标签 | 降级 advisory → ✗ 不修 |
| **P1 / P2** | reviewer `## P1`/`## P2` | ✗ advisory,不修 |
| **validator fail** | validator `validation.md` `## 判定 = fail` | ✓ v-fix 循环到 pass;连续 3 轮同 fail 签名 → `failed-deadloop` |

validator **不输出 P0/P1/P2 标签**,它的 fix_targets 全是"任务没做完",fail 必修。
用户问"能不能跳过"→ 按设计不能;唯一办法是中止 run + 改 pipeline.yml 移除该任务再重 init。

## advance 报 "result.md 缺 STATUS / 解析失败" 的正确应对

- **保留**残缺 result.md(证据,别 Edit)→ `status --run <run_id>` 看是否还 in_flight
- in_flight → 等真完成;>10 分钟不收尾 → esc 取消 + 报用户
- 不在 in_flight 但产物残缺 → 重 fork **同名** agent(先 `rm -rf agents/<key>/outbox/*`),**禁止**起新名字、**禁止**手补 STATUS

## 异常出口

coder STATUS=failed/blocked、writeback 越界、`failed-deadloop` → 停循环、报用户、等介入,**不自动 retry**。详见 `references/task-swarm.md` §3 / §8。
