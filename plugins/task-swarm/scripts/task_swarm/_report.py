"""task_swarm._report — 从 state 渲染人类可读 markdown 报告（纯函数，事实源 state.json）。

M3：遍历 task_groups（语义任务组）+ 调度依赖链。
"""
from __future__ import annotations


def render_report(sm, group=None) -> str:
    lines = []
    groups = list(sm.task_groups)
    total = len(groups)
    done = sum(1 for g in groups if g.status == "done")
    failed = any(g.status in ("failed", "failed-deadloop") for g in groups)
    overall = ("失败" if failed else "全部完成" if total and done == total else "进行中")
    lines += ["# task-swarm run report", "", f"- run_id: {sm.run_id}"]
    if getattr(sm, "spec_id", None):
        lines.append(f"- spec_id: {sm.spec_id}")
    lines += [f"- 整体状态: {overall}（{done}/{total} 任务组完成）", ""]
    sel = groups if group is None else [g for g in groups if g.id == group]
    for g in sel:
        lines.append(f"## 任务组 {g.id}: {g.name}  [{g.status}]")
        if g.needs:
            lines.append(f"- 依赖: {', '.join(g.needs)}")
        for it in g.items:
            writes = ", ".join(it.get("writes", []))
            lines.append(f"- {it.get('number')} {it.get('title')}"
                         + (f"  @writes:{writes}" if writes else ""))
        if g.validator_history:
            chain = " → ".join(f"r{h.get('round')}:{h.get('verdict')}"
                               for h in g.validator_history)
            lines.append(f"- validator: {chain}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
