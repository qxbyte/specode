#!/usr/bin/env python3
'''scripts/spec_session.py — 薄 launcher，把所有调用转给 spec_session.cli.main()。

文件名 `spec_session.py` 保留作为外部 API surface：hooks/hooks.json、
commands/*.md、tests/conftest.py:run_script 都按此路径调用。实现拆到同目录的
`spec_session/` 包内（_io / _selectors / _reminders / _business / _hooks /
_catalog / cli），launcher 只做三件事：

  1. Windows utf-8 stdout/stderr reconfigure（让 emoji / 中文 emit 不再
     UnicodeEncodeError 被 _safe_hook 吞掉）
  2. sys.path 注入 scripts/，让包内 spec_log import 可用
  3. import spec_session.cli.main 并调用

Python 的 import system 在同一 path entry 下 package > module，所以
`scripts/spec_session.py` 与 `scripts/spec_session/` 共存安全：launcher 作为
脚本被 exec、`import spec_session` 解析为 package。

stdlib-only。
'''
from __future__ import annotations

import contextlib
import sys
from pathlib import Path

# Windows 子进程 pipe stdout 的 encoding 会 fallback 到 locale（中文 Windows 是
# cp936/gbk），无法编码 emoji 等非 BMP 字符 → emit 时 UnicodeEncodeError 被
# _safe_hook 吞掉 → 主代理收不到任何 hook 注入。强制 utf-8 + errors=replace
# 兜底。stderr 同步以保证异常 trace 可读。
with contextlib.suppress(Exception):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
with contextlib.suppress(Exception):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from spec_session.cli import main  # noqa: E402


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
