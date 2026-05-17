"""Unit tests for task_swarm_parse_md.

Cover: stage/leaf identification, checkpoint linking, @swarm tag arbitration
(5-tier priority table from references/task-swarm.md), heuristic defaults,
file-union for parallelism check, invalid tags warning.
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import task_swarm_parse_md as M  # noqa: E402


SAMPLE = """\
- [ ] 1. 实现登录核心流程
  - [ ] 1.1 写 User model
    - 文件：src/models/user.py
    - 验证：pytest tests/test_user.py
    - _需求：1.1_
  - [ ] 1.2 写 auth service
    - 文件：src/auth/service.py
    - _需求：1.2_
  - [ ] 1.3 写 controller
    - 文件：src/api/login.py
    - _需求：1.3_

- [ ] 2. 检查点 — 登录跑通
  - 运行 pytest

- [ ] 3. 实现登出
  - [ ] 3.1 logout service
    - 文件：src/auth/logout.py
    - _需求：2.1_

- [*] 5. 优化
  - [ ] 5.1 失败计数 @swarm:coder-only
    - 文件：src/auth/lockout.py
"""


def test_parse_basic_stages_and_leaves():
    plan = M.parse_tasks_md(SAMPLE)
    assert [s.num for s in plan.stages] == [1, 2, 3, 5]
    assert [s.kind for s in plan.stages] == ["stage", "checkpoint", "stage", "stage"]
    s1 = plan.stages[0]
    assert [l.num for l in s1.leaves] == ["1.1", "1.2", "1.3"]
    assert s1.leaves[0].files == ["src/models/user.py"]
    assert s1.leaves[0].requirement == "1.1"
    assert s1.leaves[0].verify == "pytest tests/test_user.py"


def test_checkpoint_links_to_prior_stage():
    plan = M.parse_tasks_md(SAMPLE)
    cp = next(s for s in plan.stages if s.kind == "checkpoint")
    assert cp.num == 2
    assert cp.checkpoint_for == 1
    assert cp.deps == [1]


def test_optional_marker_propagates():
    plan = M.parse_tasks_md(SAMPLE)
    s5 = next(s for s in plan.stages if s.num == 5)
    assert s5.optional is True


def test_files_union_drops_skipped_leaves():
    text = (
        "- [ ] 1. 测试 union\n"
        "  - [ ] 1.1 a @swarm:skip\n"
        "    - 文件：src/a.py\n"
        "  - [ ] 1.2 b\n"
        "    - 文件：src/b.py\n"
    )
    plan = M.parse_tasks_md(text)
    assert plan.stages[0].files_union == ["src/b.py"]


# ---------- tag arbitration ----------

def test_tag_skip_wins_over_full():
    text = "- [ ] 1. T\n  - [*] 1.1 x @swarm:full @swarm:skip\n"
    plan = M.parse_tasks_md(text)
    leaf = plan.stages[0].leaves[0]
    assert leaf.policy == "skip"
    assert any("skip" in w for w in plan.warnings)


def test_tag_full_beats_coder_only():
    text = "- [ ] 1. T\n  - [ ] 1.1 x @swarm:full @swarm:coder-only\n"
    plan = M.parse_tasks_md(text)
    assert plan.stages[0].leaves[0].policy == "full"
    assert any("full" in w and "coder-only" in w for w in plan.warnings)


def test_tag_coder_only_overrides_heuristic():
    text = (
        "- [ ] 1. T\n"
        "  - [ ] 1.1 x @swarm:coder-only\n"
        "    - 文件：src/x.py\n"
        "    - _需求：1.1_\n"
    )
    plan = M.parse_tasks_md(text)
    assert plan.stages[0].leaves[0].policy == "coder-only"


def test_tag_full_overrides_optional_heuristic():
    text = (
        "- [ ] 1. T\n"
        "  - [*] 1.1 x @swarm:full\n"
        "    - 文件：src/x.py\n"
    )
    plan = M.parse_tasks_md(text)
    leaf = plan.stages[0].leaves[0]
    assert leaf.policy == "full"
    assert leaf.optional is True


def test_heuristic_optional_to_coder_only():
    text = (
        "- [ ] 1. T\n"
        "  - [*] 1.1 x\n"
        "    - 文件：src/x.py\n"
        "    - _需求：1.1_\n"
    )
    plan = M.parse_tasks_md(text)
    assert plan.stages[0].leaves[0].policy == "coder-only"


def test_heuristic_no_requirement_to_coder_only():
    text = (
        "- [ ] 1. T\n"
        "  - [ ] 1.1 x\n"
        "    - 文件：src/x.py\n"
    )
    plan = M.parse_tasks_md(text)
    assert plan.stages[0].leaves[0].policy == "coder-only"


def test_default_policy_for_tracked_leaf():
    text = (
        "- [ ] 1. T\n"
        "  - [ ] 1.1 x\n"
        "    - 文件：src/x.py\n"
        "    - _需求：1.1_\n"
    )
    plan = M.parse_tasks_md(text)
    assert plan.stages[0].leaves[0].policy == "default"


def test_invalid_tag_warning():
    text = "- [ ] 1. T\n  - [ ] 1.1 x @swarm:strict\n    - _需求：1.1_\n"
    plan = M.parse_tasks_md(text)
    # Invalid tag dropped; heuristic kicks in. Has requirement + not optional → default.
    assert plan.stages[0].leaves[0].policy == "default"
    assert any("strict" in w for w in plan.warnings)


# ---------- parallelism ----------

def test_parallelizable_disjoint_files():
    text = (
        "- [ ] 1. A\n"
        "  - [ ] 1.1 a\n"
        "    - 文件：src/a.py\n"
        "    - _需求：1.1_\n"
        "- [ ] 3. B\n"
        "  - [ ] 3.1 b\n"
        "    - 文件：src/b.py\n"
        "    - _需求：3.1_\n"
    )
    plan = M.parse_tasks_md(text)
    a, b = plan.stages[0], plan.stages[1]
    assert M.parallelizable(a, b) is True


def test_not_parallelizable_overlapping_files():
    text = (
        "- [ ] 1. A\n"
        "  - [ ] 1.1 a\n"
        "    - 文件：src/shared.py\n"
        "    - _需求：1.1_\n"
        "- [ ] 3. B\n"
        "  - [ ] 3.1 b\n"
        "    - 文件：src/shared.py\n"
        "    - _需求：3.1_\n"
    )
    plan = M.parse_tasks_md(text)
    assert M.parallelizable(plan.stages[0], plan.stages[1]) is False


def test_checkpoint_not_parallel_with_dep():
    text = (
        "- [ ] 1. A\n"
        "  - [ ] 1.1 a\n"
        "    - 文件：src/a.py\n"
        "    - _需求：1.1_\n"
        "- [ ] 2. 检查点\n"
    )
    plan = M.parse_tasks_md(text)
    assert M.parallelizable(plan.stages[0], plan.stages[1]) is False


def test_stages_with_role():
    plan = M.parse_tasks_md(SAMPLE)
    coder_stages = list(M.stages_with_role(plan, "coder"))
    assert [s.num for s in coder_stages] == [1, 3, 5]

    reviewer_stages = list(M.stages_with_role(plan, "reviewer"))
    # stage 5: 5.1 is coder-only (explicit tag) → no reviewer
    assert [s.num for s in reviewer_stages] == [1, 3]

    validator_stages = list(M.stages_with_role(plan, "validator"))
    assert [s.num for s in validator_stages] == [2]


def test_to_dict_is_json_safe():
    import json
    plan = M.parse_tasks_md(SAMPLE)
    json.dumps(plan.to_dict())  # must not raise
