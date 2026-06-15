"""Tests for spec_init.py — initial spec scaffolding + session/active-pointer writes."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


DOC_FILENAMES = (
    "requirements.md",
    "bugfix.md",
    "design.md",
    "implementation-log.md",
)


def test_spec_init_does_not_scaffold_tasks_md(
    run_script, doc_root, fake_home, make_session_id
):
    """M4 起 specode 不再产 tasks.md：scaffold 出来的目录不含 tasks.md。"""
    sid = make_session_id()
    cp = run_script(
        "spec_init.py",
        "--name", "no-tasks",
        "--requirement-name", "NoTasks",
        "--source-text", "x",
        "--session", sid,
    )
    assert cp.returncode == 0, cp.stderr
    spec_dir = Path(json.loads(cp.stdout)["spec_dir"])
    assert not (spec_dir / "tasks.md").exists()


def test_spec_init_creates_full_skeleton(run_script, doc_root, fake_home, make_session_id):
    sid = make_session_id()
    cp = run_script(
        "spec_init.py",
        "--name", "alpha-spec",
        "--requirement-name", "Alpha Spec",
        "--source-text", "我要做一个测试需求",
        "--session", sid,
    )
    assert cp.returncode == 0, cp.stderr
    payload = json.loads(cp.stdout)
    spec_dir = Path(payload["spec_dir"])
    assert spec_dir.exists()
    # All 5 markdown docs present
    for name in DOC_FILENAMES:
        assert (spec_dir / name).exists(), f"{name} missing"
    # .config.json present
    assert (spec_dir / ".config.json").exists()


def test_spec_init_config_json_initial_state(
    run_script, doc_root, fake_home, make_session_id
):
    sid = make_session_id()
    cp = run_script(
        "spec_init.py",
        "--name", "beta-spec",
        "--requirement-name", "Beta",
        "--source-text", "需求 B",
        "--session", sid,
    )
    assert cp.returncode == 0, cp.stderr
    payload = json.loads(cp.stdout)
    spec_dir = Path(payload["spec_dir"])
    cfg = json.loads((spec_dir / ".config.json").read_text(encoding="utf-8"))
    assert cfg["specId"] == payload["specId"]
    assert cfg["slug"] == "beta-spec"
    assert cfg["phase"] == "intake"
    # 0.10.15+：spec 创建后第一个 selector 是 project-root-choice，由
    # set-project-root CLI 推进到 workflow-choice
    assert cfg["pending_selector"] == "project-root-choice"
    assert cfg["workflow"] is None
    # lock initially held by the initialising session
    assert cfg["lock"]["holder"] == sid
    assert cfg["doc_root"] == str(doc_root)
    assert cfg["source_text"] == "需求 B"
    # 0.10.15+：spec_init 时记录 cwd 给 project-root-choice selector 渲染用
    assert "invocation_cwd" in cfg
    assert cfg["invocation_cwd"]  # 非空
    # project_root 此时尚未指定，等 set-project-root CLI 才写入
    assert cfg["project_root"] is None


def test_spec_init_writes_sessions_file(
    run_script, doc_root, fake_home, make_session_id
):
    sid = make_session_id()
    cp = run_script(
        "spec_init.py",
        "--name", "gamma",
        "--requirement-name", "Gamma",
        "--source-text", "需求 C",
        "--session", sid,
    )
    assert cp.returncode == 0, cp.stderr
    sess_path = fake_home / ".specode" / "sessions" / f"{sid}.json"
    assert sess_path.exists()
    sess = json.loads(sess_path.read_text(encoding="utf-8"))
    assert sess["session_id"] == sid
    assert sess["mode"] == "active"
    assert sess["active_spec_slug"] == "gamma"
    assert sess["phase"] == "intake"
    # 0.10.15+：spec 创建后第一个 selector 是 project-root-choice
    assert sess["pending_selector"] == "project-root-choice"
    assert sess["lock_state"] == "ok"


def test_spec_init_updates_active_pointer(
    run_script, doc_root, fake_home, make_session_id
):
    sid = make_session_id()
    cp = run_script(
        "spec_init.py",
        "--name", "delta",
        "--requirement-name", "Delta",
        "--source-text", "需求 D",
        "--session", sid,
    )
    assert cp.returncode == 0, cp.stderr
    ptr_path = doc_root / ".active-specode.json"
    assert ptr_path.exists()
    ptr = json.loads(ptr_path.read_text(encoding="utf-8"))
    assert ptr["active_spec_slug"] == "delta"
    assert ptr["session_id"] == sid
    assert ptr["specId"] == json.loads(cp.stdout)["specId"]


def test_spec_init_missing_root_exits_3(
    run_script, fake_home, monkeypatch, make_session_id
):
    """All three tiers miss → exit 3 + stderr hint."""
    monkeypatch.delenv("SPECODE_ROOT", raising=False)
    sid = make_session_id()
    cp = run_script(
        "spec_init.py",
        "--name", "no-root",
        "--requirement-name", "NoRoot",
        "--source-text", "x",
        "--session", sid,
    )
    assert cp.returncode == 3
    assert "doc_root" in cp.stderr or "vault" in cp.stderr


def test_spec_init_duplicate_slug_falls_back_to_continue_with_lock_conflict(
    run_script, doc_root, fake_home, make_session_id
):
    """0.10.27+：同 slug 重 spec_init 不再 exit 3 拒绝，而是 fallback 到 cmd_continue。

    sid1 已持有 spec lock 时，sid2 来 init 同 slug：cmd_continue 检测到锁冲突 →
    pending_selector=takeover-options + exit 4。既有 .config.json 保留不变（specId
    与 source_text 都不被覆盖）。
    """
    sid1 = make_session_id()
    cp1 = run_script(
        "spec_init.py",
        "--name", "dupe",
        "--requirement-name", "First",
        "--source-text", "first",
        "--session", sid1,
    )
    assert cp1.returncode == 0, cp1.stderr
    first_cfg = json.loads(
        (doc_root / "specs" / "dupe" / ".config.json").read_text(encoding="utf-8")
    )

    sid2 = make_session_id()
    cp2 = run_script(
        "spec_init.py",
        "--name", "dupe",
        "--requirement-name", "Second",
        "--source-text", "second",
        "--session", sid2,
    )
    # cmd_continue LockHeld → exit 4
    assert cp2.returncode == 4
    assert "fallback" in cp2.stderr
    assert "takeover-options" in cp2.stdout
    # 既有 spec config 保留 — specId 与 source_text 不被覆盖
    again_cfg = json.loads(
        (doc_root / "specs" / "dupe" / ".config.json").read_text(encoding="utf-8")
    )
    assert again_cfg["specId"] == first_cfg["specId"]
    assert again_cfg["source_text"] == first_cfg["source_text"] == "first"


def test_spec_init_missing_session_arg_errors(run_script, doc_root, fake_home):
    """argparse should reject when --session is missing."""
    cp = run_script(
        "spec_init.py",
        "--name", "no-session",
        "--requirement-name", "NoSession",
        "--source-text", "x",
    )
    # argparse exits 2 for missing required args
    assert cp.returncode != 0
    assert "session" in cp.stderr.lower()


@pytest.mark.parametrize("bad_slug,why", [
    ("evil/path", "含 /"),
    ("bad\\slash", "含 \\"),
    ("bad<x>", "含 < >"),
    ("bad:colon", "含 :"),
    ("bad*star", "含 *"),
    ("has space", "含空格"),
    (".hidden", "首字符 ."),
    # 首字符 - 由 argparse 在 --name 解析阶段就被拒（"-" 当作 flag prefix），
    # 不会进入 SLUG_RE。本测试不 cover 这条——已在更外层兜底。
    ("CON", "Windows 保留名"),
    ("nul", "Windows 保留名"),
    ("trailing.", "末尾 ."),
    ("", "空 slug"),
])
def test_spec_init_rejects_invalid_slug(
    run_script, doc_root, fake_home, make_session_id, bad_slug, why
):
    """0.10.16+：放宽到 Unicode，但仍拒绝文件系统危险字符 / Windows 保留名等。"""
    sid = make_session_id()
    cp = run_script(
        "spec_init.py",
        "--name", bad_slug,
        "--requirement-name", "Bad",
        "--source-text", "x",
        "--session", sid,
    )
    assert cp.returncode == 3, (
        f"slug={bad_slug!r} ({why}) 应被拒，但 exit={cp.returncode}\n"
        f"stderr={cp.stderr}"
    )
    assert "非法" in cp.stderr or "slug" in cp.stderr.lower()


@pytest.mark.parametrize("ok_slug", [
    "user-login",       # 标准 ASCII
    "UserLogin",        # 大写也允许（0.10.16+ 放宽）
    "登录页面",         # 中文
    "ログイン",         # 日文
    "auth_v2",          # 下划线 + 数字
    "spec.with.dots",   # 中间含 .（仅首字符不可）
    "user-1.0.0",       # 版本号风格
])
def test_spec_init_accepts_unicode_and_extended_ascii_slug(
    run_script, doc_root, fake_home, make_session_id, ok_slug
):
    """0.10.16+：Unicode (中文/日文/emoji) 与扩展 ASCII (大写/下划线/点) 都允许。"""
    sid = make_session_id()
    cp = run_script(
        "spec_init.py",
        "--name", ok_slug,
        "--requirement-name", "Test",
        "--source-text", "x",
        "--session", sid,
    )
    assert cp.returncode == 0, (
        f"slug={ok_slug!r} 应被接受，但 exit={cp.returncode}\n"
        f"stderr={cp.stderr}"
    )
    payload = json.loads(cp.stdout)
    spec_dir = Path(payload["spec_dir"])
    assert spec_dir.exists()
    assert spec_dir.name == ok_slug  # 目录名跟用户原文一致


def test_spec_init_root_override_wins(
    run_script, fake_home, tmp_path, make_session_id, monkeypatch
):
    """--root flag overrides env."""
    env_root = fake_home / "env-root"
    env_root.mkdir()
    monkeypatch.setenv("SPECODE_ROOT", str(env_root))
    cli_root = tmp_path / "cli-root"
    cli_root.mkdir()
    sid = make_session_id()
    cp = run_script(
        "spec_init.py",
        "--name", "override-spec",
        "--requirement-name", "OverrideSpec",
        "--source-text", "x",
        "--session", sid,
        "--root", str(cli_root),
    )
    assert cp.returncode == 0, cp.stderr
    payload = json.loads(cp.stdout)
    assert payload["doc_root_source"] == "override"
    assert Path(payload["spec_dir"]).is_relative_to(cli_root)
