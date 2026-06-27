"""Regression tests for task.md "## 任务清单" rendering.

v0.9 痛点 #13: `_items_as_stages` constructed StageEntry without filling
the `items` field, so `_prompt.py`'s `for it in stage.items` loop
iterated 0 times and the rendered task.md had an EMPTY 「## 任务清单」
section — coders got no specific instructions, only the file boundary
section. multi-agent fork loses all meaning.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(REPO_ROOT))

from task_swarm._prompt import render_coder_prompt  # noqa: E402
from task_swarm._state import StageEntry  # noqa: E402


def _build_stage_from_pipeline_task(task: dict, number: str = "1.1") -> StageEntry:
    """Mirror `cli._items_as_stages` exactly."""
    from task_swarm import cli

    fake_gs = type("GS", (), {"items": [task]})()
    stages = cli._items_as_stages(fake_gs)
    assert len(stages) == 1
    return stages[0]


def test_task_md_renders_pipeline_task_title_into_tasklist_section(tmp_path: Path) -> None:
    """The whole-fix regression: a pipeline task with a non-empty `title`
    must show up in the rendered task.md's 「## 任务清单」 section."""
    pipeline_task = {
        "number": "1.1",
        "title": "TicketsPage 详情面板加 createdAt/updatedAt 两行",
        "writes": ["ops-web/src/pages/TicketsPage.tsx"],
        "reads": ["ops-web/src/api/client.ts"],
        "requirements": ["AC-3", "AC-5"],
    }
    stage = _build_stage_from_pipeline_task(pipeline_task)

    run_dir = tmp_path / "run"
    (run_dir / "agents" / "coder-g1-s1.1-r1").mkdir(parents=True)

    text = render_coder_prompt(
        stage=stage,
        run_dir=run_dir,
        run_id="20260628-xxx",
        spec_id="ticket-detail-timestamps",
        spec_dir="/path/to/spec",
        group="g1",
        round_=1,
        mode="initial",
        project_root="/path/to/project_root",
    )

    # The rendered text MUST contain the task title — otherwise the coder
    # has no idea what to do.
    assert "TicketsPage 详情面板加 createdAt/updatedAt 两行" in text, (
        "task title missing from rendered task.md — v0.9 痛点 #13 regression"
    )
    # The 「任务清单」 section must NOT be immediately followed by the
    # 「文件边界」 section with nothing in between (the bug signature).
    tasklist_pos = text.index("## 任务清单（按顺序逐条完成）")
    boundary_pos = text.index("## 文件边界（严格遵守）")
    section_body = text[tasklist_pos:boundary_pos]
    # The body should contain the task line (starts with "- 1.1").
    assert "- 1.1" in section_body, (
        f"任务清单 section is empty (the v0.9 痛点 #13 signature). "
        f"Got body: {section_body!r}"
    )


def test_task_md_renders_writes_reads_requirements_tags(tmp_path: Path) -> None:
    """The rendered task line must include @writes / @reads / requirements."""
    pipeline_task = {
        "number": "2.3",
        "title": "edit X",
        "writes": ["a.py", "b.py"],
        "reads": ["c.py"],
        "requirements": ["1.1", "1.2"],
    }
    stage = _build_stage_from_pipeline_task(pipeline_task, number="2.3")
    run_dir = tmp_path / "run"
    (run_dir / "agents" / "coder-g1-s2.3-r1").mkdir(parents=True)

    text = render_coder_prompt(
        stage=stage,
        run_dir=run_dir,
        run_id="r",
        spec_id="",
        spec_dir="",
        group="g1",
        round_=1,
        mode="initial",
        project_root="/p",
    )

    # Task line must carry the inline tags.
    assert "@writes:a.py,b.py" in text
    assert "@reads:c.py" in text
    assert "1.1,1.2" in text


def test_task_md_with_zero_items_still_lists_tasklist_header(tmp_path: Path) -> None:
    """Even an empty group must produce the section header (otherwise the
    pre-existing renderer crashes on an unknown structure). This pins the
    minimal contract."""
    pipeline_task = {
        "number": "0.0",
        "title": "",
        "writes": [],
        "reads": [],
        "requirements": [],
    }
    stage = _build_stage_from_pipeline_task(pipeline_task, number="0.0")
    run_dir = tmp_path / "run"
    (run_dir / "agents" / "coder-g1-s0.0-r1").mkdir(parents=True)
    text = render_coder_prompt(
        stage=stage,
        run_dir=run_dir,
        run_id="r",
        spec_id="",
        spec_dir="",
        group="g1",
        round_=1,
        mode="initial",
        project_root="/p",
    )
    assert "## 任务清单（按顺序逐条完成）" in text
