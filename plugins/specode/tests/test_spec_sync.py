"""Unit tests for spec_sync.py — tasks_files extraction and decision functions."""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import spec_sync


def test_extract_tasks_files_from_FILE_lines(tmp_path):
    spec = tmp_path / "spec"
    spec.mkdir()
    (spec / "tasks.md").write_text(
        "# Tasks\n"
        "- [ ] FILE: src/auth/middleware.py\n"
        "- [x] FILE: src/auth/session.py\n"
        "- [ ] FILE：tests/auth/test_middleware.py\n"  # full-width 冒号
        "- [ ] FILE: src/auth/glob/**/*.py\n"
    )
    out = spec_sync.extract_tasks_files(spec)
    assert "src/auth/middleware.py" in out
    assert "src/auth/session.py" in out
    assert "tests/auth/test_middleware.py" in out
    assert "src/auth/glob/**/*.py" in out


def test_extract_tasks_files_from_affected_section(tmp_path):
    spec = tmp_path / "spec"
    spec.mkdir()
    (spec / "design.md").write_text(
        "# Design\n\n## Affected Files\n\n- `src/foo.py`\n- src/bar.py\n\n## Next\n- ignored\n"
    )
    out = spec_sync.extract_tasks_files(spec)
    assert "src/foo.py" in out
    assert "src/bar.py" in out
    assert "ignored" not in out


def test_matches_tasks_files_literal_and_glob(tmp_path):
    proj = tmp_path / "proj"
    (proj / "src" / "auth").mkdir(parents=True)
    target_literal = proj / "src" / "foo.py"
    target_glob = proj / "src" / "auth" / "middleware.py"
    target_literal.touch()
    target_glob.touch()

    assert spec_sync.matches_tasks_files(target_literal, ["src/foo.py"], proj)
    assert spec_sync.matches_tasks_files(target_glob, ["src/auth/**/*.py"], proj)
    assert not spec_sync.matches_tasks_files(target_literal, ["src/bar.py"], proj)


def test_classify_path_spec_doc_vs_project_code_vs_outside(tmp_path):
    spec = tmp_path / "spec"
    proj = tmp_path / "proj"
    spec.mkdir()
    proj.mkdir()
    (spec / "design.md").touch()
    (proj / "src.py").touch()
    outside = Path("/tmp/literally-outside.txt")

    assert spec_sync.classify_path(spec / "design.md", spec, proj) == "spec-doc"
    assert spec_sync.classify_path(proj / "src.py", spec, proj) == "project-code"
    assert spec_sync.classify_path(outside, spec, proj) == "outside"


def test_check_phase_gate_forbids_pre_implementation():
    for phase in ("intake", "requirements", "design", "tasks", "bugfix"):
        decision, msg = spec_sync.check_phase_gate(phase)
        assert decision == "deny"
        assert "INV-6" in msg
        assert phase in msg

    for phase in ("implementation", "acceptance", "iteration", "ended"):
        decision, _ = spec_sync.check_phase_gate(phase)
        assert decision == "ok"


def test_check_stop_inv2_and_inv4():
    # Empty ledger → ok
    ledger = spec_sync._new_ledger(Path("/tmp/x"))
    assert spec_sync.check_stop(ledger) == []

    # Code-only → INV-2
    ledger = spec_sync._new_ledger(Path("/tmp/x"))
    spec_sync.append_change(ledger, "code", "/proj/src/foo.py", "Edit")
    violations = spec_sync.check_stop(ledger)
    assert any(v["id"] == "INV-2" for v in violations)

    # Code + doc → ok
    spec_sync.append_change(ledger, "doc", "/spec/design.md", "Edit")
    assert spec_sync.check_stop(ledger) == []

    # Requirements w/o tasks.md → INV-4
    ledger = spec_sync._new_ledger(Path("/tmp/x"))
    spec_sync.append_change(ledger, "doc", "/spec/requirements.md", "Edit")
    violations = spec_sync.check_stop(ledger)
    assert any(v["id"] == "INV-4" for v in violations)

    # Requirements + tasks.md → ok (测试要点 lives in tasks.md)
    spec_sync.append_change(ledger, "doc", "/spec/tasks.md", "Edit")
    assert spec_sync.check_stop(ledger) == []

    # Bugfix w/o tasks.md → INV-4
    ledger = spec_sync._new_ledger(Path("/tmp/x"))
    spec_sync.append_change(ledger, "doc", "/spec/bugfix.md", "Edit")
    violations = spec_sync.check_stop(ledger)
    assert any(v["id"] == "INV-4" for v in violations)


def test_cmd_status_with_spec_dir_bypasses_active_resolver(tmp_path, capsys, monkeypatch):
    """status --spec-dir should read ledger directly, no active-pointer needed."""
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()
    ledger = spec_sync.read_ledger(spec_dir)
    spec_sync.start_new_turn(ledger, tmp_path, ["src/a.py"])
    spec_sync.write_ledger(spec_dir, ledger)

    # Ensure _resolve_active_spec_dir is NOT consulted: poison it.
    monkeypatch.setattr(
        spec_sync, "_resolve_active_spec_dir",
        lambda: (_ for _ in ()).throw(AssertionError("must not call resolver")),
    )

    rc = spec_sync.main(["status", "--spec-dir", str(spec_dir)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "(no active spec)" not in out
    assert str(spec_dir) in out
    assert "tasks_files:    1 entries" in out


def test_cmd_status_with_missing_spec_dir_errors(tmp_path, capsys):
    rc = spec_sync.main(["status", "--spec-dir", str(tmp_path / "nope")])
    assert rc == 2
    err = capsys.readouterr().err
    assert "spec_dir does not exist" in err


def test_find_active_spec_falls_back_to_default_sid(tmp_path, monkeypatch):
    """When no env id is supplied, prefer the 'default' session before
    sorting by lastActivityAt — matches normalize_session_id's fallback."""
    sys.path.insert(0, str(SCRIPTS_DIR))
    import spec_state

    monkeypatch.setattr(spec_state, "get_document_root", lambda: tmp_path)
    monkeypatch.delenv("TERM_SESSION_ID", raising=False)
    (tmp_path / "older-slug").mkdir()
    (tmp_path / "older-slug" / ".config.json").write_text('{"specId": "s1"}')
    (tmp_path / "newer-slug").mkdir()
    (tmp_path / "newer-slug" / ".config.json").write_text('{"specId": "s2"}')
    (tmp_path / ".active-specode.json").write_text(
        '{"version": 2, "sessions": {'
        '"some-tty": {"specSlug": "newer-slug", "specId": "s2", '
        '"status": "active", "lastActivityAt": "2099-01-01T00:00:00Z"},'
        '"default":  {"specSlug": "older-slug", "specId": "s1", '
        '"status": "active", "lastActivityAt": "2000-01-01T00:00:00Z"}'
        '}}'
    )

    info = spec_state.find_active_spec(prefer_session_id=None)
    assert info is not None
    assert info["session_id"] == "default"
    assert info["spec_slug"] == "older-slug"


def test_ledger_turn_lifecycle(tmp_path):
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()
    ledger = spec_sync.read_ledger(spec_dir)
    assert ledger["turn_id"] is None
    spec_sync.start_new_turn(ledger, tmp_path, ["src/a.py"])
    assert ledger["turn_id"] is not None
    assert ledger["tasks_files"] == ["src/a.py"]
    spec_sync.append_change(ledger, "code", "src/a.py", "Edit")
    assert len(ledger["turn_code_changes"]) == 1
    spec_sync.reset_turn(ledger)
    assert ledger["turn_code_changes"] == []


# ---- Advisory helpers (0.4.0) ----------------------------------------------

def test_record_advisory_dedupes_same_turn_file(tmp_path):
    import spec_sync
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()
    ledger = spec_sync.read_ledger(spec_dir)
    spec_sync.start_new_turn(ledger, tmp_path / "project", [])
    spec_sync.record_advisory(ledger, "INV-1", "msg", file="src/a.py")
    spec_sync.record_advisory(ledger, "INV-1", "msg", file="src/a.py")  # dup
    spec_sync.record_advisory(ledger, "INV-1", "msg", file="src/b.py")
    assert len(ledger["pending_advisories"]) == 2


def test_auto_dismiss_drops_inv1_2_4_keeps_inv6(tmp_path):
    import spec_sync
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()
    ledger = spec_sync.read_ledger(spec_dir)
    spec_sync.record_advisory(ledger, "INV-1", "m", file="x.py")
    spec_sync.record_advisory(ledger, "INV-2", "m")
    spec_sync.record_advisory(ledger, "INV-4", "m")
    spec_sync.record_advisory(ledger, "INV-6", "m", file="y.py")
    dropped = spec_sync.auto_dismiss_on_doc_change(ledger)
    assert dropped == 3
    remaining = {a["id"] for a in ledger["pending_advisories"]}
    assert remaining == {"INV-6"}


def test_dismiss_advisories_all(tmp_path):
    import spec_sync
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()
    ledger = spec_sync.read_ledger(spec_dir)
    spec_sync.record_advisory(ledger, "INV-1", "m", file="x.py")
    spec_sync.record_advisory(ledger, "INV-6", "m", file="y.py")
    dropped = spec_sync.dismiss_advisories(ledger)
    assert dropped == 2
    assert ledger["pending_advisories"] == []


def test_dismiss_advisories_selective(tmp_path):
    import spec_sync
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()
    ledger = spec_sync.read_ledger(spec_dir)
    spec_sync.record_advisory(ledger, "INV-1", "m", file="x.py")
    spec_sync.record_advisory(ledger, "INV-6", "m", file="y.py")
    dropped = spec_sync.dismiss_advisories(ledger, inv_ids=["INV-1"])
    assert dropped == 1
    assert [a["id"] for a in ledger["pending_advisories"]] == ["INV-6"]


def test_format_advisories_block_empty(tmp_path):
    import spec_sync
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()
    ledger = spec_sync.read_ledger(spec_dir)
    assert spec_sync.format_advisories_block(ledger) == ""


def test_format_advisories_block_groups_by_inv(tmp_path):
    import spec_sync
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()
    ledger = spec_sync.read_ledger(spec_dir)
    spec_sync.record_advisory(ledger, "INV-1", "m1", file="a.py")
    spec_sync.record_advisory(ledger, "INV-1", "m1", file="b.py")
    spec_sync.record_advisory(ledger, "INV-2", "m2")
    out = spec_sync.format_advisories_block(ledger)
    assert "pending advisories" in out
    assert "INV-1 × 2" in out
    assert "INV-2 × 1" in out
