"""tests for task_swarm_writeback.py — line-safe diff + 越界拒绝。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from task_swarm._writeback import (  # noqa: E402
    GroupFindings, StageFinding, WriteBackError, writeback_tasks_md,
)


def _make_tasks_md(tmp_path: Path) -> Path:
    p = tmp_path / "tasks.md"
    p.write_text(
        "# tasks\n\n"
        "## 阶段 1: 数据层\n"
        "- [ ] 1.1 user model @writes:src/u.py _需求：1.1_\n"
        "- [ ] 1.2 session @writes:src/s.py _需求：1.2_\n"
        "\n"
        "## 阶段 2: 服务层\n"
        "- [ ] 2.1 auth @writes:src/auth.py @depends-on:1 _需求：2.1_\n",
        encoding="utf-8",
    )
    return p


def test_writeback_basic_checkbox_toggle(tmp_path):
    p = _make_tasks_md(tmp_path)
    gf = GroupFindings(
        group_index=0, stages=[1], findings=[],
        validator_history=[{"group": 1, "round": 1, "verdict": "pass"}],
        final_verdict="pass", reproduce_cmd="pytest -v",
    )
    res = writeback_tasks_md(p, gf)
    new_text = p.read_text(encoding="utf-8")
    assert "- [x] 1.1" in new_text
    assert "- [x] 1.2" in new_text
    # stage 2 unchanged
    assert "- [ ] 2.1" in new_text


def test_writeback_appends_findings_block(tmp_path):
    p = _make_tasks_md(tmp_path)
    gf = GroupFindings(
        group_index=0, stages=[1],
        findings=[
            StageFinding(severity="p0", text="src/u.py:5 [req:1.1] — unique",
                         fix_status="已修复"),
            StageFinding(severity="advisory", text="src/u.py:50 — style",
                         fix_status="未修复"),
            StageFinding(severity="p1", text="src/s.py:10 — token len",
                         fix_status="未修复"),
        ],
        validator_history=[{"group": 1, "round": 1, "verdict": "pass"}],
        final_verdict="pass", reproduce_cmd="pytest",
    )
    writeback_tasks_md(p, gf)
    txt = p.read_text(encoding="utf-8")
    assert "[P0 已修复]" in txt
    assert "[adv 未修复]" in txt
    assert "[P1 未修复]" in txt
    assert "validator g1-r1 pass" in txt


def test_writeback_rejects_missing_stage(tmp_path):
    p = _make_tasks_md(tmp_path)
    gf = GroupFindings(group_index=0, stages=[99], findings=[])
    with pytest.raises(WriteBackError) as ei:
        writeback_tasks_md(p, gf)
    assert "99" in str(ei.value)


def test_writeback_preserves_writes_and_req_tags(tmp_path):
    p = _make_tasks_md(tmp_path)
    gf = GroupFindings(group_index=0, stages=[1], findings=[],
                       validator_history=[{"group": 1, "round": 1, "verdict": "pass"}],
                       final_verdict="pass")
    writeback_tasks_md(p, gf)
    txt = p.read_text(encoding="utf-8")
    assert "@writes:src/u.py" in txt
    assert "_需求：1.1_" in txt
    assert "@depends-on:1" in txt


def test_writeback_failed_deadloop_message(tmp_path):
    p = _make_tasks_md(tmp_path)
    gf = GroupFindings(
        group_index=0, stages=[1], findings=[],
        validator_history=[
            {"group": 1, "round": 1, "verdict": "fail", "signature": "abc"},
            {"group": 1, "round": 2, "verdict": "fail", "signature": "abc"},
            {"group": 1, "round": 3, "verdict": "fail", "signature": "abc"},
        ],
        final_verdict="failed-deadloop",
    )
    writeback_tasks_md(p, gf)
    txt = p.read_text(encoding="utf-8")
    assert "failed-deadloop" in txt


def test_writeback_validator_history_lines(tmp_path):
    p = _make_tasks_md(tmp_path)
    gf = GroupFindings(
        group_index=0, stages=[1], findings=[],
        validator_history=[
            {"group": 1, "round": 1, "verdict": "fail", "signature": "abc12345"},
            {"group": 1, "round": 2, "verdict": "pass"},
        ],
        final_verdict="pass", reproduce_cmd="pytest tests/",
    )
    writeback_tasks_md(p, gf)
    txt = p.read_text(encoding="utf-8")
    assert "g1-r1: fail" in txt
    assert "g1-r2: pass" in txt


def test_writeback_idempotent_already_checked(tmp_path):
    p = _make_tasks_md(tmp_path)
    # 第一次 writeback
    gf = GroupFindings(group_index=0, stages=[1], findings=[],
                       validator_history=[{"group": 1, "round": 1, "verdict": "pass"}],
                       final_verdict="pass")
    writeback_tasks_md(p, gf)
    # 第二次（应该不出错，checkbox 保持 x）
    writeback_tasks_md(p, gf)
    txt = p.read_text(encoding="utf-8")
    assert "- [x] 1.1" in txt


def test_writeback_rejects_nonexistent_file(tmp_path):
    with pytest.raises(WriteBackError):
        writeback_tasks_md(tmp_path / "missing.md", GroupFindings(group_index=0, stages=[1]))


def test_writeback_multi_stage_group_only_appends_to_last(tmp_path):
    p = tmp_path / "tasks.md"
    p.write_text(
        "## 阶段 1: A\n"
        "- [ ] 1.1 a @writes:a.py _需求：1.1_\n"
        "## 阶段 2: B\n"
        "- [ ] 2.1 b @writes:b.py _需求：2.1_\n",
        encoding="utf-8",
    )
    gf = GroupFindings(group_index=0, stages=[1, 2], findings=[],
                       validator_history=[{"group": 1, "round": 1, "verdict": "pass"}],
                       final_verdict="pass")
    writeback_tasks_md(p, gf)
    txt = p.read_text(encoding="utf-8")
    lines = txt.splitlines()
    # 注释块应在 stage 2 之后（文件末尾），而不是 stage 1 末尾
    # 也即：阶段 1 后面紧跟 ## 阶段 2:
    idx_stage1_item = next(i for i, l in enumerate(lines) if "1.1" in l)
    idx_stage2_header = next(i for i, l in enumerate(lines) if "## 阶段 2:" in l)
    # 这两个之间不应有 `>` 注释
    for l in lines[idx_stage1_item + 1: idx_stage2_header]:
        assert not l.startswith(">")
    # 但末尾有 `>` 注释
    assert any(l.startswith(">") for l in lines[idx_stage2_header:])
