"""tests for task_swarm_outbox.py — 3 类产物 schema 校验。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from task_swarm._outbox import (  # noqa: E402
    ParseError, parse_coder_result, parse_reviewer_review, parse_validator_validation,
)


# -------------------------------------------------------------------------
# coder
# -------------------------------------------------------------------------

def _write(p: Path, text: str) -> Path:
    p.write_text(text, encoding="utf-8")
    return p


def test_coder_result_ok(tmp_path):
    p = _write(tmp_path / "r.md",
        "# coder\n\n"
        "## 上下文\n- specId: x\n\n"
        "## 子任务状态\n- 1.1 user: done — src/u.py\n- 1.2 sess: failed — Imp\n\n"
        "## 关键变更\n- 新增 model\n\n"
        "STATUS: ok\n"
    )
    res = parse_coder_result(p)
    assert res.status == "ok"
    assert len(res.subtasks) == 2
    assert res.subtasks[0].status == "done"
    assert res.subtasks[1].status == "failed"
    assert "新增 model" in res.key_changes


def test_coder_result_failed_status(tmp_path):
    p = _write(tmp_path / "r.md",
        "# coder\n\n## 上下文\n- a\n\n## 子任务状态\n## 关键变更\n\nSTATUS: failed: ImportError\n"
    )
    res = parse_coder_result(p)
    assert res.status == "failed"
    assert "ImportError" in res.status_reason


def test_coder_result_blocked(tmp_path):
    p = _write(tmp_path / "r.md",
        "# coder\n## 子任务状态\n## 关键变更\nSTATUS: blocked: 等上游\n"
    )
    res = parse_coder_result(p)
    assert res.status == "blocked"
    assert "等上游" in res.status_reason


def test_coder_result_missing_status_raises(tmp_path):
    p = _write(tmp_path / "r.md",
        "# coder\n## 子任务状态\n- 1.1 a: done\n\n## 关键变更\n- x\n"
    )
    with pytest.raises(ParseError) as ei:
        parse_coder_result(p)
    assert "STATUS" in str(ei.value)


def test_coder_result_nonexistent_file_raises(tmp_path):
    with pytest.raises(ParseError) as ei:
        parse_coder_result(tmp_path / "missing.md")
    assert "不存在" in str(ei.value)


# -------------------------------------------------------------------------
# reviewer
# -------------------------------------------------------------------------

def test_reviewer_with_p0_evidence(tmp_path):
    p = _write(tmp_path / "r.md",
        "# rev\n\n## 结论\nneeds-changes\n\n"
        "## P0\n- src/a.py:34 [req:1.2] — login 失败未区分锁/密码错\n\n"
        "## P1\n- src/b.py:5 — 缺校验\n\n"
        "## P2\n- 命名建议\n\n"
        "## 给使用者的提示\n- 注意\n\n"
        "STATUS: ok\n"
    )
    rev = parse_reviewer_review(p)
    assert rev.verdict == "needs-changes"
    assert len(rev.p0_items) == 1
    assert rev.p0_items[0].evidence_tags == ["req:1.2"]
    assert len(rev.p1_items) == 1
    assert len(rev.p2_items) == 1
    assert rev.advisory_items == []


def test_reviewer_p0_no_evidence_downgrades(tmp_path):
    p = _write(tmp_path / "r.md",
        "# rev\n\n## 结论\napproved-with-comments\n\n"
        "## P0\n- src/a.py:34 — 没标签的 P0\n- src/b.py [security] — 有安全标签\n\n"
        "## P1\n(none)\n\n## P2\n\nSTATUS: ok\n"
    )
    rev = parse_reviewer_review(p)
    assert len(rev.p0_items) == 1
    assert "security" in rev.p0_items[0].evidence_tags
    assert len(rev.advisory_items) == 1
    assert rev.advisory_items[0].severity == "advisory"


def test_reviewer_approved_no_p0(tmp_path):
    p = _write(tmp_path / "r.md",
        "# rev\n\n## 结论\napproved\n\n## P0\n(none)\n\n## P1\n\n## P2\n\nSTATUS: ok\n"
    )
    rev = parse_reviewer_review(p)
    assert rev.verdict == "approved"
    assert rev.p0_items == []


def test_reviewer_missing_verdict_raises(tmp_path):
    p = _write(tmp_path / "r.md",
        "# rev\n\n## P0\n(none)\nSTATUS: ok\n"
    )
    with pytest.raises(ParseError):
        parse_reviewer_review(p)


def test_reviewer_bad_status_raises(tmp_path):
    p = _write(tmp_path / "r.md",
        "# rev\n## 结论\napproved\n## P0\n(none)\n\nSTATUS: failed\n"
    )
    with pytest.raises(ParseError):
        parse_reviewer_review(p)


# -------------------------------------------------------------------------
# validator
# -------------------------------------------------------------------------

def test_validator_pass(tmp_path):
    p = _write(tmp_path / "v.md",
        "# v\n\n## 判定\npass\n\n"
        "## 复现命令\n```bash\npytest -v\n```\n\n"
        "## 按子任务的验证结果\n- [x] 1.1 a: pass\n\n"
        "STATUS: ok\n"
    )
    val = parse_validator_validation(p)
    assert val.verdict == "pass"
    assert "pytest" in val.reproduce_cmd
    assert len(val.subtask_results) == 1


def test_validator_fail_with_fix_targets(tmp_path):
    p = _write(tmp_path / "v.md",
        "# v\n\n## 判定\nfail\n\n"
        "## 复现命令\n```bash\npytest -v\n```\n\n"
        "## 按子任务的验证结果\n- [ ] 1.1 ctrl: fail — 5 次失败未锁\n\n"
        "## 失败现场\n```\nFAILED tests/t.py::test_lockout\nAssertionError: expected 423\n```\n\n"
        "## 给 coder 的修复指引\n"
        "### 修复 1 — lockout 计数器\n"
        "- 文件: src/login.py\n"
        "- 位置: login() 失败分支\n"
        "- 问题: 没计数\n"
        "- 建议: 引入 lockout 模块\n"
        "- _需求：1.3_\n\n"
        "STATUS: ok\n"
    )
    val = parse_validator_validation(p)
    assert val.verdict == "fail"
    assert val.failure_excerpt
    assert len(val.fix_targets) == 1
    assert val.fix_targets[0].file_path == "src/login.py"
    assert "1.3" in val.fix_targets[0].requirements


def test_validator_fail_signature_stable(tmp_path):
    body = (
        "# v\n## 判定\nfail\n## 复现命令\n```bash\npytest\n```\n"
        "## 按子任务的验证结果\n- [ ] 1.1 a: fail\n"
        "## 失败现场\n```\nFAILED tests/t.py::test_a\nAssertionError: x\n```\n"
        "## 给 coder 的修复指引\n### 修复 1\n- 文件: a.py\n"
        "STATUS: ok\n"
    )
    p1 = _write(tmp_path / "v1.md", body)
    p2 = _write(tmp_path / "v2.md", body)
    s1 = parse_validator_validation(p1).fail_signature()
    s2 = parse_validator_validation(p2).fail_signature()
    assert s1 == s2
    assert s1  # non-empty


def test_validator_fail_signature_differs_on_different_failure(tmp_path):
    p1 = _write(tmp_path / "a.md",
        "# v\n## 判定\nfail\n## 复现命令\n```bash\npytest\n```\n"
        "## 失败现场\n```\nFAILED tests/t.py::test_a\nAssertionError: foo\n```\n"
        "## 给 coder 的修复指引\n### 修复 1\n- 文件: a.py\nSTATUS: ok\n")
    p2 = _write(tmp_path / "b.md",
        "# v\n## 判定\nfail\n## 复现命令\n```bash\npytest\n```\n"
        "## 失败现场\n```\nFAILED tests/t.py::test_b\nAssertionError: bar\n```\n"
        "## 给 coder 的修复指引\n### 修复 1\n- 文件: a.py\nSTATUS: ok\n")
    assert parse_validator_validation(p1).fail_signature() != parse_validator_validation(p2).fail_signature()


def test_validator_pass_no_signature(tmp_path):
    p = _write(tmp_path / "v.md",
        "# v\n## 判定\npass\n## 复现命令\n```bash\npytest\n```\nSTATUS: ok\n")
    val = parse_validator_validation(p)
    assert val.fail_signature() == ""


def test_validator_fail_missing_failure_excerpt_raises(tmp_path):
    p = _write(tmp_path / "v.md",
        "# v\n## 判定\nfail\n## 复现命令\n```bash\npytest\n```\n"
        "## 给 coder 的修复指引\n### 修复 1\n- 文件: a.py\n\nSTATUS: ok\n")
    with pytest.raises(ParseError) as ei:
        parse_validator_validation(p)
    assert "失败现场" in str(ei.value)


def test_validator_fail_missing_fix_targets_raises(tmp_path):
    p = _write(tmp_path / "v.md",
        "# v\n## 判定\nfail\n## 复现命令\n```bash\npytest\n```\n"
        "## 失败现场\n```\nFAILED x\nAssertionError\n```\n\nSTATUS: ok\n")
    with pytest.raises(ParseError) as ei:
        parse_validator_validation(p)
    assert "修复指引" in str(ei.value)


def test_validator_missing_verdict_raises(tmp_path):
    p = _write(tmp_path / "v.md",
        "# v\n## 复现命令\n```bash\npytest\n```\nSTATUS: ok\n")
    with pytest.raises(ParseError):
        parse_validator_validation(p)
