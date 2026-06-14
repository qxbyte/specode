"""Tests for spec_session.py business sub-commands.

Covers: acquire / release / heartbeat / verify-lock / phase-transition /
        load / continue / end / status / read-session.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def _spec_cfg(spec_dir: Path) -> dict:
    return json.loads((spec_dir / ".config.json").read_text(encoding="utf-8"))


def _sess(fake_home: Path, sid: str) -> dict:
    return json.loads((fake_home / ".specode" / "sessions" / f"{sid}.json").read_text(encoding="utf-8"))


# --- acquire / release / heartbeat ---------------------------------------

def test_acquire_when_lock_null_succeeds(
    run_script, init_spec, fake_home, make_session_id
):
    slug, sid_init, spec_dir, _ = init_spec()
    # release first so lock=null
    cp_rel = run_script("spec_session.py", "release",
                        "--spec", str(spec_dir), "--session", sid_init)
    assert cp_rel.returncode == 0
    assert _spec_cfg(spec_dir)["lock"] is None

    sid_new = make_session_id()
    cp = run_script("spec_session.py", "acquire",
                    "--spec", str(spec_dir), "--session", sid_new)
    assert cp.returncode == 0, cp.stderr
    out = json.loads(cp.stdout)
    assert out["ok"] is True
    assert out["holder"] == sid_new
    cfg = _spec_cfg(spec_dir)
    assert cfg["lock"]["holder"] == sid_new
    assert cfg["lock"]["acquired_at"]
    assert cfg["lock"]["last_heartbeat_at"]


def test_acquire_when_held_by_other_returns_exit_4(
    run_script, init_spec, fake_home, make_session_id
):
    slug, sid_init, spec_dir, _ = init_spec()
    # sid_init holds the lock by default. Try to acquire from another session.
    sid_other = make_session_id()
    cp = run_script("spec_session.py", "acquire",
                    "--spec", str(spec_dir), "--session", sid_other)
    assert cp.returncode == 4, cp.stderr
    out = json.loads(cp.stdout)
    assert out["ok"] is False
    assert out["reason"] == "LockHeld"
    assert out["holder"] == sid_init


def test_acquire_force_takes_over(
    run_script, init_spec, fake_home, make_session_id
):
    slug, sid_init, spec_dir, _ = init_spec()
    sid_other = make_session_id()
    cp = run_script("spec_session.py", "acquire",
                    "--spec", str(spec_dir), "--session", sid_other, "--force")
    assert cp.returncode == 0, cp.stderr
    out = json.loads(cp.stdout)
    assert out["ok"] is True
    assert out["holder"] == sid_other
    assert _spec_cfg(spec_dir)["lock"]["holder"] == sid_other


def test_release_when_holder_clears_lock(
    run_script, init_spec, fake_home
):
    slug, sid, spec_dir, _ = init_spec()
    cp = run_script("spec_session.py", "release",
                    "--spec", str(spec_dir), "--session", sid)
    assert cp.returncode == 0
    assert _spec_cfg(spec_dir)["lock"] is None
    sess = _sess(fake_home, sid)
    assert sess["lock_state"] == "released"


def test_release_by_non_holder_is_silent_ok(
    run_script, init_spec, fake_home, make_session_id
):
    slug, sid_init, spec_dir, _ = init_spec()
    sid_other = make_session_id()
    cp = run_script("spec_session.py", "release",
                    "--spec", str(spec_dir), "--session", sid_other)
    # release is tolerant: non-holder should not break the system
    assert cp.returncode == 0, cp.stderr
    # Lock still held by sid_init
    assert _spec_cfg(spec_dir)["lock"]["holder"] == sid_init


# --- heartbeat ----------------------------------------------------------

def test_heartbeat_refreshes_last_heartbeat(
    run_script, init_spec, fake_home
):
    slug, sid, spec_dir, _ = init_spec()
    before = _spec_cfg(spec_dir)["lock"]["last_heartbeat_at"]
    # ensure clock moves a second
    import time as _t; _t.sleep(1.1)
    cp = run_script("spec_session.py", "heartbeat",
                    "--spec", str(spec_dir), "--session", sid)
    assert cp.returncode == 0, cp.stderr
    after = _spec_cfg(spec_dir)["lock"]["last_heartbeat_at"]
    assert after >= before  # ISO timestamps; later or equal


def test_heartbeat_non_holder_returns_exit_1(
    run_script, init_spec, fake_home, make_session_id
):
    slug, sid_init, spec_dir, _ = init_spec()
    sid_other = make_session_id()
    cp = run_script("spec_session.py", "heartbeat",
                    "--spec", str(spec_dir), "--session", sid_other)
    assert cp.returncode == 1
    out = json.loads(cp.stdout)
    assert out["ok"] is False
    assert out["reason"] == "lock_lost"


# --- verify-lock -----------------------------------------------------------

def test_verify_lock_ok_for_holder(run_script, init_spec, fake_home):
    slug, sid, spec_dir, _ = init_spec()
    cp = run_script("spec_session.py", "verify-lock",
                    "--spec", str(spec_dir), "--session", sid)
    assert cp.returncode == 0, cp.stderr
    out = json.loads(cp.stdout)
    assert out["ok"] is True
    assert out["holder"] == sid


def test_verify_lock_evicted_for_other(
    run_script, init_spec, fake_home, make_session_id
):
    slug, sid_init, spec_dir, _ = init_spec()
    sid_other = make_session_id()
    cp = run_script("spec_session.py", "verify-lock",
                    "--spec", str(spec_dir), "--session", sid_other)
    assert cp.returncode == 3
    out = json.loads(cp.stdout)
    assert out["ok"] is False
    assert out["reason"] in ("evicted", "stale_lock")


def test_verify_lock_not_held_when_null(
    run_script, init_spec, fake_home, make_session_id
):
    slug, sid_init, spec_dir, _ = init_spec()
    run_script("spec_session.py", "release",
               "--spec", str(spec_dir), "--session", sid_init)
    sid_q = make_session_id()
    cp = run_script("spec_session.py", "verify-lock",
                    "--spec", str(spec_dir), "--session", sid_q)
    assert cp.returncode == 3
    out = json.loads(cp.stdout)
    assert out["ok"] is False
    assert out["reason"] == "not_held"


# --- phase-transition -----------------------------------------------------

def test_phase_transition_updates_both_files(
    run_script, init_spec, fake_home
):
    slug, sid, spec_dir, _ = init_spec()
    cp = run_script("spec_session.py", "phase-transition",
                    "--spec", str(spec_dir), "--session", sid,
                    "--from", "intake", "--to", "requirements")
    assert cp.returncode == 0, cp.stderr
    cfg = _spec_cfg(spec_dir)
    assert cfg["phase"] == "requirements"
    # auto pending_selector for requirements phase
    assert cfg["pending_selector"] == "doc-confirm-requirements"
    sess = _sess(fake_home, sid)
    assert sess["phase"] == "requirements"
    assert sess["pending_selector"] == "doc-confirm-requirements"


def test_phase_transition_to_iteration_clears_pending_selector(
    run_script, init_spec, fake_home
):
    """acceptance → iteration 不再自动注入 iteration-scope；停在 chat 等用户提。

    回归防护：曾经 `_auto_pending_selector(phase="iteration")` 返回
    `"iteration-scope"`，导致验收通过后立刻追问"本轮要调整什么"，与
    iteration.md §2 / §7「不自动呈现」设计冲突。0.10.23 起统一返回 None。
    """
    slug, sid, spec_dir, _ = init_spec()
    cfg = _spec_cfg(spec_dir)
    cfg["phase"] = "acceptance"
    (spec_dir / ".config.json").write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    cp = run_script("spec_session.py", "phase-transition",
                    "--spec", str(spec_dir), "--session", sid,
                    "--from", "acceptance", "--to", "iteration")
    assert cp.returncode == 0, cp.stderr
    out = json.loads(cp.stdout)
    assert out["ok"] is True
    assert out["phase"] == "iteration"
    assert out["pending_selector"] is None
    assert _spec_cfg(spec_dir)["pending_selector"] is None
    assert _sess(fake_home, sid)["pending_selector"] is None


def test_phase_transition_lock_lost_returns_exit_1(
    run_script, init_spec, fake_home, make_session_id
):
    slug, sid_init, spec_dir, _ = init_spec()
    sid_other = make_session_id()
    cp = run_script("spec_session.py", "phase-transition",
                    "--spec", str(spec_dir), "--session", sid_other,
                    "--from", "intake", "--to", "requirements")
    assert cp.returncode == 1
    out = json.loads(cp.stdout)
    assert out["ok"] is False
    assert out["reason"] == "lock_lost"
    # phase unchanged
    assert _spec_cfg(spec_dir)["phase"] == "intake"


def test_phase_transition_phase_mismatch_blocks(
    run_script, init_spec, fake_home
):
    slug, sid, spec_dir, _ = init_spec()
    cp = run_script("spec_session.py", "phase-transition",
                    "--spec", str(spec_dir), "--session", sid,
                    "--from", "design", "--to", "tasks")
    assert cp.returncode == 1
    out = json.loads(cp.stdout)
    assert out["reason"] == "phase_mismatch"
    assert out["current"] == "intake"
    assert _spec_cfg(spec_dir)["phase"] == "intake"


# --- end ------------------------------------------------------------------

def test_end_sets_mode_ended_and_releases_lock(
    run_script, init_spec, fake_home
):
    slug, sid, spec_dir, _ = init_spec()
    cp = run_script("spec_session.py", "end", "--session", sid)
    assert cp.returncode == 0, cp.stderr
    sess = _sess(fake_home, sid)
    assert sess["mode"] == "ended"
    assert sess["ended_at"]
    assert sess["pending_selector"] is None
    # 对齐 end.md 文档：active_spec_* 必须清空
    assert sess["active_spec_slug"] is None
    assert sess["active_spec_dir"] is None
    assert sess["spec_id"] is None
    assert sess["phase"] is None
    # 下一 turn 由 hook 注入一次性反向提醒
    assert sess["post_end_reminder_pending"] is True
    # lock cleared because end-holder == session
    assert _spec_cfg(spec_dir)["lock"] is None


# --- read-session & status ------------------------------------------------

def test_read_session_emits_payload(run_script, init_spec, fake_home):
    slug, sid, spec_dir, _ = init_spec()
    cp = run_script("spec_session.py", "read-session", "--session", sid)
    assert cp.returncode == 0
    payload = json.loads(cp.stdout)
    assert payload["session_id"] == sid
    assert payload["mode"] == "active"
    assert payload["active_spec_slug"] == slug


def test_read_session_migrates_legacy_claude_session_id(
    run_script, fake_home, make_session_id
):
    """老 sessions/<id>.json 字段名是 claude_session_id；read_session 应自动塞 session_id 字段。"""
    sid = make_session_id()
    sess_dir = fake_home / ".specode" / "sessions"
    sess_dir.mkdir(parents=True, exist_ok=True)
    legacy = {
        "claude_session_id": sid,
        "started_at": "2026-01-01T00:00:00Z",
        "last_activity_at": "2026-01-01T00:00:00Z",
        "mode": "idle",
    }
    (sess_dir / f"{sid}.json").write_text(json.dumps(legacy), encoding="utf-8")
    cp = run_script("spec_session.py", "read-session", "--session", sid)
    assert cp.returncode == 0, cp.stderr
    payload = json.loads(cp.stdout)
    assert payload["session_id"] == sid
    # 老字段仍保留（向后兼容；后续写入才会被覆盖为新格式）
    assert payload.get("claude_session_id") == sid


def test_status_emits_human_summary(run_script, init_spec, fake_home):
    slug, sid, spec_dir, _ = init_spec()
    cp = run_script("spec_session.py", "status", "--session", sid)
    assert cp.returncode == 0
    out = json.loads(cp.stdout)
    assert out["ok"] is True
    assert "session" in out
    assert "spec_config" in out
    assert out["session"]["active_spec_slug"] == slug


def test_status_session_not_found(run_script, fake_home, make_session_id):
    sid = make_session_id()
    cp = run_script("spec_session.py", "status", "--session", sid)
    # Spec says ok=False but exit 0 (still soft)
    assert cp.returncode == 0
    out = json.loads(cp.stdout)
    assert out["ok"] is False
    assert out["reason"] == "session_not_found"


def test_load_emits_spec_config(run_script, init_spec, fake_home):
    slug, sid, spec_dir, _ = init_spec()
    cp = run_script("spec_session.py", "load", "--spec", str(spec_dir))
    assert cp.returncode == 0
    out = json.loads(cp.stdout)
    assert out["ok"] is True
    assert out["config"]["slug"] == slug


# --- set-project-root (0.10.15+) -----------------------------------------

def test_set_project_root_writes_config_and_advances_selector(
    run_script, init_spec, fake_home, tmp_path
):
    """成功路径：写 project_root + pending_selector 推到 workflow-choice。"""
    slug, sid, spec_dir, _ = init_spec()
    cfg_before = _spec_cfg(spec_dir)
    assert cfg_before["pending_selector"] == "project-root-choice"
    assert cfg_before["project_root"] is None

    project = tmp_path / "my-project"
    project.mkdir()

    cp = run_script(
        "spec_session.py", "set-project-root",
        "--spec", str(spec_dir),
        "--session", sid,
        "--root", str(project),
    )
    assert cp.returncode == 0, cp.stderr
    out = json.loads(cp.stdout)
    assert out["ok"] is True
    assert out["project_root"] == str(project)
    assert out["pending_selector"] == "workflow-choice"

    cfg = _spec_cfg(spec_dir)
    assert cfg["project_root"] == str(project)
    assert cfg["pending_selector"] == "workflow-choice"
    sess = _sess(fake_home, sid)
    assert sess["pending_selector"] == "workflow-choice"


def test_set_project_root_auto_creates_missing_dir(
    run_script, init_spec, fake_home, tmp_path
):
    """--root 路径不存在时自动 mkdir -p（cwd/slug 新项目场景）。"""
    slug, sid, spec_dir, _ = init_spec()
    new_dir = tmp_path / "brand-new" / "nested"
    assert not new_dir.exists()

    cp = run_script(
        "spec_session.py", "set-project-root",
        "--spec", str(spec_dir),
        "--session", sid,
        "--root", str(new_dir),
    )
    assert cp.returncode == 0, cp.stderr
    assert new_dir.exists() and new_dir.is_dir()


def test_set_project_root_rejects_relative_path(
    run_script, init_spec, fake_home
):
    slug, sid, spec_dir, _ = init_spec()
    cp = run_script(
        "spec_session.py", "set-project-root",
        "--spec", str(spec_dir),
        "--session", sid,
        "--root", "relative/path/here",
    )
    assert cp.returncode == 1
    assert "绝对路径" in cp.stderr


def test_set_project_root_rejects_non_directory(
    run_script, init_spec, fake_home, tmp_path
):
    slug, sid, spec_dir, _ = init_spec()
    a_file = tmp_path / "i-am-a-file.txt"
    a_file.write_text("content", encoding="utf-8")

    cp = run_script(
        "spec_session.py", "set-project-root",
        "--spec", str(spec_dir),
        "--session", sid,
        "--root", str(a_file),
    )
    assert cp.returncode == 1
    assert "不是目录" in cp.stderr


def test_set_project_root_rejects_non_lock_holder(
    run_script, init_spec, fake_home, make_session_id, tmp_path
):
    slug, _sid_holder, spec_dir, _ = init_spec()
    other_sid = make_session_id()  # 不持锁
    project = tmp_path / "proj"
    project.mkdir()

    cp = run_script(
        "spec_session.py", "set-project-root",
        "--spec", str(spec_dir),
        "--session", other_sid,
        "--root", str(project),
    )
    assert cp.returncode == 1
    assert "lock holder" in cp.stderr
