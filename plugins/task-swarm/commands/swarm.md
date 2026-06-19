---
description: Standalone task-swarm multi-agent orchestration — split requirements/pipeline.yml into task groups, fork coders, run per-group reviewer+validator loops (state.json is the single source of truth)
argument-hint: "[<requirements.md | pipeline.yml>] [--max-parallel N] [--max-rounds N]"
---

## ⛔ Required pre-reading (do not skip)

Before acting, Read **this plugin's own** `skills/task-swarm/SKILL.md` (standalone persona + 7-step flow + planner guidance).
Operational details live in references:
- pipeline.yml orchestration format → `references/pipeline-yaml.md`
- roles / state machine / product schema / deadloop protection / CLI quick-ref → `references/task-swarm.md` (at least scan TOC + §3 + §9)

**Do not guess from memory** how plan output is parsed / what to do when advance fails / what to do when writeback goes out of bounds — all covered in references.

## Entry routing (standalone)

The first positional arg in `$ARGUMENTS` decides the path:

- **A `pipeline.yml`** (or any .yml that passes schema validation) → power-user already hand-wrote the orchestration → skip the planner, go straight to step 2 init.
- **A requirements doc** (design.md / requirements / superpowers plan / bare .md) → first act as **lead agent doubling as planner**:
  per SKILL.md §2 read the requirements → produce `pipeline.yml` (fork an `Explore` subagent when you need to inspect the codebase, then you synthesize) →
  persist to `<project-root>/.task-swarm/pipeline.yml` → then step 2 init.
- **No arg / ambiguous** → ask the user in chat for a requirements doc or pipeline.yml path; do not invent one.

> task-swarm is standalone: no session / lock concept, the user can trigger it directly. State persists under `<workdir>/.task-swarm/runs/`.

## Plugin-root resolution (prefix every task_swarm.py call with this)

`$CLAUDE_PLUGIN_ROOT` (CodeBuddy: `$CODEBUDDY_PLUGIN_ROOT`) is **not guaranteed to be set** in Bash calls the skill emits (the host only exports it to hook/MCP subprocesses); when empty, the old form expands to `/scripts/run.sh` → `Exit 127`. So **every** `task_swarm.py` command first resolves the root: use the env var if set, otherwise `find` the newest cached version (`sort -V | tail -1`, **never hard-code a version**). Use `find`, not a shell glob — an unmatched glob aborts with `no matches found` under zsh and `2>/dev/null` won't catch it. Shell state is not preserved between Bash calls, so re-resolve every time:

```sh
R="${CLAUDE_PLUGIN_ROOT:-$CODEBUDDY_PLUGIN_ROOT}"; [ -f "$R/scripts/run.sh" ] || R="$(find "$HOME/.claude/plugins/cache" "$HOME/.codebuddy/plugins/cache" -path '*/task-swarm/*/scripts/run.sh' 2>/dev/null | sort -V | tail -1)"; R="${R%/scripts/run.sh}"
```

## Step 2: init

```sh
R="${CLAUDE_PLUGIN_ROOT:-$CODEBUDDY_PLUGIN_ROOT}"; [ -f "$R/scripts/run.sh" ] || R="$(find "$HOME/.claude/plugins/cache" "$HOME/.codebuddy/plugins/cache" -path '*/task-swarm/*/scripts/run.sh' 2>/dev/null | sort -V | tail -1)"; R="${R%/scripts/run.sh}"
sh "$R/scripts/run.sh" "$R/scripts/task_swarm.py" \
   init --pipeline "<absolute path to pipeline.yml>" --workdir "<project root>" \
   [--project-root "<code root>"] [--spec-id <id>] [--skip-validator] [--serial-validation]
```

- `--pipeline`: absolute path to pipeline.yml, the **only input** (semantic task groups + cross-group `needs` deps + per-group task `writes`).
- `--workdir`: state persist root (state root = `<workdir>/.task-swarm/runs/`). Defaults to current cwd; in standalone mode use the project root.
- `--project-root` (optional): root of the code being changed (defaults to `--workdir`).
- `--skip-validator`: manual-acceptance mode — after review/p0-fix, skip validation/v-fix and writeback directly.
- `--serial-validation`: make the **validator globally serial** under cross-group concurrency (only one group's validation/v-fix runs at a time). Add this when tests share resources / clash on ports.
- init reports "no task groups resolved" → pipeline.yml format is wrong; fix per `references/pipeline-yaml.md` and retry.
- Once you get `{run_id, run_dir, groups, skip_validator}`, move to step 3.

## Step 3: the 7-step loop (plan → fork → wait for all to complete → advance → writeback → resolve → report)

Every `task_swarm.py` subcommand uses the same run.sh wrapper template (always run the `R=...` plugin-root resolution prefix above first, then `sh "$R/scripts/run.sh" "$R/scripts/task_swarm.py" <subcmd> ...`):

1. `init` (done in step 2)
2. `plan --run <run_id>` returns the **multi-group concurrent schedule**: `{schedule:{done,running,runnable,blocked,failed}, actions:[...], serial_validation, max_parallel}`. `actions` lists the `fork` set for each runnable/advanceable group; `schedule.runnable` is the groups startable now, `blocked` gives the reason (`needs` unmet / `writes` conflicts with a running group).
3. `fork`: in a single message, fork the coders for **all runnable groups** in `actions` together (copy each `fork[].agent_key` **verbatim**, **never** invent `coder-fix-xxx`). Total concurrency is bounded by `max_parallel` — overflow groups carry to the next round.
4. **Wait for all in-flight Tasks to be ✓ completed before you advance** (hard constraint; violating it breaks things):
   - You must see every forked Task ✓ completed in the teammates UI; any ⠙ streaming / ⠴ running Bash blocks advance
   - **Do not** judge completion from verbal reports — only a subagent's own Task tool returning ✓ counts
   - When unsure, call `plan --run <run_id>`; if it returns `coding-waiting`/`p0-fix-waiting`/`v-fix-waiting`, go back to waiting
5. `advance --run <run_id> --group <gid> --phase <p>` (gid is a string like `g1`) advances **that group's** sub state machine
6. `writeback --run <run_id> --group <gid>` (finalize this group, does not write tasks.md)
7. All groups done → `resolve --run <run_id>` to finalize → `report --run <run_id>` for the report

> plan's `schedule` is the concurrency-driving core: the lead agent forks multiple groups from `runnable` in one message, `running` are the groups in flight, `blocked` (`needs` unmet / `writes` conflicts with a running group) enter runnable only on a later plan once unblocked.

Full spec in `references/task-swarm.md`.

## heartbeat (optional for long runs)

The lead agent may call this every 5 minutes / after each subagent finishes to refresh `last_activity_at`:

```sh
R="${CLAUDE_PLUGIN_ROOT:-$CODEBUDDY_PLUGIN_ROOT}"; [ -f "$R/scripts/run.sh" ] || R="$(find "$HOME/.claude/plugins/cache" "$HOME/.codebuddy/plugins/cache" -path '*/task-swarm/*/scripts/run.sh' 2>/dev/null | sort -V | tail -1)"; R="${R%/scripts/run.sh}"
sh "$R/scripts/run.sh" "$R/scripts/task_swarm.py" \
   heartbeat --run <run_id>
```

## Terminology: reviewer severity vs validator fail (easily confused)

| Concept | Source | Triggers fix loop? |
|---|---|---|
| **P0 (with evidence tag)** | reviewer `review.md` `## P0`, must carry `[req:x.y]`/`[security]`/`[contract]` | ✓ p0-fix (one round only, no re-review, goes straight to validation) |
| **P0 (no evidence tag)** | reviewer `## P0` missing the tag | downgraded to advisory → ✗ not fixed |
| **P1 / P2** | reviewer `## P1`/`## P2` | ✗ advisory, not fixed |
| **validator fail** | validator `validation.md` `## 判定 = fail` | ✓ v-fix loops until pass; 3 consecutive rounds with the same fail signature → `failed-deadloop` |

The validator **does not emit P0/P1/P2 tags**; its fix_targets are all "task not finished", and a fail must be fixed.
If the user asks "can I skip it" → by design no; the only way is to abort the run + edit pipeline.yml to remove that task and re-init.

## Correct response when advance reports "result.md missing STATUS / parse failure"

- **Keep** the incomplete result.md (it's evidence, don't Edit it) → `status --run <run_id>` to check whether it's still in_flight
- in_flight → wait for real completion; if >10 minutes with no finalize → esc to cancel + report to user
- Not in_flight but the product is incomplete → re-fork the **same-named** agent (first `rm -rf agents/<key>/outbox/*`); **never** invent a new name, **never** hand-patch STATUS

## Failure exits

coder STATUS=failed/blocked, writeback out of bounds, `failed-deadloop` → stop the loop, report to the user, wait for intervention, **do not auto-retry**. See `references/task-swarm.md` §3 / §8.
