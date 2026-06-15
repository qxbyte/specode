"""task_swarm._report — 从 state 渲染人类可读 markdown 报告（纯函数，事实源 state.json）。"""
from __future__ import annotations


def render_report(sm, group: int = None) -> str:
    lines = []
    total = len(sm.groups)
    done = sum(1 for s in sm.group_status if s == "done")
    failed = any(s in ("failed", "failed-deadloop") for s in sm.group_status)
    overall = ("失败" if failed else "全部完成" if done == total else "进行中")
    lines += ["# task-swarm run report", "",
              f"- run_id: {sm.run_id}"]
    if getattr(sm, "spec_id", None):
        lines.append(f"- spec_id: {sm.spec_id}")
    lines += [f"- 整体状态: {overall}（{done}/{total} 任务组完成）", ""]
    idxs = range(total) if group is None else [group - 1]
    for gi in idxs:
        if gi < 0 or gi >= total:
            continue
        status = sm.group_status[gi] if gi < len(sm.group_status) else "pending"
        stages = sm.groups[gi]
        name = stages[0].title if stages else ""
        lines.append(f"## 任务组 g{gi + 1}: {name}  [{status}]")
        for s in stages:
            for it in s.items:
                writes = ", ".join(it.get("writes", []))
                lines.append(f"- {it.get('number')} {it.get('title')}"
                             + (f"  @writes:{writes}" if writes else ""))
        vh = [h for h in sm.validator_history if h.get("group") == gi + 1]
        if vh:
            chain = " → ".join(f"r{h.get('round')}:{h.get('verdict')}" for h in vh)
            lines.append(f"- validator: {chain}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
