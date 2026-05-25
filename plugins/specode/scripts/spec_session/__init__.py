'''spec_session package public surface.

外部依赖入口：
  - scripts/spec_session.py launcher 调 `spec_session.cli.main()`
  - scripts/spec_status.py 用 `from spec_session import read_session,
    read_spec_config, _session_short, _is_lock_stale`（0.10.22 拆分前
    这 4 个符号在 scripts/spec_session.py 文件 module 级；现在它们的
    canonical 位置是 spec_session._io，本文件 re-export 保持外部 import
    路径不变，避免改 spec_status.py）。

stdlib-only。
'''
from __future__ import annotations

from spec_session._io import (  # noqa: F401
    _is_lock_stale,
    _session_short,
    read_session,
    read_spec_config,
)

__all__ = [
    "_is_lock_stale",
    "_session_short",
    "read_session",
    "read_spec_config",
]
