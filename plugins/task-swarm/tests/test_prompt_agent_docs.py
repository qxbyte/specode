"""Regression tests for v0.9 痛点 #14 方案 D — `## 项目级约束（必读）` section.

subagent 进程不会自动加载项目根 CLAUDE.md / AGENT.md / AGENTS.md /
CODEBUDDY.md，导致试跑时 coder 完全不看项目级约束（试跑时 dayjs import
顺序等局部约束反复被违反就是这个根因）。修法：扫 project_root + 父目录 +
@writes 子目录里这 4 个文件名，命中的绝对路径塞进 task.md。
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(REPO_ROOT))

from task_swarm._prompt import (  # noqa: E402
    _agent_docs_paths,
    render_coder_prompt,
    render_reviewer_prompt,
    render_validator_prompt,
)
from task_swarm._state import StageEntry  # noqa: E402


def _stage(items: list[dict] | None = None, writes: list[str] | None = None,
           number: str = "1.1", title: str = "x") -> StageEntry:
    """Build a minimal StageEntry compatible with _prompt.py signatures."""
    return StageEntry(
        number=number,
        title=title,
        items=items or [{"number": number, "title": title, "writes": writes or [],
                          "reads": [], "requirements": []}],
        writes=writes or [],
        reads=[],
        requirements=[],
    )


def test_project_root_claude_md_listed_in_task_md(tmp_path: Path) -> None:
    """project_root 根下有 CLAUDE.md → task.md 里以绝对路径列出。"""
    proj = tmp_path / "proj"
    proj.mkdir()
    claude = proj / "CLAUDE.md"
    claude.write_text("# project rules\n", encoding="utf-8")

    paths = _agent_docs_paths(str(proj))
    assert claude.resolve() in paths

    stage = _stage(writes=["src/foo.py"])
    run_dir = tmp_path / "run"
    text = render_coder_prompt(
        stage=stage, run_dir=run_dir, run_id="r1", spec_id="s",
        spec_dir=str(tmp_path / "spec"), group="g1", round_=1, mode="initial",
        project_root=str(proj),
    )
    assert "## 项目级约束（必读）" in text
    assert str(claude.resolve()) in text


def test_no_agent_docs_section_absent(tmp_path: Path) -> None:
    """No CLAUDE.md / AGENT.md / etc anywhere → section absent."""
    proj = tmp_path / "proj"
    proj.mkdir()
    # parent (tmp_path) has no docs either
    stage = _stage(writes=["src/foo.py"])
    run_dir = tmp_path / "run"
    text = render_coder_prompt(
        stage=stage, run_dir=run_dir, run_id="r1", spec_id="s",
        spec_dir=str(tmp_path / "spec"), group="g1", round_=1, mode="initial",
        project_root=str(proj),
    )
    assert "## 项目级约束（必读）" not in text


def test_subdir_claude_md_picked_up_via_writes(tmp_path: Path) -> None:
    """@writes touches ops-web/src/pages/X.tsx → scan ops-web/, ops-web/src/,
    ops-web/src/pages/. CLAUDE.md in ops-web/ should be listed."""
    proj = tmp_path / "monorepo"
    proj.mkdir()
    subpkg = proj / "ops-web"
    subpkg.mkdir()
    sub_claude = subpkg / "CLAUDE.md"
    sub_claude.write_text("# ops-web specific\n", encoding="utf-8")
    # also put one at project_root to confirm both come through
    root_claude = proj / "CLAUDE.md"
    root_claude.write_text("# repo wide\n", encoding="utf-8")

    # Without writes pointing into ops-web, sub_claude is NOT reached
    paths_no_writes = _agent_docs_paths(str(proj), task_writes=[])
    assert root_claude.resolve() in paths_no_writes
    assert sub_claude.resolve() not in paths_no_writes

    # With writes pointing into ops-web/src/pages/X.tsx, sub_claude shows up
    paths = _agent_docs_paths(
        str(proj), task_writes=["ops-web/src/pages/TicketsPage.tsx"],
    )
    assert root_claude.resolve() in paths
    assert sub_claude.resolve() in paths

    # And the rendered coder task.md surfaces both
    stage = _stage(writes=["ops-web/src/pages/TicketsPage.tsx"])
    run_dir = tmp_path / "run"
    text = render_coder_prompt(
        stage=stage, run_dir=run_dir, run_id="r1", spec_id="s",
        spec_dir=str(tmp_path / "spec"), group="g1", round_=1, mode="initial",
        project_root=str(proj),
    )
    assert "## 项目级约束（必读）" in text
    assert str(root_claude.resolve()) in text
    assert str(sub_claude.resolve()) in text


def test_parent_workspace_agents_md_listed(tmp_path: Path) -> None:
    """sub-repo's project_root has no docs but the workspace parent has
    AGENTS.md (typical wework-ops-assistant case) → listed."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "AGENTS.md").write_text("# workspace rules\n", encoding="utf-8")
    subrepo = workspace / "ops-app"
    subrepo.mkdir()

    paths = _agent_docs_paths(str(subrepo))
    assert (workspace / "AGENTS.md").resolve() in paths


def test_reviewer_validator_prompts_carry_agent_docs(tmp_path: Path) -> None:
    """reviewer and validator also need to see project-level constraints."""
    proj = tmp_path / "proj"
    proj.mkdir()
    claude = proj / "CLAUDE.md"
    claude.write_text("# rules\n", encoding="utf-8")

    stages = [_stage(writes=["src/a.py"], number="1.1", title="t1"),
              _stage(writes=["src/b.py"], number="1.2", title="t2")]
    run_dir = tmp_path / "run"

    rev = render_reviewer_prompt(
        group_stages=stages, coder_outboxes=[run_dir / "agents" / "coder-g1-s1.1-r1" / "outbox"],
        run_dir=run_dir, run_id="r1", spec_id="s",
        spec_dir=str(tmp_path / "spec"), group="g1", round_=1,
        project_root=str(proj),
    )
    assert "## 项目级约束（必读）" in rev
    assert str(claude.resolve()) in rev

    val = render_validator_prompt(
        group_stages=stages, run_dir=run_dir, run_id="r1", spec_id="s",
        spec_dir=str(tmp_path / "spec"), group="g1", round_=1,
        project_root=str(proj),
    )
    assert "## 项目级约束（必读）" in val
    assert str(claude.resolve()) in val


def test_project_root_none_returns_empty(tmp_path: Path) -> None:
    """project_root unset → helper returns [], section absent."""
    assert _agent_docs_paths(None) == []
    assert _agent_docs_paths("") == []

    stage = _stage(writes=["src/foo.py"])
    run_dir = tmp_path / "run"
    text = render_coder_prompt(
        stage=stage, run_dir=run_dir, run_id="r1", spec_id="s",
        spec_dir=str(tmp_path / "spec"), group="g1", round_=1, mode="initial",
        project_root=None,
    )
    assert "## 项目级约束（必读）" not in text
