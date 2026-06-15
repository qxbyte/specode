#!/usr/bin/env python3
"""task-swarm 调度层（纯函数）：从 task_groups 的 needs 拓扑 + writes 冲突，
算出当前可并发启动集合。stdlib-only，无副作用。详见设计 M3 §2。"""
from __future__ import annotations
from typing import Any

_TERMINAL = {"done", "failed", "failed-deadloop"}
_RUNNING = {"running", "coding", "review", "p0-fix", "validation", "v-fix", "writeback"}


def _is_done(status: str) -> bool:
    return status == "done"


def _is_terminal(status: str) -> bool:
    return status in _TERMINAL


def _is_running(status: str) -> bool:
    return status in _RUNNING


def compute_schedule(groups: list[dict[str, Any]]) -> dict[str, Any]:
    """groups: [{id, needs:[gid], writes:[path], status}]。
    返回 {done:[gid], running:[gid], runnable:[gid], blocked:[{id,reason}], failed:[gid]}。
    done = 成功完成；failed = failed/failed-deadloop 终态（与 done 区分，供上层报告）。"""
    by_id = {g["id"]: g for g in groups}
    done, running, runnable, blocked, failed = [], [], [], [], []

    running_writes: set[str] = set()
    for g in groups:
        if _is_running(g["status"]):
            running_writes |= set(g.get("writes") or [])

    for g in groups:
        gid, status = g["id"], g["status"]
        if _is_done(status):
            done.append(gid); continue
        if status in ("failed", "failed-deadloop"):
            failed.append(gid); continue
        if _is_running(status):
            running.append(gid); continue
        needs = g.get("needs") or []
        unmet = [n for n in needs if not _is_done(by_id.get(n, {}).get("status", ""))]
        failed_up = [n for n in needs if by_id.get(n, {}).get("status") in ("failed", "failed-deadloop")]
        if failed_up:
            blocked.append({"id": gid, "reason": f"upstream failed: {failed_up}"}); continue
        if unmet:
            blocked.append({"id": gid, "reason": f"needs not done: {unmet}"}); continue
        if set(g.get("writes") or []) & running_writes:
            blocked.append({"id": gid, "reason": "writes conflict with running group"}); continue
        runnable.append(gid)
    return {"done": done, "running": running, "runnable": runnable,
            "blocked": blocked, "failed": failed}
