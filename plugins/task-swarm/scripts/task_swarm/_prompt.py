#!/usr/bin/env python3
"""task_swarm_prompt.py — 预渲染 coder / reviewer / validator subagent 的 task.md。

按 references/task-swarm.md §4 规范输出，每个 prompt 必须含：
    - specId / spec_dir 上下文
    - @writes / @reads 边界
    - inbox 文件清单（指向 .task-swarm/runs/<id>/agents/<key>/inbox/）
    - outbox 路径
    - STATUS 输出协议

每个 prompt 渲染后写到：
    .task-swarm/runs/<run_id>/agents/<agent-key>/task.md

stdlib-only。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from task_swarm._state import _atomic_write_text  # noqa: E402


# -------------------------------------------------------------------------
# 项目级约束扫描（v0.9 痛点 #14 方案 D）
# -------------------------------------------------------------------------

_AGENT_DOC_FILENAMES = ("CLAUDE.md", "AGENTS.md", "AGENT.md", "CODEBUDDY.md")


def _agent_docs_paths(project_root: Optional[str],
                      task_writes: Optional[list[str]] = None) -> list[Path]:
    """Discover project-level agent instruction docs subagents must respect.

    The subagent's process loads neither the host CLAUDE.md/AGENTS.md
    automatically nor any per-subdir variant. So task.md must surface the
    absolute paths and tell the subagent to read them before coding.

    Scan order (deduped, only files that actually exist returned):
      1. <project_root>/<fn>          — repo root
      2. <project_root>/../<fn>       — immediate parent (monorepo workspace)
      3. for each entry in task_writes: walk from its directory up to (but
         not including) project_root, scanning <dir>/<fn> at every level.
         Catches monorepo sub-packages that own their own CLAUDE.md.
    """
    if not project_root:
        return []
    root = Path(project_root)
    try:
        if not root.is_dir():
            return []
    except OSError:
        return []
    root_resolved = root.resolve()

    found: list[Path] = []
    seen: set[Path] = set()

    def _scan(dir_: Path) -> None:
        for fn in _AGENT_DOC_FILENAMES:
            p = dir_ / fn
            try:
                rp = p.resolve()
            except OSError:
                continue
            if rp in seen:
                continue
            try:
                if rp.is_file():
                    found.append(rp)
                    seen.add(rp)
            except OSError:
                continue

    _scan(root_resolved)
    parent = root_resolved.parent
    if parent != root_resolved:
        _scan(parent)

    for w in (task_writes or []):
        if not w:
            continue
        wpath = Path(w)
        if wpath.is_absolute():
            continue
        write_dir = wpath.parent
        if str(write_dir) in ("", "."):
            continue
        try:
            target = (root_resolved / write_dir).resolve()
        except OSError:
            continue
        try:
            target.relative_to(root_resolved)
        except ValueError:
            continue
        cur = target
        # walk up to (but not including) project_root itself (already scanned)
        while cur != root_resolved:
            _scan(cur)
            nxt = cur.parent
            if nxt == cur:
                break
            cur = nxt

    return found


def _agent_docs_block(project_root: Optional[str],
                      writes: Optional[list[str]] = None) -> str:
    """Render the '## 项目级约束（必读）' section, or empty string if no docs.

    Path discovery is delegated to :func:`_agent_docs_paths` (3-layer scan:
    project_root / immediate parent / each ``@writes`` directory upward to
    project_root). The set of paths returned therefore depends on what this
    subagent's ``@writes`` touches — different groups see different subdir
    docs (a backend group sees ``ops-app/CLAUDE.md`` but not
    ``ops-web/CLAUDE.md``, and vice-versa). The block header documents that
    so subagents don't mistake the omission for "no relevant doc exists".

    0.7.4 (M6) tightens the wording to a hard constraint: the reviewer
    treats "started Edit/Bash without Read on these paths" as a violation,
    and a companion ``_PROJECT_AGENT_DOCS.md`` sentinel is dropped into
    the agent's inbox (see :func:`_drop_agent_docs_sentinel`) so even a
    subagent that skims past this section catches the signal a second time.
    """
    docs = _agent_docs_paths(project_root, writes)
    if not docs:
        return ""
    lines = [
        "## 项目级约束（必读）",
        "",
        ("⚠ 以下文件是项目 / 工作区根目录及本任务 `@writes` 上溯目录里的 agent 指南，"
         "**优先级高于本任务指令**。subagent 进程不自动加载这些文件——"
         "**在你发出第一个 Edit / Write / Bash 之前**必须用 Read 工具逐一读完，"
         "否则视为违反任务边界（reviewer 会以此扣分）。"
         "本段只列**绝对路径**，不复制内容；inbox 里还会有一份 "
         "`_PROJECT_AGENT_DOCS.md` 二次提醒，两处一致是冗余信号设计。"),
    ]
    for p in docs:
        lines.append(f"- `{p}`")
    lines.append("")
    lines.append("> 路径覆盖规则：本组 task 看到的子目录 agent 文件取决于本组 `@writes` "
                 "实际触达的子目录（如 backend 组看到 `ops-app/CLAUDE.md` 但不会看到 "
                 "`ops-web/CLAUDE.md`）；如果某条你预期会出现的路径缺席，先确认 "
                 "`@writes` 是否覆盖到那个子目录。")
    return "\n".join(lines) + "\n\n"


# -------------------------------------------------------------------------
# v0.9.0：superpowers 集成（方案 A+B；A 改 agents/*.md persona，B 是这里）
# -------------------------------------------------------------------------

#: Default superpowers skill recommendations per (role, mode).
#: Keep lists short to avoid prompt bloat; soft-dep — superpowers absent
#: silently degrades to native.
_DEFAULT_SUBAGENT_SKILLS: dict[tuple[str, str], list[tuple[str, str]]] = {
    # (role, mode) → [(skill_name, one-line rationale), ...]
    ("coder", "initial"): [
        ("test-driven-development",
         "先写失败 test → 跑 red → 写实现 → 跑 green; 避免直接写实现没补测试"),
    ],
    ("coder", "v-fix"): [
        ("systematic-debugging",
         "validator fail 后用 4 步法 (现场 / 假设 / 最小复现 / 修后验证) 避免凭直觉乱改"),
        ("test-driven-development",
         "若 v-fix 涉及新行为, 仍按 TDD 先写 fail test 再修"),
    ],
    ("coder", "p0-fix"): [
        ("systematic-debugging",
         "P0 是 reviewer 抓出的 evidence-tagged 问题; 先精确复现 evidence 描述的场景再修"),
    ],
    ("reviewer", "any"): [
        ("requesting-code-review",
         "review 范式 (severity 分级 / evidence tag / 修复指引格式)"),
    ],
    ("validator", "any"): [
        ("verification-before-completion",
         "验证范式 (哪些信号必须 prove with executable command vs '看起来对')"),
    ],
}


def _subagent_skills_block(role: str, mode: str = "any") -> str:
    """Render the '## 开发纪律 (推荐 superpowers skill)' section for
    a subagent's task.md (v0.9.0 方案 B).

    role ∈ {coder, reviewer, validator}
    mode ∈ {initial, p0-fix, v-fix, any}; for reviewer/validator pass "any"
    """
    skills = _DEFAULT_SUBAGENT_SKILLS.get((role, mode))
    if skills is None and mode != "any":
        skills = _DEFAULT_SUBAGENT_SKILLS.get((role, "any"))
    if not skills:
        return ""
    lines = [
        "## 开发纪律 (推荐 superpowers skill)",
        "",
        ("以下 skill 是本 role 的「开发纪律」推荐. **superpowers 已安装时**, "
         "用 `Skill` tool 调用它们走范式; **未装时** silently degrade to "
         "native — 仍按本 task.md 的输出协议 / schema 硬纪律执行 (与 skill "
         "是否在场无关). skill 是加速器, 不是 task.md 边界的替代品."),
        "",
    ]
    for skill_name, rationale in skills:
        lines.append(f"- `superpowers:{skill_name}` — {rationale}")
    lines.append("")
    lines.append("> 调用模式: `Skill('superpowers:<name>')` → 若 unavailable 走 except "
                 "分支, 绝不让 skill 缺席阻塞任务 (task.md 是 single source of "
                 "truth; superpowers 是 first-class but soft dep).")
    return "\n".join(lines) + "\n\n"


def _drop_agent_docs_sentinel(inbox: Path, project_root: Optional[str],
                               writes: Optional[list[str]] = None) -> None:
    """Write ``inbox/_PROJECT_AGENT_DOCS.md`` sentinel as a redundant signal
    of the same path list rendered in the task.md '项目级约束（必读）' block.

    Rationale (M6 + M10 unified fix, 0.7.4):
      - M6: '项目级约束' section in task.md alone relied on subagent
        self-discipline to Read; missing a strong second-channel signal.
      - M10: inbox/ ended up empty in every task-swarm run because no
        orchestrator step ever populated it — the "上游产物（只读）" naming
        was therefore name-vs-fact inconsistent.

    One write addresses both: the sentinel makes inbox non-empty (truthful
    inbox) AND duplicates the agent-doc signal in a place the subagent
    will inevitably encounter when listing inbox contents.
    """
    docs = _agent_docs_paths(project_root, writes)
    if not docs:
        return
    body = [
        "# _PROJECT_AGENT_DOCS.md — sentinel",
        "",
        "本文件是 task-swarm 0.7.4+ 自动放在每个 subagent inbox 的二次提醒"
        "（与 task.md 的「## 项目级约束（必读）」段冗余对齐）。",
        "",
        "**硬约束**：在你发出第一个 Edit / Write / Bash 之前，必须用 Read 工具"
        "逐一读完下面列出的所有路径。reviewer 会以此扣分。",
        "",
        "## 必读路径（覆盖本组 @writes 触达的所有子目录）",
        "",
    ]
    for p in docs:
        body.append(f"- `{p}`")
    body.append("")
    body.append("> 如某路径在你的本地缺席（如 `/CLAUDE.md` 真不存在），跳过该条即可——"
                "这是 path discovery 的 3 层兜底；只有 `is_file()` 为 true 的路径会被列出。")
    inbox.mkdir(parents=True, exist_ok=True)
    sentinel = inbox / "_PROJECT_AGENT_DOCS.md"
    _atomic_write_text(sentinel, "\n".join(body) + "\n")


# -------------------------------------------------------------------------
# 通用上下文段
# -------------------------------------------------------------------------

def _context_block(spec_id: str, spec_dir: str, run_id: str, group: int, round_: int,
                   project_root: Optional[str] = None) -> str:
    lines = [
        "## 上下文",
        f"- specId: {spec_id}",
    ]
    if spec_dir:
        lines.append(f"- spec_dir: {spec_dir}")
    # 0.10.15+：project_root 是代码实际写入的根目录，跟 spec_dir 区分
    if project_root:
        suffix = "  ← 代码必须写到这里，不要写到 spec_dir" if spec_dir else "  ← 代码必须写到这里"
        lines.append(f"- project_root: {project_root}{suffix}")
    elif spec_dir:
        lines.append("- project_root: (未设置；fallback 用 spec_dir，但应由主代理在 init 后通过 set-project-root CLI 指定)")
    else:
        lines.append("- project_root: (未设置；应由主代理在 init 后通过 set-project-root CLI 指定)")
    lines.extend([
        f"- run_id: {run_id}",
        f"- group: {group}",
        f"- round: {round_}",
    ])
    return "\n".join(lines) + "\n"


def _agent_root(run_dir: Path, agent_key: str) -> Path:
    return run_dir / "agents" / agent_key


def _ensure_agent_dirs(run_dir: Path, agent_key: str) -> tuple[Path, Path, Path]:
    """创建 agent_root / inbox / outbox 三个目录，返回它们。"""
    root = _agent_root(run_dir, agent_key)
    inbox = root / "inbox"
    outbox = root / "outbox"
    inbox.mkdir(parents=True, exist_ok=True)
    outbox.mkdir(parents=True, exist_ok=True)
    return root, inbox, outbox


def _stage_writes(stage: Any) -> list[str]:
    """获取 stage 的 writes 列表（兼容 property / 字段两种形式）。"""
    w = getattr(stage, "writes", None)
    if w is None:
        return []
    if callable(w):
        try:
            w = w()
        except TypeError:
            return []
    return list(w)


def _stage_reads(stage: Any) -> list[str]:
    r = getattr(stage, "reads", None)
    if r is None:
        return []
    if callable(r):
        try:
            r = r()
        except TypeError:
            return []
    return list(r)


# -------------------------------------------------------------------------
# coder prompt
# -------------------------------------------------------------------------

def render_coder_prompt(
    stage: Any,  # StageEntry-like：number/title/items/writes/reads/requirements
    run_dir: Path,
    run_id: str,
    spec_id: str,
    spec_dir: str,
    group: int,
    round_: int = 1,
    mode: str = "initial",  # initial / p0-fix / v-fix
    fix_targets: Optional[list[dict]] = None,
    file_idx: Optional[int] = None,
    project_root: Optional[str] = None,
) -> str:
    """渲染 coder 的 task.md。返回 prompt 文本。同步写到 agent 目录的 task.md。"""
    if mode == "initial":
        agent_key = f"coder-{group}-s{stage.number}-r{round_}"
    elif mode == "p0-fix":
        agent_key = f"coder-p0fix-{group}-r{round_}-f{file_idx or 0}"
    elif mode == "v-fix":
        agent_key = f"coder-vfix-{group}-r{round_}-f{file_idx or 0}"
    else:
        raise ValueError(f"未知 mode: {mode}")

    root, inbox, outbox = _ensure_agent_dirs(run_dir, agent_key)

    lines: list[str] = []
    title = stage.title if hasattr(stage, "title") else "修复任务"
    if mode == "initial":
        lines.append(f"# {agent_key}：阶段 {stage.number} {title}")
    else:
        lines.append(f"# {agent_key}：{mode} 修复任务")
    lines.append("")
    lines.append(_context_block(spec_id, spec_dir, run_id, group, round_,
                                 project_root=project_root))
    lines.append("")

    # 0.10.15+：项目根目录与路径规约（避免 subagent 把代码写到 spec_dir）
    lines.append("## 项目根目录与路径规约")
    if project_root:
        lines.append(f"- 代码根目录（`project_root`）：`{project_root}`")
        if spec_dir:
            lines.append(f"- spec 文档目录（`spec_dir`）：`{spec_dir}`")
        lines.append("- 下面 `@writes` / `@reads` / "
                     "「修复指引文件」中的**相对路径**，全部相对于 "
                     "`project_root` 解析（如 `src/services/foo.ts` "
                     "→ 实际写到 `<project_root>/src/services/foo.ts`）。")
        if spec_dir:
            lines.append("- **严禁**把代码 / 数据库 / node_modules 等写到 `spec_dir/` 下；"
                         "`spec_dir/` 只放 `*.md` 文档和 `.task-swarm/` 状态。")
        lines.append("- 跑 Bash 命令时请先 `cd \"" + project_root + "\"` 再执行 "
                     "`npm install` / `pytest` / `cargo` 等。")
    elif spec_dir:
        lines.append(f"- ⚠ project_root 未设置；fallback 用 spec_dir=`{spec_dir}`")
        lines.append("- 这是兼容老 spec 的退化路径。新 spec 应在 init 后通过 "
                     "project-root-choice selector + set-project-root CLI 显式指定。")
    else:
        lines.append("- ⚠ project_root 未设置；相对路径相对于 `--workdir` 解析。")
        lines.append("- 新 run 应在 init 后通过 project-root-choice selector + "
                     "set-project-root CLI 显式指定代码根目录。")
    lines.append("")

    # v0.9 痛点 #14：subagent 不会自动加载项目级 CLAUDE.md/AGENT.md
    coder_writes = _stage_writes(stage)
    agent_docs = _agent_docs_block(project_root, coder_writes)
    if agent_docs:
        lines.append(agent_docs.rstrip("\n"))
        lines.append("")
        # 0.7.4 (M6+M10): redundant signal sentinel in inbox
        _drop_agent_docs_sentinel(inbox, project_root, coder_writes)

    # v0.9.0 (方案 B): superpowers skill 推荐段；soft dep, 未装 silently degrade
    coder_skills = _subagent_skills_block("coder", mode)
    if coder_skills:
        lines.append(coder_skills.rstrip("\n"))
        lines.append("")

    if mode == "initial":
        lines.append("## 任务清单（按顺序逐条完成）")
        items = getattr(stage, "items", []) or []
        for it in items:
            tags = []
            it_writes = it.get("writes") if isinstance(it, dict) else getattr(it, "writes", [])
            it_reads = it.get("reads") if isinstance(it, dict) else getattr(it, "reads", [])
            it_reqs = it.get("requirements") if isinstance(it, dict) else getattr(it, "requirements", [])
            num = it.get("number") if isinstance(it, dict) else getattr(it, "number", "")
            it_title = it.get("title") if isinstance(it, dict) else getattr(it, "title", "")
            if it_writes:
                tags.append(f"@writes:{','.join(it_writes)}")
            if it_reads:
                tags.append(f"@reads:{','.join(it_reads)}")
            if it_reqs:
                tags.append("_需求:" + ",".join(it_reqs) + "_")
            suffix = (" " + " ".join(tags)) if tags else ""
            lines.append(f"- {num} {it_title}{suffix}")
        lines.append("")
        st_writes = _stage_writes(stage)
        st_reads = _stage_reads(stage)
        lines.append("## 文件边界（严格遵守）")
        lines.append(f"- @writes（仅允许写入）：{', '.join(st_writes) if st_writes else '(无声明)'}")
        lines.append(f"- @reads（允许读取）：{', '.join(st_reads) if st_reads else '(无声明)'}")
    elif mode == "p0-fix":
        lines.append("## P0 修复任务")
        lines.append("reviewer 提出的 P0（带证据标签）必须修复。详情见 inbox/p0-items.md。")
        lines.append("修复后请在 outbox/result.md 的「子任务状态」节按 done/failed 标记。")
        if fix_targets:
            lines.append("")
            lines.append("## 涉及文件")
            for ft in fix_targets:
                lines.append(f"- {ft.get('file_hint') or ft.get('file_path') or 'unknown'}")
    elif mode == "v-fix":
        lines.append("## v-fix 修复任务（按 validator 修复指引）")
        lines.append("仅修复 validator 在 validation.md 「给 coder 的修复指引」中列出的项。")
        lines.append("不要扩大范围；不要重写非失败相关的代码。")
        if fix_targets:
            lines.append("")
            lines.append("## 涉及文件 / 修复指引")
            for ft in fix_targets:
                lines.append(f"- 文件：{ft.get('file_path', '?')}")
                if ft.get("location"):
                    lines.append(f"  位置：{ft['location']}")
                if ft.get("problem"):
                    lines.append(f"  问题：{ft['problem']}")
                if ft.get("suggestion"):
                    lines.append(f"  建议：{ft['suggestion']}")
                if ft.get("requirements"):
                    lines.append(f"  _需求:{','.join(ft['requirements'])}_")

    lines.append("")
    lines.append("## inbox（上游产物，**只读**）")
    lines.append(f"- 路径：`{inbox}`")
    lines.append("- 内容（由主编排器在 fork 前放入）：上一轮 result.md / review.md / validation.md（按需）")
    lines.append("")
    lines.append("## outbox（你的产物**必须**写到这里）")
    lines.append(f"- result.md：`{outbox / 'result.md'}`")
    lines.append("")
    lines.append("## 输出协议（必读）")
    lines.append("1. result.md 必须含三节：`## 上下文` / `## 子任务状态` / `## 关键变更`")
    lines.append("2. 子任务状态行格式：`- <编号> <标题>: <done|failed|skipped> — <备注/文件>`")
    lines.append("3. 末行必须是：`STATUS: ok` 或 `STATUS: failed: <原因>` 或 `STATUS: blocked: <原因>`")
    lines.append("4. 严禁评价自己产物（不写 LGTM / 看起来不错）；reviewer 自会评审")
    lines.append("5. 严禁修改 @writes 之外的文件")

    text = "\n".join(lines) + "\n"
    _atomic_write_text(root / "task.md", text)
    return text


# -------------------------------------------------------------------------
# reviewer prompt
# -------------------------------------------------------------------------

def render_reviewer_prompt(
    group_stages: list[Any],
    coder_outboxes: list[Path],
    run_dir: Path,
    run_id: str,
    spec_id: str,
    spec_dir: str,
    group: int,
    round_: int = 1,
    project_root: Optional[str] = None,
) -> str:
    agent_key = f"reviewer-{group}-r{round_}"
    root, inbox, outbox = _ensure_agent_dirs(run_dir, agent_key)
    lines: list[str] = []
    lines.append(f"# {agent_key}：本 group {len(group_stages)} 个 stage 联合评审")
    lines.append("")
    lines.append(_context_block(spec_id, spec_dir, run_id, group, round_,
                                 project_root=project_root))
    lines.append("")
    # v0.9 痛点 #14：subagent 不会自动加载项目级 CLAUDE.md/AGENT.md
    all_writes: list[str] = []
    for s in group_stages:
        all_writes.extend(_stage_writes(s))
    agent_docs = _agent_docs_block(project_root, all_writes)
    if agent_docs:
        lines.append(agent_docs.rstrip("\n"))
        lines.append("")
        # 0.7.4 (M6+M10): redundant signal sentinel in inbox
        _drop_agent_docs_sentinel(inbox, project_root, all_writes)
    # v0.9.0 (方案 B): superpowers skill 推荐段
    rev_skills = _subagent_skills_block("reviewer")
    if rev_skills:
        lines.append(rev_skills.rstrip("\n"))
        lines.append("")
    lines.append("## 评审范围")
    for s in group_stages:
        st_writes = _stage_writes(s)
        lines.append(f"- 阶段 {s.number}: {s.title}（@writes: {', '.join(st_writes)}）")
    lines.append("")
    lines.append("## inbox（上游 coder 全部产物）")
    for p in coder_outboxes:
        lines.append(f"- `{p}`")
    lines.append("")
    lines.append("## outbox")
    lines.append(f"- review.md：`{outbox / 'review.md'}`")
    lines.append("")
    lines.append("## review.md schema（必须严格遵守）")
    lines.append("````markdown")
    lines.append("# " + agent_key)
    lines.append("")
    lines.append("## 结论")
    lines.append("needs-changes | approved-with-comments | approved")
    lines.append("")
    lines.append("## P0（每条必须带证据标签：[req:x.y] / [security] / [contract]）")
    lines.append("- <file:line> [req:x.y] — <一句话说明>")
    lines.append("（如无 P0：本节写 `(none)`）")
    lines.append("")
    lines.append("## P1")
    lines.append("- <file:line> — <说明>")
    lines.append("")
    lines.append("## P2")
    lines.append("- <一句话风格类建议>")
    lines.append("")
    lines.append("## 给使用者的提示")
    lines.append("- 一句话总结")
    lines.append("")
    lines.append("STATUS: ok")
    lines.append("````")
    lines.append("")
    lines.append("## 关键约束")
    lines.append("- P0 必须带证据标签；否则自动降级为 advisory（仅写入 tasks.md 注释，不进 fix loop）")
    lines.append("- reviewer 不参与修复循环；本轮 advisory 提完即结束（v0.7 reviewer round 恒为 1）")
    lines.append("- 末行恒为 `STATUS: ok`（advisory 模式；pass/fail 在 validator）")

    text = "\n".join(lines) + "\n"
    _atomic_write_text(root / "task.md", text)
    return text


# -------------------------------------------------------------------------
# validator prompt
# -------------------------------------------------------------------------

def render_validator_prompt(
    group_stages: list[Any],
    run_dir: Path,
    run_id: str,
    spec_id: str,
    spec_dir: str,
    group: int,
    round_: int = 1,
    prev_validation: Optional[Path] = None,
    project_root: Optional[str] = None,
) -> str:
    agent_key = f"validator-{group}-r{round_}"
    root, inbox, outbox = _ensure_agent_dirs(run_dir, agent_key)
    lines: list[str] = []
    lines.append(f"# {agent_key}：本 group {len(group_stages)} 个 stage 联合验证")
    lines.append("")
    lines.append(_context_block(spec_id, spec_dir, run_id, group, round_,
                                 project_root=project_root))
    lines.append("")
    if project_root:
        lines.append(f"## 跑验证命令时请先 `cd \"{project_root}\"`")
        if spec_dir:
            lines.append("（所有 `@writes` 路径相对 `project_root`，不是 `spec_dir`）")
        else:
            lines.append("（所有 `@writes` 路径相对 `project_root`）")
        lines.append("")
    # v0.9 痛点 #14：subagent 不会自动加载项目级 CLAUDE.md/AGENT.md
    all_writes: list[str] = []
    for s in group_stages:
        all_writes.extend(_stage_writes(s))
    agent_docs = _agent_docs_block(project_root, all_writes)
    if agent_docs:
        lines.append(agent_docs.rstrip("\n"))
        lines.append("")
        # 0.7.4 (M6+M10): redundant signal sentinel in inbox
        _drop_agent_docs_sentinel(inbox, project_root, all_writes)
    # v0.9.0 (方案 B): superpowers skill 推荐段
    val_skills = _subagent_skills_block("validator")
    if val_skills:
        lines.append(val_skills.rstrip("\n"))
        lines.append("")
    lines.append("## 验证范围")
    for s in group_stages:
        lines.append(f"- 阶段 {s.number}: {s.title}")
        items = getattr(s, "items", []) or []
        for it in items:
            num = it.get("number") if isinstance(it, dict) else getattr(it, "number", "")
            it_title = it.get("title") if isinstance(it, dict) else getattr(it, "title", "")
            it_reqs = it.get("requirements") if isinstance(it, dict) else getattr(it, "requirements", [])
            req = ("（_需求:" + ",".join(it_reqs) + "_）") if it_reqs else ""
            lines.append(f"  - {num} {it_title}{req}")
    lines.append("")
    if prev_validation is not None:
        lines.append("## 上一轮 validation（本轮在其上验证 v-fix 是否成功）")
        lines.append(f"- `{prev_validation}`")
        lines.append("")
    lines.append("## outbox")
    lines.append(f"- validation.md：`{outbox / 'validation.md'}`")
    lines.append("")
    lines.append("## validation.md schema（必须严格遵守）")
    lines.append("````markdown")
    lines.append("# " + agent_key)
    lines.append("")
    lines.append("## 判定")
    lines.append("pass | fail")
    lines.append("")
    lines.append("## 复现命令")
    lines.append("```bash")
    lines.append("cd <project root>")
    lines.append("pytest tests/... -v")
    lines.append("```")
    lines.append("")
    lines.append("## 按子任务的验证结果")
    lines.append("- [x] 1.1 <标题>: pass")
    lines.append("- [ ] 1.3 <标题>: fail — <一句话现场>")
    lines.append("")
    lines.append("## 失败现场（fail 时必填）")
    lines.append("```")
    lines.append("FAILED tests/... ::test_xxx")
    lines.append("AssertionError: ...")
    lines.append("```")
    lines.append("")
    lines.append("## 给 coder 的修复指引（fail 时必填，不带 P0/P1 标签）")
    lines.append("### 修复 1 — <短标题>")
    lines.append("- 文件: <abs/rel>")
    lines.append("- 位置: <函数名 / 行号>")
    lines.append("- 问题: <说明>")
    lines.append("- 建议: <修复方向>")
    lines.append("- _需求:x.y_")
    lines.append("")
    lines.append("STATUS: ok")
    lines.append("````")
    lines.append("")
    lines.append("## 关键约束")
    lines.append("- pass / fail 是客观信号；fail 必须给出可复现命令 + 失败现场 + 按文件分组的修复指引")
    lines.append("- 不要评论代码风格（那是 reviewer 的活）；只关心可验证项")
    lines.append("- 末行恒为 `STATUS: ok`")

    text = "\n".join(lines) + "\n"
    _atomic_write_text(root / "task.md", text)
    return text


# -------------------------------------------------------------------------
# 模块自测
# -------------------------------------------------------------------------

if __name__ == "__main__":  # pragma: no cover
    print("import this module; see render_coder_prompt / render_reviewer_prompt / render_validator_prompt")
