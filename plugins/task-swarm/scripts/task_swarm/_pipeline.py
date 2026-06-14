"""task_swarm._pipeline — pipeline.yml schema 校验 + 映射到现有 Stage/StageItem。"""
from __future__ import annotations

from task_swarm._parse_md import Stage, StageItem


def validate(data) -> list:
    errors = []
    if not isinstance(data, dict):
        return ["top level must be a map"]
    if data.get("version") != 1:
        errors.append("version must be 1")
    groups = data.get("task_groups")
    if not isinstance(groups, list) or not groups:
        errors.append("task_groups must be a non-empty list")
        return errors
    gids, tids = set(), set()
    for gi, g in enumerate(groups):
        if not isinstance(g, dict):
            errors.append(f"task_group[{gi}] must be a map")
            continue
        gid = g.get("id")
        if not gid:
            errors.append(f"task_group[{gi}] missing id")
        elif gid in gids:
            errors.append(f"duplicate task_group id: {gid}")
        else:
            gids.add(gid)
        if not g.get("name"):
            errors.append(f"task_group {gid!r} missing name")
        tasks = g.get("tasks")
        if not isinstance(tasks, list) or not tasks:
            errors.append(f"task_group {gid!r} must have non-empty tasks")
            continue
        for ti, t in enumerate(tasks):
            if not isinstance(t, dict):
                errors.append(f"task[{gi}.{ti}] must be a map")
                continue
            tid = t.get("id")
            if not tid:
                errors.append(f"task in {gid!r} missing id")
            elif tid in tids:
                errors.append(f"duplicate task id: {tid}")
            else:
                tids.add(tid)
            if not t.get("title"):
                errors.append(f"task {tid!r} missing title")
            w = t.get("writes")
            if not isinstance(w, list) or not w:
                errors.append(f"task {tid!r} missing writes (non-empty list required)")
    for g in groups:
        for n in (g.get("needs") or []):
            if n not in gids:
                errors.append(f"task_group {g.get('id')!r} needs unknown group: {n}")
    return errors
