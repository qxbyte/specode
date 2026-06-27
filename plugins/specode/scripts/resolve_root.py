#!/usr/bin/env python3
"""resolve_root.py — specode lite 的 specsRoot 解析与持久化（stdlib-only）。

verbs:
  get-root  [--root P]   解析 specsRoot：--root > env SPECODE_ROOT > config.specsRoot
  set-root  --root P     绝对路径，持久化到 ~/.config/specode/config.json.specsRoot
  list-specs [--root P]  列出 root 下含 requirements.md 的子目录名（每行一个 slug）

  resolve-project-root [--cwd P]   计算 project_root 默认值（git toplevel || cwd），供
                                   host agent AskUserQuestion 确认用
  write-project-root --spec P --root A   把 project_root 写进 spec 的 requirements.md
                                   frontmatter（单一写入口；校验绝对路径/目录存在/挂载）
  read-project-root  --spec P      从 spec 的 requirements.md frontmatter 读 project_root
                                   （所有下游唯一读入口；缺字段 exit 3 / 值非法 exit 4）

project_root 是 spec（在 specsRoot 下）与其知识落地项目之间的唯一 join key，**只存一处**
——该 spec 的 requirements.md YAML frontmatter。write/read 是其唯一写入口与读入口，杜绝各
环节各自用 cwd/workdir 推导导致的分裂。

exit codes: 0 ok / 1 用法或参数错 / 3 未配置（specsRoot 未配置 / project_root 字段缺失）
            / 4 project_root 值非法（非绝对 / 目录不存在 / 外置盘未挂载）
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def _config_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "specode"


def _config_path() -> Path:
    return _config_dir() / "config.json"


def _read_config() -> dict:
    p = _config_path()
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (ValueError, OSError):
        return {}


def _atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            fd = -1  # fdopen 接管 fd
            json.dump(data, f, ensure_ascii=False, indent=2)
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


def _resolve(root_flag):
    if root_flag:
        return root_flag
    env = os.environ.get("SPECODE_ROOT")
    if env:
        return env
    cfg = _read_config()
    # specsRoot 是当前键；obsidianRoot 是 1.0.0 前的旧键，读端兜底让老用户升级即用、不必重设。
    val = cfg.get("specsRoot") or cfg.get("obsidianRoot")
    return val or None


def cmd_get_root(args) -> int:
    root = _resolve(args.root)
    if not root:
        sys.stderr.write(
            "specode: specsRoot 未配置。请先用 set-root 设置，或设 env SPECODE_ROOT。\n")
        return 3
    sys.stdout.write(root + "\n")
    return 0


def cmd_set_root(args) -> int:
    p = args.root
    if not os.path.isabs(p):
        sys.stderr.write(f"specode: 根目录必须是绝对路径，收到：{p}\n")
        return 1
    cfg = _read_config()
    cfg["specsRoot"] = p
    _atomic_write_json(_config_path(), cfg)
    sys.stdout.write(f"specode: 已设 specsRoot = {p}\n")
    return 0


def cmd_list_specs(args) -> int:
    root = _resolve(args.root)
    if not root:
        sys.stderr.write("specode: specsRoot 未配置。\n")
        return 3
    base = Path(root)
    if not base.is_dir():
        return 0  # 配置了但目录还不存在 → 空列表
    for child in sorted(base.iterdir()):
        if child.is_dir() and (child / "requirements.md").exists():
            sys.stdout.write(child.name + "\n")
    return 0


# ---------- project_root: single source of truth (FIX-1) ----------


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            fd = -1  # fdopen 接管 fd
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


def _requirements_path(spec: str) -> Path:
    """Resolve the requirements.md for a spec given a dir or a file path."""
    p = Path(spec)
    if p.is_dir():
        return p / "requirements.md"
    return p


def _split_frontmatter(text: str):
    """Return ``(fm_lines | None, body)``.

    fm_lines is the list of YAML frontmatter lines between the leading
    ``---`` and its terminator; ``None`` when the file has no (well-formed)
    frontmatter. body is everything after the closing ``---``.
    """
    if not text.startswith("---"):
        return None, text
    lines = text.split("\n")
    if lines[0].strip() != "---":
        return None, text
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            fm = lines[1:i]
            body = "\n".join(lines[i + 1 :])
            return fm, body
    return None, text  # unterminated frontmatter → treat as none


def _fm_get(fm_lines: list[str], key: str):
    prefix = key + ":"
    for line in fm_lines:
        if line.startswith(prefix):
            val = line[len(prefix) :].strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in {'"', "'"}:
                val = val[1:-1]
            return val
    return None


def _fm_set(fm_lines: list[str], key: str, value: str) -> list[str]:
    prefix = key + ":"
    out: list[str] = []
    found = False
    for line in fm_lines:
        if line.startswith(prefix):
            out.append(f"{key}: {value}")
            found = True
        else:
            out.append(line)
    if not found:
        out.append(f"{key}: {value}")
    return out


def _validate_root(p: str) -> tuple[bool, str]:
    """Return ``(ok, message)`` for a candidate project_root absolute path.

    Checks: absolute · (if under /Volumes) the mount point exists · the
    directory exists. No silent fallback — callers map failure to their own
    exit code (write → 1, read → 4).
    """
    if not os.path.isabs(p):
        return False, f"project_root 必须是绝对路径，收到：{p}"
    if p.startswith("/Volumes/"):
        parts = p.split("/")
        if len(parts) >= 3 and parts[2]:
            mount = "/Volumes/" + parts[2]
            if not os.path.isdir(mount):
                return False, f"外置盘未挂载：{mount}（拒绝写到/读自未挂载路径）"
    if not os.path.isdir(p):
        return False, f"project_root 目录不存在：{p}"
    return True, ""


def cmd_resolve_project_root(args) -> int:
    cwd = args.cwd or os.getcwd()
    try:
        out = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            sys.stdout.write(out.stdout.strip() + "\n")
            return 0
    except (OSError, subprocess.SubprocessError):
        pass
    sys.stdout.write(os.path.abspath(cwd) + "\n")
    return 0


def cmd_write_project_root(args) -> int:
    root = args.root
    ok, msg = _validate_root(root)
    if not ok:
        sys.stderr.write(f"specode: {msg}\n")
        return 1
    req = _requirements_path(args.spec)
    if not req.is_file():
        # 允许在尚无 requirements.md 时由上层先创建；这里要求文件已存在以免写错位置
        sys.stderr.write(f"specode: 找不到 requirements.md：{req}\n")
        return 1
    text = req.read_text(encoding="utf-8")
    fm_lines, body = _split_frontmatter(text)
    if fm_lines is None:
        new_text = "---\n" + f"project_root: {root}" + "\n---\n" + text
    else:
        fm_lines = _fm_set(fm_lines, "project_root", root)
        new_text = "---\n" + "\n".join(fm_lines) + "\n---\n" + body
    _atomic_write_text(req, new_text)
    sys.stdout.write(f"specode: 已写 project_root = {root} 到 {req}\n")
    return 0


def cmd_read_project_root(args) -> int:
    req = _requirements_path(args.spec)
    if not req.is_file():
        sys.stderr.write(
            f"specode: 找不到 requirements.md：{req}（无法解析 project_root）\n"
        )
        return 3
    text = req.read_text(encoding="utf-8")
    fm_lines, _ = _split_frontmatter(text)
    value = _fm_get(fm_lines, "project_root") if fm_lines is not None else None
    if not value:
        sys.stderr.write(
            "specode: requirements.md 缺 project_root frontmatter；"
            "specode v2.0 之前生成的 spec 需先补字段后重试。\n"
        )
        return 3
    ok, msg = _validate_root(value)
    if not ok:
        sys.stderr.write(f"specode: {msg}\n")
        return 4
    sys.stdout.write(value + "\n")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="resolve_root.py")
    sub = parser.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("get-root")
    g.add_argument("--root")
    g.set_defaults(func=cmd_get_root)

    s = sub.add_parser("set-root")
    s.add_argument("--root", required=True)
    s.set_defaults(func=cmd_set_root)

    lp = sub.add_parser("list-specs")
    lp.add_argument("--root")
    lp.set_defaults(func=cmd_list_specs)

    rp = sub.add_parser("resolve-project-root")
    rp.add_argument("--cwd")
    rp.set_defaults(func=cmd_resolve_project_root)

    wp = sub.add_parser("write-project-root")
    wp.add_argument("--spec", required=True)
    wp.add_argument("--root", required=True)
    wp.set_defaults(func=cmd_write_project_root)

    rdp = sub.add_parser("read-project-root")
    rdp.add_argument("--spec", required=True)
    rdp.set_defaults(func=cmd_read_project_root)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
