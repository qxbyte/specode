"""Tests for spec_session.py hook sub-commands.

Hooks always exit 0. They communicate with the host via stdout JSON of the form:
    {"hookSpecificOutput": {"hookEventName": <e>, "additionalContext": <str>}}
Empty stdout (or empty JSON) means "no injection".
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import pytest


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _parse_hook(stdout: str) -> Optional[dict]:
    """Parse a hook's stdout. Returns None when stdout is empty."""
    s = stdout.strip()
    if not s:
        return None
    return json.loads(s)


def _ctx(payload: Optional[dict]) -> str:
    """Pull additionalContext text out of a hook payload (or '' when none)."""
    if payload is None:
        return ""
    return payload.get("hookSpecificOutput", {}).get("additionalContext", "")


def _write_session(fake_home: Path, sid: str, **overrides) -> Path:
    """Write a sessions/<sid>.json with sensible defaults that callers can patch."""
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
        "task_swarm_run_id": None,
        "pending_selector": None,
    }
    base.update(overrides)
    p = sess_dir / f"{sid}.json"
    p.write_text(json.dumps(base), encoding="utf-8")
    return p


# --------------------------------------------------------------------------
# on-session-start
# --------------------------------------------------------------------------

def test_on_session_start_new_session_writes_idle(
    run_script, fake_home, make_session_id
):
    sid = make_session_id()
    cp = run_script("spec_session.py", "on-session-start",
                    stdin=json.dumps({"session_id": sid}))
    assert cp.returncode == 0, cp.stderr
    sess_path = fake_home / ".specode" / "sessions" / f"{sid}.json"
    assert sess_path.exists()
    sess = json.loads(sess_path.read_text(encoding="utf-8"))
    assert sess["mode"] == "idle"
    assert sess["session_id"] == sid


def test_on_session_start_additional_context_contains_session_id(
    run_script, fake_home, make_session_id
):
    sid = make_session_id()
    cp = run_script("spec_session.py", "on-session-start",
                    stdin=json.dumps({"session_id": sid}))
    payload = _parse_hook(cp.stdout)
    ctx = _ctx(payload)
    assert sid in ctx
    assert "Specode session" in ctx


def test_on_session_start_reactivates_ended_session(
    run_script, fake_home, make_session_id
):
    sid = make_session_id()
    _write_session(fake_home, sid, mode="ended", ended_at="2026-01-01T00:00:00Z")
    cp = run_script("spec_session.py", "on-session-start",
                    stdin=json.dumps({"session_id": sid}))
    assert cp.returncode == 0
    sess = json.loads(
        (fake_home / ".specode" / "sessions" / f"{sid}.json").read_text(encoding="utf-8")
    )
    assert sess["mode"] == "idle"  # back to idle from ended
    assert sess["ended_at"] is None


# --------------------------------------------------------------------------
# on-user-prompt
# --------------------------------------------------------------------------

def test_on_user_prompt_ended_session_emits_nothing(
    run_script, fake_home, make_session_id
):
    sid = make_session_id()
    _write_session(fake_home, sid, mode="ended")
    cp = run_script(
        "spec_session.py", "on-user-prompt",
        stdin=json.dumps({"session_id": sid, "prompt": "hello"})
    )
    assert cp.returncode == 0
    # mode=ended branch returns early; no additionalContext emitted.
    assert _parse_hook(cp.stdout) is None


def test_on_user_prompt_post_end_reminder_emits_once_then_clears(
    run_script, fake_home, make_session_id
):
    """刚 /specode:end 完的下一 turn 必须收到一次性反向提醒；标志被消费后，
    再后续 turn 不再注入任何内容。"""
    sid = make_session_id()
    _write_session(fake_home, sid, mode="ended", post_end_reminder_pending=True)

    # 第一 turn：注入反向提醒
    cp = run_script(
        "spec_session.py", "on-user-prompt",
        stdin=json.dumps({"session_id": sid, "prompt": "随便问点啥"})
    )
    assert cp.returncode == 0
    ctx = _ctx(_parse_hook(cp.stdout))
    assert "spec 模式已退出" in ctx
    assert "不要" in ctx and "─── spec-mode ───" in ctx
    # 标志应已被清掉，落盘
    sess = json.loads(
        (fake_home / ".specode" / "sessions" / f"{sid}.json").read_text(encoding="utf-8")
    )
    assert sess.get("post_end_reminder_pending") is False

    # 第二 turn：不再注入
    cp = run_script(
        "spec_session.py", "on-user-prompt",
        stdin=json.dumps({"session_id": sid, "prompt": "再问一句"})
    )
    assert cp.returncode == 0
    assert _parse_hook(cp.stdout) is None


def test_on_user_prompt_idle_session_emits_nothing(
    run_script, fake_home, make_session_id
):
    sid = make_session_id()
    _write_session(fake_home, sid, mode="idle")
    cp = run_script(
        "spec_session.py", "on-user-prompt",
        stdin=json.dumps({"session_id": sid, "prompt": "hello"})
    )
    assert cp.returncode == 0
    # idle also returns early
    assert _parse_hook(cp.stdout) is None


def test_on_user_prompt_active_with_workflow_choice_emits_all_segments(
    run_script, fake_home, make_session_id, doc_root
):
    sid = make_session_id()
    # set up an active spec with a real spec config
    spec_dir = doc_root / "specs" / "active-spec"
    spec_dir.mkdir(parents=True)
    (spec_dir / ".config.json").write_text(json.dumps({
        "specId": "abc",
        "slug": "active-spec",
        "phase": "intake",
        "workflow": None,
        "pending_selector": "workflow-choice",
        "lock": {"holder": sid},
        "source_text": "示例源需求摘要内容",
    }), encoding="utf-8")
    _write_session(
        fake_home, sid,
        mode="active",
        active_spec_slug="active-spec",
        active_spec_dir=str(spec_dir),
        phase="intake",
        pending_selector="workflow-choice",
        lock_state="ok",
    )
    cp = run_script(
        "spec_session.py", "on-user-prompt",
        stdin=json.dumps({"session_id": sid, "prompt": "继续推进"})
    )
    payload = _parse_hook(cp.stdout)
    ctx = _ctx(payload)
    # 5 segments expected
    assert sid in ctx                                        # session_id 提醒
    assert "选择器节点：工作流选择" in ctx
    assert "AskUserQuestion" in ctx
    assert "multiSelect: false" in ctx
    assert "Requirements first" in ctx
    assert "Technical Design first" in ctx
    assert "Bugfix" in ctx
    assert "状态行" in ctx                                    # footer template
    assert "spec-mode" in ctx
    assert "文档优先提醒" in ctx
    assert "你仍处于 spec 模式" in ctx                         # continue reminder


def test_on_user_prompt_project_root_choice_emits_with_cwd_context(
    run_script, fake_home, make_session_id, doc_root
):
    """0.10.15+：pending_selector=project-root-choice 时，hook 注入 selector
    模板并把 invocation_cwd / cwd_subdir 填进去给主代理。"""
    sid = make_session_id()
    spec_dir = doc_root / "specs" / "pr-test"
    spec_dir.mkdir(parents=True)
    fake_cwd = "/home/user/my-repo"
    (spec_dir / ".config.json").write_text(json.dumps({
        "specId": "pr",
        "slug": "pr-test",
        "phase": "intake",
        "workflow": None,
        "pending_selector": "project-root-choice",
        "lock": {"holder": sid},
        "source_text": "新需求一句话",
        "invocation_cwd": fake_cwd,
        "project_root": None,
    }), encoding="utf-8")
    _write_session(
        fake_home, sid,
        mode="active",
        active_spec_slug="pr-test",
        active_spec_dir=str(spec_dir),
        phase="intake",
        pending_selector="project-root-choice",
        lock_state="ok",
    )
    cp = run_script(
        "spec_session.py", "on-user-prompt",
        stdin=json.dumps({"session_id": sid, "prompt": "走起"})
    )
    ctx = _ctx(_parse_hook(cp.stdout))
    # selector 模板被注入
    assert "选择器节点：项目实现目录选择" in ctx
    assert "AskUserQuestion" in ctx
    # invocation_cwd 占位被替换成实际值
    assert fake_cwd in ctx
    # cwd_subdir 也已填入（路径拼接 cwd + slug）
    assert "pr-test" in ctx  # slug 出现在 cwd/slug 选项
    # 3 个 label 都在
    assert "cwd（在已有项目里迭代）" in ctx
    assert "cwd/slug（新项目子目录）" in ctx
    assert "自定义路径" in ctx


def test_on_user_prompt_active_implementation_no_pending(
    run_script, fake_home, make_session_id, doc_root
):
    """phase=implementation with no pending_selector → selector segment absent
    but other segments present."""
    sid = make_session_id()
    spec_dir = doc_root / "specs" / "mid-impl"
    spec_dir.mkdir(parents=True)
    (spec_dir / ".config.json").write_text(json.dumps({
        "specId": "x",
        "slug": "mid-impl",
        "phase": "implementation",
        "workflow": "requirements-first",
        "pending_selector": None,
        "lock": {"holder": sid},
    }), encoding="utf-8")
    _write_session(
        fake_home, sid,
        mode="active",
        active_spec_slug="mid-impl",
        active_spec_dir=str(spec_dir),
        phase="implementation",
        pending_selector=None,
        lock_state="ok",
    )
    cp = run_script(
        "spec_session.py", "on-user-prompt",
        stdin=json.dumps({"session_id": sid, "prompt": "更多 coding"})
    )
    ctx = _ctx(_parse_hook(cp.stdout))
    assert "选择器节点：" not in ctx          # no selector segment
    assert "文档优先提醒" in ctx
    assert "状态行" in ctx
    assert "你仍处于 spec 模式" in ctx
    assert sid in ctx


def test_on_user_prompt_readonly_footer_has_readonly_marker(
    run_script, fake_home, make_session_id, doc_root
):
    sid = make_session_id()
    spec_dir = doc_root / "specs" / "ro-spec"
    spec_dir.mkdir(parents=True)
    (spec_dir / ".config.json").write_text(json.dumps({
        "specId": "ro",
        "slug": "ro-spec",
        "phase": "tasks",
        "pending_selector": None,
        "lock": {"holder": "someone-else"},
    }), encoding="utf-8")
    _write_session(
        fake_home, sid,
        mode="readonly",
        active_spec_slug="ro-spec",
        active_spec_dir=str(spec_dir),
        phase="tasks",
        pending_selector=None,
        lock_state="readonly",
    )
    cp = run_script(
        "spec_session.py", "on-user-prompt",
        stdin=json.dumps({"session_id": sid, "prompt": "只读一下"})
    )
    ctx = _ctx(_parse_hook(cp.stdout))
    assert "[只读]" in ctx
    assert "只读模式" in ctx


def test_on_user_prompt_help_fastpath_only_emits_help(
    run_script, fake_home, make_session_id
):
    sid = make_session_id()
    # Even active sessions only emit the help fast-path when prompt matches
    _write_session(fake_home, sid, mode="active",
                   active_spec_slug="any", phase="intake",
                   pending_selector="workflow-choice",
                   active_spec_dir="/dev/null")
    cp = run_script(
        "spec_session.py", "on-user-prompt",
        stdin=json.dumps({"session_id": sid, "prompt": "/specode:spec -h"})
    )
    ctx = _ctx(_parse_hook(cp.stdout))
    assert "fast-path" in ctx
    assert "specode v" in ctx  # accept any version (dynamic since 0.10.1)
    # Workflow-choice selector should NOT leak in
    assert "选择器节点：工作流选择" not in ctx


def test_on_user_prompt_vault_status_fastpath(
    run_script, fake_home, make_session_id
):
    sid = make_session_id()
    _write_session(fake_home, sid, mode="idle")
    cp = run_script(
        "spec_session.py", "on-user-prompt",
        stdin=json.dumps({"session_id": sid, "prompt": "/specode:spec --vault-status"})
    )
    ctx = _ctx(_parse_hook(cp.stdout))
    assert "vault-status fast-path" in ctx
    # The wrapped content contains JSON with either "source": "..." or "doc_root"
    assert "doc_root" in ctx or "source" in ctx


def test_on_user_prompt_guard_off_emits_nothing(
    run_script, fake_home, make_session_id
):
    sid = make_session_id()
    _write_session(fake_home, sid, mode="active",
                   active_spec_slug="any", phase="intake",
                   pending_selector="workflow-choice",
                   active_spec_dir="/dev/null")
    cp = run_script(
        "spec_session.py", "on-user-prompt",
        stdin=json.dumps({"session_id": sid, "prompt": "hi"}),
        extra_env={"SPECODE_GUARD": "off"},
    )
    assert cp.returncode == 0
    assert cp.stdout.strip() == ""


# --------------------------------------------------------------------------
# on-stop
# --------------------------------------------------------------------------

def test_on_stop_active_emits_code_doc_sync(
    run_script, fake_home, make_session_id, doc_root
):
    sid = make_session_id()
    _write_session(fake_home, sid, mode="active",
                   active_spec_slug="s", phase="implementation",
                   active_spec_dir=str(doc_root / "specs" / "s"))
    cp = run_script(
        "spec_session.py", "on-stop",
        stdin=json.dumps({"session_id": sid})
    )
    ctx = _ctx(_parse_hook(cp.stdout))
    assert "代码-文档同步提醒" in ctx
    assert "tasks.md" in ctx
    assert "implementation-log.md" in ctx
    assert "你仍处于 spec 模式" in ctx


def test_on_stop_ended_emits_nothing(
    run_script, fake_home, make_session_id
):
    sid = make_session_id()
    _write_session(fake_home, sid, mode="ended")
    cp = run_script(
        "spec_session.py", "on-stop",
        stdin=json.dumps({"session_id": sid})
    )
    assert _parse_hook(cp.stdout) is None


def test_on_stop_readonly_only_readonly_reminder(
    run_script, fake_home, make_session_id, doc_root
):
    sid = make_session_id()
    _write_session(fake_home, sid, mode="readonly",
                   active_spec_slug="s", phase="implementation",
                   active_spec_dir=str(doc_root / "specs" / "s"))
    cp = run_script(
        "spec_session.py", "on-stop",
        stdin=json.dumps({"session_id": sid})
    )
    ctx = _ctx(_parse_hook(cp.stdout))
    assert "只读模式" in ctx
    # No code-doc sync segment in readonly
    assert "代码-文档同步提醒" not in ctx


# --------------------------------------------------------------------------
# on-session-end
# --------------------------------------------------------------------------

def test_on_session_end_releases_held_lock(
    run_script, fake_home, make_session_id, doc_root
):
    sid = make_session_id()
    spec_dir = doc_root / "specs" / "end-spec"
    spec_dir.mkdir(parents=True)
    (spec_dir / ".config.json").write_text(json.dumps({
        "specId": "e",
        "slug": "end-spec",
        "phase": "tasks",
        "pending_selector": "tasks-execution",
        "lock": {"holder": sid, "acquired_at": "2026-01-01T00:00:00Z",
                 "last_heartbeat_at": "2026-01-01T00:00:00Z"},
    }), encoding="utf-8")
    _write_session(
        fake_home, sid,
        mode="active",
        active_spec_slug="end-spec",
        active_spec_dir=str(spec_dir),
        phase="tasks",
        lock_state="ok",
    )
    cp = run_script(
        "spec_session.py", "on-session-end",
        stdin=json.dumps({"session_id": sid})
    )
    assert cp.returncode == 0
    cfg = json.loads((spec_dir / ".config.json").read_text(encoding="utf-8"))
    assert cfg["lock"] is None
    sess = json.loads(
        (fake_home / ".specode" / "sessions" / f"{sid}.json").read_text(encoding="utf-8")
    )
    assert sess["mode"] == "ended"
    assert sess["ended_at"]


def test_on_session_end_no_active_spec_is_ok(
    run_script, fake_home, make_session_id
):
    sid = make_session_id()
    _write_session(fake_home, sid, mode="idle")
    cp = run_script(
        "spec_session.py", "on-session-end",
        stdin=json.dumps({"session_id": sid})
    )
    assert cp.returncode == 0
    sess = json.loads(
        (fake_home / ".specode" / "sessions" / f"{sid}.json").read_text(encoding="utf-8")
    )
    assert sess["mode"] == "ended"


def test_on_session_end_missing_session_is_ok(
    run_script, fake_home, make_session_id
):
    sid = make_session_id()
    # no session file exists
    cp = run_script(
        "spec_session.py", "on-session-end",
        stdin=json.dumps({"session_id": sid})
    )
    assert cp.returncode == 0
    # Hook returns early when session not found; no file written
    sess_path = fake_home / ".specode" / "sessions" / f"{sid}.json"
    assert not sess_path.exists()


# --------------------------------------------------------------------------
# on-pre-tool-use: task-swarm 受控路径阻断
# --------------------------------------------------------------------------

def _prep_active_with_task_swarm(fake_home, doc_root, sid: str,
                                  run_id: str = "20260101-abcdef"):
    """造一个 active spec + task_swarm_run_id 已绑定的 session，并建出
    spec_dir/.task-swarm/runs/<run_id>/ 目录给路径解析用。"""
    spec_dir = doc_root / "specs" / "ts-block"
    (spec_dir / ".task-swarm" / "runs" / run_id / "agents" / "coder-g1-s1-r1"
        / "outbox").mkdir(parents=True, exist_ok=True)
    (spec_dir / ".task-swarm" / "runs" / run_id / "state.json").write_text(
        '{"phase":"coding"}', encoding="utf-8"
    )
    (spec_dir / ".config.json").write_text(json.dumps({
        "specId": "ts",
        "slug": "ts-block",
        "phase": "tasks",
        "lock": {"holder": sid, "acquired_at": "2026-01-01T00:00:00Z",
                 "last_heartbeat_at": "2026-01-01T00:00:00Z"},
    }), encoding="utf-8")
    _write_session(
        fake_home, sid,
        mode="active",
        active_spec_slug="ts-block",
        active_spec_dir=str(spec_dir),
        phase="tasks",
        lock_state="ok",
        task_swarm_run_id=run_id,
    )
    return spec_dir


def test_on_pre_tool_use_blocks_edit_of_state_json(
    run_script, fake_home, make_session_id, doc_root
):
    sid = make_session_id()
    run_id = "20260101-deadbe"
    spec_dir = _prep_active_with_task_swarm(fake_home, doc_root, sid, run_id)
    target = spec_dir / ".task-swarm" / "runs" / run_id / "state.json"

    cp = run_script(
        "spec_session.py", "on-pre-tool-use",
        stdin=json.dumps({
            "session_id": sid,
            "tool_name": "Edit",
            "tool_input": {"file_path": str(target)},
        })
    )
    # exit 2 = PreToolUse hook 阻断
    assert cp.returncode == 2, f"expected deny exit=2, got {cp.returncode}\nstderr={cp.stderr}"
    assert "task-swarm" in cp.stderr
    assert "state.json" in cp.stderr
    # 必须给出正确路径 hint
    assert "task_swarm.py" in cp.stderr


def test_on_pre_tool_use_blocks_edit_of_agent_task_md(
    run_script, fake_home, make_session_id, doc_root
):
    sid = make_session_id()
    run_id = "20260101-deadbe"
    spec_dir = _prep_active_with_task_swarm(fake_home, doc_root, sid, run_id)
    target = (spec_dir / ".task-swarm" / "runs" / run_id
              / "agents" / "coder-g1-s1-r1" / "task.md")

    cp = run_script(
        "spec_session.py", "on-pre-tool-use",
        stdin=json.dumps({
            "session_id": sid,
            "tool_name": "Edit",
            "tool_input": {"file_path": str(target)},
        })
    )
    assert cp.returncode == 2
    assert "task.md" in cp.stderr


def test_on_pre_tool_use_blocks_write_to_agent_outbox(
    run_script, fake_home, make_session_id, doc_root
):
    """覆盖事故场景：主代理手工 Edit subagent outbox 补 STATUS 必须被阻断。"""
    sid = make_session_id()
    run_id = "20260101-deadbe"
    spec_dir = _prep_active_with_task_swarm(fake_home, doc_root, sid, run_id)
    target = (spec_dir / ".task-swarm" / "runs" / run_id
              / "agents" / "coder-g1-s1-r1" / "outbox" / "result.md")

    cp = run_script(
        "spec_session.py", "on-pre-tool-use",
        stdin=json.dumps({
            "session_id": sid,
            "tool_name": "Write",
            "tool_input": {"file_path": str(target)},
        })
    )
    assert cp.returncode == 2
    assert "outbox" in cp.stderr


def test_on_pre_tool_use_blocks_edit_of_tasks_md(
    run_script, fake_home, make_session_id, doc_root
):
    """0.10.21+：active spec + task_swarm_run_id 进行中时，tasks.md 直写
    从软提醒升级为强阻断（exit 2）。

    历史 bug：login-page 现场主代理见 writeback 越界报错就手工 Edit tasks.md
    把 [ ] 改成 [x]，破坏 state.json 与 tasks.md 行号一致性，后续 writeback
    永远过不去。"""
    sid = make_session_id()
    run_id = "20260101-deadbe"
    spec_dir = _prep_active_with_task_swarm(fake_home, doc_root, sid, run_id)
    tasks_md = spec_dir / "tasks.md"
    tasks_md.write_text("## 阶段 1: x\n- [ ] 1.1 t\n", encoding="utf-8")

    cp = run_script(
        "spec_session.py", "on-pre-tool-use",
        stdin=json.dumps({
            "session_id": sid,
            "tool_name": "Edit",
            "tool_input": {"file_path": str(tasks_md)},
        })
    )
    assert cp.returncode == 2, f"expected deny exit=2, got {cp.returncode}\nstderr={cp.stderr}"
    assert "tasks.md" in cp.stderr
    assert "task_swarm.py writeback" in cp.stderr


def test_on_pre_tool_use_allows_normal_source_file_edit(
    run_script, fake_home, make_session_id, doc_root
):
    """非 task-swarm 路径的 Edit 不能被误拦截（保留正常代码 Edit 通行）。"""
    sid = make_session_id()
    run_id = "20260101-deadbe"
    spec_dir = _prep_active_with_task_swarm(fake_home, doc_root, sid, run_id)
    normal_file = spec_dir / "src" / "foo.py"
    normal_file.parent.mkdir(parents=True, exist_ok=True)
    normal_file.write_text("x = 1\n", encoding="utf-8")

    cp = run_script(
        "spec_session.py", "on-pre-tool-use",
        stdin=json.dumps({
            "session_id": sid,
            "tool_name": "Edit",
            "tool_input": {"file_path": str(normal_file)},
        })
    )
    # 不阻断
    assert cp.returncode == 0
    # 也不应当 emit 阻断提示
    assert "specode 阻断" not in (cp.stderr or "")


def test_on_pre_tool_use_no_active_spec_does_not_block(
    run_script, fake_home, make_session_id, doc_root
):
    """idle/ended session 即使路径落在 .task-swarm 下也不阻断（hook 只在 active
    且绑定 task_swarm_run_id 时生效）。"""
    sid = make_session_id()
    spec_dir = doc_root / "specs" / "x"
    fake_path = spec_dir / ".task-swarm" / "runs" / "rid" / "state.json"
    fake_path.parent.mkdir(parents=True, exist_ok=True)
    fake_path.write_text("{}", encoding="utf-8")
    _write_session(fake_home, sid, mode="idle")  # 注意：没有 task_swarm_run_id

    cp = run_script(
        "spec_session.py", "on-pre-tool-use",
        stdin=json.dumps({
            "session_id": sid,
            "tool_name": "Edit",
            "tool_input": {"file_path": str(fake_path)},
        })
    )
    assert cp.returncode == 0
