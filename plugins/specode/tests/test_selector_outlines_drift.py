"""SELECTOR_OUTLINES drift 守门：

常量字典 (`spec_session/_selector_skeleton.py::SELECTOR_OUTLINES`) 必须与
`spec_session/_selectors.py::SELECTOR_PROMPTS` 当前内容解析结果一致。
SELECTOR_PROMPTS 改了忘跑 `scripts/_gen_selector_outlines.py` 重生常量 → 本测试会红，
提示哪条 selector 漂移。

与 `test_template_outlines_drift.py` / `test_selectors_drift.py` 同一类守门测试。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PLUGIN_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


from spec_session._selector_skeleton import (  # noqa: E402
    SELECTOR_OUTLINES,
    parse_all_selectors,
)
from spec_session._selectors import SELECTOR_PROMPTS  # noqa: E402


@pytest.fixture(scope="module")
def parsed_outlines() -> dict:
    return parse_all_selectors(SELECTOR_PROMPTS)


def test_selector_outlines_key_set_matches_prompts(parsed_outlines):
    assert set(SELECTOR_OUTLINES.keys()) == set(SELECTOR_PROMPTS.keys()) == set(parsed_outlines.keys())


@pytest.mark.parametrize("key", sorted(SELECTOR_PROMPTS.keys()))
def test_selector_outline_no_drift(key, parsed_outlines):
    expected = parsed_outlines[key]
    actual = SELECTOR_OUTLINES[key]
    assert actual == expected, (
        f"selector `{key}` 漂移：\n"
        f"  常量字典: {actual}\n"
        f"  实际解析: {expected}\n"
        f"修复：跑 `python3 scripts/_gen_selector_outlines.py` 重生 SELECTOR_OUTLINES。"
    )


def test_only_clarification_wizard_is_dynamic(parsed_outlines):
    """11 个 selector 中只有 clarification-wizard 是 dynamic。"""
    dynamic_keys = [k for k, v in parsed_outlines.items() if v.get("kind") == "dynamic"]
    assert dynamic_keys == ["clarification-wizard"], (
        f"动态 selector 集合变化：{dynamic_keys}。如果新增了 dynamic selector，"
        "需要更新本测试断言并检查 PreToolUse 校验路径。"
    )


def test_iteration_scope_is_only_multiselect(parsed_outlines):
    """iteration-scope 是唯一的 multiSelect=true selector（详 references/selectors.md §类型 C）。"""
    multi_keys = [
        k for k, v in parsed_outlines.items()
        if v.get("kind") == "fixed" and v.get("multi_select")
    ]
    assert multi_keys == ["iteration-scope"]
