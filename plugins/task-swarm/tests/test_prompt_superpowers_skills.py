"""Regression tests for the «开发纪律 (范式参考)» section in task.md
(originated as v0.9.0 方案 B; v0.9.2 dropped 方案 A and reframed this section
as a paradigm reference — Claude Code subagent has no Skill tool, so the
section now lists skill names as paradigm identifiers, not invoke targets).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(REPO_ROOT))

from task_swarm._prompt import (  # noqa: E402
    _subagent_skills_block,
    render_coder_prompt,
    render_reviewer_prompt,
    render_validator_prompt,
)
from task_swarm._state import StageEntry  # noqa: E402


def _stage(writes: list[str] | None = None, number: str = "1.1") -> StageEntry:
    return StageEntry(
        number=number, title="t",
        items=[{"number": number, "title": "t", "writes": writes or [],
                "reads": [], "requirements": []}],
        writes=writes or [], reads=[], requirements=[],
    )


def test_coder_initial_recommends_tdd() -> None:
    block = _subagent_skills_block("coder", "initial")
    assert "## 开发纪律" in block
    assert "test-driven-development" in block
    assert "systematic-debugging" not in block


def test_coder_vfix_recommends_systematic_debug_and_tdd() -> None:
    block = _subagent_skills_block("coder", "v-fix")
    assert "systematic-debugging" in block
    assert "test-driven-development" in block


def test_coder_p0fix_recommends_systematic_debug() -> None:
    block = _subagent_skills_block("coder", "p0-fix")
    assert "systematic-debugging" in block


def test_reviewer_any_recommends_code_review() -> None:
    block = _subagent_skills_block("reviewer", "any")
    assert "requesting-code-review" in block


def test_validator_any_recommends_verification() -> None:
    block = _subagent_skills_block("validator", "any")
    assert "verification-before-completion" in block


def test_unknown_role_returns_empty_block() -> None:
    assert _subagent_skills_block("notarole", "any") == ""


def test_block_warns_against_skill_invoke() -> None:
    """0.9.2: section must explicitly tell the subagent NOT to call Skill(...)
    and must affirm task.md as single source of truth."""
    block = _subagent_skills_block("coder", "initial")
    assert "不要尝试" in block or "无 Skill tool" in block
    assert "task.md" in block


def test_block_drops_skill_invoke_pseudo_code() -> None:
    """0.9.2: the old «调用模式: Skill('superpowers:<name>')» line must be gone
    so subagents don't waste a roundtrip on a guaranteed-unavailable call."""
    block = _subagent_skills_block("coder", "initial")
    assert "Skill('superpowers:" not in block
    assert "调用模式" not in block


def test_render_coder_prompt_includes_skills_block(tmp_path: Path) -> None:
    stage = _stage(writes=["src/a.py"])
    run_dir = tmp_path / "run"
    text = render_coder_prompt(
        stage=stage, run_dir=run_dir, run_id="r", spec_id="s",
        spec_dir=str(tmp_path / "spec"), group="g1", round_=1, mode="initial",
        project_root=str(tmp_path),
    )
    assert "## 开发纪律" in text
    assert "test-driven-development" in text


def test_render_coder_prompt_vfix_includes_systematic_debug(tmp_path: Path) -> None:
    stage = _stage(writes=["src/a.py"])
    run_dir = tmp_path / "run"
    text = render_coder_prompt(
        stage=stage, run_dir=run_dir, run_id="r", spec_id="s",
        spec_dir=str(tmp_path / "spec"), group="g1", round_=1, mode="v-fix",
        fix_targets=[{"file_path": "src/a.py", "problem": "x"}],
        project_root=str(tmp_path),
    )
    assert "systematic-debugging" in text


def test_render_reviewer_prompt_includes_skills_block(tmp_path: Path) -> None:
    stages = [_stage(writes=["src/a.py"])]
    run_dir = tmp_path / "run"
    text = render_reviewer_prompt(
        group_stages=stages,
        coder_outboxes=[run_dir / "agents" / "coder-g1-s1.1-r1" / "outbox"],
        run_dir=run_dir, run_id="r", spec_id="s",
        spec_dir=str(tmp_path / "spec"), group="g1", round_=1,
        project_root=str(tmp_path),
    )
    assert "## 开发纪律" in text
    assert "requesting-code-review" in text


def test_render_validator_prompt_includes_skills_block(tmp_path: Path) -> None:
    stages = [_stage(writes=["src/a.py"])]
    run_dir = tmp_path / "run"
    text = render_validator_prompt(
        group_stages=stages, run_dir=run_dir, run_id="r", spec_id="s",
        spec_dir=str(tmp_path / "spec"), group="g1", round_=1,
        project_root=str(tmp_path),
    )
    assert "## 开发纪律" in text
    assert "verification-before-completion" in text
