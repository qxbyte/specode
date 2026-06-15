"""tests for task_swarm/_pipeline.py — pipeline.yml schema validator."""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from task_swarm._pipeline import validate  # noqa: E402


def _ok():
    return {"version": 1, "task_groups": [
        {"id": "g1", "name": "A", "tasks": [
            {"id": "g1.1", "title": "t", "writes": ["a.py"]}]}]}


def test_valid_pipeline_no_errors():
    assert validate(_ok()) == []


def test_missing_version():
    d = _ok(); del d["version"]
    assert any("version" in e for e in validate(d))


def test_empty_task_groups():
    assert any("task_groups" in e for e in validate({"version": 1, "task_groups": []}))


def test_duplicate_task_id():
    d = _ok(); d["task_groups"][0]["tasks"].append({"id": "g1.1", "title": "t2", "writes": ["b.py"]})
    assert any("g1.1" in e and "duplicate" in e.lower() for e in validate(d))


def test_needs_dangling():
    d = _ok(); d["task_groups"][0]["needs"] = ["nope"]
    assert any("nope" in e for e in validate(d))


def test_task_without_writes():
    d = _ok(); del d["task_groups"][0]["tasks"][0]["writes"]
    assert any("writes" in e for e in validate(d))


def test_to_group_states_preserves_group_level_needs_and_writes():
    from task_swarm._pipeline import to_group_states
    pipe = {
        "version": 1,
        "task_groups": [
            {"id": "g1", "name": "A", "tasks": [
                {"id": "g1.1", "title": "t1", "writes": ["src/a.py"]},
                {"id": "g1.2", "title": "t2", "writes": ["src/b.py"]}]},
            {"id": "g2", "name": "B", "needs": ["g1"], "tasks": [
                {"id": "g2.1", "title": "t3", "writes": ["src/c.py"]}]},
        ],
    }
    gs = to_group_states(pipe)
    assert [g["id"] for g in gs] == ["g1", "g2"]
    assert gs[0]["name"] == "A"
    assert gs[1]["needs"] == ["g1"]
    assert set(gs[0]["writes"]) == {"src/a.py", "src/b.py"}
    assert [it["number"] for it in gs[0]["items"]] == ["1.1", "1.2"]
    assert gs[0]["items"][0]["title"] == "t1"
    assert gs[0]["items"][0]["writes"] == ["src/a.py"]
