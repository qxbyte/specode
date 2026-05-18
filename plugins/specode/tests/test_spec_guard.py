"""Integration tests for spec_guard.py: hook handlers + invariants end-to-end."""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


def make_edit_payload(target, project_root, session_id="test-sess"):
    return {
        "session_id": session_id,
        "cwd": str(project_root),
        "tool_name": "Edit",
        "tool_input": {"file_path": str(target)},
    }


def _new_turn(ws, hook_caller):
    hook_caller("user-prompt-submit", {"session_id": ws["session_id"], "cwd": str(ws["project_root"])}, capture_stdout=True)


# ---- INV-1 (Code-Doc Sync) -------------------------------------------------

def test_user_prompt_submit_injects_status_block(workspace, hook_caller):
    rc, stdout, _ = hook_caller(
        "user-prompt-submit",
        {"session_id": workspace["session_id"], "cwd": str(workspace["project_root"])},
        capture_stdout=True,
    )
    assert rc == 0
    payload = json.loads(stdout)
    block = payload["hookSpecificOutput"]["additionalContext"]
    assert "specode active" in block
    assert "test-spec" in block
    assert "implementation" in block


def test_pretooluse_allows_tasks_files(workspace, hook_caller):
    _new_turn(workspace, hook_caller)
    target = workspace["project_root"] / "src/foo.py"
    rc, _, _ = hook_caller("pre-tool-use", make_edit_payload(target, workspace["project_root"]))
    assert rc == 0


def test_pretooluse_inv1_advisory_does_not_block(workspace, hook_caller):
    """INV-1 is advisory as of 0.4.0: tool call passes, advisory recorded."""
    import spec_sync
    _new_turn(workspace, hook_caller)
    target = workspace["project_root"] / "src/baz.py"
    rc, _, err = hook_caller(
        "pre-tool-use",
        make_edit_payload(target, workspace["project_root"]),
        capture_stderr=True,
    )
    assert rc == 0, "INV-1 must not block (advisory only)"
    assert "INV-1" in err and "ADVISORY" in err
    ledger = spec_sync.read_ledger(workspace["spec_dir"])
    advisories = [a for a in (ledger.get("pending_advisories") or []) if a.get("id") == "INV-1"]
    assert len(advisories) == 1
    assert advisories[0]["file"] == str(target)


def test_pretooluse_allows_after_doc_change(workspace, hook_caller):
    _new_turn(workspace, hook_caller)
    # Stage a doc change first.
    doc_target = workspace["spec_dir"] / "design.md"
    hook_caller("post-tool-use", make_edit_payload(doc_target, workspace["project_root"]))
    target = workspace["project_root"] / "src/baz.py"
    rc, _, err = hook_caller(
        "pre-tool-use",
        make_edit_payload(target, workspace["project_root"]),
        capture_stderr=True,
    )
    assert rc == 0, f"expected ok, got {rc}, err={err}"


def test_freeform_silences_inv1_advisory(workspace, hook_caller):
    """In freeform mode INV-1 doesn't even raise advisory (intentionally silent)."""
    import spec_sync
    (workspace["spec_dir"] / ".config.json").write_text(
        json.dumps({"specId": "test-id", "freeformMode": True})
    )
    _new_turn(workspace, hook_caller)
    target = workspace["project_root"] / "src/quux.py"
    rc, _, err = hook_caller(
        "pre-tool-use", make_edit_payload(target, workspace["project_root"]), capture_stderr=True
    )
    assert rc == 0
    assert "INV-1" not in err
    ledger = spec_sync.read_ledger(workspace["spec_dir"])
    assert not [a for a in (ledger.get("pending_advisories") or []) if a.get("id") == "INV-1"]


def test_inv6_advisory_in_forbidden_phase(workspace, hook_caller):
    """INV-6 is advisory as of 0.4.0 — phase-gate violation logs sticky warning but does not block."""
    import spec_sync
    workspace["current_phase"] = "design"
    _new_turn(workspace, hook_caller)
    target = workspace["project_root"] / "src/quux.py"
    rc, _, err = hook_caller(
        "pre-tool-use", make_edit_payload(target, workspace["project_root"]), capture_stderr=True
    )
    assert rc == 0, "INV-6 must not block (advisory only)"
    assert "INV-6" in err and "ADVISORY" in err
    ledger = spec_sync.read_ledger(workspace["spec_dir"])
    assert any(a.get("id") == "INV-6" for a in (ledger.get("pending_advisories") or []))


# ---- INV-2 (turn conservation) --------------------------------------------

def test_stop_inv2_advisory_when_code_only(workspace, hook_caller):
    """INV-2 is advisory: Stop passes but records sticky advisory."""
    import spec_sync
    _new_turn(workspace, hook_caller)
    target = workspace["project_root"] / "src/foo.py"
    hook_caller("post-tool-use", make_edit_payload(target, workspace["project_root"]))
    rc, _, err = hook_caller(
        "stop", {"session_id": workspace["session_id"]}, capture_stderr=True
    )
    assert rc == 0, "INV-2 must not block (advisory only)"
    assert "INV-2" in err and "ADVISORY" in err
    ledger = spec_sync.read_ledger(workspace["spec_dir"])
    assert any(a.get("id") == "INV-2" for a in (ledger.get("pending_advisories") or []))


def test_stop_passes_with_code_plus_doc(workspace, hook_caller):
    _new_turn(workspace, hook_caller)
    hook_caller("post-tool-use", make_edit_payload(workspace["spec_dir"] / "design.md", workspace["project_root"]))
    hook_caller("post-tool-use", make_edit_payload(workspace["project_root"] / "src/foo.py", workspace["project_root"]))
    rc, _, _ = hook_caller("stop", {"session_id": workspace["session_id"]}, capture_stderr=True)
    assert rc == 0


def test_inv4_advisory_requirements_without_tasks(workspace, hook_caller):
    import spec_sync
    _new_turn(workspace, hook_caller)
    hook_caller("post-tool-use", make_edit_payload(workspace["spec_dir"] / "requirements.md", workspace["project_root"]))
    rc, _, err = hook_caller("stop", {"session_id": workspace["session_id"]}, capture_stderr=True)
    assert rc == 0, "INV-4 must not block (advisory only)"
    assert "INV-4" in err and "ADVISORY" in err
    ledger = spec_sync.read_ledger(workspace["spec_dir"])
    assert any(a.get("id") == "INV-4" for a in (ledger.get("pending_advisories") or []))


def test_inv4_requirements_with_tasks(workspace, hook_caller):
    _new_turn(workspace, hook_caller)
    hook_caller("post-tool-use", make_edit_payload(workspace["spec_dir"] / "requirements.md", workspace["project_root"]))
    hook_caller("post-tool-use", make_edit_payload(workspace["spec_dir"] / "tasks.md", workspace["project_root"]))
    rc, _, _ = hook_caller("stop", {"session_id": workspace["session_id"]}, capture_stderr=True)
    assert rc == 0


def test_inv4_advisory_bugfix_without_tasks(workspace, hook_caller):
    import spec_sync
    _new_turn(workspace, hook_caller)
    hook_caller("post-tool-use", make_edit_payload(workspace["spec_dir"] / "bugfix.md", workspace["project_root"]))
    rc, _, err = hook_caller("stop", {"session_id": workspace["session_id"]}, capture_stderr=True)
    assert rc == 0, "INV-4 must not block (advisory only)"
    assert "INV-4" in err and "ADVISORY" in err


# ---- INV-3 (verify-lock) --------------------------------------------------

def test_inv3_denies_when_evicted(workspace, hook_caller):
    (workspace["spec_dir"] / ".config.json").write_text(json.dumps({
        "specId": "test-id",
        "lock": {
            "sessionId": "other-session",
            "acquiredAt": "2026-05-15T00:00:00+00:00",
            "lastHeartbeatAt": "2026-05-15T00:00:00+00:00",
        },
        "evictedSessions": [{
            "sessionId": workspace["session_id"],
            "evictedAt": "2026-05-15T00:00:00+00:00",
            "evictedBy": "other-session",
            "reason": "force_acquire",
        }],
    }))
    _new_turn(workspace, hook_caller)
    rc, _, err = hook_caller(
        "pre-tool-use",
        make_edit_payload(workspace["spec_dir"] / "design.md", workspace["project_root"]),
        capture_stderr=True,
    )
    assert rc == 2 and "INV-3" in err


def test_inv3_allows_when_lock_owned(workspace, hook_caller):
    (workspace["spec_dir"] / ".config.json").write_text(json.dumps({
        "specId": "test-id",
        "lock": {
            "sessionId": workspace["session_id"],
            "acquiredAt": "2026-05-15T00:00:00+00:00",
            "lastHeartbeatAt": "2026-05-15T00:00:00+00:00",
        },
    }))
    _new_turn(workspace, hook_caller)
    rc, _, _ = hook_caller(
        "pre-tool-use",
        make_edit_payload(workspace["spec_dir"] / "design.md", workspace["project_root"]),
        capture_stderr=True,
    )
    assert rc == 0


# ---- outside / silent paths -----------------------------------------------

def test_outside_project_root_ignored(workspace, hook_caller):
    _new_turn(workspace, hook_caller)
    rc, _, _ = hook_caller(
        "pre-tool-use",
        make_edit_payload(Path("/tmp/elsewhere.txt"), workspace["project_root"]),
        capture_stderr=True,
    )
    assert rc == 0


# ---- Advisory infrastructure (0.4.0) ---------------------------------------

def test_advisory_sticky_appears_in_next_status_block(workspace, hook_caller):
    """An INV-2 advisory recorded on Stop must show up in next UserPromptSubmit block."""
    _new_turn(workspace, hook_caller)
    # Trigger INV-2 advisory
    hook_caller("post-tool-use", make_edit_payload(workspace["project_root"] / "src/foo.py", workspace["project_root"]))
    hook_caller("stop", {"session_id": workspace["session_id"]}, capture_stderr=True)

    # Next turn: status block must surface pending advisory
    rc, stdout, _ = hook_caller(
        "user-prompt-submit",
        {"session_id": workspace["session_id"], "cwd": str(workspace["project_root"])},
        capture_stdout=True,
    )
    assert rc == 0
    payload = json.loads(stdout)
    block = payload["hookSpecificOutput"]["additionalContext"]
    assert "pending advisories" in block
    assert "INV-2" in block


def test_spec_doc_edit_auto_dismisses_advisory(workspace, hook_caller):
    """Editing any spec doc clears INV-1/2/4 advisories (drift is being fixed)."""
    import spec_sync
    _new_turn(workspace, hook_caller)
    hook_caller("post-tool-use", make_edit_payload(workspace["project_root"] / "src/foo.py", workspace["project_root"]))
    hook_caller("stop", {"session_id": workspace["session_id"]}, capture_stderr=True)
    ledger = spec_sync.read_ledger(workspace["spec_dir"])
    assert any(a.get("id") == "INV-2" for a in ledger.get("pending_advisories") or [])

    # Now edit a spec doc → advisory should auto-clear
    hook_caller("post-tool-use", make_edit_payload(workspace["spec_dir"] / "design.md", workspace["project_root"]))
    ledger = spec_sync.read_ledger(workspace["spec_dir"])
    assert not [a for a in (ledger.get("pending_advisories") or []) if a.get("id") == "INV-2"]


# INV-3 hard-deny path is already covered by test_inv3_denies_when_evicted above.


# ---- INV-11 Bash hang guard integration (0.4.0) ----------------------------

def _bash_payload(command, session_id="test-sess", tool_response=None, cwd=None):
    p = {
        "session_id": session_id,
        "cwd": cwd or "/tmp",
        "tool_name": "Bash",
        "tool_input": {"command": command},
    }
    if tool_response is not None:
        p["tool_response"] = tool_response
    return p


def test_inv11_pretooluse_denies_npm_create_without_yes(workspace, hook_caller):
    rc, _, err = hook_caller(
        "pre-tool-use",
        _bash_payload("npm create vite@latest myapp -- --template react-ts"),
        capture_stderr=True,
    )
    assert rc == 2
    assert "INV-11" in err
    assert "npm-create" in err
    assert "--yes" in err


def test_inv11_pretooluse_allows_npm_create_with_yes(workspace, hook_caller):
    rc, _, _ = hook_caller(
        "pre-tool-use",
        _bash_payload("npm create vite@latest myapp -- --yes --template react-ts"),
    )
    assert rc == 0


def test_inv11_pretooluse_denies_vim(workspace, hook_caller):
    rc, _, err = hook_caller(
        "pre-tool-use",
        _bash_payload("vim file.txt"),
        capture_stderr=True,
    )
    assert rc == 2 and "tty-editor" in err


def test_inv11_pretooluse_denies_git_commit_no_message(workspace, hook_caller):
    rc, _, err = hook_caller(
        "pre-tool-use",
        _bash_payload("git commit"),
        capture_stderr=True,
    )
    assert rc == 2 and "git-commit-needs-message" in err


def test_inv11_pretooluse_allows_safe_bash(workspace, hook_caller):
    for cmd in ["ls -la", "git status", "npm install", "python3 -c 'print(1)'"]:
        rc, _, _ = hook_caller("pre-tool-use", _bash_payload(cmd))
        assert rc == 0, f"expected ok for {cmd!r}"


def test_inv11_posttool_hang_injects_advisory(workspace, hook_caller):
    """PostToolUse on a Bash that ran into 'Ok to proceed?' must inject advisory."""
    hang_output = "Need to install the following packages:\ncreate-vite@9.0.7\nOk to proceed? (y)\n"
    rc, stdout, _ = hook_caller(
        "post-tool-use",
        _bash_payload(
            "npm create vite@latest myapp -- --template react-ts",
            tool_response={"stdout": hang_output, "stderr": "", "exit_code": None},
        ),
        capture_stdout=True,
    )
    assert rc == 0
    payload = json.loads(stdout)
    block = payload["hookSpecificOutput"]["additionalContext"]
    assert "INV-11" in block
    assert "ok to proceed" in block.lower()
    assert "do NOT retry" in block


def test_inv11_posttool_no_advisory_on_clean_output(workspace, hook_caller):
    rc, stdout, _ = hook_caller(
        "post-tool-use",
        _bash_payload(
            "npm install",
            tool_response={"stdout": "added 100 packages\n", "stderr": "", "exit_code": 0},
        ),
        capture_stdout=True,
    )
    assert rc == 0
    assert stdout == "" or "INV-11" not in stdout


def test_inv11_posttool_exit_124_triggers_advisory(workspace, hook_caller):
    rc, stdout, _ = hook_caller(
        "post-tool-use",
        _bash_payload(
            "some-stuck-command",
            tool_response={"stdout": "partial\n", "stderr": "", "exit_code": 124},
        ),
        capture_stdout=True,
    )
    assert rc == 0
    payload = json.loads(stdout)
    assert "INV-11" in payload["hookSpecificOutput"]["additionalContext"]
    assert "124" in payload["hookSpecificOutput"]["additionalContext"]


def test_inv11_works_without_active_spec(hook_caller, monkeypatch):
    """INV-11 must guard Bash even when no spec session is active."""
    import spec_state
    monkeypatch.setattr(spec_state, "find_active_spec", lambda prefer_session_id=None: None)
    rc, _, err = hook_caller(
        "pre-tool-use",
        _bash_payload("vim file.txt"),
        capture_stderr=True,
    )
    assert rc == 2 and "INV-11" in err
