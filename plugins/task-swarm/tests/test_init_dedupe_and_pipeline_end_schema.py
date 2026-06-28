"""Regression tests for v0.8.0 M7 (init dedupe) + M3 schema (pipeline-end validator).

试跑 ticket-assign-it-member 时连续两次 init 同 spec_id ticket-assign-it-member
产生 2 个互不知道的 run + 2 条 registry 项需手动清理。M7 修法：spec_id 已有
活跃 run 时按 --on-existing 策略处理（error/resume/abort-old/force-new）。

M3 是 pipeline.yml schema 加 run.pipeline_end_validator 字段的预留（v0.8.0
只 parse + 持久化到 state.json，不消费；advance/plan logic 留 v0.8.1）。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1] / "scripts"
TASK_SWARM_PY = REPO_ROOT / "task_swarm.py"

sys.path.insert(0, str(REPO_ROOT))
from task_swarm._pipeline import validate as pipeline_validate  # noqa: E402
from task_swarm._state import StateMachine  # noqa: E402


def _make_pipeline_yml(path: Path, spec_id: str = "demo-spec") -> None:
    """Minimal valid pipeline.yml."""
    path.write_text(
        f"""version: 1
run:
  spec_id: {spec_id}
task_groups:
  - id: g1
    name: "demo group"
    tasks:
      - id: g1.1
        title: "demo task"
        writes:
          - src/foo.py
""",
        encoding="utf-8",
    )


def _run_init(workdir: Path, pipeline: Path, spec_id: str,
              on_existing: str | None = None,
              fake_home: Path | None = None) -> subprocess.CompletedProcess:
    """Run `task_swarm.py init` as a subprocess (isolates registry per test)."""
    cmd = [
        sys.executable, str(TASK_SWARM_PY), "init",
        "--pipeline", str(pipeline),
        "--workdir", str(workdir),
        "--spec-id", spec_id,
    ]
    if on_existing:
        cmd += ["--on-existing", on_existing]
    env = os.environ.copy()
    if fake_home is not None:
        env["HOME"] = str(fake_home)
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


# ---------- M7 init dedupe ----------

def test_init_first_call_succeeds_no_existing(tmp_path: Path) -> None:
    """First init for a spec_id always succeeds — nothing to dedupe."""
    pipeline = tmp_path / "pipeline.yml"
    _make_pipeline_yml(pipeline)
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    home = tmp_path / "home"
    home.mkdir()

    result = _run_init(workdir, pipeline, "demo-spec", fake_home=home)
    assert result.returncode == 0, f"first init failed: {result.stderr}"
    data = json.loads(result.stdout)
    assert "run_id" in data
    assert data.get("resumed") is None


def test_init_second_call_blocks_by_default(tmp_path: Path) -> None:
    """Second init for same spec_id (active run) → exit 1 + hint listing options."""
    pipeline = tmp_path / "pipeline.yml"
    _make_pipeline_yml(pipeline)
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    home = tmp_path / "home"
    home.mkdir()

    r1 = _run_init(workdir, pipeline, "demo-spec", fake_home=home)
    assert r1.returncode == 0

    r2 = _run_init(workdir, pipeline, "demo-spec", fake_home=home)
    assert r2.returncode == 1, "second init must block by default"
    assert "已有" in r2.stderr and "活跃 run" in r2.stderr
    for hint in ("--on-existing resume", "--on-existing abort-old",
                 "--on-existing force-new"):
        assert hint in r2.stderr


def test_init_resume_returns_existing_run(tmp_path: Path) -> None:
    """--on-existing resume → return existing run_id (no new run created)."""
    pipeline = tmp_path / "pipeline.yml"
    _make_pipeline_yml(pipeline)
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    home = tmp_path / "home"
    home.mkdir()

    r1 = _run_init(workdir, pipeline, "demo-spec", fake_home=home)
    data1 = json.loads(r1.stdout)
    rid1 = data1["run_id"]

    r2 = _run_init(workdir, pipeline, "demo-spec",
                   on_existing="resume", fake_home=home)
    assert r2.returncode == 0
    data2 = json.loads(r2.stdout)
    assert data2.get("resumed") is True
    assert data2["run_id"] == rid1  # same run, not a new one


def test_init_abort_old_marks_existing_aborted_and_creates_new(tmp_path: Path) -> None:
    """--on-existing abort-old → old run marked aborted + new run created."""
    pipeline = tmp_path / "pipeline.yml"
    _make_pipeline_yml(pipeline)
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    home = tmp_path / "home"
    home.mkdir()

    r1 = _run_init(workdir, pipeline, "demo-spec", fake_home=home)
    rid1 = json.loads(r1.stdout)["run_id"]
    old_state = workdir / ".task-swarm" / "runs" / rid1 / "state.json"

    r2 = _run_init(workdir, pipeline, "demo-spec",
                   on_existing="abort-old", fake_home=home)
    assert r2.returncode == 0
    rid2 = json.loads(r2.stdout)["run_id"]
    assert rid2 != rid1

    # Old run is now aborted
    old_data = json.loads(old_state.read_text())
    assert old_data.get("failed_status") == "aborted"
    abort_events = [e for e in old_data.get("events", []) if e.get("type") == "abort"]
    assert len(abort_events) >= 1


def test_init_force_new_creates_alongside_silently(tmp_path: Path) -> None:
    """--on-existing force-new → new run created, old one untouched."""
    pipeline = tmp_path / "pipeline.yml"
    _make_pipeline_yml(pipeline)
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    home = tmp_path / "home"
    home.mkdir()

    r1 = _run_init(workdir, pipeline, "demo-spec", fake_home=home)
    rid1 = json.loads(r1.stdout)["run_id"]

    r2 = _run_init(workdir, pipeline, "demo-spec",
                   on_existing="force-new", fake_home=home)
    assert r2.returncode == 0
    rid2 = json.loads(r2.stdout)["run_id"]
    assert rid2 != rid1

    # Old run NOT aborted (force-new explicitly ignores existing)
    old_state = workdir / ".task-swarm" / "runs" / rid1 / "state.json"
    old_data = json.loads(old_state.read_text())
    assert old_data.get("failed_status") != "aborted"


# ---------- M3 schema: run.pipeline_end_validator ----------

def test_pipeline_end_validator_schema_accepts_bool() -> None:
    """run.pipeline_end_validator is an optional bool — true/false accepted."""
    for val in (True, False):
        data = {
            "version": 1,
            "run": {"spec_id": "x", "pipeline_end_validator": val},
            "task_groups": [
                {"id": "g1", "name": "n", "tasks": [
                    {"id": "g1.1", "title": "t", "writes": ["a"]}
                ]}
            ],
        }
        assert pipeline_validate(data) == [], (
            f"pipeline_end_validator={val} should validate; got errors"
        )


def test_pipeline_end_validator_schema_rejects_non_bool() -> None:
    """run.pipeline_end_validator must be bool — string / int rejected."""
    for val in ("yes", 1, "true"):
        data = {
            "version": 1,
            "run": {"spec_id": "x", "pipeline_end_validator": val},
            "task_groups": [
                {"id": "g1", "name": "n", "tasks": [
                    {"id": "g1.1", "title": "t", "writes": ["a"]}
                ]}
            ],
        }
        errors = pipeline_validate(data)
        assert any("pipeline_end_validator" in e for e in errors), (
            f"pipeline_end_validator={val!r} must be rejected; got {errors}"
        )


def test_pipeline_end_validator_default_false_persisted(tmp_path: Path) -> None:
    """When pipeline.yml omits run.pipeline_end_validator, state.json
    persists `false` (default) — back-compat with every existing pipeline."""
    pipeline = tmp_path / "pipeline.yml"
    _make_pipeline_yml(pipeline)  # no pipeline_end_validator set
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    r = _run_init(workdir, pipeline, "demo-spec", fake_home=home)
    assert r.returncode == 0
    rid = json.loads(r.stdout)["run_id"]

    sm = StateMachine.load(workdir / ".task-swarm" / "runs" / rid)
    assert sm.pipeline_end_validator is False


def test_pipeline_end_validator_true_persisted(tmp_path: Path) -> None:
    """When pipeline.yml sets run.pipeline_end_validator: true, state.json
    persists `true` (ready for v0.8.1 to consume)."""
    pipeline = tmp_path / "pipeline.yml"
    pipeline.write_text(
        """version: 1
run:
  spec_id: demo-spec
  pipeline_end_validator: true
task_groups:
  - id: g1
    name: "demo"
    tasks:
      - id: g1.1
        title: "t"
        writes:
          - a.py
""",
        encoding="utf-8",
    )
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    r = _run_init(workdir, pipeline, "demo-spec", fake_home=home)
    assert r.returncode == 0, f"init failed: {r.stderr}"
    rid = json.loads(r.stdout)["run_id"]

    sm = StateMachine.load(workdir / ".task-swarm" / "runs" / rid)
    assert sm.pipeline_end_validator is True
