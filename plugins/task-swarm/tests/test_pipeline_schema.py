"""tests for task_swarm/_pipeline.py — pipeline.yml schema validator."""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from task_swarm._pipeline import to_stages, validate  # noqa: E402
from task_swarm._parse_md import parse_tasks_md  # noqa: E402
from task_swarm._pipeline_yaml import parse as yparse  # noqa: E402


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


def test_to_stages_basic():
    d = {"version": 1, "task_groups": [
        {"id": "g1", "name": "A", "needs": [], "tasks": [
            {"id": "g1.1", "title": "alpha", "writes": ["a.py"], "requirements": ["1.1"]}]},
        {"id": "g2", "name": "B", "needs": ["g1"], "tasks": [
            {"id": "g2.1", "title": "beta", "writes": ["b.py"], "requirements": ["2.1"]}]}]}
    stages = to_stages(d)
    assert [s.number for s in stages] == [1, 2]
    assert stages[0].title == "A"
    assert stages[0].items[0].number == "1.1"
    assert stages[0].items[0].title == "alpha"
    assert stages[0].items[0].writes == ["a.py"]
    assert stages[1].depends_on == [1]   # needs g1 -> group index 1


def test_yml_equiv_to_markdown(tmp_path):
    md = ("## 阶段 1: A\n- [ ] 1.1 alpha @writes:a.py _需求：1.1_\n"
          "## 阶段 2: B\n- [ ] 2.1 beta @writes:b.py @depends-on:1 _需求：2.1_\n")
    p = tmp_path / "tasks.md"; p.write_text(md, encoding="utf-8")
    md_stages = parse_tasks_md(p)
    yml = ("version: 1\ntask_groups:\n"
           "  - id: g1\n    name: A\n    tasks:\n      - id: g1.1\n        title: alpha\n"
           "        writes: [a.py]\n        requirements: [\"1.1\"]\n"
           "  - id: g2\n    name: B\n    needs: [g1]\n    tasks:\n      - id: g2.1\n"
           "        title: beta\n        writes: [b.py]\n        requirements: [\"2.1\"]\n")
    y_stages = to_stages(yparse(yml))
    for ms, ys in zip(md_stages, y_stages):
        assert ms.number == ys.number
        assert ms.title == ys.title
        assert [i.number for i in ms.items] == [i.number for i in ys.items]
        assert [i.writes for i in ms.items] == [i.writes for i in ys.items]
        assert ms.depends_on == ys.depends_on
