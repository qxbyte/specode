---
description: Use when working with task-swarm / reviewer / validator / v-fix / p0-fix / writes / needs / pipeline.yml / writeback / deadloop / multi-agent concurrent task-group execution. Details the full task-swarm protocol (role boundaries, per-group state machine + cross-group scheduling, artifact schemas, deadloop guard).
---

# task-swarm Protocol Reference (references/task-swarm.md)

This document is the full protocol behind the task-swarm `/task-swarm:swarm` command.
During a task-swarm run the lead agent must follow this protocol strictly.

---

## 1. Roles and concurrency

| Role | Concurrent | Tool allowlist (physical isolation) | When forked |
|---|---|---|---|
| `task-swarm-coder` | **many parallel instances** | `Bash, Read, Edit, Write, Grep, Glob` | coding / p0-fix / v-fix phases |
| `task-swarm-reviewer` | **single instance per group** | `Bash, Read, Grep, Glob` (no Edit/Write) | review phase (once per group per review-round) |
| `task-swarm-validator` | **single instance per group** | `Bash, Read, Grep, Glob` (no Edit/Write) | validation phase (once per group per validation-round; globally serialized across groups under `--serial-validation`) |

> The planner is the lead agent itself, not a subagent. Multiple groups may run concurrently; the reviewer/validator **inside** each group are still single-instance.

Why reviewer / validator are single-instance per group:
- reviewer = a god's-eye code reader who needs a holistic judgment over all coder artifacts; splitting it would break cross-correlation detection.
- validator = an objective test-running signal; running it concurrently is pointless — one process running the same test suite once is enough.
- coder = where parallelism pays off most (each stage owns its own files when stages don't interfere).

---

## 2. Orchestration format and concurrency scheduling

> **Orchestration format**: pipeline.yml is task-swarm's **only input** (`--pipeline`, schema in `references/pipeline-yaml.md`). It directly expresses **semantic task groups** (`task_group`): each group holds a batch of same-topic tasks (each with its own `writes`/`reads`), and groups declare dependencies via `needs`.

`task_swarm.py init` maps pipeline.yml into group-level scheduling state (`_pipeline.to_group_states` → the per-group sub-state-machines of `_state`). The scheduling layer (`_schedule.compute_schedule`) decides which groups may run concurrently each round by these rules:

1. A group's `needs` dependencies must all be `done` (topological unlock).
2. A group's `writes` union (the `writes` of all tasks in the group) must not intersect the `writes` of the **currently running groups**; on conflict the group stays `blocked` and only becomes runnable after the conflicting group finishes.
3. Upstream group `failed` → downstream group also goes `blocked` (`upstream failed`).
4. Total concurrency is bounded by `max_parallel`.

In the coding phase the lead agent emits the coder Task block for every runnable group **within the same message**, and the host runs them in parallel.

**Hard constraint**: before dispatching coders, always call `task_swarm.py plan` to get `schedule` + `actions`, and **copy** `actions[].fork[].agent_key` verbatim — never dispatch from memory; the script has already resolved dependency topology and writes-conflict scheduling.

---

## 3. Phase state machine

Each `task_group` runs **its own independent sub-state-machine** (diagram below), without blocking the others; above them sits a **scheduling layer** (§2) that decides which groups may advance concurrently each round via `needs` topological unlock + `writes` disjointness. `advance --group <gid>` / `writeback --group <gid>` both act on a single group's sub-state-machine. The diagram describes the phase flow of **one group**:

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
 writeback v-fix ──► validation (loop)
 │
 ▼
 this group done →(downstream groups unlock once their needs are met)
```

> By default the validator runs per group independently; under `init --serial-validation` the scheduling layer makes **validation/v-fix globally serial** (only one group in a validation-class phase at a time), for tests with shared resources / port conflicts.

| Phase | Trigger | Subagent | Completion condition | Failure behavior |
|---|---|---|---|---|
| `coding` | entering a new group | N concurrent coders | all STATUS: ok | any fail → lead agent reports to user, whole group failed |
| `review` | coding done | single reviewer | review.md contains graded P0/P1/P2 | reviewer fail → lead agent reports, **proceeds** to validation (reviewer is advisory) |
| `p0-fix` | review contains **evidence-tagged** P0 | M concurrent coders (grouped by files the P0s touch) | all STATUS: ok (no re-review) | any fail → lead agent records the P0 as "unfixed" in state (reflected in report), proceeds to validation |
| `validation` | p0-fix done or review has no P0 | single validator | validator pass | validator fail → enter v-fix |
| `v-fix` | validation fail | M concurrent coders (grouped by files the validator's fix guidance touches) | all STATUS: ok | any fail → lead agent reports to user, whole group failed |
| `validation` (again) | v-fix done | single validator | pass → writeback; fail → v-fix loop | deadloop detection: 3 consecutive rounds with the same fail signature → whole group failed |
| `writeback` | validation pass | lead agent calls CLI | finalize this group (group state set to done/failed), does not write tasks.md | — |

**Key differences (vs the original 0.3.0 scheme)**:
- "the whole group codes together → one reviewer → one validator"; reviewer / validator look at group scope.
- reviewer P0 → coder fix is **triggered only once** (no re-review after fixing; straight to validation).
- validator fail → coder fix **loops** until pass.
- deadloop detection: v-fix → validation with the same fail signature (test name + assertion hash) 3 rounds in a row → whole group failed.

---

## 4. Subagent artifact schemas

When forking each subagent, the lead agent pre-renders the prompt file to:

```
.task-swarm/runs/<run_id>/agents/<agent-key>/task.md
```

Artifact paths:

```
.task-swarm/runs/<run_id>/agents/<agent-key>/outbox/
 result.md ← coder
 review.md ← reviewer
 validation.md ← validator
```

`agent-key` naming convention:
- coder: `coder-g{group}-s{stage}-r{round}`
- p0-fix coder: `coder-p0fix-g{group}-r{round}-f{file-idx}`
- v-fix coder: `coder-vfix-g{group}-r{round}-f{file-idx}`
- reviewer: `reviewer-g{group}-r{round}`
- validator: `validator-g{group}-r{round}`

### 4.1 coder result.md schema

```markdown
# <agent-key>: <stage title or fix task>

## 上下文
- specId / spec_dir / group / stage / round

## 子任务状态
- 2.1 user model: done — src/models/user.py
- 2.2 user service: failed — ImportError, missing deps

## 关键变更
- ...

## 给下游 reviewer 的提示（可选）
- ...

STATUS: ok | failed: <reason> | blocked: <reason>
```

### 4.2 reviewer review.md schema

```markdown
# reviewer-g{group}-r{round}

## 结论
needs-changes | approved-with-comments | approved

## P0（必须带证据标签：[req:x.y] / [security] / [contract]）
- src/auth/service.py:34 [req:1.2] — login failure doesn't distinguish lockout vs wrong password
（如无 P0：本节写 `(none)`）

## P1
- src/models/user.py:12 — email field format validation missing

## P2
- naming `auth_svc` could be `auth_service`

## 给使用者的提示
- one-line summary

STATUS: ok
```

**advance --phase review parsing**:
1. Extract all P0 items + evidence tags.
2. **P0 items without an evidence tag are auto-downgraded to advisory.**
3. If P0 items remain after downgrade → next phase = `p0-fix`, write `p0_pending[]` to state.json.
4. If no P0 → next phase = `validation`.
5. All P0/P1/P2 items (including downgraded ones) are written to `findings[]`, summarized when `report` renders.

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
- [ ] 1.3 controller: fail — account not locked after 5 failures (_需求：1.3_)

## 失败现场（fail 时必填）
` ` `
FAILED tests/test_auth.py::test_lockout_after_5_failures
AssertionError: expected 423, got 401
` ` `

## 给 coder 的修复指引（fail 时必填，不带 P0/P1 标签）
### 修复 1 — lockout counter
- 文件: src/api/login.py
- 位置: login failure branch
- 问题: lockout counter is never called
- 建议: introduce src/auth/lockout.py, record failure count, return 423 on the 5th
- _需求：1.3_

STATUS: ok
```

**advance --phase validation parsing**:
1. Grab the "判定" line → pass or fail.
2. fail → parse "给 coder 的修复指引" → emit `fix_targets[]` (grouped by file) → next phase = `v-fix`.
3. pass → next phase = `writeback`.
4. **Deadloop detection**: compare this round's fail signature (test name + assertion-text hash) against the previous round; 3 identical rounds in a row → mark the group `failed-deadloop` in state.json.

---

## 5. writeback — finalize the group

`task_swarm.py writeback --run <id> --group <gid>` is the per-group **finalize** action (since M3 it no longer writes tasks.md):

1. Verify the group has reached the `writeback` phase (or `failed-deadloop`).
2. Set the group to a terminal state: validator pass → `done`; deadloop → `failed`.
3. Append a `writeback` event to state.
4. When all groups are terminal, automatically finalize the run (write `completed_at` + run-level `done`/`failed`).
5. Return `{ok, group, finalized, verdict, schedule}` — `schedule` tells the lead agent which downstream groups become runnable after finalize.

Review/validation findings are already persisted in state.json + each group's outbox; the final summary is rendered by `report --run <id>` (see §9), not written back to tasks.md.

### 5.1 Fix-status labels (used when report renders)

| Label | Meaning |
|---|---|
| `[P0 已修复]` | evidence-tagged P0 + p0-fix-phase coder STATUS: ok |
| `[P0 未修复]` | evidence-tagged P0 + p0-fix coder failed / lead agent chose to skip |
| `[P1 未修复]` / `[P2 未修复]` | listed by reviewer but not fixed by default; status defaults to "unfixed" |
| `[adv 未修复]` | listed as P0 by reviewer but without an evidence tag, auto-downgraded |

---

## 6. plan reminder matrix (lead agent polls actively)

task-swarm runs standalone with **no hook**. After each subagent completes (or each fork batch completes), the lead agent **itself** calls `task_swarm.py plan --run <id>` to get the next-step hint. The table below shows what `plan` injects in each state:

| Current state | Injected text gist |
|---|---|
| coding in progress, coders still pending | "coding phase is still waiting on N subagents; no need to fork new agents; decide once they're all back." |
| all coders returned | "all coders for this group are back. Please fork **1** `task-swarm-reviewer`." |
| review returned, has evidence-tagged P0 | "reviewer raised N evidence-tagged P0s. Fork M `task-swarm-coder` (p0-fix) grouped by the files the P0s touch. Note: reviewer fix is **triggered only once**, no re-review." |
| review returned, no P0 (or all downgraded) | "reviewer raised no evidence-tagged P0. Please fork **1** `task-swarm-validator`." |
| p0-fix all returned | "p0-fix coders are back. Please fork **1** `task-swarm-validator`." |
| validation returned pass | "validator pass. Call `task_swarm.py writeback --group <gid>` to finalize this group; downstream groups become runnable once their needs are met." |
| validation returned fail | "validator fail. Per validation.md's fix_targets, fork **N** `task-swarm-coder` (v-fix), one per file." |
| v-fix all returned | "v-fix coders are back. Please fork **1** `task-swarm-validator` to verify." |
| v-fix already 3 rounds with same fail signature | "⚠️ Deadloop detected: g{g} has hit the same fail 3 rounds in a row. Suggest stopping this group and reporting `failed-deadloop` to the user." |
| all groups done | "all groups are done. Call `task_swarm.py resolve` to finalize, then `report` to produce the report." |

Every reminder **always appends**: "本提醒仅供参考；fork 谁、是否 fork、何时 writeback 仍由你判断；可忽略。"

---

## 7. Information-flow overview

```
lead agent (task-swarm orchestration session)
 │
 ├─[call]── task_swarm.py init ───────────► state.json (groups, stages)
 │ ┌──────────────────────────────────────┘
 │ │
 ├─[read]── task_swarm.py plan ──► list of subagents to fork now
 │
 ├─[fork]── Task(coder1) ─┐
 │ [fork]── Task(coder2)─┼─► (run concurrently)
 │ [fork]── Task(coderN)─┘
 │ ┌─► each writes outbox/result.md
 │ ←─── lead agent calls plan after each return
 │
 ├─[call]── task_swarm.py advance --group <gid> --phase coding ──► state.json updated
 │
 ├─[fork]── Task(reviewer) ─► outbox/review.md
 ├─[call]── task_swarm.py advance --group <gid> --phase review ──► state.json + p0_pending[]
 ├─[fork]── Task(coder p0-fix x M) ─► outbox/result.md ...
 ├─[fork]── Task(validator) ─► outbox/validation.md
 ├─[call]── task_swarm.py advance --group <gid> --phase validation
 │
 │ if fail:
 │ ├─[fork]── Task(coder v-fix x M) ─► outbox/...
 │ └─ loop back to validator
 │
 │ if pass:
 │ └─[call]── task_swarm.py writeback --run <id> --group <gid>
 │ ─► finalize this group (state set done), downstream groups unlock
 │
 └─ all groups done → resolve + report → exit task-swarm mode
```

**Key invariants**:

1. The lead agent is the **only** holder of the spec lock; subagents never touch the lock.
2. All cross-process information flows through the filesystem (outbox + state.json).
3. `state.json` is the single source of truth; if the lead agent loses its state it can fully recover from `state.json` + outbox files (resume is not yet implemented, but the data structures leave room for it).
4. The hook is read-only and advisory — any "what to do next" decision is the lead agent's.

---

## 8. Deadloop guard rules

- 3 consecutive v-fix → validation rounds with an **identical** fail signature (test name + assertion-text hash) → the whole group is marked `failed-deadloop`.
- That group's state is marked `failed-deadloop` and stops advancing; other independent groups keep running. `report` flags the group as deadloop.
- After user intervention they can: edit source by hand → rerun `/task-swarm:swarm`; or call `task_swarm.py resolve --run <id> --abort` to abort the whole run.

---

## 9. CLI reference

```text
task_swarm.py init --pipeline <abs> [--max-parallel N] [--max-rounds N] [--serial-validation]
 [--workdir <dir>] [--project-root <dir>] [--spec-id <id>] [--session <session_id>]
 → {"run_id", "groups": [...], ...}
 # --pipeline: path to pipeline.yml (the only input; schema in references/pipeline-yaml.md)
 # --serial-validation: serialize the validator globally (only one group's validation/v-fix at a time)
 # --workdir: directory holding the state root (default = cwd); state root = <workdir>/.task-swarm/runs/
 # --project-root: root of the code being changed (default = --workdir)
 # --spec-id (optional): spec identifier, written into state for artifacts to reference

task_swarm.py status --run <run_id>
 → overview of each group's phase / round / pending subagents

task_swarm.py plan --run <run_id>
 → {"schedule":{done,running,runnable,blocked,failed}, "actions":[{group,phase,fork:[...]}],
 "serial_validation", "max_parallel"} (does not change state)
 # schedule drives concurrency: runnable can start, blocked carries the reason (needs unmet / writes conflict with a running group)

task_swarm.py advance --run <run_id> --group <gid>
 --phase <coding|review|p0-fix|validation|v-fix> [--round <n>]
 → parse this group's outbox, advance its sub-state-machine, return the next-step suggestion

task_swarm.py writeback --run <run_id> --group <gid>
 → finalize this group (set done/failed; does not write tasks.md), return the updated schedule

task_swarm.py heartbeat --run <run_id>
 → refresh state.json.last_activity_at
 # heartbeat only refreshes state.json.last_activity_at (keep-alive for long runs, state layer); standalone mode has no spec lock.

task_swarm.py resolve --run <run_id> [--abort]
 → mark complete or abort; clear sessions.task_swarm_run_id

task_swarm.py report --run <run_id> [--group <gid>] [--out <path>]
 → render the final summary (findings + validator rounds + fix-status labels)
```
