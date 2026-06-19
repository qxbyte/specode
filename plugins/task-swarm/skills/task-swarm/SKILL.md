---
name: task-swarm
description: Use when driving the task-swarm multi-agent orchestrator standalone — reading a requirement/design doc, generating a pipeline.yml, then running the fork → review → validate loop to complete a multi-task implementation. Trigger words — task-swarm, concurrent task execution, pipeline.yml orchestration, multi-coder fork.
---

# task-swarm standalone orchestration SKILL

## §0 Who you are

The lead agent = task-swarm's **orchestrator + planner**. task-swarm provides four things:
the pipeline.yml orchestration format, the state-machine CLI (`task_swarm.py`), the sub-agent role
definitions (coder/reviewer/validator), and report rendering.

The CLI **only guards 4 points of mechanical integrity**; all other orchestration judgment is yours, and the CLI does not constrain your thinking:
1. schema validation (pipeline.yml format is legal)
2. agent_key consistency (state machine and artifacts line up)
3. advance artifact completeness / format checks
4. atomic writes + blocking manual edits to controlled files

task-swarm **runs standalone and does not depend on specode**. If specode is also installed, the specode
side delegates into it — but that is still specode calling task-swarm's standalone interface, not reverse coupling.

### Delegated mode (when integrated by an upper-layer spec workflow)

When delegated by an upper-layer spec workflow, `init` additionally carries `--spec-id <id>` / `--spec-dir <dir>`,
two **optional traceback parameters** (already supported, see §2 / commands), used only to tag this run to its source
requirement for report traceback; task-swarm's own behavior, state persist location, and state machine are unchanged.
After the run's `resolve` finalizes, the calling lead agent (per its own workflow's rules) decides the next step —
task-swarm neither perceives nor drives the caller's subsequent phases.

## §1 Standalone flow overview (7 steps)

1. **Take the requirement**: design.md / requirements / superpowers plan / bare requirement / an already-written pipeline.yml
2. **Act as planner to generate pipeline.yml** (§2); if the input is already a `.yml` and passes schema → skip this step
3. `init --pipeline <yml> --workdir <project root>` to get a `run_id` (add `--serial-validation` when tests share resources/ports)
4. `plan --run <id>` returns the **set of runnable groups** → in the **same message** fork all coders of those groups (total concurrency ≤ `max_parallel`, copy verbatim the agent_key plan gives you)
5. **Each group waits for all in-flight Tasks ✓ completed** (mechanical discipline, §4) → `advance --run <id> --group <gid> --phase <p>`
6. `writeback --run <id> --group <gid>` (finalize this group) → back to step 4; once `needs` is satisfied, downstream groups unlock into runnable, until all groups are done
7. All groups done → `resolve --run <id>` to finalize → `report --run <id>` to produce the report

All `task_swarm.py` calls go through the `run.sh` wrapper (see the commands/swarm.md template).

## §2 Lead agent as planner — generate a compliant pipeline.yml

- Read the requirement doc and understand what to build. When you need the codebase's current state, **fork an `Explore` sub-agent to investigate**,
  but **you** synthesize the findings into the yml — the planner role is yours, not the sub-agent's.
- Split into `task_group`s (semantic task groups); the task points within each group obey:
  - `@writes` (`writes:` in the yml) must not intersect across **concurrent-eligible groups**; conflicting files must be serialized, expressed via `needs` topology
  - granularity 30min–2h to complete; split anything too large; do not hard-bind dependencies when work can run concurrently
  - each task group is paired with a reviewer + validator (pushed down to the task group; refinement in later milestones)
- **Write the format per `references/pipeline-yaml.md`, not from memory** (a restricted YAML subset; see that doc for pitfalls)
- After writing, run `init --pipeline` to trigger schema validation; on errors, fix the yml per the hints and retry (**self-fix loop**, until init succeeds)

## §3 Roles / state machine / artifact schema / deadloop guard

→ `references/task-swarm.md` (before acting, at least skim the TOC + §3 state machine + §9 CLI quick reference).
**Do not infer advance/writeback failure handling from memory** — the details are all in references.

## §4 Mechanical discipline (maps to the CLI's 4 guard points; violating it causes chaos)

- **Before advance you must wait for all the group's forked Tasks ✓ completed**; no streaming/running Bash may `advance --group <gid>`.
  When unsure, call `plan --run <id>`; if it returns a `*-waiting` action, return to waiting.
- **Do not invent agent_key**: you must use the canonical names plan gives you (`coder-{gid}-s{n}-r1`, `reviewer-{gid}-r1`, `validator-{gid}-r1`, `coder-vfix-{gid}-r{R}-f{I}`, etc., where gid is the group id such as g1); do not make up `coder-fix-xxx`.
- **result.md missing STATUS** → re-fork the **same-named** agent (clear its outbox first); **never hand-patch STATUS** (a missing STATUS usually means the subagent exited early and the code was not flushed to disk).
- **Do not manually edit controlled files** (state.json / outbox artifacts) — the CLI will exit 2 to block it.

## §5 Exception exits

coder STATUS=failed/blocked, writeback out-of-bounds, `failed-deadloop` (3 consecutive rounds with the same fail signature)
→ **stop the loop, report to the user, wait for user intervention; do not auto-retry**. See `references/task-swarm.md` §3 / §8.

## §6 No-specode-dependency declaration

This SKILL does not reference any specode session script, selector, or acceptance stage. State persists to
`<workdir>/.task-swarm/runs/<run_id>/`. Standalone mode has no spec-lock concept and no session gate —
the user can trigger it directly with `/task-swarm:swarm <requirement doc>`.
