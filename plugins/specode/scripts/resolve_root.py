#!/usr/bin/env python3
"""resolve_root.py — specode lite 的 specsRoot 解析与持久化（stdlib-only）。

verbs:
  get-root  [--root P]   解析 specsRoot：--root > env SPECODE_ROOT > config.specsRoot
  set-root  --root P     绝对路径，持久化到 ~/.config/specode/config.json.specsRoot
  list-specs [--root P]  列出 root 下含 requirements.md 的子目录名（每行一个 slug）

exit codes: 0 ok / 1 用法或参数错 / 3 未配置 specsRoot
"""
from __future__ import annotations

import argparse
import json
import os
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

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
