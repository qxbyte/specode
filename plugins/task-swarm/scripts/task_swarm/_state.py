#!/usr/bin/env python3
"""task_swarm_state.py — task-swarm 状态机（state.json 单一事实源；详见 references/task-swarm.md §7）。

负责：
    - state.json 的 load/save（atomic write + fsync）
    - phase 状态机推进（references/task-swarm.md §3）
    - 死循环检测（连续 3 轮同 fail 签名 → group failed-deadloop）

state.json schema 见 references/task-swarm.md §7 关键不变量。本模块只管"事实源"，
派发 / 解析在 task_swarm.py 主 CLI 里。

stdlib-only。
"""
from __future__ import annotations

import contextlib
import json
import os
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional


# -------------------------------------------------------------------------
# 时间 / 原子写
# -------------------------------------------------------------------------

def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
            fh.flush()
            with contextlib.suppress(OSError):
                os.fsync(fh.fileno())
        os.replace(tmp, path)
        with contextlib.suppress(OSError):
            dir_fd = os.open(str(path.parent), os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def _atomic_write_json(path: Path, payload: Any) -> None:
    _atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))


# -------------------------------------------------------------------------
# 数据模型
# -------------------------------------------------------------------------

@dataclass
class StageEntry:
    """state.json 里一条 stage 记录。"""
    number: int
    title: str
    writes: list[str] = field(default_factory=list)
    reads: list[str] = field(default_factory=list)
    depends_on: list[int] = field(default_factory=list)
    requirements: list[str] = field(default_factory=list)
    items: list[dict] = field(default_factory=list)
    header_line_no: int = 0
    end_line_no: int = 0


@dataclass
class GroupState:
    """一个语义任务组的独立子状态机（M3）。把原 StateMachine 顶层 per-phase
    字段整体下沉到这里。每组独立推进 coding→review→p0-fix→validation→v-fix→done。"""
    id: str
    name: str = ""
    needs: list[str] = field(default_factory=list)
    writes: list[str] = field(default_factory=list)
    items: list[dict] = field(default_factory=list)
    status: str = "pending"
    phase: str = "init"
    round: int = 0
    coder_in_flight: list[str] = field(default_factory=list)
    coder_done: list[str] = field(default_factory=list)
    reviewer_done: bool = False
    p0_in_flight: list[str] = field(default_factory=list)
    p0_done: list[str] = field(default_factory=list)
    p0_pending: list[dict] = field(default_factory=list)
    validator_in_flight: bool = False
    vfix_in_flight: list[str] = field(default_factory=list)
    vfix_done: list[str] = field(default_factory=list)
    findings: list[dict] = field(default_factory=list)
    fix_targets: list[dict] = field(default_factory=list)
    validator_history: list[dict] = field(default_factory=list)
    fail_signature: str = ""

    @classmethod
    def from_pipeline_group(cls, g: dict) -> "GroupState":
        return cls(id=g["id"], name=g.get("name", ""), needs=list(g.get("needs") or []),
                   writes=list(g.get("writes") or []), items=list(g.get("items") or []))

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "GroupState":
        return cls(**d)

    def sched_view(self) -> dict:
        """给 _schedule.compute_schedule 的精简视图。"""
        return {"id": self.id, "needs": self.needs, "writes": self.writes, "status": self.status}

    # ---- phase 推进（从 StateMachine 顶层下沉，逐组实例化；事件由 cli 层 append）----

    def begin_coding(self) -> None:
        self.phase = "coding"
        self.round = 1
        self.coder_in_flight = [f"coder-{self.id}-s{it['number']}-r1" for it in self.items]
        self.coder_done = []
        self.reviewer_done = False
        self.p0_in_flight = []
        self.p0_done = []
        self.validator_in_flight = False
        self.vfix_in_flight = []
        self.vfix_done = []
        self.findings = []
        self.p0_pending = []
        self.fix_targets = []
        self.validator_history = []
        self.fail_signature = ""
        self.status = "coding"

    def mark_coder_done(self, agent_key: str) -> None:
        if agent_key in self.coder_in_flight:
            self.coder_in_flight.remove(agent_key)
        if agent_key not in self.coder_done:
            self.coder_done.append(agent_key)

    def all_coders_returned(self) -> bool:
        return not self.coder_in_flight

    def begin_review(self) -> None:
        self.phase = "review"
        self.reviewer_done = False
        self.status = "review"

    def mark_reviewer_done(self) -> None:
        self.reviewer_done = True

    def begin_p0_fix(self, p0_pending: list[dict]) -> list[str]:
        self.phase = "p0-fix"
        self.round = 1
        self.p0_pending = list(p0_pending)
        files: list[str] = []
        for p in p0_pending:
            f = (p.get("file_hint") or "unknown").strip()
            if f not in files:
                files.append(f)
        self.p0_in_flight = [f"coder-p0fix-{self.id}-r1-f{i}" for i in range(len(files))]
        self.p0_done = []
        self.status = "p0-fix"
        return files

    def mark_p0_done(self, agent_key: str) -> None:
        if agent_key in self.p0_in_flight:
            self.p0_in_flight.remove(agent_key)
        if agent_key not in self.p0_done:
            self.p0_done.append(agent_key)

    def all_p0_returned(self) -> bool:
        return not self.p0_in_flight

    def begin_validation(self) -> None:
        self.phase = "validation"
        self.validator_in_flight = True
        self.status = "validation"

    def mark_validator_done(self) -> None:
        self.validator_in_flight = False

    def record_round_signature(self, fail_sig: str) -> None:
        self.validator_history.append({
            "group": self.id,
            "round": self.round,
            "verdict": "fail" if fail_sig else "pass",
            "signature": fail_sig,
            "at": _now_iso(),
        })
        self.fail_signature = fail_sig

    def detect_deadloop(self) -> bool:
        sigs = [h["signature"] for h in self.validator_history
                if h.get("verdict") == "fail" and h.get("signature")]
        if len(sigs) < DEADLOOP_THRESHOLD:
            return False
        return all(s == sigs[-1] for s in sigs[-DEADLOOP_THRESHOLD:])

    def begin_v_fix(self, fix_targets: list[dict]) -> list[str]:
        self.phase = "v-fix"
        self.round += 1
        files: list[str] = []
        for t in fix_targets:
            f = (t.get("file_path") or "unknown").strip()
            if f and f not in files:
                files.append(f)
        if not files:
            files = ["unknown"]
        self.fix_targets = list(fix_targets)
        self.vfix_in_flight = [f"coder-vfix-{self.id}-r{self.round}-f{i}" for i in range(len(files))]
        self.vfix_done = []
        self.status = "v-fix"
        return files

    def mark_vfix_done(self, agent_key: str) -> None:
        if agent_key in self.vfix_in_flight:
            self.vfix_in_flight.remove(agent_key)
        if agent_key not in self.vfix_done:
            self.vfix_done.append(agent_key)

    def all_vfix_returned(self) -> bool:
        return not self.vfix_in_flight

    def begin_writeback(self) -> None:
        self.phase = "writeback"
        self.status = "writeback"

    def finalize(self, status: str = "done") -> None:
        self.status = status
        self.phase = "done"

    def fail_deadloop(self) -> None:
        self.status = "failed-deadloop"
        self.phase = "error"


# Phase 枚举（同 references/task-swarm.md §3）
PHASES = {
    "init", "coding", "review", "p0-fix",
    "validation", "v-fix", "writeback", "done", "error",
}

GROUP_STATUS_VALUES = {
    "pending", "coding", "review", "p0-fix", "validation",
    "v-fix", "writeback", "done", "failed", "failed-deadloop",
}

# 连续相同 fail 签名达到此值 → 整个 group 标 failed-deadloop
DEADLOOP_THRESHOLD = 3


# -------------------------------------------------------------------------
# StateMachine
# -------------------------------------------------------------------------

@dataclass
class StateMachine:
    run_id: str
    tasks_md: str
    run_dir: str
    max_parallel: int = 4
    max_rounds: int = 6
    session_id: Optional[str] = None
    spec_dir: Optional[str] = None
    spec_id: Optional[str] = None
    workdir: Optional[str] = None
    project_root: Optional[str] = None
    pipeline_path: Optional[str] = None

    # 人工验收模式：review/p0-fix 完成后跳过 validation/v-fix 直接 writeback。
    skip_validator: bool = False

    # M3：每语义任务组一个独立子状态机（GroupState）。task_groups 是唯一事实源。
    task_groups: list["GroupState"] = field(default_factory=list)
    serial_validation: bool = False

    # v0.8.0 M3: pipeline.yml 的 run.pipeline_end_validator 字段持久化到此。
    # 当前 schema 保留；plan/advance 不消费（v0.8.1 实现 cross-group end
    # validator phase 时启用）。
    pipeline_end_validator: bool = False

    # run 级状态
    started_at: str = ""
    last_activity_at: str = ""
    completed_at: Optional[str] = None
    failed_status: Optional[str] = None  # done / failed / failed-deadloop / aborted
    events: list[dict] = field(default_factory=list)

    # -----------------------------------------------------------------
    # 文件 IO
    # -----------------------------------------------------------------

    @staticmethod
    def state_path(run_dir: Path) -> Path:
        return run_dir / "state.json"

    @classmethod
    def load(cls, run_dir: Path) -> "StateMachine":
        sp = cls.state_path(run_dir)
        if not sp.exists():
            raise FileNotFoundError(f"state.json 不存在：{sp}")
        with sp.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        # task_groups（M3 模型）；旧线性 schema（无 task_groups）→ 自动迁移
        raw_tg = data.get("task_groups")
        if raw_tg is not None:
            task_groups = [GroupState.from_dict(g) for g in raw_tg]
        else:
            task_groups = _migrate_linear_to_groups(data)
        return cls(
            run_id=data["run_id"],
            tasks_md=data.get("tasks_md", ""),
            run_dir=str(run_dir),
            max_parallel=data.get("max_parallel", 4),
            max_rounds=data.get("max_rounds", 6),
            session_id=data.get("session_id") or data.get("claude_session_id"),
            spec_dir=data.get("spec_dir"),
            spec_id=data.get("spec_id"),
            workdir=data.get("workdir"),
            project_root=data.get("project_root"),
            pipeline_path=data.get("pipeline_path"),
            task_groups=task_groups,
            serial_validation=data.get("serial_validation", False),
            pipeline_end_validator=data.get("pipeline_end_validator", False),
            started_at=data.get("started_at", ""),
            last_activity_at=data.get("last_activity_at", ""),
            completed_at=data.get("completed_at"),
            failed_status=data.get("failed_status"),
            events=data.get("events", []),
            skip_validator=data.get("skip_validator", False),
        )

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "tasks_md": self.tasks_md,
            "run_dir": self.run_dir,
            "max_parallel": self.max_parallel,
            "max_rounds": self.max_rounds,
            "session_id": self.session_id,
            "spec_dir": self.spec_dir,
            "spec_id": self.spec_id,
            "workdir": self.workdir,
            "project_root": self.project_root,
            "pipeline_path": self.pipeline_path,
            "task_groups": [g.to_dict() for g in self.task_groups],
            "serial_validation": self.serial_validation,
            "pipeline_end_validator": self.pipeline_end_validator,
            "started_at": self.started_at,
            "last_activity_at": self.last_activity_at,
            "completed_at": self.completed_at,
            "failed_status": self.failed_status,
            "events": list(self.events),
            "skip_validator": self.skip_validator,
        }

    def save(self) -> None:
        self.last_activity_at = _now_iso()
        _atomic_write_json(self.state_path(Path(self.run_dir)), self.to_dict())

    def events_append(self, event: dict) -> None:
        e = dict(event)
        e.setdefault("at", _now_iso())
        self.events.append(e)


def _migrate_linear_to_groups(data: dict) -> list["GroupState"]:
    """旧线性 schema（groups[批次] + 顶层 per-phase 字段）→ task_groups。
    每个旧批次映射成一个 GroupState，id 用 g{i+1}，status 取 group_status[i]，
    顶层 per-phase 字段只灌到 current_group_index 指向的那组。"""
    out = []
    groups = data.get("groups", [])
    gstatus = data.get("group_status", ["pending"] * len(groups))
    ci = data.get("current_group_index", 0)
    for i, batch in enumerate(groups):
        items = []
        for s in batch:
            items.append({"number": s.get("number"), "title": s.get("title", ""),
                          "writes": s.get("writes", []), "reads": s.get("reads", []),
                          "requirements": s.get("requirements", [])})
        writes_union = []
        for it in items:
            for f in it["writes"]:
                if f not in writes_union:
                    writes_union.append(f)
        gs = GroupState(id=f"g{i+1}", name="", needs=[], writes=writes_union, items=items,
                        status=gstatus[i] if i < len(gstatus) else "pending")
        if i == ci:
            gs.phase = data.get("phase", "init")
            gs.round = data.get("round", 0)
            gs.coder_in_flight = data.get("coder_in_flight", [])
            gs.coder_done = data.get("coder_done", [])
            gs.reviewer_done = data.get("reviewer_done", False)
            gs.p0_in_flight = data.get("p0_in_flight", [])
            gs.p0_done = data.get("p0_done", [])
            gs.p0_pending = data.get("p0_pending", [])
            gs.validator_in_flight = data.get("validator_in_flight", False)
            gs.vfix_in_flight = data.get("vfix_in_flight", [])
            gs.vfix_done = data.get("vfix_done", [])
            gs.findings = data.get("findings", [])
            gs.fix_targets = data.get("fix_targets", [])
            gs.validator_history = data.get("validator_history", [])
            gs.fail_signature = data.get("fail_signature", "")
        out.append(gs)
    return out


# -------------------------------------------------------------------------
# 模块自测
# -------------------------------------------------------------------------

if __name__ == "__main__":  # pragma: no cover
    import sys
    if len(sys.argv) < 2:
        print("usage: task_swarm_state.py <run_dir>")
        raise SystemExit(2)
    sm = StateMachine.load(Path(sys.argv[1]))
    print(json.dumps(sm.to_dict(), ensure_ascii=False, indent=2))
