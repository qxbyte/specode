#!/usr/bin/env python3
"""spec_hooks.py — specode lite 的唯一 hook：SessionStart 注入纪律。

读 stdin（容忍非 TTY / 空），emit additionalContext JSON 到 stdout，exit 0。
任何异常都吞掉并 exit 0（advisory，绝不阻断）。
"""
from __future__ import annotations

import json
import sys

DISCIPLINE = (
    "specode（spec-mode 轻量工作流）可用。仅在用户输入 `/spec`、`/spec continue <slug>`、"
    "`/spec list` 或显式要求用 spec 模式时激活；否则按普通对话处理。激活后遵循 "
    "specode SKILL.md：① 在 requirements/design/执行/验收各 phase 优先调对应 superpowers "
    "skill（缺席则 specode-native 降级）；② 3 份固定产物 requirements.md / design.md / "
    "implementation-log.md 永远以固定文件名落在 <specsRoot>/<slug>/；③ design 完成后用 "
    "AskUserQuestion 呈现「执行方式」selector（task-swarm / superpowers / specode 自执行）。"
)


def main() -> int:
    try:
        try:
            sys.stdin.read()
        except Exception:
            pass
        out = {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": DISCIPLINE,
            }
        }
        sys.stdout.write(json.dumps(out, ensure_ascii=False))
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
