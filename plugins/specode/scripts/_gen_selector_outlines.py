#!/usr/bin/env python3
"""_gen_selector_outlines.py — 开发期工具：从 SELECTOR_PROMPTS 重算 SELECTOR_OUTLINES。

非 hook、非业务 CLI。selector 模板内容改动后手动跑一次，把 stdout 字面量复制粘贴
覆盖 `scripts/spec_session/_selector_skeleton.py` 中 SELECTOR_OUTLINES 块（带
BEGIN/END 注释）。

`tests/test_selector_outlines_drift.py` 每次跑测试都自动对比，模板改了忘 regen 会红。

用法：
  python3 scripts/_gen_selector_outlines.py

stdlib-only。
"""
from __future__ import annotations

import sys
from pathlib import Path


THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR))

from spec_session._selector_skeleton import parse_all_selectors  # noqa: E402
from spec_session._selectors import SELECTOR_PROMPTS  # noqa: E402


def _format_value(value) -> str:
    if isinstance(value, list):
        if not value:
            return "[]"
        inner = ",\n".join(f"            {repr(item)}" for item in value)
        return "[\n" + inner + ",\n        ]"
    if isinstance(value, bool):
        return repr(value)
    if isinstance(value, (int, float)):
        return repr(value)
    return repr(value)


def _format_outlines(outlines: dict) -> str:
    lines = ["SELECTOR_OUTLINES: dict[str, dict] = {"]
    for key, outline in outlines.items():
        lines.append(f"    {repr(key)}: {{")
        for k, v in outline.items():
            lines.append(f"        {repr(k)}: {_format_value(v)},")
        lines.append("    },")
    lines.append("}")
    return "\n".join(lines)


def main() -> int:
    outlines = parse_all_selectors(SELECTOR_PROMPTS)
    sys.stdout.write(
        "# 把下方字面量覆盖 scripts/spec_session/_selector_skeleton.py 中\n"
        "# `>>> BEGIN AUTO-MAINTAINED` 与 `>>> END AUTO-MAINTAINED` 之间的 SELECTOR_OUTLINES。\n\n"
    )
    sys.stdout.write(_format_outlines(outlines) + "\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
