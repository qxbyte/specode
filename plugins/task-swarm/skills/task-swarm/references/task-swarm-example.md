---
description: Use when you want a complete, working pipeline.yml example to understand the actual syntax of task_group / needs / writes / reads / requirements and cross-group concurrency scheduling.
---

# task-swarm example: 3 task groups / 8 tasks

A **complete, working** pipeline.yml example, demonstrating:

- `task_group` plus the `writes` / `reads` syntax of each `task` within a group
- `needs` (inter-group dependency, topological unlock)
- `requirements` (`_需求：x.y_` traceability)
- Cross-group concurrency scheduling: groups with no dependency and disjoint writes run concurrently; groups with conflicting writes or unmet `needs` run serially

---

## Example pipeline.yml

```yaml
version: 1
run:
  spec_id: user-login
  max_parallel: 4
task_groups:
  - id: g1
    name: "data layer"
    tasks:
      - id: g1.1
        title: "define User model"
        writes: [src/models/user.py]
        requirements: ["1.1"]
      - id: g1.2
        title: "define Session model"
        writes: [src/models/session.py]
        requirements: ["1.2"]
      - id: g1.3
        title: "database migration script"
        writes: [migrations/0001_init.sql]
        reads:  [src/models/user.py, src/models/session.py]
        requirements: ["1.3"]
  - id: g2
    name: "service layer"
    needs: [g1]
    tasks:
      - id: g2.1
        title: "AuthService login/logout"
        writes: [src/auth/service.py]
        reads:  [src/models/user.py, src/models/session.py]
        requirements: ["2.1", "2.2"]
      - id: g2.2
        title: "PasswordHasher util"
        writes: [src/auth/hasher.py]
        requirements: ["2.3"]
      - id: g2.3
        title: "LockoutCounter util"
        writes: [src/auth/lockout.py]
        requirements: ["2.4"]
  - id: g3
    name: "API layer"
    needs: [g2]          # depends on service layer; also co-writes user.py with g1 (writes conflict is serialized by the scheduler too)
    tasks:
      - id: g3.1
        title: "/login endpoint"
        writes: [src/api/login.py]
        reads:  [src/auth/service.py, src/auth/lockout.py]
        requirements: ["3.1"]
      - id: g3.2
        title: "User schema validation extension"
        writes: [src/models/user.py]
        reads:  [src/api/login.py]
        requirements: ["3.2"]
```

---

## Expected schedule (max_parallel=4)

`plan`'s `schedule` unlocks round by round following the `needs` topology plus disjoint `writes`:

```
Round 1: runnable = [g1]
         (g2 needs g1, g3 needs g2 → blocked: needs not done)
Round 2 (after g1 done): runnable = [g2]
Round 3 (after g2 done): runnable = [g3]
```

The three groups here form a linear dependency chain, so execution is in fact serial. Drop the `needs` of `g2`/`g3` and make each group's `writes` mutually disjoint, and the scheduler runs them concurrently (total concurrency ≤ `max_parallel`); note that **both g3 and g1 write `src/models/user.py`**, so even without `needs` the scheduler orders g3 after g1 due to `writes conflict with running group` — a file conflict serializes naturally, no hand-written dependency required.

When the lead agent dispatches coders, copy each runnable group's `actions[].fork[].agent_key` (e.g. `coder-g1-s1-r1`) verbatim and fork them concurrently in the same message.

> Note: each task, even with multiple sub-items, is handled by the group's coder sequence; the concurrency granularity is the task_group, not an individual task.

---

## Report example: one validator fail → v-fix → pass round

When `report --run <id>` renders, the g3 section contains:

```markdown
## g3 API layer — done

> ✅ validator g3-r2 pass: `pytest tests/test_login.py -v`
>
> Review suggestions (task-swarm reviewer):
> - [P0 fixed] src/auth/service.py:34 [req:2.1] — login failure did not distinguish lockout from wrong password
> - [P0 fixed] src/api/login.py:8 [security] — missing rate limit
> - [P1 unfixed] src/models/user.py:12 — email field format validation missing
> - [adv unfixed] src/auth/service.py:50 — error wrapping style (no evidence tag, auto-downgraded)
>
> validator rounds:
> - g3-r1: fail — fail signature 4a2b3c1d8e9f
> - g3-r2: pass
```

---

## What requirements does

`requirements: ["x.y"]` lets the validator, when running tests, map "test pass / fail" back to a specific SHALL clause:

- Test fails → the validation.md "按子任务的验证结果" line records `_需求：x.y_`
- `report` keeps that number when aggregating
- (When integrated with specode, the specode side runs a separate SHALL↔test check in the acceptance phase; standalone mode does not involve this)

---

## Choosing between needs and writes

- **`needs`**: expresses a **non-file-conflict** ordering dependency (e.g. "the service layer waits for the data layer to build its interfaces"). It references another `task_group id`; this group unlocks only once the upstream is `done`, and if the upstream is `failed` this group becomes `blocked: upstream failed`.
- **`writes` conflict**: auto-detected by the scheduler — groups with overlapping writes never run at the same time, no `needs` needed.
- Combined: only groups that have no `needs` and disjoint writes truly run concurrently.
