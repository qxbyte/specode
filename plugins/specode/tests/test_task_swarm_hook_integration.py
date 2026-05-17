"""Integration tests for task-swarm hook hooks inside spec_guard.

Exercises the same dispatch path that hooks.json triggers, ensuring
INV-7/8/9 fire correctly when task-swarm is active.
"""
from __future__ import annotations

import io
import json
import shutil
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import spec_guard  # noqa: E402
import spec_state  # noqa: E402


def _call(sub: str, payload: dict) -> tuple[int, str, str]:
    stdin = io.StringIO(json.dumps(payload))
    out = io.StringIO()
    err = io.StringIO()
    real_stdin = sys.stdin
    sys.stdin = stdin
    try:
        with redirect_stdout(out), redirect_stderr(err):
            rc = spec_guard.main(["spec_guard", sub])
    finally:
        sys.stdin = real_stdin
    return rc, out.getvalue(), err.getvalue()


@pytest.fixture
def swarm_workspace():
    """Build a project with an active task-swarm run, but NO active spec.

    Tests below exercise INV-7/8/9 in isolation — they don't need a real
    spec session because find_active_spec is monkeypatched.
    """
    tmp = Path(tempfile.mkdtemp(prefix="ts-hook-"))
    proj = tmp / "project"
    proj.mkdir()
    spec = tmp / "spec-dir"
    spec.mkdir()
    (spec / "tasks.md").write_text(
        "- [ ] 1. T\n  - [ ] 1.1 a\n    - 文件：src/a.py\n    - _需求：1.1_\n",
        encoding="utf-8",
    )
    (spec / ".config.json").write_text(json.dumps({"specId": "test"}))

    run_id = "run-test"
    run_dir = proj / ".task-swarm" / "runs" / run_id
    (run_dir / "agents" / "stage-1-coder" / "inbox").mkdir(parents=True)
    (run_dir / "agents" / "stage-1-coder" / "outbox").mkdir(parents=True)
    (run_dir / "agents" / "stage-1-coder" / "task.md").write_text(
        "## 边界\n- @writes（你只能修改这些路径）: src/a.py\n",
        encoding="utf-8",
    )
    (proj / ".task-swarm" / "active-run").write_text(run_id, encoding="utf-8")

    original = spec_state.find_active_spec

    def fake_find(prefer_session_id=None):
        return {
            "spec_slug": "test-spec",
            "spec_dir": str(spec),
            "current_phase": "implementation",
            "session_id": "test-sess",
            "spec_id": "test",
            "last_activity_at": "2026-05-15T00:00:00Z",
        }

    spec_state.find_active_spec = fake_find

    yield {
        "tmp": tmp,
        "proj": proj,
        "spec": spec,
        "run_dir": run_dir,
        "ws": run_dir / "agents" / "stage-1-coder",
    }

    spec_state.find_active_spec = original
    shutil.rmtree(tmp, ignore_errors=True)


# ---------- INV-7 ----------

def test_inv7_blocks_general_purpose_task(swarm_workspace):
    payload = {
        "session_id": "test-sess",
        "cwd": str(swarm_workspace["proj"]),
        "tool_name": "Task",
        "tool_input": {"subagent_type": "general-purpose", "prompt": "x"},
    }
    rc, _, err = _call("pre-tool-use", payload)
    assert rc == 2
    assert "INV-7" in err


def test_inv7_allows_prefixed_subagent(swarm_workspace):
    payload = {
        "session_id": "test-sess",
        "cwd": str(swarm_workspace["proj"]),
        "tool_name": "Task",
        "tool_input": {"subagent_type": "specode:task-swarm-coder", "prompt": "x"},
    }
    rc, _, _ = _call("pre-tool-use", payload)
    assert rc == 0


def test_inv7_inert_when_no_active_run(swarm_workspace):
    # Remove active-run pointer
    (swarm_workspace["proj"] / ".task-swarm" / "active-run").unlink()
    payload = {
        "session_id": "test-sess",
        "cwd": str(swarm_workspace["proj"]),
        "tool_name": "Task",
        "tool_input": {"subagent_type": "general-purpose", "prompt": "x"},
    }
    rc, _, _ = _call("pre-tool-use", payload)
    assert rc == 0  # no swarm active → no INV-7


# ---------- INV-8 ----------

def test_inv8_blocks_edit_outside_writes(swarm_workspace):
    target = swarm_workspace["proj"] / ".task-swarm" / "runs" / "run-test" / "agents" / "stage-1-coder" / "scratch.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("x")
    # Edit inside subagent ws but NOT in outbox AND not in @writes → deny
    payload = {
        "session_id": "test-sess",
        "cwd": str(swarm_workspace["proj"]),
        "tool_name": "Edit",
        "tool_input": {"file_path": str(target), "old_string": "x", "new_string": "y"},
    }
    rc, _, err = _call("pre-tool-use", payload)
    # scratch.py is inside agent workspace but not in outbox and not in
    # @writes (src/a.py) — INV-8 should deny.
    assert rc == 2
    assert "INV-8" in err


def test_inv8_allows_outbox_writes(swarm_workspace):
    target = swarm_workspace["ws"] / "outbox" / "result.md"
    payload = {
        "session_id": "test-sess",
        "cwd": str(swarm_workspace["proj"]),
        "tool_name": "Write",
        "tool_input": {"file_path": str(target), "content": "STATUS: ok\n"},
    }
    rc, _, _ = _call("pre-tool-use", payload)
    assert rc == 0


# ---------- INV-9 ----------

def test_inv9_blocks_traceability_change(swarm_workspace):
    tasks = swarm_workspace["spec"] / "tasks.md"
    payload = {
        "session_id": "test-sess",
        "cwd": str(swarm_workspace["proj"]),
        "tool_name": "Edit",
        "tool_input": {
            "file_path": str(tasks),
            "old_string": "_需求：1.1_",
            "new_string": "_需求：1.2_",
        },
    }
    rc, _, err = _call("pre-tool-use", payload)
    assert rc == 2
    assert "INV-9" in err


def test_inv9_allows_checkbox_swap(swarm_workspace):
    tasks = swarm_workspace["spec"] / "tasks.md"
    payload = {
        "session_id": "test-sess",
        "cwd": str(swarm_workspace["proj"]),
        "tool_name": "Edit",
        "tool_input": {
            "file_path": str(tasks),
            "old_string": "- [ ] 1.1 a",
            "new_string": "- [x] 1.1 a",
        },
    }
    rc, _, err = _call("pre-tool-use", payload)
    assert rc == 0, err


def test_user_prompt_submit_injects_swarm_block(swarm_workspace):
    """When a swarm run is active, UserPromptSubmit block includes swarm summary."""
    # Init a minimal state.json so the block has data to render.
    state_path = swarm_workspace["run_dir"] / "state.json"
    state_path.write_text(json.dumps({
        "run_id": "run-test",
        "config": {"parallel": 3, "max_rounds": 3},
        "stages": [
            {"num": 1, "phase": "running", "in_flight": {"role": "coder", "round": 2}},
            {"num": 2, "phase": "pending"},
            {"num": 3, "phase": "converged"},
        ],
    }), encoding="utf-8")
    payload = {"session_id": "test-sess", "cwd": str(swarm_workspace["proj"])}
    rc, out, _ = _call("user-prompt-submit", payload)
    assert rc == 0
    body = json.loads(out)
    block = body["hookSpecificOutput"]["additionalContext"]
    assert "task-swarm" in block
    assert "run-test" in block
    assert "stage 1 coder r2" in block
    assert "next:" in block


def test_user_prompt_submit_no_swarm_block_when_no_run(swarm_workspace):
    (swarm_workspace["proj"] / ".task-swarm" / "active-run").unlink()
    payload = {"session_id": "test-sess", "cwd": str(swarm_workspace["proj"])}
    rc, out, _ = _call("user-prompt-submit", payload)
    assert rc == 0
    body = json.loads(out)
    block = body["hookSpecificOutput"]["additionalContext"]
    assert "task-swarm" not in block


def test_inv9_inert_when_no_swarm_active(swarm_workspace):
    (swarm_workspace["proj"] / ".task-swarm" / "active-run").unlink()
    tasks = swarm_workspace["spec"] / "tasks.md"
    payload = {
        "session_id": "test-sess",
        "cwd": str(swarm_workspace["proj"]),
        "tool_name": "Edit",
        "tool_input": {
            "file_path": str(tasks),
            "old_string": "_需求：1.1_",
            "new_string": "_需求：1.2_",
        },
    }
    rc, _, err = _call("pre-tool-use", payload)
    # No swarm → INV-9 doesn't trigger. Note: classify_path will classify
    # tasks.md as spec-doc → INV-3 lock check. With our fixture there's no
    # real lock model so it returns "not_held" or similar (ok). Expect rc=0.
    # However spec_session may raise SystemExit if .config.json is malformed
    # — the check_verify_lock helper swallows it.
    assert rc == 0
