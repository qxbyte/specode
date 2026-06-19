---
description: Use when writing or understanding task-swarm's pipeline.yml — the primary orchestration format (YAML subset + schema).
---

# pipeline.yml — task-swarm orchestration format

pipeline.yml is task-swarm's **primary orchestration format** (it replaces the legacy markdown `tasks.md`). Start a run with `task_swarm.py init --pipeline <file>`.

## Restricted YAML subset

task-swarm ships its own stdlib parser supporting only a subset of YAML:

- **Supported**: block map (2-space indent), block list (`- `), flow list (`[a, b]`), single-line scalar (str / int / `true` / `false` / null), single/double-quoted strings, `#` comments.
- **Not supported (errors out, with line number + construct name)**: block scalar (`|` / `>`), flow map (`{k: v}`), anchors / aliases (`&` / `*`), multi-document (`---`), tags (`!!`), nested flow.
- bool accepts only `true` / `false`; `yes` / `no` / `on` / `off` are treated as strings.

## Schema

```yaml
version: 1
run:
  spec_id: user-login        # optional
  max_parallel: 4            # optional, default 4
  max_rounds: 6              # optional, default 6
task_groups:                 # required, >=1 (= semantic task groups)
  - id: g1                   # required, unique
    name: "Q01 API rework"   # required
    needs: []                # optional; references other task_group ids (inter-group dependency)
    review:                  # optional, default {reviewer: true, validator: true}; effective per-group from M3
      reviewer: true
      validator: true
    tasks:                   # required, >=1 (= task points)
      - id: g1.1             # required, unique
        title: "edit controller"  # required
        writes: [src/a.py]   # required (coder), >=1; file conflict -> concurrency scheduling basis
        reads:  [src/base.py] # optional
        requirements: ["1.1"] # optional; requirement traceability
```

## Scheduling semantics (M3 cross-group concurrency)

task-swarm drives task groups concurrently; two rules decide which groups may run together in a round (`plan`'s `schedule.runnable`):

- **`needs` (inter-group dependency, topological unlock)**: `needs: [g1]` means this group waits until `g1` reaches a terminal state (`done`) before it can start. `needs` must reference an existing `task_group id` (otherwise the schema reports `needs unknown group`); if an upstream group is `failed`, the downstream group becomes `blocked` (`upstream failed`). A group with no `needs` is runnable from the start.
- **`writes` disjoint across concurrent groups**: the scheduler takes the union of all task `writes` per group; if a group's writes union intersects the writes of a **currently running group**, that group becomes `blocked` (`writes conflict with running group`) and only becomes runnable in a later round, once the conflicting group finishes. Thus groups with a file conflict are naturally serialized, while non-conflicting groups run concurrently automatically — you don't hand-write dependencies to express file mutual exclusion, but you can still use `needs` to force ordering (for non-file-conflict reasons).
- Total concurrency is additionally capped by `run.max_parallel` (default 4).
- `init --serial-validation` further makes the validator globally serialized (only one group in validation/v-fix at a time), for testing scenarios with shared resources / port conflicts — it does not affect coding concurrency.

## Usage

```sh
task_swarm.py init --pipeline pipeline.yml --workdir <project root> [--serial-validation]
```

On schema validation failure or YAML out-of-bounds → exit code 1 + per-item errors, no run created.

> Note: the `review` field is currently (M2) only parsed and temporarily honored via the global `--skip-validator`; per-task-group effect lands in a later milestone. pipeline.yml is the **only input format** (the markdown `tasks.md` path was removed in M3).
