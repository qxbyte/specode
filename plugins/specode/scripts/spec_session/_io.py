"""spec_session package 内部实现：原子写 / session+spec config 读写 / 锁工具 / 共享常量。

不要直接运行本文件。它通过 spec_session.py 导出，spec_status.py 也通过
spec_session.py 间接消费这里的 read_session / read_spec_config /
_session_short / _is_lock_stale。

stdlib-only。
"""
from __future__ import annotations

import contextlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Optional


# -------------------------------------------------------------------------
# 共享常量
# -------------------------------------------------------------------------

STALE_LOCK_SECONDS = 30 * 60  # 30 分钟无 heartbeat 视为 stale

VALID_PHASES = {
    "intake",
    "requirements",
    "bugfix",
    "design",
    "tasks",
    "implementation",
    "acceptance",
    "iteration",
}


# -------------------------------------------------------------------------
# 时间工具
# -------------------------------------------------------------------------

def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _parse_iso(s: Optional[str]) -> Optional[float]:
    if not s:
        return None
    try:
        # 朴素 ISO8601-UTC 解析
        if s.endswith("Z"):
            s2 = s[:-1] + "+00:00"
        else:
            s2 = s
        import datetime as _dt
        return _dt.datetime.fromisoformat(s2).timestamp()
    except Exception:
        return None


# -------------------------------------------------------------------------
# 原子写
# -------------------------------------------------------------------------

def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
            fh.flush()
            try:
                os.fsync(fh.fileno())
            except OSError:
                pass
        os.replace(tmp, path)
        try:
            dir_fd = os.open(str(path.parent), os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            except OSError:
                pass
            finally:
                os.close(dir_fd)
        except OSError:
            pass
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def _atomic_write_json(path: Path, payload: Any) -> None:
    _atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))


# -------------------------------------------------------------------------
# 数据层
# -------------------------------------------------------------------------

def _sessions_dir() -> Path:
    return Path.home() / ".specode" / "sessions"


def session_file_path(session_id: str) -> Path:
    return _sessions_dir() / f"{session_id}.json"


def read_session(session_id: str) -> Optional[dict]:
    p = session_file_path(session_id)
    if not p.exists():
        return None
    try:
        with p.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            # 兼容老 sessions/<id>.json：字段名曾叫 claude_session_id，迁移到 session_id
            if "session_id" not in data and "claude_session_id" in data:
                data["session_id"] = data["claude_session_id"]
            return data
    except Exception:
        return None
    return None


def write_session_atomic(session_id: str, data: dict) -> None:
    _atomic_write_json(session_file_path(session_id), data)


def read_spec_config(spec_dir: Path) -> Optional[dict]:
    p = spec_dir / ".config.json"
    if not p.exists():
        return None
    try:
        with p.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return data
    except Exception:
        return None
    return None


def write_spec_config_atomic(spec_dir: Path, data: dict) -> None:
    _atomic_write_json(spec_dir / ".config.json", data)


# -------------------------------------------------------------------------
# 锁工具
# -------------------------------------------------------------------------

def _is_lock_stale(lock: dict) -> bool:
    last = _parse_iso(lock.get("last_heartbeat_at") or lock.get("acquired_at"))
    if last is None:
        return True
    return (time.time() - last) > STALE_LOCK_SECONDS


def _session_short(sid: Optional[str]) -> str:
    if not sid:
        return "????????"
    return sid[:8]


# -------------------------------------------------------------------------
# CLI 共享辅助
# -------------------------------------------------------------------------

def _ensure_spec_dir(spec_dir_str: str) -> Path:
    p = Path(spec_dir_str).expanduser().resolve()
    if not p.exists() or not p.is_dir():
        raise FileNotFoundError(f"spec_dir 不存在：{p}")
    return p


def _emit_json(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
