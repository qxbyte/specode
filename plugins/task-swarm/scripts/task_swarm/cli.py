"""task_swarm.cli — task-swarm 编排主 CLI（详见 references/task-swarm.md）。

由 `scripts/task_swarm.py` launcher 调用（launcher 负责 sys.path 注入）。
实现拆到同包内：

    _state.py      per-group 子状态机 + state.json 单一事实源 + 死循环检测
    _pipeline.py   pipeline.yml schema 校验 + 组级调度状态映射
    _schedule.py   needs 拓扑 + writes 不相交并发调度
    _outbox.py     coder/reviewer/validator 三类产物 schema 校验
    _prompt.py     各 subagent 角色的 prompt 渲染

子命令：
    init      --pipeline <abs> [--workdir <dir>] [--project-root <dir>] [--spec-id <id>]
              [--max-parallel N] [--max-rounds N] [--session <id>] [--skip-validator]
              [--serial-validation]
    status    --run <run_id>
    plan      --run <run_id>
    advance   --run <run_id> --group <gid> --phase <coding|review|p0-fix|validation|v-fix> [--round <n>]
    writeback --run <run_id> --group <gid>
    heartbeat --run <run_id>
    resolve   --run <run_id> [--abort]

主代理通过 plan→fork→advance 循环驱动：plan 给出多组并发调度，主代理同 message
fork 多组 coder（总并发受 max_parallel），各组等齐后 `advance --group <gid>`。
本脚本只负责"确定性查询 / 状态推进 / outbox 解析"。

stdlib-only。
"""
from __future__ import annotations

import argparse
import json
import os
import random
import string
import sys
import time
from pathlib import Path
from typing import Any, Optional

from task_swarm._state import StateMachine, StageEntry, GroupState, _now_iso  # noqa: E402
from task_swarm._schedule import compute_schedule  # noqa: E402
from task_swarm._outbox import (  # noqa: E402
    ParseError, parse_coder_result, parse_reviewer_review, parse_validator_validation,
)
from task_swarm._prompt import (  # noqa: E402
    render_coder_prompt, render_reviewer_prompt, render_validator_prompt,
)
from task_swarm._pipeline_yaml import parse as _yaml_parse, PipelineYamlError  # noqa: E402
from task_swarm._pipeline import validate as _pipeline_validate, to_group_states as _pipeline_to_group_states  # noqa: E402
from task_swarm._report import render_report  # noqa: E402


# -------------------------------------------------------------------------
# 工具
# -------------------------------------------------------------------------

def _gen_run_id() -> str:
    """YYYYMMDD-HHMMSS-<6 位随机>，与 spec-mode 0.3.0 一致。"""
    ts = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    rand = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"{ts}-{rand}"


def _emit(payload: Any) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _runs_root_for(workdir: Path) -> Path:
    """状态根:<workdir>/.task-swarm/runs/。"""
    return workdir / ".task-swarm" / "runs"


# -------------------------------------------------------------------------
# Registry — v0.9 痛点 #12: cwd 漂移让 plan/advance/writeback/resolve fail.
# User-wide ~/.task-swarm/registry.json maps run_id → run_dir, populated
# by init, consulted by every other subcommand. Lets the user `cd` anywhere
# after init and still reach the run by its id alone.
# -------------------------------------------------------------------------


def _registry_path() -> Path:
    home = Path(os.environ.get("HOME") or Path.home())
    return home / ".task-swarm" / "registry.json"


def _registry_read() -> dict:
    p = _registry_path()
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (ValueError, OSError):
        return {}


def _registry_register(run_id: str, run_dir: Path) -> None:
    """Atomic write: load → mutate → atomic replace, so concurrent inits
    in different workdirs don't lose each other's entries."""
    p = _registry_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    data = _registry_read()
    data[run_id] = {"run_dir": str(Path(run_dir).resolve())}
    # tempfile then os.replace = atomic on POSIX
    import tempfile as _tempfile

    fd, tmp = _tempfile.mkstemp(dir=str(p.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            fd = -1
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)
    finally:
        if fd >= 0:
            try:
                os.close(fd)
            except OSError:
                pass
        if os.path.exists(tmp):
            os.remove(tmp)


def _find_run_dir(run_id: str) -> Path:
    """定位 run 目录,不依赖任何 specode session。

    Resolution order (v0.9 痛点 #12 — cwd drift fix):
      1. run_id 本身是已存在的绝对/相对路径(含 state.json) → 直接用
      2. $TASK_SWARM_WORKDIR env override → <env>/.task-swarm/runs/<run_id>/
      3. ~/.task-swarm/registry.json lookup (populated by init)
      4. <cwd>/.task-swarm/runs/<run_id>/
      5. 向上递归 cwd 的父目录,找 .task-swarm/runs/<run_id>/

    Step 3 entries are validated — a stale entry (run_dir was deleted) falls
    through to step 4/5 so a re-created run under a moved workdir wins.
    """
    p = Path(run_id)
    if p.exists() and (p / "state.json").exists():
        return p.resolve()

    # (2) $TASK_SWARM_WORKDIR env override
    env_wd = os.environ.get("TASK_SWARM_WORKDIR")
    if env_wd:
        cand = Path(env_wd) / ".task-swarm" / "runs" / run_id
        if (cand / "state.json").is_file():
            return cand.resolve()

    # (3) registry lookup, validated
    entry = _registry_read().get(run_id)
    if isinstance(entry, dict):
        run_dir = entry.get("run_dir")
        if isinstance(run_dir, str):
            cand = Path(run_dir)
            if (cand / "state.json").is_file():
                return cand.resolve()
            # stale — fall through

    # (4) + (5) cwd-scan fallback (legacy back-compat)
    cwd = Path.cwd()
    for base in [cwd, *cwd.parents]:
        cand = base / ".task-swarm" / "runs" / run_id
        if (cand / "state.json").is_file():
            return cand.resolve()
    return cwd / ".task-swarm" / "runs" / run_id


# -------------------------------------------------------------------------
# init
# -------------------------------------------------------------------------

_ACTIVE_STATUSES = {"running", "in_progress", "init", None, ""}


def _find_active_runs_for_spec(spec_id: str) -> list[tuple[str, Path, str]]:
    """Scan registry for runs sharing this spec_id that are still active.

    Returns ``[(run_id, run_dir, status), ...]``. A run is *active* when its
    ``state.json`` has ``failed_status`` either missing or not in
    ``{"done", "failed", "aborted"}``. Stale registry entries (run_dir
    deleted / state.json malformed) are silently skipped so a fresh init
    after a manual ``rm -rf`` doesn't trip the dedupe.

    v0.8.0 (M7): used by ``cmd_init`` to detect "已经有同 spec_id 的活跃
    run" before silently creating another, fixing the試跑场景"忘了已经
    init 过一次，又调 init → 出现 2 个互不知道的 run，registry 累积 stale"。
    """
    if not spec_id:
        return []
    found: list[tuple[str, Path, str]] = []
    for rid, entry in _registry_read().items():
        run_dir_str = (entry or {}).get("run_dir") if isinstance(entry, dict) else None
        if not run_dir_str:
            continue
        run_dir = Path(run_dir_str)
        state_path = run_dir / "state.json"
        if not state_path.is_file():
            continue  # stale registry entry
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if state.get("spec_id") != spec_id:
            continue
        status = state.get("failed_status") or state.get("status") or "running"
        if status in {"done", "failed", "aborted"}:
            continue  # not active
        found.append((rid, run_dir, status))
    return found


def _mark_run_aborted(run_dir: Path, reason: str) -> None:
    """Mark a state.json as aborted in place (atomic; v0.8.0 dedupe support)."""
    state_path = run_dir / "state.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["failed_status"] = "aborted"
        events = state.get("events") or []
        events.append({"type": "abort", "reason": reason, "at": _now_iso()})
        state["events"] = events
        # Atomic write (same pattern as registry).
        import tempfile as _tempfile
        fd, tmp = _tempfile.mkstemp(dir=str(state_path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                fd = -1
                json.dump(state, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, state_path)
        finally:
            if fd >= 0:
                try:
                    os.close(fd)
                except OSError:
                    pass
            if os.path.exists(tmp):
                os.remove(tmp)
    except (ValueError, OSError) as exc:
        sys.stderr.write(f"task-swarm: failed to abort stale run {run_dir}: {exc}\n")


def cmd_init(args: argparse.Namespace) -> int:
    if not getattr(args, "pipeline", None):
        sys.stderr.write("必须给 --pipeline <yml>（markdown --tasks 路径已在 M3 移除）\n")
        return 1
    pipeline_src = Path(args.pipeline).resolve()
    if not pipeline_src.exists():
        sys.stderr.write(f"pipeline.yml 不存在：{pipeline_src}\n")
        return 1
    try:
        data = _yaml_parse(pipeline_src.read_text(encoding="utf-8"))
    except PipelineYamlError as e:
        sys.stderr.write(f"pipeline.yml 解析失败：{e}\n")
        return 1
    errs = _pipeline_validate(data)
    if errs:
        sys.stderr.write("pipeline.yml schema 校验失败：\n" + "\n".join(f"  - {e}" for e in errs) + "\n")
        return 1
    group_dicts = _pipeline_to_group_states(data)
    if not group_dicts:
        sys.stderr.write("pipeline.yml 未解析出任何 task_group\n")
        return 1
    run_meta = data.get("run") or {}

    workdir = Path(args.workdir).resolve() if args.workdir else Path.cwd()
    spec_id = args.spec_id or run_meta.get("spec_id") or None

    # v0.8.0 M7: dedupe — block silent duplicate init when an active run for
    # the same spec_id already exists (else registry quickly fills with
    # stale entries the user never realised were created).
    on_existing = getattr(args, "on_existing", "error") or "error"
    if spec_id:
        existing = _find_active_runs_for_spec(spec_id)
        if existing:
            if on_existing == "error":
                lines = [
                    f"task-swarm init: spec_id={spec_id!r} 已有 {len(existing)} 个活跃 run；",
                    "重复 init 会产生 stale registry 项 + 浪费 .task-swarm/runs/ 空间。",
                    "已有活跃 run:",
                ]
                for rid, rdir, status in existing:
                    lines.append(f"  - {rid} status={status} dir={rdir}")
                lines.append("")
                lines.append("处理方式（选一加到 init 命令）：")
                lines.append("  --on-existing resume       → 不新建，返回最新 active run 信息")
                lines.append("  --on-existing abort-old    → 旧 run 标 aborted 后新建")
                lines.append("  --on-existing force-new    → 忽略，新建（旧 run 继续占空间，不推荐）")
                sys.stderr.write("\n".join(lines) + "\n")
                return 1
            elif on_existing == "resume":
                # Pick the most recent active run (registry is dict, no order;
                # use the run_id which embeds the timestamp).
                rid, rdir, status = sorted(existing, key=lambda x: x[0])[-1]
                _emit({
                    "run_id": rid,
                    "run_dir": str(rdir),
                    "spec_id": spec_id,
                    "status": status,
                    "resumed": True,
                    "message": f"resumed existing active run for spec_id={spec_id!r}",
                })
                return 0
            elif on_existing == "abort-old":
                for rid, rdir, _ in existing:
                    _mark_run_aborted(rdir, f"superseded by re-init of spec_id={spec_id}")
                # fall through to fresh init
            elif on_existing == "force-new":
                pass  # explicit override; just init alongside
            else:
                sys.stderr.write(
                    f"未知 --on-existing 值：{on_existing}（支持：error / resume / abort-old / force-new）\n"
                )
                return 1
    spec_dir = getattr(args, "spec_dir_arg", None) or None
    project_root = str(Path(args.project_root).resolve()) if args.project_root else str(workdir)
    max_parallel = args.max_parallel if args.max_parallel else int(run_meta.get("max_parallel") or 4)
    max_rounds = args.max_rounds if args.max_rounds else int(run_meta.get("max_rounds") or 6)
    serial_validation = bool(getattr(args, "serial_validation", False)) or bool(run_meta.get("serial_validation"))
    # v0.8.0 M3: persist pipeline_end_validator flag from run-meta to state.json.
    # Schema reservation — plan/advance does not yet honor this; logic lands in
    # v0.8.1. Today it just lives on the StateMachine and is emitted by report.
    pipeline_end_validator = bool(run_meta.get("pipeline_end_validator", False))

    run_id = _gen_run_id()
    runs_root = _runs_root_for(workdir)
    run_dir = runs_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "agents").mkdir(parents=True, exist_ok=True)

    pipeline_path = str(run_dir / "pipeline.yml")
    (run_dir / "pipeline.yml").write_text(pipeline_src.read_text(encoding="utf-8"), encoding="utf-8")

    task_groups = [GroupState.from_pipeline_group(g) for g in group_dicts]

    sm = StateMachine(
        run_id=run_id,
        tasks_md="",
        run_dir=str(run_dir),
        max_parallel=max_parallel,
        max_rounds=max_rounds,
        session_id=args.session,
        workdir=str(workdir),
        spec_id=spec_id,
        spec_dir=spec_dir,
        project_root=project_root,
        pipeline_path=pipeline_path,
        task_groups=task_groups,
        serial_validation=serial_validation,
        pipeline_end_validator=pipeline_end_validator,
        started_at=_now_iso(),
        last_activity_at=_now_iso(),
        skip_validator=bool(getattr(args, "skip_validator", False)),
    )
    sm.events_append({
        "type": "init",
        "pipeline": True,
        "groups": len(task_groups),
        "serial_validation": serial_validation,
        "skip_validator": sm.skip_validator,
    })
    sm.save()
    # v0.9 痛点 #12: register so later plan/advance/writeback/resolve can
    # find the run by id alone, even from a different cwd.
    try:
        _registry_register(run_id, run_dir)
    except OSError as exc:
        # registry write failure is non-fatal — fall back to cwd scan path.
        sys.stderr.write(f"task-swarm: registry write failed: {exc}\n")

    _emit({
        "run_id": run_id,
        "run_dir": str(run_dir),
        "pipeline_path": pipeline_path,
        "workdir": str(workdir),
        "project_root": project_root,
        "spec_id": spec_id,
        "serial_validation": serial_validation,
        "groups": [{"id": g.id, "name": g.name, "needs": g.needs, "writes": g.writes}
                   for g in task_groups],
    })
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    try:
        run_dir = _find_run_dir(args.run)
    except FileNotFoundError as e:
        sys.stderr.write(f"{e}\n")
        return 1
    sm = StateMachine.load(run_dir)
    sched = compute_schedule([g.sched_view() for g in sm.task_groups])
    payload = {
        "run_id": sm.run_id,
        "schedule": sched,
        "serial_validation": sm.serial_validation,
        "groups": [{"id": g.id, "name": g.name, "status": g.status, "phase": g.phase,
                    "round": g.round, "needs": g.needs,
                    "coder_in_flight": list(g.coder_in_flight),
                    "p0_in_flight": list(g.p0_in_flight),
                    "validator_in_flight": g.validator_in_flight,
                    "vfix_in_flight": list(g.vfix_in_flight)}
                   for g in sm.task_groups],
        "started_at": sm.started_at,
        "last_activity_at": sm.last_activity_at,
        "completed_at": sm.completed_at,
        "failed_status": sm.failed_status,
    }
    _emit(payload)
    return 0


# -------------------------------------------------------------------------
# plan
# -------------------------------------------------------------------------


PLAN_TEMPLATES = {
    "coding-waiting": "coding phase 仍有 {n} 个 coder 未返回，等齐后再判断。",
    "coding-fork": "本 group 开始 coding。请按下面 {n} 个 coder agent_key fork（同 message 内并发）。",
    "review-fork": "本 group coder 已全部返回。请 fork **1 个** `task-swarm-reviewer`。",
    "p0-fix-fork": "reviewer 提了 {n} 个带证据 P0。请按 P0 涉及文件 fork **{n}** 个 `task-swarm-coder`（p0-fix）。注意：reviewer 修复**只触发一次**，不 re-review。",
    "validation-fork": "请 fork **1 个** `task-swarm-validator`。",
    "validation-fork-after-p0": "p0-fix coder 已返回。请 fork **1 个** `task-swarm-validator`。",
    "writeback": "validator pass。请调 `task_swarm.py writeback --run {run} --group {g}` finalize 本组，下游组 needs 满足后解锁。",
    "v-fix-fork": "validator fail。请按 validation.md 的 fix_targets 各文件 fork **{n}** 个 `task-swarm-coder`（v-fix）。注意：validator fail 循环修复直到 pass。本轮是 {g}-r{r}。",
    "validation-after-vfix": "v-fix coder 已返回。请 fork **1 个** `task-swarm-validator` 验证。",
    "deadloop": "⚠️ 死循环检测：{g} 已连续 3 轮同一 fail 签名。建议停止本 group，向用户报告 `failed-deadloop`，让用户介入。",
    "all-done": "全部 group 已完成。请调 `task_swarm.py resolve` 收尾，再 `report` 出报告。",
}


def _plan_for_group(sm: StateMachine, gs: "GroupState") -> dict:
    """根据单个 group 的子状态机推导其下一步建议（确定性查询，不改 state）。"""
    run_dir = Path(sm.run_dir)
    g = _items_as_stages(gs)

    if gs.status == "failed-deadloop":
        return {"group": gs.id, "phase": gs.phase, "action": "deadloop",
                "message": PLAN_TEMPLATES["deadloop"].format(g=gs.id), "fork": []}

    # phase=init：尚未开始本 group coding
    if gs.phase == "init":
        forks = []
        for s in g:
            key = f"coder-{gs.id}-s{s.number}-r1"
            forks.append({"agent": "task-swarm-coder", "agent_key": key,
                          "task_md": str(run_dir / "agents" / key / "task.md"),
                          "stage": s.number, "writes": s.writes})
        return {"group": gs.id, "phase": "coding", "action": "coding-fork",
                "message": PLAN_TEMPLATES["coding-fork"].format(n=len(forks)), "fork": forks}

    # coding 进行中
    if gs.phase == "coding":
        if gs.coder_in_flight and not gs.coder_done:
            forks = []
            for s in g:
                key = f"coder-{gs.id}-s{s.number}-r1"
                forks.append({"agent": "task-swarm-coder", "agent_key": key,
                              "task_md": str(run_dir / "agents" / key / "task.md"),
                              "stage": s.number, "writes": s.writes})
            return {"group": gs.id, "phase": "coding", "action": "coding-fork",
                    "message": PLAN_TEMPLATES["coding-fork"].format(n=len(forks)),
                    "fork": forks, "in_flight": list(gs.coder_in_flight)}
        if gs.coder_in_flight:
            return {"group": gs.id, "phase": "coding", "action": "coding-waiting",
                    "message": PLAN_TEMPLATES["coding-waiting"].format(n=len(gs.coder_in_flight)),
                    "fork": [], "in_flight": list(gs.coder_in_flight)}
        key = f"reviewer-{gs.id}-r1"
        return {"group": gs.id, "phase": "review", "action": "review-fork",
                "message": PLAN_TEMPLATES["review-fork"],
                "fork": [{"agent": "task-swarm-reviewer", "agent_key": key,
                          "task_md": str(run_dir / "agents" / key / "task.md")}]}

    # review
    if gs.phase == "review":
        if not gs.reviewer_done:
            key = f"reviewer-{gs.id}-r1"
            return {"group": gs.id, "phase": "review", "action": "review-fork",
                    "message": PLAN_TEMPLATES["review-fork"],
                    "fork": [{"agent": "task-swarm-reviewer", "agent_key": key,
                              "task_md": str(run_dir / "agents" / key / "task.md")}]}
        if gs.p0_pending:
            files = []
            for p in gs.p0_pending:
                f = (p.get("file_hint") or "unknown").strip()
                if f not in files:
                    files.append(f)
            forks = []
            for i, f in enumerate(files):
                key = f"coder-p0fix-{gs.id}-r1-f{i}"
                forks.append({"agent": "task-swarm-coder", "agent_key": key,
                              "task_md": str(run_dir / "agents" / key / "task.md"), "file": f})
            return {"group": gs.id, "phase": "p0-fix", "action": "p0-fix-fork",
                    "message": PLAN_TEMPLATES["p0-fix-fork"].format(n=len(forks)), "fork": forks}
        key = f"validator-{gs.id}-r1"
        return {"group": gs.id, "phase": "validation", "action": "validation-fork",
                "message": PLAN_TEMPLATES["validation-fork"],
                "fork": [{"agent": "task-swarm-validator", "agent_key": key,
                          "task_md": str(run_dir / "agents" / key / "task.md")}]}

    # p0-fix
    if gs.phase == "p0-fix":
        if gs.p0_in_flight and not gs.p0_done:
            files = []
            for p in gs.p0_pending:
                f = (p.get("file_hint") or "unknown").strip()
                if f not in files:
                    files.append(f)
            forks = []
            for i, f in enumerate(files):
                key = f"coder-p0fix-{gs.id}-r1-f{i}"
                forks.append({"agent": "task-swarm-coder", "agent_key": key,
                              "task_md": str(run_dir / "agents" / key / "task.md"), "file": f})
            return {"group": gs.id, "phase": "p0-fix", "action": "p0-fix-fork",
                    "message": PLAN_TEMPLATES["p0-fix-fork"].format(n=len(forks)), "fork": forks}
        if gs.p0_in_flight:
            return {"group": gs.id, "phase": "p0-fix", "action": "p0-fix-waiting",
                    "message": f"p0-fix 仍有 {len(gs.p0_in_flight)} 个 coder 未返回。", "fork": []}
        key = f"validator-{gs.id}-r1"
        return {"group": gs.id, "phase": "validation", "action": "validation-fork-after-p0",
                "message": PLAN_TEMPLATES["validation-fork-after-p0"],
                "fork": [{"agent": "task-swarm-validator", "agent_key": key,
                          "task_md": str(run_dir / "agents" / key / "task.md")}]}

    # validation
    if gs.phase == "validation":
        if gs.validator_in_flight:
            target_round = gs.round if gs.round > 0 else 1
            key = f"validator-{gs.id}-r{target_round}"
            if gs.validator_history:
                msg = PLAN_TEMPLATES["validation-after-vfix"]; action = "validation-after-vfix"
            elif gs.p0_done:
                msg = PLAN_TEMPLATES["validation-fork-after-p0"]; action = "validation-fork-after-p0"
            else:
                msg = PLAN_TEMPLATES["validation-fork"]; action = "validation-fork"
            return {"group": gs.id, "phase": "validation", "action": action, "message": msg,
                    "fork": [{"agent": "task-swarm-validator", "agent_key": key,
                              "task_md": str(run_dir / "agents" / key / "task.md")}],
                    "round": target_round}
        if gs.fix_targets:
            if gs.detect_deadloop():
                return {"group": gs.id, "phase": gs.phase, "action": "deadloop",
                        "message": PLAN_TEMPLATES["deadloop"].format(g=gs.id), "fork": []}
            files = []
            for t in gs.fix_targets:
                f = (t.get("file_path") or "").strip()
                if f and f not in files:
                    files.append(f)
            forks = []
            for i, f in enumerate(files):
                key = f"coder-vfix-{gs.id}-r{gs.round + 1}-f{i}"
                forks.append({"agent": "task-swarm-coder", "agent_key": key,
                              "task_md": str(run_dir / "agents" / key / "task.md"), "file": f})
            return {"group": gs.id, "phase": "v-fix", "action": "v-fix-fork",
                    "message": PLAN_TEMPLATES["v-fix-fork"].format(n=len(forks), g=gs.id, r=gs.round + 1),
                    "fork": forks}
        return {"group": gs.id, "phase": "writeback", "action": "writeback",
                "message": PLAN_TEMPLATES["writeback"].format(run=sm.run_id, g=gs.id), "fork": []}

    # v-fix
    if gs.phase == "v-fix":
        if gs.vfix_in_flight and not gs.vfix_done:
            files = []
            for t in gs.fix_targets:
                f = (t.get("file_path") or "").strip()
                if f and f not in files:
                    files.append(f)
            forks = []
            for i, f in enumerate(files):
                key = f"coder-vfix-{gs.id}-r{gs.round}-f{i}"
                forks.append({"agent": "task-swarm-coder", "agent_key": key,
                              "task_md": str(run_dir / "agents" / key / "task.md"), "file": f})
            return {"group": gs.id, "phase": "v-fix", "action": "v-fix-fork",
                    "message": PLAN_TEMPLATES["v-fix-fork"].format(n=len(forks), g=gs.id, r=gs.round),
                    "fork": forks}
        if gs.vfix_in_flight:
            return {"group": gs.id, "phase": "v-fix", "action": "v-fix-waiting",
                    "message": f"v-fix 仍有 {len(gs.vfix_in_flight)} 个 coder 未返回。", "fork": []}
        key = f"validator-{gs.id}-r{gs.round + 1}"
        return {"group": gs.id, "phase": "validation", "action": "validation-after-vfix",
                "message": PLAN_TEMPLATES["validation-after-vfix"],
                "fork": [{"agent": "task-swarm-validator", "agent_key": key,
                          "task_md": str(run_dir / "agents" / key / "task.md")}]}

    if gs.phase == "writeback":
        return {"group": gs.id, "phase": "writeback", "action": "writeback",
                "message": PLAN_TEMPLATES["writeback"].format(run=sm.run_id, g=gs.id), "fork": []}

    if gs.phase == "error":
        return {"group": gs.id, "phase": "error", "action": "deadloop",
                "message": PLAN_TEMPLATES["deadloop"].format(g=gs.id), "fork": []}

    return {"group": gs.id, "phase": gs.phase, "action": "unknown",
            "message": f"未知 phase={gs.phase}", "fork": []}


def _materialize_next_prompt(sm: StateMachine, gs: "GroupState") -> None:
    """防御性渲染：plan 被独立调用时，确保下一阶段的 prompt 文件已就位。"""
    if gs.phase == "coding" and not gs.coder_in_flight and gs.coder_done:
        _materialize_prompt_reviewer(sm, gs)
    elif gs.phase == "review" and gs.reviewer_done and gs.p0_pending:
        _materialize_prompts_p0_fix(sm, gs)
    elif gs.phase == "review" and gs.reviewer_done and not gs.p0_pending:
        _materialize_prompt_validator(sm, gs)
    elif gs.phase == "p0-fix" and not gs.p0_in_flight and gs.p0_done:
        _materialize_prompt_validator(sm, gs)
    elif gs.phase == "validation" and not gs.validator_in_flight and gs.fix_targets:
        if not gs.detect_deadloop():
            _materialize_prompts_v_fix(sm, gs)
    elif gs.phase == "v-fix" and not gs.vfix_in_flight and gs.vfix_done:
        _materialize_prompt_validator(sm, gs)


_ACTIVE_STATUSES = ("coding", "review", "p0-fix", "validation", "v-fix", "writeback", "running")


def cmd_plan(args: argparse.Namespace) -> int:
    try:
        run_dir = _find_run_dir(args.run)
    except FileNotFoundError as e:
        sys.stderr.write(f"{e}\n")
        return 1
    sm = StateMachine.load(run_dir)
    by_id = {g.id: g for g in sm.task_groups}
    sched = compute_schedule([g.sched_view() for g in sm.task_groups])

    # 启动 runnable 组：begin_coding + 渲染 coder prompt。
    # compute_schedule 只判 runnable-vs-running，故本轮再按"已启动 writes"过滤组间互斥。
    started_writes: set = set()
    for g in sm.task_groups:
        if g.status in _ACTIVE_STATUSES:
            started_writes |= set(g.writes)
    started = []
    for gid in sched["runnable"]:
        gs = by_id[gid]
        if set(gs.writes) & started_writes:
            continue  # 与本轮已启动/在跑组 writes 冲突 → 留到下轮
        if gs.phase == "init":
            _materialize_prompts_for_coding(sm, gs)
            gs.begin_coding()
            sm.events_append({"type": "phase", "phase": "coding", "group": gs.id})
            started.append(gs.id)
            started_writes |= set(gs.writes)
    if started:
        sm.save()
        sched = compute_schedule([g.sched_view() for g in sm.task_groups])

    # 防御性渲染各活跃组的下一阶段 prompt
    for gs in sm.task_groups:
        if gs.status not in ("done", "failed", "failed-deadloop"):
            _materialize_next_prompt(sm, gs)

    # 全部组终态 → all-done
    active = [g for g in sm.task_groups if g.status not in ("done", "failed", "failed-deadloop")]
    if not active:
        _emit({"action": "all-done", "message": PLAN_TEMPLATES["all-done"],
               "schedule": sched, "serial_validation": sm.serial_validation,
               "max_parallel": sm.max_parallel, "actions": []})
        return 0

    # 为 runnable + running 组各生成下一步 action
    actions = []
    validator_emitted = False
    for gs in sm.task_groups:
        if gs.id in sched["runnable"] or gs.id in sched["running"]:
            act = _plan_for_group(sm, gs)
            if sm.serial_validation and act.get("action") in (
                    "validation-fork", "validation-fork-after-p0", "validation-after-vfix"):
                if validator_emitted:
                    act = {"group": gs.id, "phase": gs.phase, "action": "validation-waiting",
                           "message": "serial_validation：已有 validator 在跑，本组排队。", "fork": []}
                else:
                    validator_emitted = True
            actions.append(act)

    _emit({"schedule": sched, "serial_validation": sm.serial_validation,
           "max_parallel": sm.max_parallel, "actions": actions})
    return 0


def _resolve_project_root(sm: StateMachine) -> Optional[str]:
    """project_root 来自 init 时存入 state 的字段;缺省回退 workdir。"""
    return sm.project_root or sm.workdir


def _items_as_stages(gs: "GroupState") -> list[StageEntry]:
    """GroupState.items(dict) → StageEntry 列表，供 render_* 的属性访问。

    v0.9 痛点 #13: 每条 StageEntry 还要把**自己这条 item** 透传到 ``items``
    字段，否则 ``_prompt.py`` 的 ``for it in stage.items`` 循环 0 次，
    渲染出的 task.md ``## 任务清单`` 段为空 — coder 拿不到具体任务指令。
    """
    return [StageEntry(
        number=it["number"], title=it.get("title", ""),
        writes=list(it.get("writes") or []), reads=list(it.get("reads") or []),
        requirements=list(it.get("requirements") or []),
        items=[it],
    ) for it in gs.items]


def _materialize_prompts_for_coding(sm: StateMachine, gs: "GroupState") -> None:
    project_root = _resolve_project_root(sm)
    for s in _items_as_stages(gs):
        render_coder_prompt(
            stage=s,
            run_dir=Path(sm.run_dir),
            run_id=sm.run_id,
            spec_id=sm.spec_id or "",
            spec_dir=sm.spec_dir or "",
            group=gs.id,
            round_=1,
            mode="initial",
            project_root=project_root,
        )


def _materialize_prompt_reviewer(sm: StateMachine, gs: "GroupState") -> None:
    run_dir = Path(sm.run_dir)
    stages = _items_as_stages(gs)
    coder_outboxes = [
        run_dir / "agents" / f"coder-{gs.id}-s{s.number}-r1" / "outbox" / "result.md"
        for s in stages
    ]
    render_reviewer_prompt(
        group_stages=stages,
        coder_outboxes=coder_outboxes,
        run_dir=run_dir,
        run_id=sm.run_id,
        spec_id=sm.spec_id or "",
        spec_dir=sm.spec_dir or "",
        group=gs.id,
        round_=1,
        project_root=_resolve_project_root(sm),
    )


def _materialize_prompts_p0_fix(sm: StateMachine, gs: "GroupState") -> None:
    project_root = _resolve_project_root(sm)
    stages = _items_as_stages(gs)
    files: list[str] = []
    for p in gs.p0_pending:
        f = (p.get("file_hint") or "unknown").strip()
        if f not in files:
            files.append(f)
    for i, f in enumerate(files):
        match_stage = None
        for s in stages:
            if f in s.writes:
                match_stage = s
                break
        if match_stage is None and stages:
            match_stage = stages[0]
        if match_stage is None:
            continue
        render_coder_prompt(
            stage=match_stage,
            run_dir=Path(sm.run_dir),
            run_id=sm.run_id,
            spec_id=sm.spec_id or "",
            spec_dir=sm.spec_dir or "",
            group=gs.id,
            round_=1,
            mode="p0-fix",
            fix_targets=[p for p in gs.p0_pending
                         if (p.get("file_hint") or "").strip() == f],
            file_idx=i,
            project_root=project_root,
        )


def _materialize_prompts_v_fix(sm: StateMachine, gs: "GroupState") -> None:
    project_root = _resolve_project_root(sm)
    stages = _items_as_stages(gs)
    files: list[str] = []
    for t in gs.fix_targets:
        f = (t.get("file_path") or "").strip()
        if f and f not in files:
            files.append(f)
    if not files:
        files = ["unknown"]
    for i, f in enumerate(files):
        match_stage = None
        for s in stages:
            if f in s.writes:
                match_stage = s
                break
        if match_stage is None and stages:
            match_stage = stages[0]
        if match_stage is None:
            continue
        ftargets = [t for t in gs.fix_targets
                    if (t.get("file_path") or "").strip() == f]
        # round_ 用 gs.round（begin_v_fix 已自增，vfix_in_flight 用的就是当前 gs.round）。
        render_coder_prompt(
            stage=match_stage,
            run_dir=Path(sm.run_dir),
            run_id=sm.run_id,
            spec_id=sm.spec_id or "",
            spec_dir=sm.spec_dir or "",
            group=gs.id,
            round_=gs.round,
            mode="v-fix",
            fix_targets=ftargets,
            file_idx=i,
            project_root=project_root,
        )


def _materialize_prompt_validator(sm: StateMachine, gs: "GroupState") -> None:
    if gs.phase == "v-fix":
        next_round = gs.round + 1
    elif gs.phase in ("review", "p0-fix"):
        next_round = 1
    else:
        next_round = gs.round if gs.round > 0 else 1
    prev_validation: Optional[Path] = None
    if gs.validator_history:
        last = gs.validator_history[-1]
        prev_validation = (Path(sm.run_dir) / "agents"
                           / f"validator-{gs.id}-r{last.get('round')}"
                           / "outbox" / "validation.md")
        if not prev_validation.exists():
            prev_validation = None
    render_validator_prompt(
        group_stages=_items_as_stages(gs),
        run_dir=Path(sm.run_dir),
        run_id=sm.run_id,
        spec_id=sm.spec_id or "",
        spec_dir=sm.spec_dir or "",
        group=gs.id,
        round_=next_round,
        prev_validation=prev_validation,
        project_root=_resolve_project_root(sm),
    )


# -------------------------------------------------------------------------
# advance
# -------------------------------------------------------------------------

def _coder_outbox_paths(sm: StateMachine, keys: list[str]) -> list[Path]:
    out: list[Path] = []
    for k in keys:
        out.append(Path(sm.run_dir) / "agents" / k / "outbox" / "result.md")
    return out


def cmd_advance(args: argparse.Namespace) -> int:
    try:
        run_dir = _find_run_dir(args.run)
    except FileNotFoundError as e:
        sys.stderr.write(f"{e}\n")
        return 1
    sm = StateMachine.load(run_dir)
    gid = getattr(args, "group", None)
    if not gid:
        sys.stderr.write("advance 需要 --group <gid>\n")
        return 1
    gs = next((g for g in sm.task_groups if g.id == gid), None)
    if gs is None:
        sys.stderr.write(f"--group {gid} 不存在；可选：{[g.id for g in sm.task_groups]}\n")
        return 1
    phase = args.phase
    errors: list[str] = []
    next_msg = ""

    if phase == "coding":
        all_keys = list(gs.coder_in_flight) + list(gs.coder_done)
        if not all_keys:
            all_keys = [f"coder-{gs.id}-s{s['number']}-r1" for s in gs.items]
        any_failed = False
        for k in all_keys:
            p = Path(sm.run_dir) / "agents" / k / "outbox" / "result.md"
            try:
                res = parse_coder_result(p)
                gs.mark_coder_done(k)
                if res.status != "ok":
                    any_failed = True
                    errors.append(f"{k}: STATUS={res.status} {res.status_reason}")
            except ParseError as e:
                errors.append(f"{k}: parse error: {e}")
                any_failed = True
        sm.events_append({"type": "advance", "phase": "coding", "group": gs.id, "errors": errors})
        if any_failed:
            sm.failed_status = sm.failed_status or "failed"
            gs.status = "failed"
            sm.save()
            _emit({"ok": False, "group": gs.id, "phase": gs.phase, "errors": errors,
                   "next": "report-failed-group"})
            return 0
        gs.begin_review()
        sm.events_append({"type": "phase", "phase": "review", "group": gs.id})
        _materialize_prompt_reviewer(sm, gs)
        next_msg = f"下一步：fork reviewer（agent_key=reviewer-{gs.id}-r1）"

    elif phase == "review":
        path = Path(sm.run_dir) / "agents" / f"reviewer-{gs.id}-r1" / "outbox" / "review.md"
        try:
            rev = parse_reviewer_review(path)
            gs.mark_reviewer_done()
            gs.findings = []
            for f in rev.p0_items:
                gs.findings.append({"severity": "p0", "text": f.text,
                                    "evidence_tags": f.evidence_tags, "file_hint": f.file_hint,
                                    "fix_status": "未修复"})
            for f in rev.advisory_items:
                gs.findings.append({"severity": "advisory", "text": f.text,
                                    "evidence_tags": [], "file_hint": f.file_hint,
                                    "fix_status": "未修复"})
            for f in rev.p1_items:
                gs.findings.append({"severity": "p1", "text": f.text,
                                    "evidence_tags": [], "file_hint": f.file_hint,
                                    "fix_status": "未修复"})
            for f in rev.p2_items:
                gs.findings.append({"severity": "p2", "text": f.text,
                                    "evidence_tags": [], "file_hint": f.file_hint,
                                    "fix_status": "未修复"})
            gs.p0_pending = [{"text": f.text, "evidence_tags": f.evidence_tags,
                              "file_hint": f.file_hint} for f in rev.p0_items]
            sm.events_append({"type": "advance", "phase": "review", "group": gs.id,
                              "verdict": rev.verdict, "p0": len(rev.p0_items),
                              "advisory": len(rev.advisory_items),
                              "p1": len(rev.p1_items), "p2": len(rev.p2_items)})
            if gs.p0_pending:
                gs.begin_p0_fix(gs.p0_pending)
                sm.events_append({"type": "phase", "phase": "p0-fix", "group": gs.id})
                _materialize_prompts_p0_fix(sm, gs)
                next_msg = "下一步：fork p0-fix coder（按文件分组）"
            elif sm.skip_validator:
                gs.begin_writeback()
                next_msg = (f"无 P0 + skip_validator（人工验收）；请调 "
                            f"`task_swarm.py writeback --run {sm.run_id} --group {gs.id}`。")
            else:
                gs.begin_validation()
                sm.events_append({"type": "phase", "phase": "validation",
                                  "group": gs.id, "round": gs.round})
                _materialize_prompt_validator(sm, gs)
                next_msg = "下一步：fork validator"
        except ParseError as e:
            errors.append(str(e))

    elif phase == "p0-fix":
        all_keys = list(gs.p0_in_flight) + list(gs.p0_done)
        if not all_keys:
            files: list[str] = []
            for p in gs.p0_pending:
                f = (p.get("file_hint") or "unknown").strip()
                if f not in files:
                    files.append(f)
            all_keys = [f"coder-p0fix-{gs.id}-r1-f{i}" for i in range(len(files))]
        any_failed = False
        for k in all_keys:
            p = Path(sm.run_dir) / "agents" / k / "outbox" / "result.md"
            try:
                res = parse_coder_result(p)
                gs.mark_p0_done(k)
                if res.status != "ok":
                    any_failed = True
                    errors.append(f"{k}: STATUS={res.status} {res.status_reason}")
            except ParseError as e:
                errors.append(f"{k}: parse error: {e}")
                any_failed = True
        for finding in gs.findings:
            if finding["severity"] == "p0":
                finding["fix_status"] = "未修复" if any_failed else "已修复"
        sm.events_append({"type": "advance", "phase": "p0-fix", "group": gs.id,
                          "any_failed": any_failed, "errors": errors})
        if sm.skip_validator:
            gs.begin_writeback()
            next_msg = (f"p0-fix 完成 + skip_validator（人工验收）；请调 "
                        f"`task_swarm.py writeback --run {sm.run_id} --group {gs.id}`。"
                        + (" 未修部分标 [P0 未修复]。" if any_failed else ""))
        else:
            gs.begin_validation()
            sm.events_append({"type": "phase", "phase": "validation",
                              "group": gs.id, "round": gs.round})
            _materialize_prompt_validator(sm, gs)
            next_msg = "p0-fix 完成；进入 validation。" + (
                " 失败的 P0 标 [P0 未修复]。" if any_failed else "")

    elif phase == "validation":
        round_used = gs.round if gs.round > 0 else 1
        path = (Path(sm.run_dir) / "agents"
                / f"validator-{gs.id}-r{round_used}" / "outbox" / "validation.md")
        try:
            val = parse_validator_validation(path)
            gs.mark_validator_done()
            gs.round = round_used
            sig = val.fail_signature()
            gs.record_round_signature(sig)
            sm.events_append({"type": "advance", "phase": "validation", "group": gs.id,
                              "verdict": val.verdict, "round": round_used, "signature": sig})
            if val.verdict == "pass":
                gs.fix_targets = []
                gs.begin_writeback()
                next_msg = (f"validator pass。请调 `task_swarm.py writeback "
                            f"--run {sm.run_id} --group {gs.id}`。")
            else:
                gs.fix_targets = [
                    {"file_path": t.file_path, "title": t.title, "location": t.location,
                     "problem": t.problem, "suggestion": t.suggestion,
                     "requirements": list(t.requirements)}
                    for t in val.fix_targets
                ]
                if gs.detect_deadloop():
                    gs.fail_deadloop()
                    sm.failed_status = sm.failed_status or "failed-deadloop"
                    sm.events_append({"type": "group-failed", "group": gs.id, "reason": "deadloop"})
                    sm.save()
                    _emit({"ok": False, "group": gs.id, "phase": gs.phase, "deadloop": True,
                           "next": "report-deadloop", "round": gs.round})
                    return 0
                gs.begin_v_fix(gs.fix_targets)
                sm.events_append({"type": "phase", "phase": "v-fix",
                                  "group": gs.id, "round": gs.round})
                _materialize_prompts_v_fix(sm, gs)
                next_msg = (f"validator fail。请按 fix_targets 各文件 fork v-fix coder。"
                            f"本轮 {gs.id}-r{gs.round}。")
        except ParseError as e:
            errors.append(str(e))

    elif phase == "v-fix":
        all_keys = list(gs.vfix_in_flight) + list(gs.vfix_done)
        if not all_keys:
            files = []
            for t in gs.fix_targets:
                f = (t.get("file_path") or "").strip()
                if f and f not in files:
                    files.append(f)
            if not files:
                files = ["unknown"]
            all_keys = [f"coder-vfix-{gs.id}-r{gs.round}-f{i}" for i in range(len(files))]
        any_failed = False
        for k in all_keys:
            p = Path(sm.run_dir) / "agents" / k / "outbox" / "result.md"
            try:
                res = parse_coder_result(p)
                gs.mark_vfix_done(k)
                if res.status != "ok":
                    any_failed = True
                    errors.append(f"{k}: STATUS={res.status} {res.status_reason}")
            except ParseError as e:
                errors.append(f"{k}: parse error: {e}")
                any_failed = True
        sm.events_append({"type": "advance", "phase": "v-fix", "group": gs.id,
                          "round": gs.round, "any_failed": any_failed, "errors": errors})
        if any_failed:
            sm.failed_status = sm.failed_status or "failed"
            gs.status = "failed"
            sm.save()
            _emit({"ok": False, "group": gs.id, "phase": gs.phase, "errors": errors,
                   "next": "report-failed-group"})
            return 0
        gs.begin_validation()
        sm.events_append({"type": "phase", "phase": "validation",
                          "group": gs.id, "round": gs.round})
        _materialize_prompt_validator(sm, gs)
        next_msg = f"v-fix ok。请 fork validator-{gs.id}-r{gs.round}。"

    else:
        sys.stderr.write(f"未知 phase: {phase}\n")
        return 1

    sm.save()
    plan = _plan_for_group(sm, gs)
    _emit({"ok": not errors, "group": gs.id, "phase": gs.phase, "round": gs.round,
           "errors": errors, "next": next_msg, "plan": plan})
    return 0


def cmd_writeback(args: argparse.Namespace) -> int:
    try:
        run_dir = _find_run_dir(args.run)
    except FileNotFoundError as e:
        sys.stderr.write(f"{e}\n")
        return 1
    sm = StateMachine.load(run_dir)
    gid = args.group
    gs = next((g for g in sm.task_groups if g.id == gid), None)
    if gs is None:
        sys.stderr.write(f"--group {gid} 不存在；可选：{[g.id for g in sm.task_groups]}\n")
        return 1
    if gs.phase != "writeback" and gs.status != "failed-deadloop":
        sys.stderr.write(f"--group {gid} 未到 writeback 阶段（phase={gs.phase}）\n")
        return 1
    # writeback = finalize 本组（yml 单轨；M3 已移除 markdown line-safe 写回）
    final_verdict = "failed-deadloop" if gs.status == "failed-deadloop" else "pass"
    gs.finalize("done" if final_verdict == "pass" else "failed")
    sm.events_append({"type": "writeback", "group": gs.id, "pipeline": True,
                      "verdict": final_verdict})
    # 所有组终态 → run 收尾
    if all(g.status in ("done", "failed", "failed-deadloop") for g in sm.task_groups):
        sm.completed_at = sm.completed_at or _now_iso()
        if not sm.failed_status:
            sm.failed_status = ("done" if all(g.status == "done" for g in sm.task_groups)
                                else "failed")
        sm.events_append({"type": "run-done", "status": sm.failed_status})
    sm.save()
    sched = compute_schedule([g.sched_view() for g in sm.task_groups])
    _emit({"ok": True, "group": gs.id, "finalized": True, "verdict": final_verdict,
           "schedule": sched})
    return 0


def cmd_heartbeat(args: argparse.Namespace) -> int:
    """刷新 state.json.last_activity_at（长流程保活，状态层）。

    task-swarm 独立运行，无 spec 锁概念；本命令只更新 last_activity_at，
    供后续监控/超时里程碑使用。
    """
    try:
        run_dir = _find_run_dir(args.run)
    except FileNotFoundError as e:
        sys.stderr.write(f"{e}\n")
        return 1
    sm = StateMachine.load(run_dir)
    sm.events_append({"type": "heartbeat"})
    sm.save()
    _emit({
        "ok": True,
        "run_id": sm.run_id,
        "spec_dir": sm.spec_dir,
        "session_id": sm.session_id,
        "hint": "已刷新 last_activity_at。",
    })
    return 0


# -------------------------------------------------------------------------
# resolve
# -------------------------------------------------------------------------

def cmd_resolve(args: argparse.Namespace) -> int:
    try:
        run_dir = _find_run_dir(args.run)
    except FileNotFoundError as e:
        sys.stderr.write(f"{e}\n")
        return 1
    sm = StateMachine.load(run_dir)
    if args.abort:
        sm.failed_status = "aborted"
        sm.completed_at = _now_iso()
        sm.events_append({"type": "resolve", "status": "aborted"})
    else:
        sm.completed_at = sm.completed_at or _now_iso()
        sm.failed_status = sm.failed_status or "done"
        sm.events_append({"type": "resolve", "status": sm.failed_status})

    # P2-1: ingest lessons into <project_root>/.ai-memory/knowledge/
    # only on successful runs; never bubble up — ingest failures must not
    # turn a successful run into a failed resolve.
    ingest_result: dict[str, Any] = {"cases": [], "pitfalls": [], "skipped": "not-done"}
    if sm.failed_status == "done" and not getattr(args, "no_ingest", False):
        try:
            from task_swarm._ingest_lessons import ingest_lessons

            ingest_result = ingest_lessons(sm)
            sm.events_append(
                {
                    "type": "ingest-lessons",
                    "cases": len(ingest_result.get("cases", [])),
                    "pitfalls": len(ingest_result.get("pitfalls", [])),
                    "skipped": ingest_result.get("skipped"),
                }
            )
        except Exception as exc:  # noqa: BLE001 — ingest must never block resolve
            ingest_result = {"cases": [], "pitfalls": [], "skipped": f"error:{type(exc).__name__}"}
            sm.events_append(
                {"type": "ingest-lessons", "error": f"{type(exc).__name__}: {exc}"}
            )

    sm.save()
    _emit({
        "ok": True,
        "run_id": sm.run_id,
        "status": sm.failed_status,
        "completed_at": sm.completed_at,
        "ingest": {
            "cases": len(ingest_result.get("cases", [])),
            "pitfalls": len(ingest_result.get("pitfalls", [])),
            "skipped": ingest_result.get("skipped"),
        },
    })
    return 0


# -------------------------------------------------------------------------
# report
# -------------------------------------------------------------------------

def cmd_report(args: argparse.Namespace) -> int:
    try:
        run_dir = _find_run_dir(args.run)
    except FileNotFoundError as e:
        sys.stderr.write(f"{e}\n")
        return 1
    sm = StateMachine.load(run_dir)
    text = render_report(sm, group=args.group)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


# -------------------------------------------------------------------------
# argparse
# -------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="task_swarm.py",
                                description="task-swarm 编排主 CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("init")
    pi.add_argument("--pipeline", default=None,
                    help="pipeline.yml 路径(唯一编排输入;markdown --tasks 已在 M3 移除)")
    pi.add_argument("--serial-validation", dest="serial_validation", action="store_true",
                    help="跨组并发时 validator 全局串行(测试有共享资源时用)")
    pi.add_argument("--max-parallel", type=int, default=4)
    pi.add_argument("--max-rounds", type=int, default=6)
    pi.add_argument("--session", default=None)
    pi.add_argument("--workdir", default=None,
                    help="状态根所在目录;默认当前工作目录(cwd)")
    pi.add_argument("--spec-id", dest="spec_id", default=None,
                    help="可选:回溯用的 spec 标识;独立模式可省")
    pi.add_argument("--project-root", dest="project_root", default=None,
                    help="被改动代码的根目录;默认 = --workdir")
    pi.add_argument("--spec-dir", dest="spec_dir_arg", default=None,
                    help="可选:spec 文档目录(*.md 所在);specode 委托模式用,独立模式可省")
    pi.add_argument("--skip-validator", action="store_true",
                    help="人工验收模式：review/p0-fix 完成后直接 writeback，跳过 validation/v-fix")
    pi.add_argument(
        "--on-existing", dest="on_existing", default="error",
        choices=["error", "resume", "abort-old", "force-new"],
        help=("v0.8.0 M7：spec_id 已有活跃 run 时的处理 — error（默认，"
              "exit 1 + 提示）/ resume（返回 existing 不新建）/ abort-old"
              "（旧 run 标 aborted + 新建）/ force-new（忽略并新建）"),
    )

    ps = sub.add_parser("status")
    ps.add_argument("--run", required=True)

    pp = sub.add_parser("plan")
    pp.add_argument("--run", required=True)

    pa = sub.add_parser("advance")
    pa.add_argument("--run", required=True)
    pa.add_argument("--group", required=True, help="语义任务组 id（如 g1）")
    pa.add_argument("--phase", required=True,
                    choices=["coding", "review", "p0-fix", "validation", "v-fix"])
    pa.add_argument("--round", type=int, default=1)

    pw = sub.add_parser("writeback")
    pw.add_argument("--run", required=True)
    pw.add_argument("--group", required=True, help="语义任务组 id（如 g1）")

    ph = sub.add_parser("heartbeat")
    ph.add_argument("--run", required=True)

    pr = sub.add_parser("resolve")
    pr.add_argument("--run", required=True)
    pr.add_argument("--abort", action="store_true")
    pr.add_argument(
        "--no-ingest",
        dest="no_ingest",
        action="store_true",
        help="skip writing case/pitfall yml to <project_root>/.ai-memory/knowledge/",
    )

    prep = sub.add_parser("report")
    prep.add_argument("--run", required=True)
    prep.add_argument("--group", default=None, help="语义任务组 id（如 g1）；省略=全部")
    prep.add_argument("--out", default=None)

    return p


COMMANDS = {
    "init": cmd_init,
    "status": cmd_status,
    "plan": cmd_plan,
    "advance": cmd_advance,
    "writeback": cmd_writeback,
    "heartbeat": cmd_heartbeat,
    "resolve": cmd_resolve,
    "report": cmd_report,
}


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    fn = COMMANDS.get(args.cmd)
    if fn is None:
        parser.print_help()
        return 1
    return fn(args) or 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
