#!/usr/bin/env python3
'''scripts/task_swarm.py — 薄 launcher，把所有调用转给 task_swarm.cli.main()。

文件名 `task_swarm.py` 保留作为外部 API surface：commands/task-swarm.md +
spec_session/_hooks.py:_run_task_swarm_plan 都按此路径调用。实现拆到同目录的
`task_swarm/` 包内（_state / _pipeline / _schedule / _outbox / _prompt / _writeback / cli），
launcher 只做两件事：

  1. sys.path 注入 scripts/，让包内 spec_log import 可用
  2. import task_swarm.cli.main 并调用

同名文件 + 同名目录共存安全：Python FileFinder 在同一 path entry 下
package > module，launcher 自己被 exec、不走 import 系统。

stdlib-only。
'''
from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from task_swarm.cli import main  # noqa: E402


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
