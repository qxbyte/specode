"""task_swarm._pipeline — pipeline.yml schema 校验 + 映射到组级调度状态。"""
from __future__ import annotations


def validate(data) -> list:
    errors = []
    if not isinstance(data, dict):
        return ["top level must be a map"]
    if data.get("version") != 1:
        errors.append("version must be 1")
    # v0.8.0 M3: run.pipeline_end_validator field — optional bool.
    # Schema reservation only; plan/advance logic to implement an extra
    # cross-group validator phase after all groups done lands in v0.8.1.
    # Today: parsed + persisted to state.json, ignored by orchestrator.
    run_meta = data.get("run") or {}
    if not isinstance(run_meta, dict):
        errors.append("run must be a map")
    else:
        pev = run_meta.get("pipeline_end_validator")
        if pev is not None and not isinstance(pev, bool):
            errors.append("run.pipeline_end_validator must be true/false (bool)")
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


def to_group_states(pipeline: dict) -> list[dict]:
    """pipeline.yml dict → list[group dict]，组级保留 needs + writes 并集（M3 调度用）。
    每个 group dict: {id, name, needs:[gid], writes:[path 并集], items:[item dict]}。
    item dict: {number(去 g 前缀，如 '1.1'), title, writes, reads, requirements}。"""
    out = []
    for tg in pipeline.get("task_groups", []):
        items, writes_union = [], []
        for t in tg.get("tasks", []):
            tid = str(t["id"])
            num = tid[1:] if tid.startswith("g") else tid
            w = list(t.get("writes") or [])
            for f in w:
                if f not in writes_union:
                    writes_union.append(f)
            items.append({
                "number": num, "title": t.get("title", ""),
                "writes": w, "reads": list(t.get("reads") or []),
                "requirements": list(t.get("requirements") or []),
            })
        out.append({
            "id": str(tg["id"]), "name": tg.get("name", ""),
            "needs": list(tg.get("needs") or []),
            "writes": writes_union, "items": items,
        })
    return out
