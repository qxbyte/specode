'''spec_session package 内部实现：所有 hook 子命令（hook_on_*）+ safe wrapper。

hook 子命令仅由 hooks/hooks.json 调用；全部 exit 0、任何异常通过 @_safe_hook
内部 catch（PreToolUse 对 AskUserQuestion selector 参数 hallucinate 的 exit 2
校验除外，见 hook_on_pre_tool_use）。

不要直接运行本文件。stdlib-only。
'''
from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Optional

from spec_session._io import (
    _now_iso,
    _session_short,
    read_session,
    read_spec_config,
    write_session_atomic,
    write_spec_config_atomic,
)
from spec_session._reminders import (
    CODE_DOC_SYNC_STOP,
    DOC_PRIORITY_REMINDER_ACTIVE,
    DOC_PRIORITY_REMINDER_READONLY,
    SPEC_MODE_CONTINUE_REMINDER,
    SPEC_MODE_ENDED_REMINDER,
    SPEC_MODE_READONLY_REMINDER,
    STATUS_FOOTER_TEMPLATE,
    _render_help_text,
    _wrap_help_fastpath,
)
from spec_session._selectors import _fill_selector
from spec_session._template_skeleton import (
    TEMPLATE_OUTLINES,
    format_outline_notice,
)
from spec_session._selector_skeleton import (
    SELECTOR_OUTLINES,
    format_selector_cheatsheet,
    validate_ask_user_question_input,
)


_THIS_DIR = Path(__file__).resolve().parents[1]  # = scripts/（本文件在 scripts/spec_session/）

# spec_log 兜底 import（sibling 同目录脚本；scripts/spec_session.py launcher 已注入 sys.path）
try:
    from spec_log import write_event as _log_event  # type: ignore
except Exception:
    def _log_event(event: str, payload: Optional[dict] = None,
                   session_id: Optional[str] = None) -> None:
        return None


def _read_stdin_payload() -> dict:
    """读 hook stdin payload。**不要 block**：如 stdin 不是管道，立刻返回 {}。"""
    data: dict = {}
    try:
        if sys.stdin is None:
            return data
        # 判断是否 tty/无管道
        try:
            isatty = sys.stdin.isatty()
        except Exception:
            isatty = True
        if isatty:
            return data
        raw = sys.stdin.read()
        if not raw:
            return data
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict):
                return obj
        except Exception:
            return data
    except Exception:
        return data
    return data


def _emit_hook_additional_context(text: str, hook_event_name: str = "UserPromptSubmit") -> None:
    """按宿主 hook 协议 emit additionalContext JSON。"""
    payload = {
        "hookSpecificOutput": {
            "hookEventName": hook_event_name,
            "additionalContext": text,
        }
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _bypass_active() -> bool:
    return os.environ.get("SPECODE_GUARD", "").lower() == "off"


def _safe_hook(fn):
    """装饰器：hook 子命令的最外层异常吞并，恒 exit 0。"""
    def wrapper(args: argparse.Namespace) -> int:
        if _bypass_active():
            return 0
        # log hook invocation（0.10.0+；日志失败不阻断 hook）
        with contextlib.suppress(Exception):
            _log_event("hook_invoked", {"hook": fn.__name__}, session_id=None)
        try:
            fn(args)
        except SystemExit:
            raise
        except BaseException:
            with contextlib.suppress(Exception):
                # 写一份本地 trace 便于排查；忽略 IO 错误
                err = traceback.format_exc()
                sys.stderr.write(f"specode hook 异常已吞并：\n{err}\n")
                _log_event("hook_exception", {"hook": fn.__name__, "trace_head": err[:500]}, session_id=None)
        return 0
    return wrapper


# -------------------------------------------------------------------------
# 0.10.0+ 工具调用日志 hook（PreToolUse / PostToolUse 全通配，仅落日志）
# -------------------------------------------------------------------------

@_safe_hook
def hook_on_log_pre_tool_use(args: argparse.Namespace) -> None:
    """PreToolUse 全通配 hook：抓主代理每个工具调用前的 payload。仅落日志，不注入。"""
    payload = _read_stdin_payload()
    session_id = payload.get("session_id") or payload.get("sessionId") or args.session_override
    _log_event("tool_pre", {
        "tool_name": payload.get("tool_name") or payload.get("toolName"),
        "tool_input": payload.get("tool_input") or payload.get("toolInput"),
    }, session_id=session_id)


@_safe_hook
def hook_on_log_post_tool_use(args: argparse.Namespace) -> None:
    """PostToolUse 全通配 hook：抓主代理每个工具调用后的 payload。仅落日志，不注入。"""
    payload = _read_stdin_payload()
    session_id = payload.get("session_id") or payload.get("sessionId") or args.session_override
    _log_event("tool_post", {
        "tool_name": payload.get("tool_name") or payload.get("toolName"),
        "tool_response_head": str(payload.get("tool_response") or payload.get("toolResponse") or "")[:300],
    }, session_id=session_id)


# ---- on-session-start ----

@_safe_hook
def hook_on_session_start(args: argparse.Namespace) -> None:
    payload = _read_stdin_payload()
    session_id = payload.get("session_id") or payload.get("sessionId") or args.session_override
    if not session_id:
        return
    existing = read_session(session_id)
    if existing is None:
        new_payload = {
            "session_id": session_id,
            "started_at": _now_iso(),
            "last_activity_at": _now_iso(),
            "ended_at": None,
            "mode": "idle",
            "active_spec_slug": None,
            "active_spec_dir": None,
            "spec_id": None,
            "phase": None,
            "lock_state": "released",
            "task_swarm_run_id": None,
            "pending_selector": None,
        }
        try:
            write_session_atomic(session_id, new_payload)
        except Exception:
            pass
        existing = new_payload
    else:
        existing["last_activity_at"] = _now_iso()
        # 断线重连：如果原 ended，重新激活为 idle
        if existing.get("mode") == "ended":
            existing["mode"] = "idle"
            existing["ended_at"] = None
        try:
            write_session_atomic(session_id, existing)
        except Exception:
            pass

    mode = existing.get("mode") or "idle"
    slug = existing.get("active_spec_slug") or "无"
    text = (
        "## Specode session 就绪\n\n"
        f"当前会话 session_id: {session_id}\n"
        f"后续调用 specode CLI 时请始终用 `--session {session_id}` 传入。\n\n"
        f"（此 session 当前 mode={mode}，spec={slug}；\n"
        "  如需开始新 spec，使用 `/specode:spec <需求>`；\n"
        "  如需恢复，使用 `/specode:continue [slug]`。）\n"
    )
    if mode == "active" and existing.get("active_spec_slug"):
        text += "\n"
        text += SPEC_MODE_CONTINUE_REMINDER.replace("<slug>", existing.get("active_spec_slug") or "?").replace("<phase>", existing.get("phase") or "?")

    _emit_hook_additional_context(text, hook_event_name="SessionStart")


# ---- on-user-prompt ----

FAST_PATH_HELP = re.compile(r"^\s*/specode:spec\s+(-h|--help)\s*$", re.IGNORECASE)
FAST_PATH_VAULT = re.compile(
    r"^\s*/specode:spec\s+--(vault-status|detect-vault|sync-status)\s*$",
    re.IGNORECASE,
)


def _run_subcmd(argv: list[str]) -> str:
    """运行 spec_vault.py 等子命令，捕获 stdout。失败返回错误描述。"""
    try:
        proc = subprocess.run(
            [sys.executable, str(_THIS_DIR / argv[0])] + argv[1:],
            capture_output=True, text=True, timeout=10,
        )
        out = proc.stdout.strip()
        if proc.returncode not in (0, 3):
            out = (out + "\n[exit=" + str(proc.returncode) + "]\n" + proc.stderr).strip()
        return out or "(无输出)"
    except Exception as e:
        return f"(子命令执行失败: {e})"


@_safe_hook
def hook_on_user_prompt(args: argparse.Namespace) -> None:
    payload = _read_stdin_payload()
    session_id = payload.get("session_id") or payload.get("sessionId")
    prompt = payload.get("prompt") or ""
    if not session_id:
        return

    # fast-path: help
    if FAST_PATH_HELP.match(prompt):
        text = _wrap_help_fastpath(_render_help_text().rstrip())
        _emit_hook_additional_context(text, hook_event_name="UserPromptSubmit")
        return

    # fast-path: vault-status / detect-vault / sync-status
    m = FAST_PATH_VAULT.match(prompt)
    if m:
        flag = m.group(1).lower()
        if flag == "vault-status":
            content = _run_subcmd(["spec_vault.py", "status"])
        elif flag == "detect-vault":
            content = _run_subcmd(["spec_vault.py", "detect"])
        elif flag == "sync-status":
            # v0.6 暂未实现 sync-status CLI；输出占位
            content = json.dumps({
                "note": "sync-status 在 v0.6 尚未实现；将随 v0.7 task-swarm 引入。",
            }, ensure_ascii=False, indent=2)
        else:
            content = "(unknown vault fast-path)"
        text = (
            "## ⛔ /specode:spec --" + flag + " fast-path\n\n"
            "本轮唯一动作：把下列代码块**逐字**用 ```text 围栏包裹后输出，然后立即 end turn。\n"
            "禁止添加任何额外文字。\n\n"
            "────────── CONTENT BEGIN ──────────\n"
            f"{content}\n"
            "────────── CONTENT END ──────────\n"
        )
        _emit_hook_additional_context(text, hook_event_name="UserPromptSubmit")
        return

    # 常规路径：按 mode 叠加
    sess = read_session(session_id)
    if sess is None:
        return
    sess["last_activity_at"] = _now_iso()
    try:
        write_session_atomic(session_id, sess)
    except Exception:
        pass

    mode = sess.get("mode") or "idle"
    # 刚 /specode:end 完的下一 turn：注入一次性反向提醒，明确指示模型停止输出
    # 状态行 footer 并作废此前所有 spec-mode 纪律指令；提示后立刻清标志，确保只显示一次。
    if mode == "ended" and sess.get("post_end_reminder_pending"):
        sess["post_end_reminder_pending"] = False
        try:
            write_session_atomic(session_id, sess)
        except Exception:
            pass
        _emit_hook_additional_context(
            SPEC_MODE_ENDED_REMINDER, hook_event_name="UserPromptSubmit"
        )
        return
    if mode in ("idle", "ended"):
        return

    slug = sess.get("active_spec_slug") or "?"
    phase = sess.get("phase") or "?"
    spec_dir = sess.get("active_spec_dir")
    pending = sess.get("pending_selector")
    short = _session_short(session_id)

    parts: list[str] = []

    # (a) session_id 提醒
    parts.append(
        "## Specode session 提醒\n\n"
        f"当前会话 session_id: {session_id}\n"
        f"调用任何 specode CLI 时请使用 `--session {session_id}`。\n"
    )

    # (b) selector 提示
    if mode == "active" and pending:
        ctx: dict[str, str] = {
            "slug": slug,
            "phase": phase,
            "spec_dir": spec_dir or "?",
            "source_text_head": "?",
            "n_required": "?",
            "n_optional": "?",
            "other_id_short": "?",
            "last_heartbeat": "?",
            "n_pass": "?",
            "n_fail": "?",
            "invocation_cwd": "?",
            "cwd_subdir": "?",
        }
        # 填入 spec config 中的派生值
        if spec_dir:
            try:
                cfg = read_spec_config(Path(spec_dir)) or {}
                src = cfg.get("source_text") or ""
                if src:
                    ctx["source_text_head"] = src[:60].replace("\n", " ")
                lock = cfg.get("lock") or {}
                other = lock.get("holder")
                if other and other != session_id:
                    ctx["other_id_short"] = _session_short(other)
                    ctx["last_heartbeat"] = str(lock.get("last_heartbeat_at") or "?")
                inv = cfg.get("invocation_cwd")
                if inv:
                    ctx["invocation_cwd"] = str(inv)
                    # cwd/slug：用 os.path.join 跨平台拼接，但模板里用斜杠展示更直观；
                    # spec_session 不直接 mkdir，set-project-root CLI 才创建实际目录
                    sep = "\\" if "\\" in str(inv) else "/"
                    ctx["cwd_subdir"] = f"{inv}{sep}{slug}"
            except Exception:
                pass
        sel = _fill_selector(pending, ctx)
        if sel:
            parts.append(sel)
            # 0.10.27+：附加 selector 参数铁律 cheat sheet
            # （fixed 列 verbatim labels 集合；dynamic 列结构约束）。PreToolUse hook 会按
            # 这份 outline 校验主代理传给 AskUserQuestion 的参数；这里前置注入让主代理
            # 在决策传参之前就能看到完整名单，最大化避免 hallucinate。
            cheat = format_selector_cheatsheet(pending)
            if cheat:
                parts.append(cheat)
    elif mode == "readonly" and pending:
        parts.append(
            "## ℹ️ 只读模式：当前 pending_selector="
            f"`{pending}` （仅信息提示，只读不能确认）\n"
        )
        # readonly 也注入 cheat sheet —— takeover-options 等场景需要
        cheat = format_selector_cheatsheet(pending)
        if cheat:
            parts.append(cheat)

    # (c) 文档优先提醒
    if mode == "active":
        parts.append(
            DOC_PRIORITY_REMINDER_ACTIVE
            .replace("<slug>", slug)
            .replace("<phase>", phase)
        )
    elif mode == "readonly":
        parts.append(
            DOC_PRIORITY_REMINDER_READONLY
            .replace("<slug>", slug)
            .replace("<phase>", phase)
        )

    # (d) 状态行 footer
    if mode in ("active", "readonly"):
        footer = (
            STATUS_FOOTER_TEMPLATE
            .replace("<slug>", slug)
            .replace("<session_short>", short)
            .replace("<phase>", phase)
            .replace("<mode>", mode)
        )
        parts.append(footer)

    # (e) 模式提醒
    if mode == "active":
        parts.append(
            SPEC_MODE_CONTINUE_REMINDER
            .replace("<slug>", slug)
            .replace("<phase>", phase)
        )
    elif mode == "readonly":
        parts.append(
            SPEC_MODE_READONLY_REMINDER
            .replace("<slug>", slug)
            .replace("<phase>", phase)
        )

    if not parts:
        return
    text = "\n\n".join(p.rstrip() for p in parts) + "\n"
    _emit_hook_additional_context(text, hook_event_name="UserPromptSubmit")


# ---- on-stop ----

@_safe_hook
def hook_on_stop(args: argparse.Namespace) -> None:
    payload = _read_stdin_payload()
    session_id = payload.get("session_id") or payload.get("sessionId")
    if not session_id:
        return
    sess = read_session(session_id)
    if sess is None:
        return
    sess["last_activity_at"] = _now_iso()
    try:
        write_session_atomic(session_id, sess)
    except Exception:
        pass
    mode = sess.get("mode") or "idle"
    if mode in ("idle", "ended"):
        return
    slug = sess.get("active_spec_slug") or "?"
    phase = sess.get("phase") or "?"
    if mode == "active":
        text_parts = [
            CODE_DOC_SYNC_STOP.replace("<slug>", slug).replace("<phase>", phase),
            SPEC_MODE_CONTINUE_REMINDER.replace("<slug>", slug).replace("<phase>", phase),
        ]
    else:
        text_parts = [
            SPEC_MODE_READONLY_REMINDER.replace("<slug>", slug).replace("<phase>", phase),
        ]
    text = "\n\n".join(p.rstrip() for p in text_parts) + "\n"
    _emit_hook_additional_context(text, hook_event_name="Stop")


# ---- on-session-end ----

@_safe_hook
def hook_on_session_end(args: argparse.Namespace) -> None:
    payload = _read_stdin_payload()
    session_id = payload.get("session_id") or payload.get("sessionId")
    if not session_id:
        return
    sess = read_session(session_id)
    if sess is None:
        return
    spec_dir_str = sess.get("active_spec_dir")
    if spec_dir_str:
        try:
            spec_dir = Path(spec_dir_str)
            if spec_dir.exists():
                cfg = read_spec_config(spec_dir)
                if cfg is not None:
                    lock = cfg.get("lock") or {}
                    if lock.get("holder") == session_id:
                        cfg["lock"] = None
                        with contextlib.suppress(Exception):
                            write_spec_config_atomic(spec_dir, cfg)
        except Exception:
            pass
    sess["mode"] = "ended"
    sess["ended_at"] = _now_iso()
    sess["lock_state"] = "released"
    sess["pending_selector"] = None
    with contextlib.suppress(Exception):
        write_session_atomic(session_id, sess)
    # 不输出 additionalContext


# ---- v0.8 on-heartbeat-quiet（静默续锁） ----

@_safe_hook
def hook_on_heartbeat_quiet(args: argparse.Namespace) -> None:
    payload = _read_stdin_payload()
    session_id = (
        payload.get("session_id")
        or payload.get("sessionId")
        or args.session_override
    )
    if not session_id:
        return
    sess = read_session(session_id)
    if sess is None:
        return
    if sess.get("mode") != "active":
        return
    spec_dir_str = sess.get("active_spec_dir")
    if not spec_dir_str:
        return
    spec_dir = Path(spec_dir_str)
    if not spec_dir.exists():
        return
    cfg = read_spec_config(spec_dir)
    if cfg is None:
        return
    lock = cfg.get("lock") or {}
    if not isinstance(lock, dict):
        return
    holder = lock.get("holder") or lock.get("session_id") or lock.get("claude_session_id")
    if holder != session_id:
        return

    now = _now_iso()
    lock["last_heartbeat_at"] = now
    cfg["lock"] = lock
    try:
        write_spec_config_atomic(spec_dir, cfg)
    except Exception:
        return
    sess["last_activity_at"] = now
    with contextlib.suppress(Exception):
        write_session_atomic(session_id, sess)
    # 不输出 additionalContext


# ---- v0.8 on-pre-tool-use（模板章节大纲注入） ----

@_safe_hook
def hook_on_pre_tool_use(args: argparse.Namespace) -> None:
    payload = _read_stdin_payload()
    session_id = (
        payload.get("session_id")
        or payload.get("sessionId")
        or args.session_override
    )
    if not session_id:
        return
    sess = read_session(session_id)
    if sess is None:
        return
    mode = sess.get("mode") or "idle"
    if mode in ("idle", "ended"):
        return  # 不在 spec 模式：全放行

    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return
    tool_name = payload.get("tool_name") or payload.get("toolName") or ""

    # === 0.10.27+：AskUserQuestion selector 参数校验（active + readonly 都拦） ===
    # 主代理调 AskUserQuestion 时按 pending_selector 对应的 SELECTOR_OUTLINES
    # verbatim 校验 questions / options[*].label —— hallucinate（如把 workflow-choice
    # invent 成 TDD/RAPID/TASK_SWARM）直接 exit 2 阻断。
    if tool_name == "AskUserQuestion":
        pending = sess.get("pending_selector")
        if not pending:
            return  # 主代理在合法场景外用 AskUserQuestion（例如自主澄清），放行
        outline = SELECTOR_OUTLINES.get(pending)
        if outline is None:
            return  # 未知 selector key，不拦（防御性）
        violation = validate_ask_user_question_input(pending, tool_input, outline)
        if violation:
            sys.stderr.write(
                f"specode 阻断：AskUserQuestion 参数与 `{pending}` selector 模板不符。\n\n"
                f"{violation}\n\n"
                f"参考：`scripts/spec_session/_selectors.py` 的 "
                f"SELECTOR_PROMPTS[{pending!r}]，所有字段必须 verbatim 传入。\n"
            )
            sys.exit(2)
        return  # 校验通过

    # === Edit/Write/MultiEdit 路径（现有逻辑，仅 active 时执行） ===
    if mode != "active":
        return
    spec_dir_str = sess.get("active_spec_dir")
    if not spec_dir_str:
        return

    file_path = tool_input.get("file_path") or ""
    if not file_path or not isinstance(file_path, str):
        return

    try:
        edited = Path(file_path).resolve()
    except Exception:
        return
    spec_dir = Path(spec_dir_str)

    # --- 模板章节大纲注入：Write 4 份核心文档时前置提醒（0.10.26+） ---
    # 仅 Write（不含 Edit/MultiEdit）—— Edit 类工具的章节漂移由 B 层 spec_lint 后置兜底。
    if tool_name != "Write":
        return
    if edited.name not in TEMPLATE_OUTLINES:
        return
    try:
        if edited.parent != spec_dir.resolve():
            return  # 不是当前 active spec-dir 内的文档
    except Exception:
        return
    notice = format_outline_notice(edited.name)
    _emit_hook_additional_context(notice, hook_event_name="PreToolUse")
