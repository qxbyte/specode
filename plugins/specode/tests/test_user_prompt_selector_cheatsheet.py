"""Tests for UserPromptSubmit selector cheat sheet 注入（0.10.27+）。

active / readonly 模式下 pending_selector 命中固定 selector → additionalContext
含 verbatim labels cheat sheet；命中 dynamic selector → 含结构约束描述。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


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
        "mode": "active",
        "active_spec_slug": "sel-cheat",
        "active_spec_dir": None,
        "spec_id": "x",
        "phase": "intake",
        "lock_state": "ok",
        "pending_selector": None,
    }
    base.update(overrides)
    p = sess_dir / f"{sid}.json"
    p.write_text(json.dumps(base), encoding="utf-8")
    return p


def _make_spec(doc_root: Path, slug: str = "sel-cheat") -> Path:
    sd = doc_root / "specs" / slug
    sd.mkdir(parents=True, exist_ok=True)
    (sd / ".config.json").write_text(json.dumps({
        "specId": slug, "slug": slug, "phase": "intake",
        "source_text": "测试 selector cheat sheet",
        "invocation_cwd": "/tmp/proj",
    }), encoding="utf-8")
    return sd


def _payload(sid: str, prompt: str = "go") -> str:
    return json.dumps({"session_id": sid, "prompt": prompt})


def test_active_workflow_choice_cheatsheet_contains_verbatim_labels(
    run_script, fake_home, make_session_id, doc_root
):
    sid = make_session_id()
    sd = _make_spec(doc_root)
    _write_session(fake_home, sid, active_spec_dir=str(sd),
                   pending_selector="workflow-choice")
    cp = run_script("spec_session.py", "on-user-prompt", stdin=_payload(sid))
    ctx = _ctx(_parse_hook(cp.stdout))
    # cheat sheet 标题
    assert "AskUserQuestion 参数铁律" in ctx
    assert "workflow-choice" in ctx
    assert "fixed" in ctx
    # 3 个 verbatim labels
    assert "Requirements first" in ctx
    assert "Technical Design first" in ctx
    assert "Bugfix" in ctx
    # 强调字眼
    assert "verbatim" in ctx
    assert "exit 2" in ctx
    # hallucinate 反例提示
    assert "TDD" in ctx and "RAPID" in ctx


def test_active_clarification_wizard_cheatsheet_marked_dynamic(
    run_script, fake_home, make_session_id, doc_root
):
    sid = make_session_id()
    sd = _make_spec(doc_root)
    _write_session(fake_home, sid, active_spec_dir=str(sd),
                   pending_selector="clarification-wizard")
    cp = run_script("spec_session.py", "on-user-prompt", stdin=_payload(sid))
    ctx = _ctx(_parse_hook(cp.stdout))
    assert "AskUserQuestion 参数铁律" in ctx
    assert "clarification-wizard" in ctx
    assert "dynamic" in ctx
    # 结构约束提示
    assert "动态生成" in ctx
    assert "2" in ctx and "4" in ctx
    assert "multiSelect=false" in ctx


def test_active_iteration_scope_cheatsheet_shows_multiselect_true(
    run_script, fake_home, make_session_id, doc_root
):
    sid = make_session_id()
    sd = _make_spec(doc_root)
    _write_session(fake_home, sid, active_spec_dir=str(sd),
                   pending_selector="iteration-scope")
    cp = run_script("spec_session.py", "on-user-prompt", stdin=_payload(sid))
    ctx = _ctx(_parse_hook(cp.stdout))
    assert "iteration-scope" in ctx
    assert "multiSelect" in ctx and "true" in ctx
    # 4 个 verbatim labels
    for lbl in ("改 requirements", "改 design", "改 tasks", "重跑测试"):
        assert lbl in ctx, f"missing label: {lbl}"


def test_readonly_takeover_options_cheatsheet_present(
    run_script, fake_home, make_session_id, doc_root
):
    """readonly 模式（如 takeover-options 场景）也注入 cheat sheet。"""
    sid = make_session_id()
    sd = _make_spec(doc_root)
    _write_session(fake_home, sid, mode="readonly", active_spec_dir=str(sd),
                   pending_selector="takeover-options")
    cp = run_script("spec_session.py", "on-user-prompt", stdin=_payload(sid))
    ctx = _ctx(_parse_hook(cp.stdout))
    assert "takeover-options" in ctx
    assert "AskUserQuestion 参数铁律" in ctx
    for lbl in ("强制接管", "只读查看", "取消"):
        assert lbl in ctx


def test_active_no_pending_selector_no_cheatsheet(
    run_script, fake_home, make_session_id, doc_root
):
    """无 pending_selector 时不注入 cheat sheet（避免噪声）。"""
    sid = make_session_id()
    sd = _make_spec(doc_root)
    _write_session(fake_home, sid, active_spec_dir=str(sd),
                   pending_selector=None)
    cp = run_script("spec_session.py", "on-user-prompt", stdin=_payload(sid))
    ctx = _ctx(_parse_hook(cp.stdout))
    assert "AskUserQuestion 参数铁律" not in ctx


def test_idle_mode_no_cheatsheet(
    run_script, fake_home, make_session_id
):
    sid = make_session_id()
    _write_session(fake_home, sid, mode="idle", pending_selector="workflow-choice")
    cp = run_script("spec_session.py", "on-user-prompt", stdin=_payload(sid))
    ctx = _ctx(_parse_hook(cp.stdout))
    # idle 模式不进 (b) 分支，无 cheat sheet
    assert "AskUserQuestion 参数铁律" not in ctx
