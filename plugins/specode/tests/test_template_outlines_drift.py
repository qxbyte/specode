"""TEMPLATE_OUTLINES drift 守门：

模板章节常量字典 (`spec_session/_template_skeleton.py::TEMPLATE_OUTLINES`) 必须
与 `assets/templates/*.md` 当前内容解析结果一致。模板改了忘跑
`scripts/_gen_template_outline.py` 重生常量 → 本测试会红，提示哪份模板漂移。

与 `tests/test_selectors_drift.py` 同一类守门测试。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PLUGIN_ROOT / "scripts"
TEMPLATES_DIR = PLUGIN_ROOT / "assets" / "templates"


# 让 spec_session 包可被本测试 import（与 conftest 的 subprocess 路径独立）。
sys.path.insert(0, str(SCRIPTS_DIR))


from spec_session._template_skeleton import (  # noqa: E402
    TEMPLATE_OUTLINES,
    parse_templates_dir,
)


@pytest.fixture(scope="module")
def parsed_outlines() -> dict:
    return parse_templates_dir(TEMPLATES_DIR)


def test_template_outlines_phase_set(parsed_outlines):
    """常量字典 key 集合必须等于 3 份核心模板（M4 起不再有 tasks.md）。"""
    assert set(TEMPLATE_OUTLINES.keys()) == set(parsed_outlines.keys()) == {
        "requirements.md",
        "bugfix.md",
        "design.md",
    }


@pytest.mark.parametrize("phase", ["requirements.md", "bugfix.md", "design.md"])
def test_template_outline_no_drift(phase, parsed_outlines):
    """每份模板的 mandatory / optional / dynamic_prefixes 必须与常量字典完全一致。

    任一不一致 → 提示开发者跑 `python3 scripts/_gen_template_outline.py` 重生常量并
    粘贴覆盖 `_template_skeleton.py` 中 AUTO-MAINTAINED 区块。
    """
    expected = parsed_outlines[phase]
    actual = TEMPLATE_OUTLINES[phase]
    for key in ("mandatory", "optional", "dynamic_prefixes"):
        assert actual.get(key, []) == expected.get(key, []), (
            f"{phase} 的 `{key}` 与 assets/templates/{phase} 解析结果漂移：\n"
            f"  常量字典: {actual.get(key, [])}\n"
            f"  实际解析: {expected.get(key, [])}\n"
            f"修复：跑 `python3 scripts/_gen_template_outline.py` 重生 TEMPLATE_OUTLINES。"
        )
