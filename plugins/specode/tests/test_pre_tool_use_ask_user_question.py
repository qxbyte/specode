"""Tests for PreToolUse AskUserQuestion verbatim 比对（0.10.27+）。

主代理调 AskUserQuestion 时，PreToolUse hook 按 pending_selector 对应的
SELECTOR_OUTLINES verbatim 比对 question / header / multiSelect / options[*].label：

- 固定 selector（10 个）：集合相等比对，缺 label / 多 unknown label 都 exit 2
- 动态 selector（clarification-wizard）：仅校验结构（questions 数量 2-4、
  每个 multiSelect=false、每个 options ≥ 2）

主代理 hallucinate（如把 workflow-choice 三选项 invent 成 TDD/RAPID/TASK_SWARM）→
exit 2 阻断；用户截图里的现场正是该用例覆盖的反例。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


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


def _payload(sid: str, tool_name: str, tool_input: dict) -> str:
    return json.dumps({
        "session_id": sid,
        "tool_name": tool_name,
        "tool_input": tool_input,
    })


def _active_sess(fake_home: Path, sid: str, pending: Optional[str]) -> None:
    _write_session(
        fake_home, sid,
        mode="active",
        active_spec_slug="sel-test",
        active_spec_dir="/tmp/sel-test",  # spec_dir 文件本身不被读
        phase="intake",
        pending_selector=pending,
    )


# --------------------------------------------------------------------------
# Fixed selector — workflow-choice (用户截图里事故现场的 selector)
# --------------------------------------------------------------------------

WORKFLOW_VERBATIM_INPUT = {
    "questions": [{
        "question": "工作流选择 —— 决定走哪条 spec 流程？",
        "header": "工作流选择",
        "multiSelect": False,
        "options": [
            {"label": "Requirements first", "description": "..."},
            {"label": "Technical Design first", "description": "..."},
            {"label": "Bugfix", "description": "..."},
        ],
    }],
}


def test_workflow_choice_verbatim_input_passes(
    run_script, fake_home, make_session_id
):
    sid = make_session_id()
    _active_sess(fake_home, sid, "workflow-choice")
    cp = run_script("spec_session.py", "on-pre-tool-use",
                    stdin=_payload(sid, "AskUserQuestion", WORKFLOW_VERBATIM_INPUT))
    assert cp.returncode == 0, cp.stderr
    assert cp.stdout.strip() == ""


def test_workflow_choice_invented_labels_blocked(
    run_script, fake_home, make_session_id
):
    """模拟用户截图事故：主代理把三选项 invent 成 TDD/RAPID/TASK_SWARM → exit 2。"""
    sid = make_session_id()
    _active_sess(fake_home, sid, "workflow-choice")
    bad_input = {
        "questions": [{
            "question": "请选择该 spec 适用的工作流（workflow）",
            "header": "工作流选择",
            "multiSelect": False,
            "options": [
                {"label": "TDD (test-first)", "description": "测试驱动开发"},
                {"label": "RAPID (test-last)", "description": "快速原型开发"},
                {"label": "TASK_SWARM (multi-agent)", "description": "多 agent 并行"},
            ],
        }],
    }
    cp = run_script("spec_session.py", "on-pre-tool-use",
                    stdin=_payload(sid, "AskUserQuestion", bad_input))
    assert cp.returncode == 2
    assert "workflow-choice" in cp.stderr
    assert "hallucinate" in cp.stderr or "未知" in cp.stderr
    # 缺失的 label 应该被点出
    assert "Requirements first" in cp.stderr
    assert "Bugfix" in cp.stderr


def test_workflow_choice_missing_one_label_blocked(
    run_script, fake_home, make_session_id
):
    sid = make_session_id()
    _active_sess(fake_home, sid, "workflow-choice")
    bad_input = {
        "questions": [{
            "question": "工作流选择 —— 决定走哪条 spec 流程？",
            "header": "工作流选择",
            "multiSelect": False,
            "options": [
                {"label": "Requirements first"},
                {"label": "Bugfix"},
                # 缺 "Technical Design first"
            ],
        }],
    }
    cp = run_script("spec_session.py", "on-pre-tool-use",
                    stdin=_payload(sid, "AskUserQuestion", bad_input))
    assert cp.returncode == 2
    assert "Technical Design first" in cp.stderr
    assert "缺失" in cp.stderr


def test_workflow_choice_multiselect_wrong_blocked(
    run_script, fake_home, make_session_id
):
    """multiSelect=true 错传，应被拦（workflow-choice 是单选）。"""
    sid = make_session_id()
    _active_sess(fake_home, sid, "workflow-choice")
    bad_input = {
        "questions": [{
            "question": "工作流选择 —— 决定走哪条 spec 流程？",
            "header": "工作流选择",
            "multiSelect": True,
            "options": [
                {"label": "Requirements first"},
                {"label": "Technical Design first"},
                {"label": "Bugfix"},
            ],
        }],
    }
    cp = run_script("spec_session.py", "on-pre-tool-use",
                    stdin=_payload(sid, "AskUserQuestion", bad_input))
    assert cp.returncode == 2
    assert "multiSelect" in cp.stderr


# --------------------------------------------------------------------------
# Dynamic selector — clarification-wizard
# --------------------------------------------------------------------------

def test_clarification_wizard_valid_structure_passes(
    run_script, fake_home, make_session_id
):
    """clarification-wizard 是动态 selector：2-4 个 question、各 multiSelect=false、各 ≥ 2 options。"""
    sid = make_session_id()
    _active_sess(fake_home, sid, "clarification-wizard")
    ok = {
        "questions": [
            {
                "question": "动态自定义子问题 1？",
                "header": "决策 1",
                "multiSelect": False,
                "options": [
                    {"label": "选项 A", "description": "解释 A"},
                    {"label": "选项 B", "description": "解释 B"},
                ],
            },
            {
                "question": "动态自定义子问题 2？",
                "header": "决策 2",
                "multiSelect": False,
                "options": [
                    {"label": "X", "description": "..."},
                    {"label": "Y", "description": "..."},
                ],
            },
        ],
    }
    cp = run_script("spec_session.py", "on-pre-tool-use",
                    stdin=_payload(sid, "AskUserQuestion", ok))
    assert cp.returncode == 0, cp.stderr


def test_clarification_wizard_only_one_question_blocked(
    run_script, fake_home, make_session_id
):
    sid = make_session_id()
    _active_sess(fake_home, sid, "clarification-wizard")
    bad = {
        "questions": [{
            "question": "只有 1 个",
            "header": "x",
            "multiSelect": False,
            "options": [{"label": "A"}, {"label": "B"}],
        }],
    }
    cp = run_script("spec_session.py", "on-pre-tool-use",
                    stdin=_payload(sid, "AskUserQuestion", bad))
    assert cp.returncode == 2
    assert "2" in cp.stderr  # 提示必须 2-4 个


def test_clarification_wizard_too_few_options_blocked(
    run_script, fake_home, make_session_id
):
    sid = make_session_id()
    _active_sess(fake_home, sid, "clarification-wizard")
    bad = {
        "questions": [
            {
                "question": "q1",
                "header": "h1",
                "multiSelect": False,
                "options": [{"label": "only one"}],  # 仅 1 个 option
            },
            {
                "question": "q2",
                "header": "h2",
                "multiSelect": False,
                "options": [{"label": "A"}, {"label": "B"}],
            },
        ],
    }
    cp = run_script("spec_session.py", "on-pre-tool-use",
                    stdin=_payload(sid, "AskUserQuestion", bad))
    assert cp.returncode == 2
    assert "options" in cp.stderr


# --------------------------------------------------------------------------
# Multi-select selector — iteration-scope
# --------------------------------------------------------------------------

def test_iteration_scope_multiselect_true_passes(
    run_script, fake_home, make_session_id
):
    """iteration-scope 必须 multiSelect=true。"""
    sid = make_session_id()
    _active_sess(fake_home, sid, "iteration-scope")
    ok = {
        "questions": [{
            "question": "本轮 iteration 要调整哪些文档/动作？（可多选）",
            "header": "迭代范围",
            "multiSelect": True,
            "options": [
                {"label": "改 requirements"},
                {"label": "改 design"},
                {"label": "改 tasks"},
                {"label": "重跑测试"},
            ],
        }],
    }
    cp = run_script("spec_session.py", "on-pre-tool-use",
                    stdin=_payload(sid, "AskUserQuestion", ok))
    assert cp.returncode == 0, cp.stderr


def test_iteration_scope_multiselect_false_blocked(
    run_script, fake_home, make_session_id
):
    """iteration-scope 传 multiSelect=false → 阻断。"""
    sid = make_session_id()
    _active_sess(fake_home, sid, "iteration-scope")
    bad = {
        "questions": [{
            "question": "本轮 iteration 要调整哪些文档/动作？（可多选）",
            "header": "迭代范围",
            "multiSelect": False,
            "options": [
                {"label": "改 requirements"},
                {"label": "改 design"},
                {"label": "改 tasks"},
                {"label": "重跑测试"},
            ],
        }],
    }
    cp = run_script("spec_session.py", "on-pre-tool-use",
                    stdin=_payload(sid, "AskUserQuestion", bad))
    assert cp.returncode == 2
    assert "multiSelect" in cp.stderr


# --------------------------------------------------------------------------
# 旁路场景：不该拦
# --------------------------------------------------------------------------

def test_no_pending_selector_passes(
    run_script, fake_home, make_session_id
):
    """主代理在合法场景外用 AskUserQuestion（无 pending_selector） → 不拦。"""
    sid = make_session_id()
    _active_sess(fake_home, sid, None)  # pending=None
    bad = {"questions": [{"question": "随便", "header": "x", "options": [{"label": "y"}]}]}
    cp = run_script("spec_session.py", "on-pre-tool-use",
                    stdin=_payload(sid, "AskUserQuestion", bad))
    assert cp.returncode == 0


def test_idle_mode_passes(
    run_script, fake_home, make_session_id
):
    sid = make_session_id()
    _write_session(fake_home, sid, mode="idle", pending_selector="workflow-choice")
    bad = {"questions": [{"question": "x", "header": "y", "options": [{"label": "z"}]}]}
    cp = run_script("spec_session.py", "on-pre-tool-use",
                    stdin=_payload(sid, "AskUserQuestion", bad))
    assert cp.returncode == 0


def test_readonly_mode_still_validates(
    run_script, fake_home, make_session_id
):
    """readonly 模式下 AskUserQuestion 仍按 pending_selector 校验（takeover-options 等场景）。"""
    sid = make_session_id()
    _write_session(
        fake_home, sid,
        mode="readonly",
        active_spec_slug="ro-test",
        active_spec_dir="/tmp/ro-test",
        pending_selector="takeover-options",
    )
    bad = {
        "questions": [{
            "question": "假的接管问题？",
            "header": "x",
            "multiSelect": False,
            "options": [
                {"label": "随便接管"},
                {"label": "不接管"},
            ],
        }],
    }
    cp = run_script("spec_session.py", "on-pre-tool-use",
                    stdin=_payload(sid, "AskUserQuestion", bad))
    assert cp.returncode == 2
    assert "takeover-options" in cp.stderr


def test_specode_guard_off_passes(
    run_script, fake_home, make_session_id
):
    sid = make_session_id()
    _active_sess(fake_home, sid, "workflow-choice")
    bad = {"questions": [{"question": "x", "header": "y", "options": [{"label": "TDD"}]}]}
    cp = run_script(
        "spec_session.py", "on-pre-tool-use",
        stdin=_payload(sid, "AskUserQuestion", bad),
        extra_env={"SPECODE_GUARD": "off"},
    )
    assert cp.returncode == 0


def test_unknown_pending_selector_passes(
    run_script, fake_home, make_session_id
):
    """pending_selector 是个未知 key（开发期可能出现） → 防御性放行，不阻断。"""
    sid = make_session_id()
    _active_sess(fake_home, sid, "nonexistent-selector")
    bad = {"questions": [{"question": "x", "header": "y", "options": [{"label": "z"}]}]}
    cp = run_script("spec_session.py", "on-pre-tool-use",
                    stdin=_payload(sid, "AskUserQuestion", bad))
    assert cp.returncode == 0
