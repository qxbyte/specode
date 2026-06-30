#!/usr/bin/env python3
"""knowledge.py — specode 项目级知识库 (knowledge-base/) 索引维护 (stdlib-only)。

verbs:
  ensure-gitignore --project-root <abs>   确保 <root>/.gitignore 含 `knowledge-base/`
  memory-rebuild   --kb <dir>             由 <dir>/**/*.md frontmatter 重建 <dir>/MEMORY.md
  memory-validate  --kb <dir>             校验 MEMORY 与磁盘文档是否一致（漂移检测）

knowledge-base/ 是「定位用，非事实用」的指针库；MEMORY.md 是其轻量索引，
单一事实源是各文档的 frontmatter——memory-rebuild 永远由 frontmatter 全量重建。

exit codes: 0 ok / 1 用法或参数错 / 2 校验发现漂移（memory-validate）
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

GITIGNORE_ENTRY = "knowledge-base/"


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            fd = -1
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if fd >= 0:
            try:
                os.close(fd)
            except OSError:
                pass
        if os.path.exists(tmp):
            os.remove(tmp)


def cmd_ensure_gitignore(args) -> int:
    root = Path(args.project_root)
    if not root.is_dir():
        sys.stderr.write(f"knowledge: project-root 目录不存在：{root}\n")
        return 1
    gi = root / ".gitignore"
    lines = gi.read_text(encoding="utf-8").splitlines() if gi.exists() else []
    if GITIGNORE_ENTRY in (ln.strip() for ln in lines):
        sys.stdout.write(f"knowledge: .gitignore 已含 {GITIGNORE_ENTRY}\n")
        return 0
    new_text = ("\n".join(lines) + "\n" if lines else "") + GITIGNORE_ENTRY + "\n"
    _atomic_write_text(gi, new_text)
    sys.stdout.write(f"knowledge: 已在 {gi} 追加 {GITIGNORE_ENTRY}\n")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="knowledge.py")
    sub = parser.add_subparsers(dest="cmd", required=True)

    eg = sub.add_parser("ensure-gitignore")
    eg.add_argument("--project-root", required=True)
    eg.set_defaults(func=cmd_ensure_gitignore)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
