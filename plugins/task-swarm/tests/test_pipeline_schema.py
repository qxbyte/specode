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
