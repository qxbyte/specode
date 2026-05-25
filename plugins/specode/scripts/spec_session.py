#!/usr/bin/env python3
'''spec_session.py — specode 会话 / 锁 / hook 注入统一入口（详见 SKILL.md + references/）。

业务子命令（被 SKILL.md 引导主会话调用；都接 --session）：
  acquire / release / heartbeat / verify-lock / phase-transition
  load / continue / end / status / read-session / list-specs / set-project-root

hook 子命令（仅由 hooks/hooks.json 调用；全部 exit 0，仅注入提示；唯一例外：
PreToolUse 对 task-swarm 受控路径与 tasks.md 直写的 exit 2 强阻断）：
  on-session-start / on-user-prompt / on-stop / on-session-end
  on-task-completed / on-heartbeat-quiet / on-pre-tool-use
  on-log-pre-tool-use / on-log-post-tool-use

强制写入语义：
  - 任何修改 sessions/<id>.json 或 <spec-dir>/.config.json 的命令必须 tempfile +
    os.replace + fsync。
  - 写失败 → 整命令视失败、回滚已变更的另一份文件、exit 1。

文件结构（0.10.22 拆分；本文件仅作薄入口）：
  _ss_io.py        原子写 / session+spec config 读写 / 锁工具 / 共享常量
  _ss_selectors.py SELECTOR_PROMPTS 字典 + _fill_selector
  _ss_reminders.py reminder 模板字符串 + help 文本渲染
  _ss_business.py  所有 cmd_* 业务命令
  _ss_hooks.py     所有 hook_on_* + safe wrapper + task-swarm plan 辅助

stdlib-only。
'''
from __future__ import annotations

import argparse
import contextlib
import sys
from pathlib import Path
from typing import Optional

# Windows 子进程 pipe stdout 的 encoding 会 fallback 到 locale（中文 Windows 是
# cp936/gbk），无法编码 emoji 等非 BMP 字符 → emit 时 UnicodeEncodeError 被
# _safe_hook 吞掉 → 主代理收不到任何 hook 注入。强制 utf-8 + errors=replace
# 兜底。stderr 同步以保证异常 trace 可读。
with contextlib.suppress(Exception):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
with contextlib.suppress(Exception):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]

THIS_DIR = Path(__file__).resolve().parent

# sibling 模块通过同目录 import；spec_log 同款 sys.path 注入。
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

try:
    from spec_log import write_event as _log_event  # type: ignore
except Exception:
    def _log_event(event: str, payload: Optional[dict] = None,
                   session_id: Optional[str] = None) -> None:
        return None

# 业务命令
from _ss_business import (  # noqa: E402
    cmd_acquire,
    cmd_continue,
    cmd_end,
    cmd_heartbeat,
    cmd_list_specs,
    cmd_load,
    cmd_phase_transition,
    cmd_read_session,
    cmd_release,
    cmd_set_project_root,
    cmd_status,
    cmd_verify_lock,
)

# Hook handlers
from _ss_hooks import (  # noqa: E402
    hook_on_heartbeat_quiet,
    hook_on_log_post_tool_use,
    hook_on_log_pre_tool_use,
    hook_on_pre_tool_use,
    hook_on_session_end,
    hook_on_session_start,
    hook_on_stop,
    hook_on_task_completed,
    hook_on_user_prompt,
)
from _ss_catalog import hook_on_user_prompt_catalog  # noqa: E402

# 为 spec_status.py 维持的向后兼容 re-export
# （spec_status.py:25 直接 `from spec_session import read_session, read_spec_config,
#  _session_short, _is_lock_stale`；0.10.22 拆分后这 4 个符号搬到了 _ss_io，
#  在这里 re-export 保持外部 import 路径不变。）
from _ss_io import (  # noqa: E402, F401
    _is_lock_stale,
    _session_short,
    read_session,
    read_spec_config,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="spec_session.py", description="specode session / lock / hook entry")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("acquire")
    p.add_argument("--spec", required=True)
    p.add_argument("--session", required=True)
    p.add_argument("--force", action="store_true")

    p = sub.add_parser("release")
    p.add_argument("--spec", required=True)
    p.add_argument("--session", required=True)

    p = sub.add_parser("heartbeat")
    p.add_argument("--spec", required=True)
    p.add_argument("--session", required=True)

    p = sub.add_parser("verify-lock")
    p.add_argument("--spec", required=True)
    p.add_argument("--session", required=True)

    p = sub.add_parser("phase-transition")
    p.add_argument("--spec", required=True)
    p.add_argument("--session", required=True)
    p.add_argument("--from", dest="frm", required=True)
    p.add_argument("--to", required=True)

    p = sub.add_parser("load")
    p.add_argument("--spec", required=True)

    p = sub.add_parser("continue")
    p.add_argument("--spec", required=True)
    p.add_argument("--session", required=True)
    p.add_argument("--force", action="store_true")
    p.add_argument("--readonly", action="store_true")

    p = sub.add_parser("end")
    p.add_argument("--session", required=True)

    p = sub.add_parser("set-project-root")
    p.add_argument("--spec", required=True, help="spec 目录")
    p.add_argument("--session", required=True, help="必须是 lock holder")
    p.add_argument("--root", required=True, help="项目实现根目录（绝对路径，不存在则 mkdir）")

    p = sub.add_parser("status")
    p.add_argument("--session", required=True)

    p = sub.add_parser("read-session")
    p.add_argument("--session", required=True)

    p = sub.add_parser("list-specs")
    p.add_argument("--root", default=None,
                   help="doc root override；缺省按三层 resolve_doc_root")

    # hook 子命令（无必需参数；从 stdin 拿 session_id）
    for name in (
        "on-session-start",
        "on-user-prompt",
        "on-user-prompt-catalog",
        "on-stop",
        "on-session-end",
        "on-task-completed",
        "on-heartbeat-quiet",
        "on-pre-tool-use",
        "on-log-pre-tool-use",
        "on-log-post-tool-use",
    ):
        ph = sub.add_parser(name)
        ph.add_argument("--session-override", default=None,
                        help="测试用：覆盖 stdin payload 中的 session_id")
        if name == "on-heartbeat-quiet":
            ph.add_argument("--quiet", action="store_true")

    return parser


COMMANDS = {
    "acquire": cmd_acquire,
    "release": cmd_release,
    "heartbeat": cmd_heartbeat,
    "verify-lock": cmd_verify_lock,
    "phase-transition": cmd_phase_transition,
    "load": cmd_load,
    "continue": cmd_continue,
    "end": cmd_end,
    "set-project-root": cmd_set_project_root,
    "status": cmd_status,
    "read-session": cmd_read_session,
    "list-specs": cmd_list_specs,
    "on-session-start": hook_on_session_start,
    "on-user-prompt": hook_on_user_prompt,
    "on-user-prompt-catalog": hook_on_user_prompt_catalog,
    "on-stop": hook_on_stop,
    "on-session-end": hook_on_session_end,
    "on-task-completed": hook_on_task_completed,
    "on-heartbeat-quiet": hook_on_heartbeat_quiet,
    "on-pre-tool-use": hook_on_pre_tool_use,
    "on-log-pre-tool-use": hook_on_log_pre_tool_use,
    "on-log-post-tool-use": hook_on_log_post_tool_use,
}


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    fn = COMMANDS.get(args.cmd)
    if fn is None:
        parser.print_help()
        return 1
    # log cli 调用（0.10.0+；只记业务命令，hook 调用由 _safe_hook 已记）
    if not args.cmd.startswith("on-"):
        with contextlib.suppress(Exception):
            session_id = getattr(args, "session", None) or getattr(args, "session_override", None)
            _log_event("cli_call", {
                "script": "spec_session.py",
                "cmd": args.cmd,
                "spec": getattr(args, "spec", None),
                "phase_from": getattr(args, "frm", None),
                "phase_to": getattr(args, "to", None),
                "force": getattr(args, "force", False),
                "readonly": getattr(args, "readonly", False),
            }, session_id=session_id)
    rc = fn(args) or 0
    if not args.cmd.startswith("on-"):
        with contextlib.suppress(Exception):
            session_id = getattr(args, "session", None) or getattr(args, "session_override", None)
            _log_event("cli_exit", {"script": "spec_session.py", "cmd": args.cmd, "exit_code": rc}, session_id=session_id)
    return rc


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
