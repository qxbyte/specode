---
description: Use when 涉及 task-swarm / reviewer / validator / v-fix / p0-fix / writes / needs / pipeline.yml / writeback / deadloop / 多 agent 并发执行任务组。详述 task-swarm 完整协议（角色边界、per-group 状态机 + 跨组调度、产物 schema、死循环保护）。
---

# task-swarm 协议参考（references/task-swarm.md）

本文档是 task-swarm `/task-swarm:swarm` 命令背后的完整协议。
主代理在 task-swarm run 期间必须严格按本协议工作。

---

## 1. 角色与并发度

| 角色 | 是否并发 | 工具白名单（物理隔离） | 何时被 fork |
|---|---|---|---|
| `task-swarm-coder` | **多实例并行** | `Bash, Read, Edit, Write, Grep, Glob` | coding / p0-fix / v-fix 各 phase |
| `task-swarm-reviewer` | **每组单实例** | `Bash, Read, Grep, Glob`（无 Edit/Write） | review phase（每组每 review-round 一次） |
| `task-swarm-validator` | **每组单实例** | `Bash, Read, Grep, Glob`（无 Edit/Write） | validation phase（每组每 validation-round 一次；`--serial-validation` 时跨组全局串行） |

> planner 由主代理自己担任，不是子 agent。多个组可并发，各组**内部**的 reviewer/validator 仍是单实例。

reviewer / validator 每组单实例的理由：
- reviewer = 一个上帝视角的读代码人，要对全部 coder 产物有整体判断；切成多份会破坏交叉关联检测。
- validator = 跑测试的客观信号，并发跑没意义；同一测试套件单进程跑一次就够。
- coder = 并行收益最大（多 stage 互不干扰时各占一份文件）。

---

## 2. 编排格式与并发调度

> **编排格式**：pipeline.yml 是 task-swarm 的**唯一输入**（`--pipeline`，schema 见 `references/pipeline-yaml.md`）。它直接表达**语义任务组**（`task_group`）：每组内是一批同主题的 task（含各自 `writes`/`reads`），组与组之间用 `needs` 声明依赖。

`task_swarm.py init` 把 pipeline.yml 映射成组级调度状态（`_pipeline.to_group_states` → `_state` 的 per-group 子状态机）。调度层（`_schedule.compute_schedule`）按以下规则决定每轮哪些组可并发跑：

1. 组的 `needs` 依赖必须全部 `done`（拓扑解锁）。
2. 组的 `writes` 并集（组内所有 task 的 `writes`）与**当前在跑组**的 `writes` 不相交；冲突则该组留在 `blocked`，等冲突组结束后才进 runnable。
3. 上游组 `failed` → 下游组也进 `blocked`（`upstream failed`）。
4. 总并发受 `max_parallel` 约束。

主代理在 coding phase **同一 message 内**为所有 runnable 组各发出其 coder Task block，由宿主并行执行。

**强约束**：派发 coder 时，必须先调 `task_swarm.py plan` 拿 `schedule` + `actions`，**逐字拷贝** `actions[].fork[].agent_key`——绝不可凭印象自己派；脚本已经处理过依赖拓扑与 writes 冲突调度。

---

## 3. Phase 状态机

每个 `task_group` 跑**自己独立的子状态机**（下图），互不阻塞;其上有一层**调度层**（§2）按 `needs` 拓扑解锁 + `writes` 不相交决定哪些组当轮可并发推进。`advance --group <gid>` / `writeback --group <gid>` 都作用于单个组的子状态机。下图描述**单个组**的 phase 流转：

```
init → coding → review ─┬─► p0-fix ──► validation
 │ │
 └─►(no P0) ────────┘
 │
 ┌────────────────┤
 │ │
 (pass) (fail)
 │ │
 ▼ ▼
 writeback v-fix ──► validation (循环)
 │
 ▼
 本组 done →（下游组 needs 满足后解锁）
```

> validator 默认按组独立跑；`init --serial-validation` 时调度层让 **validation/v-fix 全局串行**（同一时刻只允许一个组处于 validation 类 phase），用于测试有共享资源/端口冲突的场景。

| Phase | 触发 | 子代理 | 完成条件 | 失败行为 |
|---|---|---|---|---|
| `coding` | 进入新 group | 并发 N 个 coder | 全部 STATUS: ok | 任一 fail → 主代理报告用户、整个 group failed |
| `review` | coding 完成 | 单个 reviewer | review.md 含分级 P0/P1/P2 | reviewer fail → 主代理报告，**继续走** validation（reviewer 是 advisory） |
| `p0-fix` | review 含**带证据标签**的 P0 | 并发 M 个 coder（按 P0 涉及文件分组） | 全部 STATUS: ok（不再 review） | 任一 fail → 主代理把 P0 标"未修复"记入 state（report 体现），继续走 validation |
| `validation` | p0-fix 完成 或 review 无 P0 | 单个 validator | validator pass | validator fail → 进入 v-fix |
| `v-fix` | validation fail | 并发 M 个 coder（按 validator 修复指引涉及文件分组） | 全部 STATUS: ok | 任一 fail → 主代理报告用户、整个 group failed |
| `validation` (再) | v-fix 完成 | 单个 validator | pass → writeback；fail → v-fix 循环 | 死循环检测：连续 3 轮同一 fail 签名 → 整个 group failed |
| `writeback` | validation pass | 主代理调 CLI | finalize 本组（组状态置 done/failed），不写 tasks.md | — |

**关键差别（与原 0.3.0 方案）**：
- "整个 group 一起 coding → 一次 reviewer → 一次 validator"，reviewer / validator 看的是 group 范围。
- reviewer P0 → coder 修复**只触发一次**（修完不再 re-review，直接进 validation）。
- validator fail → coder 修复**循环**到 pass。
- 死循环检测：v-fix → validation 连续 3 轮同一 fail 签名（测试名 + assertion 哈希）→ 整个 group failed。

---

## 4. 子代理产物 schema

每个子代理 fork 时主代理把 prompt 文件预渲染到：

```
.task-swarm/runs/<run_id>/agents/<agent-key>/task.md
```

产物路径：

```
.task-swarm/runs/<run_id>/agents/<agent-key>/outbox/
 result.md ← coder
 review.md ← reviewer
 validation.md ← validator
```

`agent-key` 命名约定：
- coder：`coder-g{group}-s{stage}-r{round}`
- p0-fix coder：`coder-p0fix-g{group}-r{round}-f{file-idx}`
- v-fix coder：`coder-vfix-g{group}-r{round}-f{file-idx}`
- reviewer：`reviewer-g{group}-r{round}`
- validator：`validator-g{group}-r{round}`

### 4.1 coder result.md schema

```markdown
# <agent-key>：<阶段标题或修复任务>

## 上下文
- specId / spec_dir / group / stage / round

## 子任务状态
- 2.1 user model: done — src/models/user.py
- 2.2 user service: failed — ImportError, 缺 deps

## 关键变更
- ...

## 给下游 reviewer 的提示（可选）
- ...

STATUS: ok | failed: <原因> | blocked: <原因>
```

### 4.2 reviewer review.md schema

```markdown
# reviewer-g{group}-r{round}

## 结论
needs-changes | approved-with-comments | approved

## P0（必须带证据标签：[req:x.y] / [security] / [contract]）
- src/auth/service.py:34 [req:1.2] — login 失败未区分锁/密码错
（如无 P0：本节写 `(none)`）

## P1
- src/models/user.py:12 — email 字段格式校验缺失

## P2
- 命名 `auth_svc` 可改为 `auth_service`

## 给使用者的提示
- 一句话总结

STATUS: ok
```

**advance --phase review 解析**：
1. 提取所有 P0 项 + 证据标签。
2. **无证据标签的 P0 自动降级为 advisory**。
3. 若降级后仍有 P0 → 下一 phase = `p0-fix`，state.json 写 `p0_pending[]`。
4. 若无 P0 → 下一 phase = `validation`。
5. 所有 P0/P1/P2 项（含降级的）都写入 `findings[]`，`report` 渲染时汇总。

### 4.3 validator validation.md schema

```markdown
# validator-g{group}-r{round}

## 判定
pass | fail

## 复现命令
` ` `bash
cd <project root>
pytest tests/test_auth.py -v
` ` `

## 按子任务的验证结果
- [x] 1.1 user model: pass
- [ ] 1.3 controller: fail — 5 次失败未锁账号 (_需求：1.3_)

## 失败现场（fail 时必填）
` ` `
FAILED tests/test_auth.py::test_lockout_after_5_failures
AssertionError: expected 423, got 401
` ` `

## 给 coder 的修复指引（fail 时必填，不带 P0/P1 标签）
### 修复 1 — lockout 计数器
- 文件: src/api/login.py
- 位置: login 失败分支
- 问题: 没有调用 lockout 计数器
- 建议: 引入 src/auth/lockout.py，记录失败次数，第 5 次返回 423
- _需求：1.3_

STATUS: ok
```

**advance --phase validation 解析**：
1. 抓"判定"行 → pass 或 fail。
2. fail → 解析"给 coder 的修复指引"→ 输出 `fix_targets[]`（按文件分组）→ 下一 phase = `v-fix`。
3. pass → 下一 phase = `writeback`。
4. **死循环检测**：比对本轮 fail 签名（测试名 + assertion 文本哈希）与上一轮，连续 3 轮相同 → state.json 标 group `failed-deadloop`。

---

## 5. writeback —— finalize 本组

`task_swarm.py writeback --run <id> --group <gid>` 是 per-group 的**收尾**动作（M3 起不再写 tasks.md）：

1. 校验该组已到 `writeback` phase（或 `failed-deadloop`）。
2. 把组状态置为终态：validator pass → `done`；deadloop → `failed`。
3. 追加 `writeback` 事件到 state。
4. 所有组都进终态时，自动给 run 收尾（写 `completed_at` + run 级 `done`/`failed`）。
5. 返回 `{ok, group, finalized, verdict, schedule}`——`schedule` 让主代理知道 finalize 后哪些下游组解锁进 runnable。

评审/验证的 findings 已沉淀在 state.json + 各组 outbox 里；最终汇总由 `report --run <id>` 渲染（见 §9），不再回写到 tasks.md。

### 5.1 修复状态标签（report 渲染时使用）

| 标签 | 含义 |
|---|---|
| `[P0 已修复]` | 带证据标签的 P0 + p0-fix 阶段 coder STATUS: ok |
| `[P0 未修复]` | 带证据标签的 P0 + p0-fix coder failed / 主代理选择跳过 |
| `[P1 未修复]` / `[P2 未修复]` | reviewer 列出但默认不修；状态默认为"未修复" |
| `[adv 未修复]` | reviewer 列为 P0 但未带证据标签，被自动降级 |

---

## 6. plan 提醒矩阵(主代理主动轮询)

task-swarm 独立运行,**无 hook**。主代理每完成一个 subagent(或每完成一组 fork)后,
**自己**调 `task_swarm.py plan --run <id>` 拿下一步提示。下表是 `plan` 在各状态下的输出提示:

| 当前 state | 注入文本要点 |
|---|---|
| coding 进行中，仍有 coder 未返回 | "coding phase 还在等 N 个 subagent，无需 fork 新 agent；等齐后再判断。" |
| coding 全部返回 | "本 group coder 已全部返回。请 fork **1 个** `task-swarm-reviewer`。" |
| review 返回，含带证据 P0 | "reviewer 提了 N 个带证据 P0。请按 P0 涉及文件 fork M 个 `task-swarm-coder`（p0-fix）。提醒：reviewer 修复**只触发一次**，不 re-review。" |
| review 返回，无 P0（或全降级） | "reviewer 无带证据 P0。请 fork **1 个** `task-swarm-validator`。" |
| p0-fix 全部返回 | "p0-fix coder 已返回。请 fork **1 个** `task-swarm-validator`。" |
| validation 返回 pass | "validator pass。请调 `task_swarm.py writeback --group <gid>` finalize 本组；下游组 needs 满足后解锁进 runnable。" |
| validation 返回 fail | "validator fail。请按 validation.md 的 fix_targets 各文件 fork **N 个** `task-swarm-coder`（v-fix）。" |
| v-fix 全部返回 | "v-fix coder 已返回。请 fork **1 个** `task-swarm-validator` 验证。" |
| v-fix 已连续 3 轮同 fail 签名 | "⚠️ 死循环检测：g{g} 已连续 3 轮同一 fail。建议停止本 group，向用户报告 `failed-deadloop`。" |
| 所有 group 完成 | "全部 group 已完成。请调 `task_swarm.py resolve` 收尾，再 `report` 出报告。" |

所有提醒**末尾固定加**："本提醒仅供参考；fork 谁、是否 fork、何时 writeback 仍由你判断；可忽略。"

---

## 7. 信息流总览

```
主代理（task-swarm 编排会话）
 │
 ├─[调]── task_swarm.py init ─────────────► state.json (groups, stages)
 │ ┌──────────────────────────────────────┘
 │ │
 ├─[读]── task_swarm.py plan ──► 当前应 fork 的 subagent 列表
 │
 ├─[fork]── Task(coder1) ─┐
 │ [fork]── Task(coder2)─┼─► （并发执行）
 │ [fork]── Task(coderN)─┘
 │ ┌─► 各自写 outbox/result.md
 │ ←─── 主代理每返回一个后主动调 plan
 │
 ├─[调]── task_swarm.py advance --group <gid> --phase coding ──► state.json 更新
 │
 ├─[fork]── Task(reviewer) ─► outbox/review.md
 ├─[调]── task_swarm.py advance --group <gid> --phase review ──► state.json + p0_pending[]
 ├─[fork]── Task(coder p0-fix x M) ─► outbox/result.md ...
 ├─[fork]── Task(validator) ─► outbox/validation.md
 ├─[调]── task_swarm.py advance --group <gid> --phase validation
 │
 │ if fail:
 │ ├─[fork]── Task(coder v-fix x M) ─► outbox/...
 │ └─ loop 回 validator
 │
 │ if pass:
 │ └─[调]── task_swarm.py writeback --run <id> --group <gid>
 │ ─► finalize 本组（state 置 done），下游组解锁
 │
 └─ 全组 done → resolve + report → 退出 task-swarm 模式
```

**关键不变量**：

1. 主代理是**唯一**持有 spec 锁的实体；subagent 不动锁。
2. 所有跨进程信息走文件系统（outbox + state.json）。
3. `state.json` 是唯一事实源；主代理状态丢了可以从 `state.json` + outbox 文件完全恢复（resume 暂未实现，但数据结构已为之留路）。
4. hook 只读、只提醒——任何"该做什么"由主代理决定。

---

## 8. 死循环保护规则

- 连续 3 轮 v-fix → validation 出现**完全相同**的 fail 签名（测试名 + assertion 文本哈希）→ 整个 group 标 `failed-deadloop`。
- 该组 state 标 `failed-deadloop`、不再推进；其余无依赖组可继续跑。`report` 会标明该组 deadloop。
- 用户介入后可：手改源码 → 重跑 `/task-swarm:swarm`；或调 `task_swarm.py resolve --run <id> --abort` 中止整个 run。

---

## 9. CLI 接口速查

```text
task_swarm.py init --pipeline <abs> [--max-parallel N] [--max-rounds N] [--serial-validation]
 [--workdir <dir>] [--project-root <dir>] [--spec-id <id>] [--session <session_id>]
 → {"run_id", "groups": [...], ...}
 # --pipeline：pipeline.yml 路径（唯一输入；schema 见 references/pipeline-yaml.md）
 # --serial-validation：让 validator 全局串行（同一时刻只跑一个组的 validation/v-fix）
 # --workdir：state 根所在目录（缺省 = cwd）；state 根 = <workdir>/.task-swarm/runs/
 # --project-root：被改代码的根目录（缺省 = --workdir）
 # --spec-id（可选）：spec 标识，写入 state 供产物引用

task_swarm.py status --run <run_id>
 → 当前各组 phase / round / 待派 subagent 概览

task_swarm.py plan --run <run_id>
 → {"schedule":{done,running,runnable,blocked,failed}, "actions":[{group,phase,fork:[...]}],
 "serial_validation", "max_parallel"}（不改 state）
 # schedule 给并发驱动：runnable 可起、blocked 含原因（needs 未满足 / writes 与在跑组冲突）

task_swarm.py advance --run <run_id> --group <gid>
 --phase <coding|review|p0-fix|validation|v-fix> [--round <n>]
 → 解析本组 outbox、推进该组子状态机、返回下一步建议

task_swarm.py writeback --run <run_id> --group <gid>
 → finalize 本组（置 done/failed；不写 tasks.md），返回更新后的 schedule

task_swarm.py heartbeat --run <run_id>
 → 刷新 state.json.last_activity_at
 # heartbeat 只刷新 state.json.last_activity_at（长流程保活，状态层）；独立模式无 spec 锁。

task_swarm.py resolve --run <run_id> [--abort]
 → 标记完成或中止；清理 sessions.task_swarm_run_id

task_swarm.py report --run <run_id> [--group <gid>] [--out <path>]
 → 渲染最终汇总（findings + validator 历轮 + 修复状态标签）
```
