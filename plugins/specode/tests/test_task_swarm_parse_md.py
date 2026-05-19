"""tests for task_swarm_parse_md.py — tasks.md 解析 + group 切分。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path("/Users/xueqiang/Git/specode/plugins/specode/scripts")
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from task_swarm_parse_md import (  # noqa: E402
    parse_tasks_md, group_by_file_conflict, Stage, StageItem,
)


def _write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "tasks.md"
    p.write_text(text, encoding="utf-8")
    return p


def test_parse_basic_stage(tmp_path):
    md = (
        "# tasks\n\n"
        "## 阶段 1: 第一阶段\n"
        "- [ ] 1.1 写 user @writes:src/user.py _需求：1.1_\n"
        "- [ ] 1.2 写 session @writes:src/session.py _需求：1.2_\n"
    )
    stages = parse_tasks_md(_write(tmp_path, md))
    assert len(stages) == 1
    assert stages[0].number == 1
    assert stages[0].title == "第一阶段"
    assert len(stages[0].items) == 2
    assert stages[0].items[0].number == "1.1"
    assert stages[0].items[0].writes == ["src/user.py"]
    assert stages[0].items[0].requirements == ["1.1"]


def test_parse_multiple_stages_and_deps(tmp_path):
    md = (
        "## 阶段 1: A\n"
        "- [ ] 1.1 alpha @writes:a.py _需求：1.1_\n"
        "## 阶段 2: B\n"
        "- [ ] 2.1 beta @writes:b.py @depends-on:1 _需求：2.1_\n"
    )
    stages = parse_tasks_md(_write(tmp_path, md))
    assert [s.number for s in stages] == [1, 2]
    assert stages[1].items[0].depends_on == ["1"]
    assert stages[1].depends_on == [1]


def test_parse_recognises_chinese_colon(tmp_path):
    md = (
        "## 阶段 1：中文冒号\n"
        "- [ ] 1.1 任务 @writes：x.py _需求：1.1_\n"
    )
    stages = parse_tasks_md(_write(tmp_path, md))
    assert len(stages) == 1
    assert stages[0].items[0].writes == ["x.py"]


def test_parse_ignores_non_item_lines(tmp_path):
    md = (
        "## 阶段 1: A\n"
        "这一段是介绍，不是任务。\n"
        "- [ ] 1.1 真正任务 @writes:x.py _需求：1.1_\n"
        "* [ ] 不被识别（用了 *）\n"
    )
    stages = parse_tasks_md(_write(tmp_path, md))
    assert len(stages[0].items) == 1


def test_parse_checkbox_state(tmp_path):
    md = (
        "## 阶段 1: A\n"
        "- [x] 1.1 已完成 @writes:a.py _需求：1.1_\n"
        "- [ ] 1.2 未完成 @writes:b.py _需求：1.2_\n"
    )
    stages = parse_tasks_md(_write(tmp_path, md))
    assert stages[0].items[0].checkbox.lower() == "x"
    assert stages[0].items[1].checkbox == " "


def test_group_single_stage_one_group():
    s = Stage(number=1, title="A", items=[StageItem(number="1.1", title="x", writes=["a.py"])])
    groups = group_by_file_conflict([s])
    assert len(groups) == 1
    assert groups[0][0].number == 1


def test_group_two_stages_disjoint_files_one_group():
    s1 = Stage(number=1, title="A", items=[StageItem(number="1.1", title="x", writes=["a.py"])])
    s2 = Stage(number=2, title="B", items=[StageItem(number="2.1", title="y", writes=["b.py"])])
    groups = group_by_file_conflict([s1, s2])
    assert len(groups) == 1
    assert {s.number for s in groups[0]} == {1, 2}


def test_group_same_file_split_to_two_groups():
    s1 = Stage(number=1, title="A", items=[StageItem(number="1.1", title="x", writes=["a.py"])])
    s2 = Stage(number=2, title="B", items=[StageItem(number="2.1", title="y", writes=["a.py"])])
    groups = group_by_file_conflict([s1, s2])
    assert len(groups) == 2
    assert groups[0][0].number == 1
    assert groups[1][0].number == 2


def test_group_depends_on_forces_serial():
    s1 = Stage(number=1, title="A", items=[StageItem(number="1.1", title="x", writes=["a.py"])])
    s2 = Stage(number=2, title="B",
               items=[StageItem(number="2.1", title="y", writes=["b.py"], depends_on=["1"])])
    groups = group_by_file_conflict([s1, s2])
    assert len(groups) == 2
    assert groups[0][0].number == 1
    assert groups[1][0].number == 2


def test_group_max_parallel_capacity():
    stages = [
        Stage(number=i, title=f"S{i}",
              items=[StageItem(number=f"{i}.1", title=f"x{i}", writes=[f"f{i}.py"])])
        for i in range(1, 6)
    ]
    groups = group_by_file_conflict(stages, max_parallel=2)
    # 5 stages with max=2 → 3 groups (2,2,1)
    assert sum(len(g) for g in groups) == 5
    for g in groups:
        assert len(g) <= 2


def test_group_full_example_3_groups(tmp_path):
    md = (
        "## 阶段 1: 数据层\n"
        "- [ ] 1.1 user model @writes:src/models/user.py _需求：1.1_\n"
        "- [ ] 1.2 session model @writes:src/models/session.py _需求：1.2_\n"
        "## 阶段 2: 服务层\n"
        "- [ ] 2.1 auth service @writes:src/auth/service.py @depends-on:1 _需求：2.1_\n"
        "## 阶段 3: API\n"
        "- [ ] 3.1 login @writes:src/api/login.py @depends-on:2 _需求：3.1_\n"
        "- [ ] 3.2 user 扩展 @writes:src/models/user.py @depends-on:1 _需求：3.2_\n"
    )
    stages = parse_tasks_md(_write(tmp_path, md))
    groups = group_by_file_conflict(stages, max_parallel=4)
    # 阶段 3 同时与 1 文件冲突 + depends-on=2 → 必须晚于 1 与 2
    assert len(groups) == 3
    assert groups[0][0].number == 1
    assert groups[1][0].number == 2
    assert groups[2][0].number == 3


def test_parse_empty_file(tmp_path):
    p = _write(tmp_path, "")
    stages = parse_tasks_md(p)
    assert stages == []


def test_group_empty_returns_empty():
    assert group_by_file_conflict([]) == []
