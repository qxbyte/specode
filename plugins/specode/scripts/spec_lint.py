#!/usr/bin/env python3
"""spec_lint.py — 对当前 spec 目录做轻量 lint。

仅产出 WARNING；所有 lint 一律 exit 0（不阻断模型流程）。

规则：
  1. implementation-log.md 中每个 `## ` 条目正文 < 30 字符或缺
     文件引用 (`.py` / `.md` 等) → WARNING（"空 log 等于没改过"）
  2. requirements.md 中的 EARS SHALL 行缺动词或缺 trigger
     （形如 WHEN / IF / WHILE / WHERE 关键字开头）→ WARNING
  3. 3 份核心文档 (requirements/bugfix/design).md 的 `## ` 章节集合必须与
     `assets/templates/<phase>.md` 一致：缺 mandatory / 多 unknown 即报 WARNING。
     详 `_template_skeleton.py`。

接入：acceptance phase 进入前由主代理调一次，把 WARNING 列给用户参考
（详见 SKILL.md §Phase Order 中 acceptance 部分）。

用法：
  spec_lint.py --spec <spec-dir>        lint 该 spec 目录下核心文档

stdlib-only。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Optional


THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from spec_session._template_skeleton import (  # type: ignore  # noqa: E402
    TEMPLATE_OUTLINES,
    extract_h2_titles,
    matches_template_section,
)


# -------------------------------------------------------------------------

FILE_REF_RE = re.compile(r"[A-Za-z0-9_./-]+\.(py|md|js|ts|tsx|jsx|go|rs|java|kt|rb|c|h|cpp|sh|yaml|yml|json)")
EARS_HEADS = ("WHEN", "IF", "WHILE", "WHERE", "WHENEVER")
SHALL_LINE_RE = re.compile(r"\bSHALL\b", re.IGNORECASE)


def _warn(buf: list[str], rule: str, msg: str) -> None:
    buf.append(f"[WARN][{rule}] {msg}")


def _read(p: Path) -> Optional[str]:
    try:
        if p.exists() and p.is_file():
            return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None
    return None


def rule_log_entries(spec_dir: Path, warnings: list[str]) -> None:
    log = _read(spec_dir / "implementation-log.md")
    if not log:
        return
    # 拆 ## 开头的条目
    parts = re.split(r"(?m)^##\s+", log)
    # parts[0] 是文件头；条目从 parts[1:] 起
    for entry in parts[1:]:
        # 取第一行作为 title，正文是其余
        head, _, body = entry.partition("\n")
        body_stripped = body.strip()
        title = head.strip()
        if not body_stripped:
            _warn(warnings, "log",
                  f"implementation-log.md 条目「{title[:30]}」正文为空。")
            continue
        if len(body_stripped) < 30:
            _warn(warnings, "log",
                  f"implementation-log.md 条目「{title[:30]}」正文过短（< 30 字符）；信息量不足。")
        if not FILE_REF_RE.search(body_stripped):
            _warn(warnings, "log",
                  f"implementation-log.md 条目「{title[:30]}」未引用任何源码 / 文档文件路径。")


def rule_template_structure(spec_dir: Path, warnings: list[str]) -> None:
    """3 份核心文档 `## ` 章节集合 vs TEMPLATE_OUTLINES。

    - 文档不存在：跳过（spec 可能只有 requirements 或只有 bugfix）。
    - mandatory 中有标题在文档里找不到 → WARNING。
    - 文档里出现的 `## ` 标题既不在 mandatory/optional 名单 → WARNING。
    - 不做顺序校验（第一版保守）。
    """
    for phase_md, outline in TEMPLATE_OUTLINES.items():
        text = _read(spec_dir / phase_md)
        if text is None:
            continue
        actual_titles = extract_h2_titles(text)
        actual_set = set(actual_titles)
        mand_set = set(outline.get("mandatory", []))
        opt_set = set(outline.get("optional", []))
        for missing in sorted(mand_set - actual_set):
            _warn(warnings, "tmpl",
                  f"{phase_md} 缺少 mandatory 章节「{missing}」（模板要求 verbatim 保留）。")
        for title in actual_titles:
            if title in mand_set or title in opt_set:
                continue
            if matches_template_section(title, outline):
                continue
            _warn(warnings, "tmpl",
                  f"{phase_md} 含未知章节「{title}」"
                  "（不在 assets/templates 模板 mandatory/optional 名单，且非动态前缀）。")


def rule_ears_shall(spec_dir: Path, warnings: list[str]) -> None:
    req = _read(spec_dir / "requirements.md")
    if not req:
        return
    for idx, line in enumerate(req.splitlines(), start=1):
        if not SHALL_LINE_RE.search(line):
            continue
        # 简单 EARS 检查：行内或紧邻上文应含 EARS 关键字
        upper = line.upper()
        has_trigger = any(k in upper for k in EARS_HEADS)
        if not has_trigger:
            # 看前后两行
            # 注意：splitlines 不保留尾换行；这里不报上下文，仅提示
            _warn(warnings, "ears",
                  f"requirements.md 第 {idx} 行包含 SHALL 但未检测到 EARS trigger（WHEN/IF/WHILE/WHERE）。")
            continue
        # 检查 SHALL 之后是否有动词（粗略判定：SHALL 后至少有非空白且非 thE/A/AN 的词）
        m = re.search(r"SHALL\s+([A-Za-z一-鿿]+)", line, re.IGNORECASE)
        if not m or m.group(1).lower() in ("the", "a", "an"):
            _warn(warnings, "ears",
                  f"requirements.md 第 {idx} 行 SHALL 后缺动词。")


# -------------------------------------------------------------------------

def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="spec_lint.py", description="lint a specode spec directory")
    parser.add_argument("--spec", required=True, help="spec 目录绝对路径")
    args = parser.parse_args(argv)

    spec_dir = Path(args.spec).expanduser().resolve()
    if not spec_dir.is_dir():
        sys.stderr.write(f"spec 目录不存在：{spec_dir}\n")
        return 0  # lint 不阻断；返回 0

    warnings: list[str] = []
    rule_log_entries(spec_dir, warnings)
    rule_ears_shall(spec_dir, warnings)
    rule_template_structure(spec_dir, warnings)

    if not warnings:
        sys.stdout.write("spec_lint: 0 warnings.\n")
        return 0
    sys.stdout.write(f"spec_lint: {len(warnings)} warning(s).\n")
    for w in warnings:
        sys.stdout.write(w + "\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
