#!/usr/bin/env python3
"""knowledge.py — specode 项目级知识库 (knowledge-base/) 索引维护 (stdlib-only)。

verbs:
  ensure-gitignore --project-root <abs>   确保 <root>/.gitignore 含 `knowledge-base/`
                                          （无 .git 且无 .gitignore 时跳过，不建 stray）
  memory-rebuild   --kb <dir>             由 <dir>/**/*.md frontmatter 重建 <dir>/MEMORY.md
  memory-validate  --kb <dir>             校验 MEMORY 与磁盘文档是否一致（漂移检测）
  copy-to          --kb <src> --dest <abs>  把 cases/+navigation/ 复制到 dest 并重建其
                                          MEMORY（一步 dual-landing；dest 绝对路径直写不拼接）

knowledge-base/ 是「定位用，非事实用」的指针库；MEMORY.md 是其轻量索引，
单一事实源是各文档的 frontmatter——memory-rebuild 永远由 frontmatter 全量重建。

exit codes: 0 ok / 1 用法或参数错 / 2 校验发现漂移（memory-validate）
"""
from __future__ import annotations

import argparse
import os
import shutil
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


# --- frontmatter helpers (mirror resolve_root.py, stdlib-only) ---

def _split_frontmatter(text: str):
    if not text.startswith("---"):
        return None
    lines = text.split("\n")
    if lines[0].strip() != "---":
        return None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return lines[1:i]
    return None


def _fm_get(fm_lines, key: str):
    prefix = key + ":"
    for line in fm_lines:
        if line.startswith(prefix):
            val = line[len(prefix):].strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in {'"', "'"}:
                val = val[1:-1]
            return val
    return None


def _fm_get_tags(fm_lines):
    raw = _fm_get(fm_lines, "tags")
    if not raw:
        return []
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1]
    return [t.strip() for t in raw.split(",") if t.strip()]


def _iter_docs(kb: Path):
    for p in sorted(kb.rglob("*.md")):
        if p.name == "MEMORY.md":
            continue
        yield p


def _parse_doc(p: Path, kb: Path):
    """Return a row dict or None if malformed (missing 标题/类型)."""
    fm = _split_frontmatter(p.read_text(encoding="utf-8"))
    if fm is None:
        return None
    title = _fm_get(fm, "标题")
    ktype = _fm_get(fm, "类型")
    if not title or not ktype:
        return None
    return {
        "标题": title,
        "类型": ktype,
        "描述": _fm_get(fm, "描述") or "",
        "来源": _fm_get(fm, "来源") or "",
        "路径": p.relative_to(kb).as_posix(),
        "tags": ",".join(_fm_get_tags(fm)),
    }


_COLS = ["标题", "类型", "描述", "来源", "路径", "tags"]


def _sanitize_cell(val: str) -> str:
    """Replace characters that would break the markdown table."""
    return val.replace("\n", " ").replace("\r", " ").replace("|", "/").strip()


def _render_memory(rows) -> str:
    head = "# Knowledge MEMORY（本项目知识点索引）\n\n"
    note = "> 由 `knowledge.py memory-rebuild` 从各知识点 frontmatter 自动重建，请勿手改。\n\n"
    header = "| " + " | ".join(_COLS) + " |\n"
    sep = "|" + "|".join(["---"] * len(_COLS)) + "|\n"
    body = "".join(
        "| " + " | ".join(_sanitize_cell(r[c]) for c in _COLS) + " |\n" for r in rows
    )
    return head + note + header + sep + body


def _rebuild_memory(kb: Path):
    """Rebuild kb/MEMORY.md from doc frontmatter. Returns (n_rows, skipped_paths)."""
    rows, skipped = [], []
    for p in _iter_docs(kb):
        row = _parse_doc(p, kb)
        (rows if row else skipped).append(row if row else p)
    rows.sort(key=lambda r: (r["类型"], r["路径"]))
    _atomic_write_text(kb / "MEMORY.md", _render_memory(rows))
    return len(rows), skipped


def cmd_memory_rebuild(args) -> int:
    kb = Path(args.kb)
    if not kb.is_dir():
        sys.stderr.write(f"knowledge: knowledge-base 目录不存在：{kb}\n")
        return 1
    n, skipped = _rebuild_memory(kb)
    for p in skipped:
        sys.stderr.write(f"knowledge: 跳过缺 标题/类型 的文档：{p}\n")
    sys.stdout.write(f"knowledge: 已重建 MEMORY（{n} 条，跳过 {len(skipped)}）\n")
    return 0


def cmd_copy_to(args) -> int:
    """F4: one-step dual-landing — copy cases/ + navigation/ to an absolute
    dest dir, then rebuild that dir's MEMORY. 直写不拼接：dest 即写入目录。"""
    src = Path(args.kb)
    if not src.is_dir():
        sys.stderr.write(f"knowledge: 源 knowledge-base 不存在：{src}\n")
        return 1
    dest = Path(args.dest)
    if not dest.is_absolute():
        sys.stderr.write(f"knowledge: 目标必须是绝对路径（直写不拼接）：{dest}\n")
        return 1
    dest.mkdir(parents=True, exist_ok=True)
    copied = []
    for subname in ("cases", "navigation"):
        s = src / subname
        if s.is_dir():
            shutil.copytree(s, dest / subname, dirs_exist_ok=True)
            copied.append(subname)
    n, _ = _rebuild_memory(dest)
    sys.stdout.write(
        f"knowledge: 已复制 {('/'.join(copied)) or '(无文档)'} 到 {dest} "
        f"并重建 MEMORY（{n} 条）\n")
    return 0


def cmd_ensure_gitignore(args) -> int:
    root = Path(args.project_root)
    if not root.is_dir():
        sys.stderr.write(f"knowledge: project-root 目录不存在：{root}\n")
        return 1
    gi = root / ".gitignore"
    if not gi.exists() and not (root / ".git").exists():
        # F3: 非 git 项目且无既有 .gitignore → 不创建 stray 文件（无 git 时
        # .gitignore 也不生效；knowledge-base 本就本地私有，无需 ignore）。
        sys.stdout.write(
            f"knowledge: {root} 无 .git 且无 .gitignore，跳过"
            f"（knowledge-base 本地私有，无需 ignore）\n")
        return 0
    lines = gi.read_text(encoding="utf-8").splitlines() if gi.exists() else []
    if GITIGNORE_ENTRY in (ln.strip() for ln in lines):
        sys.stdout.write(f"knowledge: .gitignore 已含 {GITIGNORE_ENTRY}\n")
        return 0
    new_text = ("\n".join(lines) + "\n" if lines else "") + GITIGNORE_ENTRY + "\n"
    _atomic_write_text(gi, new_text)
    sys.stdout.write(f"knowledge: 已在 {gi} 追加 {GITIGNORE_ENTRY}\n")
    return 0


def _memory_paths(kb: Path):
    """Parse the 路径 column out of an existing MEMORY.md (empty if none)."""
    mem = kb / "MEMORY.md"
    if not mem.exists():
        return set()
    paths = set()
    for line in mem.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| ") or "| 标题 |" in line:
            continue
        # Precise separator row: only pipes, dashes, and spaces
        if set(line.strip()) <= {"|", "-", " "}:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == len(_COLS):
            paths.add(cells[_COLS.index("路径")])
    return paths


def cmd_memory_validate(args) -> int:
    kb = Path(args.kb)
    if not kb.is_dir():
        sys.stderr.write(f"knowledge: knowledge-base 目录不存在：{kb}\n")
        return 1
    indexed = _memory_paths(kb)
    on_disk = {p.relative_to(kb).as_posix() for p in _iter_docs(kb)
               if _parse_doc(p, kb) is not None}
    dangling = sorted(indexed - on_disk)
    unindexed = sorted(on_disk - indexed)
    for d in dangling:
        sys.stdout.write(f"⚠ 悬空索引（MEMORY 有、磁盘无）：{d}\n")
    for u in unindexed:
        sys.stdout.write(f"⚠ 未索引文档（磁盘有、MEMORY 无）：{u}\n")
    if dangling or unindexed:
        sys.stdout.write("knowledge: MEMORY 漂移，建议 `memory-rebuild`。\n")
        return 2
    sys.stdout.write("✓ knowledge: MEMORY 与磁盘一致\n")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="knowledge.py")
    sub = parser.add_subparsers(dest="cmd", required=True)

    eg = sub.add_parser("ensure-gitignore")
    eg.add_argument("--project-root", required=True)
    eg.set_defaults(func=cmd_ensure_gitignore)

    mr = sub.add_parser("memory-rebuild")
    mr.add_argument("--kb", required=True)
    mr.set_defaults(func=cmd_memory_rebuild)

    mv = sub.add_parser("memory-validate")
    mv.add_argument("--kb", required=True)
    mv.set_defaults(func=cmd_memory_validate)

    ct = sub.add_parser("copy-to",
                        help="copy cases/+navigation/ to an absolute dest dir "
                             "and rebuild that dir's MEMORY (one-step dual-landing)")
    ct.add_argument("--kb", required=True)
    ct.add_argument("--dest", required=True)
    ct.set_defaults(func=cmd_copy_to)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
