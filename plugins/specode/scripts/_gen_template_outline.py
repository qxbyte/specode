#!/usr/bin/env python3
"""_gen_template_outline.py — 开发期工具：从 assets/templates/*.md 重算 TEMPLATE_OUTLINES。

非 hook、非业务 CLI。模板章节改动后手动跑一次，把 stdout 字典字面量复制粘贴覆盖
`scripts/spec_session/_template_skeleton.py` 中的 TEMPLATE_OUTLINES 块（带 BEGIN/END 注释）。

`tests/test_template_outlines_drift.py` 每次跑测试都会对比，模板改了忘 regen 会红。

用法：
  python3 scripts/_gen_template_outline.py            # 默认从 ../assets/templates/ 读
  python3 scripts/_gen_template_outline.py --templates <dir>

stdlib-only。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


THIS_DIR = Path(__file__).resolve().parent
# 确保能 import spec_session._template_skeleton
sys.path.insert(0, str(THIS_DIR))

from spec_session._template_skeleton import parse_templates_dir  # noqa: E402


def _format_str_list(items: list[str], indent: int) -> str:
    if not items:
        return "[]"
    pad = " " * indent
    inner = ",\n".join(f"{pad}    {repr(item)}" for item in items)
    return "[\n" + inner + f",\n{pad}]"


def _format_outlines(outlines: dict[str, dict[str, list[str]]]) -> str:
    lines = ["TEMPLATE_OUTLINES: dict[str, dict[str, list[str]]] = {"]
    for phase, outline in outlines.items():
        lines.append(f"    {repr(phase)}: {{")
        for key in ("mandatory", "optional", "dynamic_prefixes"):
            items = outline.get(key, [])
            rendered = _format_str_list(items, indent=8)
            lines.append(f"        {repr(key)}: {rendered},")
        lines.append("    },")
    lines.append("}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="_gen_template_outline.py",
                                     description="重算 TEMPLATE_OUTLINES 字面量")
    parser.add_argument(
        "--templates",
        default=str(THIS_DIR.parent / "assets" / "templates"),
        help="模板目录（默认 ../assets/templates/）",
    )
    args = parser.parse_args(argv)

    templates_dir = Path(args.templates).resolve()
    if not templates_dir.is_dir():
        sys.stderr.write(f"模板目录不存在：{templates_dir}\n")
        return 1

    outlines = parse_templates_dir(templates_dir)
    sys.stdout.write(
        "# 把下方字面量覆盖 scripts/spec_session/_template_skeleton.py 中\n"
        "# `>>> BEGIN AUTO-MAINTAINED` 与 `>>> END AUTO-MAINTAINED` 之间的 TEMPLATE_OUTLINES。\n\n"
    )
    sys.stdout.write(_format_outlines(outlines) + "\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
