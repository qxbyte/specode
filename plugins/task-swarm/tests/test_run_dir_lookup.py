"""v0.9 痛点 #12 — task-swarm subcommands no longer hard-depend on cwd.

Bug: `init --workdir /A/B` wrote state to `/A/B/.task-swarm/`, but a later
`plan --run <id>` from any other cwd would `FileNotFoundError` because
`_find_run_dir` only knew how to scan from cwd upward.

Fix: register `(run_id → run_dir)` in user-wide `~/.task-swarm/registry.json`
at init time. `_find_run_dir` then consults:

    1. run_id itself is a path → use it as-is (back-compat)
    2. $TASK_SWARM_WORKDIR env var override
    3. ~/.task-swarm/registry.json lookup (NEW)
    4. cwd + cwd.parents recursive scan (back-compat fallback)

This file tests the new resolution chain without invoking the real CLI:
we exercise the resolver directly because the full init flow needs
PyYAML / pipeline parsing which is covered elsewhere.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(REPO_SCRIPTS))

from task_swarm import cli  # noqa: E402


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("TASK_SWARM_WORKDIR", raising=False)
    return tmp_path


def _make_run(workdir: Path, run_id: str) -> Path:
    """Create a fake state.json under workdir/.task-swarm/runs/run_id/."""
    run_dir = workdir / ".task-swarm" / "runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "state.json").write_text("{}", encoding="utf-8")
    return run_dir


# ---------- (1) run_id is already a path ----------


def test_find_run_dir_accepts_absolute_path_as_run_id(fake_home, tmp_path):
    workdir = tmp_path / "proj"
    run_dir = _make_run(workdir, "20260628-1-abcdef")
    found = cli._find_run_dir(str(run_dir))
    assert found.resolve() == run_dir.resolve()


# ---------- (2) $TASK_SWARM_WORKDIR env override ----------


def test_find_run_dir_uses_TASK_SWARM_WORKDIR_env(fake_home, tmp_path, monkeypatch):
    workdir = tmp_path / "proj"
    run_id = "20260628-2-abcdef"
    _make_run(workdir, run_id)
    monkeypatch.setenv("TASK_SWARM_WORKDIR", str(workdir))
    (tmp_path / "elsewhere").mkdir()
    monkeypatch.chdir(tmp_path / "elsewhere")  # NOT under workdir

    found = cli._find_run_dir(run_id)
    assert (found / "state.json").is_file()
    assert str(workdir) in str(found)


# ---------- (3) registry lookup (the v0.9 #12 main fix) ----------


def test_find_run_dir_via_registry_when_cwd_drifted(fake_home, tmp_path, monkeypatch):
    """The flagship case: init was called from /A/B/proj, registry was
    populated, then user `cd`-ed away. plan/advance must still find the
    run via registry."""
    workdir = tmp_path / "proj"
    run_id = "20260628-3-abcdef"
    run_dir = _make_run(workdir, run_id)

    # Simulate what init does: register the run
    cli._registry_register(run_id, run_dir)

    # User cd-ed to an unrelated dir
    elsewhere = tmp_path / "totally" / "unrelated"
    elsewhere.mkdir(parents=True)
    monkeypatch.chdir(elsewhere)

    found = cli._find_run_dir(run_id)
    assert (found / "state.json").is_file()
    assert found.resolve() == run_dir.resolve()


def test_registry_survives_multiple_runs(fake_home, tmp_path):
    """Multiple concurrent runs in different workdirs all coexist in the
    registry; each can be looked up independently."""
    wd1 = tmp_path / "proj1"
    wd2 = tmp_path / "proj2"
    rd1 = _make_run(wd1, "run-1")
    rd2 = _make_run(wd2, "run-2")
    cli._registry_register("run-1", rd1)
    cli._registry_register("run-2", rd2)

    f1 = cli._find_run_dir("run-1")
    f2 = cli._find_run_dir("run-2")
    assert f1.resolve() == rd1.resolve()
    assert f2.resolve() == rd2.resolve()


def test_registry_stale_entry_falls_back_to_cwd_scan(fake_home, tmp_path, monkeypatch):
    """If registry points at a run_dir that has been deleted (user `rm -rf`d
    or moved repo), fall back to cwd recursive scan — don't return a
    nonexistent path."""
    workdir = tmp_path / "proj"
    run_id = "20260628-stale"
    run_dir = _make_run(workdir, run_id)
    cli._registry_register(run_id, run_dir)

    # Now delete the run_dir behind the registry's back
    import shutil

    shutil.rmtree(run_dir)

    # Recreate under a *different* workdir (simulating user moved the project)
    new_workdir = tmp_path / "renamed"
    new_run_dir = _make_run(new_workdir, run_id)

    monkeypatch.chdir(new_workdir)
    found = cli._find_run_dir(run_id)
    assert found.resolve() == new_run_dir.resolve(), (
        "stale registry should not win over an existing on-disk run found via cwd scan"
    )


# ---------- (4) cwd-scan fallback still works ----------


def test_find_run_dir_falls_back_to_cwd_scan_when_no_registry(
    fake_home, tmp_path, monkeypatch
):
    """Back-compat: no env, no registry, cwd is at or under workdir →
    recursive scan still works (old behaviour preserved)."""
    workdir = tmp_path / "proj"
    run_id = "20260628-cwd-only"
    run_dir = _make_run(workdir, run_id)

    # Don't register, just cd to workdir
    monkeypatch.chdir(workdir)
    found = cli._find_run_dir(run_id)
    assert found.resolve() == run_dir.resolve()


# ---------- registry file structure ----------


def test_registry_file_lives_under_user_home(fake_home, tmp_path):
    """v0.9 #12 contract: registry is user-wide, not per-project."""
    assert cli._registry_path().is_absolute()
    # Must be under HOME (so cd-ing away never loses it)
    assert str(cli._registry_path()).startswith(str(fake_home))


def test_registry_write_is_atomic_and_round_trips(fake_home, tmp_path):
    """Multiple registrations preserve earlier entries (no truncation race)."""
    wd1 = tmp_path / "p1"
    wd2 = tmp_path / "p2"
    rd1 = _make_run(wd1, "r1")
    rd2 = _make_run(wd2, "r2")
    cli._registry_register("r1", rd1)
    cli._registry_register("r2", rd2)

    data = json.loads(cli._registry_path().read_text(encoding="utf-8"))
    assert "r1" in data and "r2" in data
    # Each entry is at minimum {run_dir: abs_path}
    assert Path(data["r1"]["run_dir"]).resolve() == rd1.resolve()
    assert Path(data["r2"]["run_dir"]).resolve() == rd2.resolve()
