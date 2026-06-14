"""Tests for PreToolUse Write 模板章节大纲注入分支（0.10.26+）。

PreToolUse `hook_on_pre_tool_use` 在 active spec 期间对 Write 4 份核心文档之一
（spec-dir 白名单）会通过 additionalContext 注入 mandatory / optional / dynamic
名单。Edit / MultiEdit 不触发（交给 B 层 spec_lint）；非 spec-dir 内文件不触发；
非 active 模式不触发；SPECODE_GUARD=off 不触发。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import pytest


def _parse_hook(stdout: str) -> Optional[dict]:
    s = stdout.strip()
    if not s:
        return None
    return json.loads(s)


def _ctx(payload: Optional[dict]) -> str:
    if payload is None:
        return ""
    return payload.get("hookSpecificOutput", {}).get("additionalContext", "")


def _write_session(fake_home: Path, sid: str, **overrides) -> Path:
    sess_dir = fake_home / ".specode" / "sessions"
    sess_dir.mkdir(parents=True, exist_ok=True)
    base = {
        "session_id": sid,
        "started_at": "2026-01-01T00:00:00Z",
        "last_activity_at": "2026-01-01T00:00:00Z",
        "ended_at": None,
        "mode": "idle",
        "active_spec_slug": None,
        "active_spec_dir": None,
        "spec_id": None,
        "phase": None,
        "lock_state": "released",
        "pending_selector": None,
    }
    base.update(overrides)
    p = sess_dir / f"{sid}.json"
    p.write_text(json.dumps(base), encoding="utf-8")
    return p


def _prep_active_spec(fake_home: Path, doc_root: Path, sid: str,
                      slug: str = "tmpl-notice", phase: str = "requirements") -> Path:
    """造一个 active spec。"""
    spec_dir = doc_root / "specs" / slug
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / ".config.json").write_text(json.dumps({
        "specId": slug,
        "slug": slug,
        "phase": phase,
        "lock": {"holder": sid, "acquired_at": "2026-01-01T00:00:00Z",
                 "last_heartbeat_at": "2026-01-01T00:00:00Z"},
    }), encoding="utf-8")
    _write_session(
        fake_home, sid,
        mode="active",
        active_spec_slug=slug,
        active_spec_dir=str(spec_dir),
        phase=phase,
        lock_state="ok",
    )
    return spec_dir


def _payload(sid: str, tool_name: str, file_path: str) -> str:
    return json.dumps({
        "session_id": sid,
        "tool_name": tool_name,
        "tool_input": {"file_path": file_path},
    })


# --------------------------------------------------------------------------

def test_write_requirements_md_injects_mandatory_and_optional(
    run_script, fake_home, make_session_id, doc_root
):
    sid = make_session_id()
    spec_dir = _prep_active_spec(fake_home, doc_root, sid)
    target = spec_dir / "requirements.md"

    cp = run_script("spec_session.py", "on-pre-tool-use",
                    stdin=_payload(sid, "Write", str(target)))
    assert cp.returncode == 0, cp.stderr
    ctx = _ctx(_parse_hook(cp.stdout))
    assert "requirements.md" in ctx
    # mandatory 命中：4 个章节都应出现
    assert "一、背景 / 目标 / 范围" in ctx
    assert "二、目标用户与场景" in ctx
    assert "三、待澄清问题" in ctx
    assert "四、需求详述" in ctx
    # optional 命中
    assert "五、非功能 / 约束（可选）" in ctx
    # 关键关键词
    assert "mandatory" in ctx
    assert "verbatim" in ctx
    assert "PreToolUse" in cp.stdout  # event name


def test_write_tasks_md_includes_dynamic_phase_prefix(
    run_script, fake_home, make_session_id, doc_root
):
    sid = make_session_id()
    spec_dir = _prep_active_spec(fake_home, doc_root, sid, phase="tasks")
    target = spec_dir / "tasks.md"

    cp = run_script("spec_session.py", "on-pre-tool-use",
                    stdin=_payload(sid, "Write", str(target)))
    assert cp.returncode == 0
    ctx = _ctx(_parse_hook(cp.stdout))
    assert "tasks.md" in ctx
    assert "概述" in ctx
    assert "测试要点" in ctx
    assert "验收" in ctx
    # 动态前缀
    assert "阶段 N: …" in ctx
    assert "dynamic" in ctx


def test_write_design_md_silent_no_optional(
    run_script, fake_home, make_session_id, doc_root
):
    """design.md 模板没有 optional 章节——注入文案应不含 optional 列表块。"""
    sid = make_session_id()
    spec_dir = _prep_active_spec(fake_home, doc_root, sid, phase="design")
    target = spec_dir / "design.md"

    cp = run_script("spec_session.py", "on-pre-tool-use",
                    stdin=_payload(sid, "Write", str(target)))
    assert cp.returncode == 0
    ctx = _ctx(_parse_hook(cp.stdout))
    assert "design.md" in ctx
    assert "概述" in ctx
    assert "架构" in ctx
    # design.md 无 optional：optional 标题块不该出现
    assert "optional（可整段删" not in ctx


def test_write_non_spec_dir_md_no_inject(
    run_script, fake_home, make_session_id, doc_root, tmp_path
):
    """Write 不在 active spec-dir 内的 requirements.md → 不注入（白名单保护）。"""
    sid = make_session_id()
    _prep_active_spec(fake_home, doc_root, sid)
    # 项目根 / 别的目录里的同名文档
    bogus = tmp_path / "elsewhere" / "requirements.md"
    bogus.parent.mkdir(parents=True, exist_ok=True)
    bogus.write_text("# 假冒\n", encoding="utf-8")

    cp = run_script("spec_session.py", "on-pre-tool-use",
                    stdin=_payload(sid, "Write", str(bogus)))
    assert cp.returncode == 0
    assert cp.stdout.strip() == "", f"expected no inject, got: {cp.stdout!r}"


def test_write_non_core_doc_in_spec_dir_no_inject(
    run_script, fake_home, make_session_id, doc_root
):
    """spec-dir 内的 implementation-log.md 不在 4 份核心列表里 → 不注入。"""
    sid = make_session_id()
    spec_dir = _prep_active_spec(fake_home, doc_root, sid)
    target = spec_dir / "implementation-log.md"

    cp = run_script("spec_session.py", "on-pre-tool-use",
                    stdin=_payload(sid, "Write", str(target)))
    assert cp.returncode == 0
    assert cp.stdout.strip() == ""


def test_edit_requirements_md_no_inject(
    run_script, fake_home, make_session_id, doc_root
):
    """Edit 不触发模板注入（让 B 层 spec_lint 后置兜底）。"""
    sid = make_session_id()
    spec_dir = _prep_active_spec(fake_home, doc_root, sid)
    target = spec_dir / "requirements.md"
    target.write_text("dummy", encoding="utf-8")

    cp = run_script("spec_session.py", "on-pre-tool-use",
                    stdin=_payload(sid, "Edit", str(target)))
    assert cp.returncode == 0
    assert cp.stdout.strip() == ""


def test_multiedit_requirements_md_no_inject(
    run_script, fake_home, make_session_id, doc_root
):
    sid = make_session_id()
    spec_dir = _prep_active_spec(fake_home, doc_root, sid)
    target = spec_dir / "requirements.md"
    target.write_text("dummy", encoding="utf-8")

    cp = run_script("spec_session.py", "on-pre-tool-use",
                    stdin=_payload(sid, "MultiEdit", str(target)))
    assert cp.returncode == 0
    assert cp.stdout.strip() == ""


def test_readonly_mode_no_inject(
    run_script, fake_home, make_session_id, doc_root
):
    """readonly 模式不该触发任何 PreToolUse 注入（包括模板大纲）。"""
    sid = make_session_id()
    spec_dir = doc_root / "specs" / "tmpl-readonly"
    spec_dir.mkdir(parents=True, exist_ok=True)
    _write_session(
        fake_home, sid,
        mode="readonly",
        active_spec_slug="tmpl-readonly",
        active_spec_dir=str(spec_dir),
        phase="requirements",
    )
    target = spec_dir / "requirements.md"

    cp = run_script("spec_session.py", "on-pre-tool-use",
                    stdin=_payload(sid, "Write", str(target)))
    assert cp.returncode == 0
    assert cp.stdout.strip() == ""


def test_idle_mode_no_inject(
    run_script, fake_home, make_session_id, doc_root
):
    sid = make_session_id()
    _write_session(fake_home, sid, mode="idle")
    target = doc_root / "specs" / "x" / "requirements.md"
    target.parent.mkdir(parents=True, exist_ok=True)

    cp = run_script("spec_session.py", "on-pre-tool-use",
                    stdin=_payload(sid, "Write", str(target)))
    assert cp.returncode == 0
    assert cp.stdout.strip() == ""


def test_specode_guard_off_no_inject(
    run_script, fake_home, make_session_id, doc_root
):
    sid = make_session_id()
    spec_dir = _prep_active_spec(fake_home, doc_root, sid)
    target = spec_dir / "requirements.md"

    cp = run_script(
        "spec_session.py", "on-pre-tool-use",
        stdin=_payload(sid, "Write", str(target)),
        extra_env={"SPECODE_GUARD": "off"},
    )
    assert cp.returncode == 0
    assert cp.stdout.strip() == ""
