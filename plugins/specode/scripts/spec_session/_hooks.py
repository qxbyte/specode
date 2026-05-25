'''spec_session package 内部实现：所有 hook 子命令（hook_on_*）+ safe wrapper + task-swarm plan 提醒辅助。

hook 子命令仅由 hooks/hooks.json 调用；全部 exit 0、任何异常通过 @_safe_hook
内部 catch（PreToolUse 对 task-swarm 受控路径与 tasks.md 的 exit 2 强阻断除外，
见 hook_on_pre_tool_use）。

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
    elif mode == "readonly" and pending:
        parts.append(
            "## ℹ️ 只读模式：当前 pending_selector="
            f"`{pending}` （仅信息提示，只读不能确认）\n"
        )

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


# ---- v0.7 on-task-completed（task-swarm 节点提醒） ----

TASK_COMPLETED_TRAILER = "\n\n本提醒仅供参考；fork 谁、是否 fork、何时 writeback 仍由你判断；可忽略。"


def _run_task_swarm_plan(run_id: str) -> Optional[dict]:
    """调子进程 task_swarm.py plan --run <run_id>，解析 stdout JSON 返回 dict。

    任何失败（exit != 0、JSON 解析失败、子进程异常）返回 None。
    """
    try:
        proc = subprocess.run(
            [sys.executable, str(_THIS_DIR / "task_swarm.py"), "plan", "--run", run_id],
            capture_output=True, text=True, timeout=10,
        )
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    out = (proc.stdout or "").strip()
    if not out:
        return None
    try:
        obj = json.loads(out)
        if isinstance(obj, dict):
            return obj
    except Exception:
        return None
    return None


def _format_plan_context(plan: dict) -> str:
    """按 references/task-swarm.md §6 hook 提醒矩阵把 plan dict 渲染成 additionalContext 文本。"""
    phase = str(plan.get("phase") or "?")
    action = str(plan.get("action") or "")
    group = plan.get("group")
    rnd = plan.get("round")
    in_flight = plan.get("in_flight") or []
    fork = plan.get("fork") or []
    msg = str(plan.get("message") or "")
    n_fork = len(fork) if isinstance(fork, list) else 0
    n_in_flight = len(in_flight) if isinstance(in_flight, list) else 0

    # 选择具体建议文本（references/task-swarm.md §6 9 种状态）
    if action == "deadloop" or phase == "error":
        body = (
            f"⚠️ 死循环检测：g{group} 已连续 3 轮同一 fail 签名。\n"
            "建议停止本 group，向用户报告 `failed-deadloop`，让用户介入。"
        )
    elif action == "all-done" or phase == "done":
        body = (
            "全部 group 已完成。请按 SKILL.md 退出 task-swarm 模式，"
            "回到 spec-mode acceptance phase。"
        )
    elif phase == "coding" and action == "coding-waiting":
        body = (
            f"coding phase 还在等 {n_in_flight} 个 subagent；"
            "无需 fork 新 agent，等齐后再判断。"
        )
    elif phase == "coding" and action == "coding-fork":
        body = (
            f"本 group 开始 coding。请按下面 {n_fork} 个 coder agent_key fork"
            "（同 message 内并发）。"
        )
    elif phase == "review" and action == "review-fork":
        body = (
            "本 group coder 已全部返回。请 fork **1 个** `task-swarm-reviewer`，"
            "prompt 已生成。"
        )
    elif phase == "p0-fix" and action == "p0-fix-fork":
        body = (
            f"reviewer 提了带证据 P0。请按 P0 涉及文件 fork **{n_fork}** 个 "
            "`task-swarm-coder`（p0-fix），prompt 已生成。\n"
            "提醒：reviewer 修复**只触发一次**，不 re-review。"
        )
    elif phase == "p0-fix" and action == "p0-fix-waiting":
        body = f"p0-fix 仍有 {n_in_flight} 个 coder 未返回，等齐后再判断。"
    elif phase == "validation" and action == "validation-fork":
        body = (
            "reviewer 无带证据 P0（或全部降级为 advisory）。"
            "请 fork **1 个** `task-swarm-validator`，prompt 已生成。"
        )
    elif phase == "validation" and action == "validation-fork-after-p0":
        body = (
            "p0-fix coder 已返回。请 fork **1 个** `task-swarm-validator`，"
            "prompt 已生成。"
        )
    elif phase == "validation" and action == "validation-after-vfix":
        body = (
            "v-fix coder 已返回。请 fork **1 个** `task-swarm-validator` 验证。"
        )
    elif phase == "writeback" and action == "writeback":
        body = (
            "validator pass。请调 `task_swarm.py writeback "
            f"--run <run_id> --group {group}` 回写 tasks.md，然后进入下一 group。"
        )
    elif phase == "v-fix" and action == "v-fix-fork":
        body = (
            f"validator fail。请按 validation.md 的 fix_targets 各文件 "
            f"fork **{n_fork}** 个 `task-swarm-coder`（v-fix）。\n"
            "注意：validator fail 循环修复直到 pass。"
            f"本轮是 g{group}-r{rnd}。"
        )
    elif phase == "v-fix" and action == "v-fix-waiting":
        body = f"v-fix 仍有 {n_in_flight} 个 coder 未返回，等齐后再判断。"
    else:
        body = msg or f"phase={phase} action={action}（详见 plan 输出）"

    header = (
        f"## task-swarm 节点提醒（phase={phase}, "
        f"group={group if group is not None else '?'}, "
        f"round={rnd if rnd is not None else '?'}）\n\n"
    )
    return header + body + TASK_COMPLETED_TRAILER


@_safe_hook
def hook_on_task_completed(args: argparse.Namespace) -> None:
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
    run_id = sess.get("task_swarm_run_id")
    if not run_id:
        return

    plan = _run_task_swarm_plan(run_id)
    if isinstance(plan, dict):
        text = _format_plan_context(plan)
    else:
        # plan 调用失败 → 兜底文本
        text = (
            "## task-swarm 节点提醒\n\n"
            f"无法自动获取 task-swarm run `{run_id}` 的下一步建议——"
            "请手动调用：\n\n"
            "```bash\n"
            f"task_swarm.py plan --run {run_id}\n"
            "```\n\n"
            "拿到输出后再判断 fork 谁 / 是否 writeback。"
            + TASK_COMPLETED_TRAILER
        )
    _emit_hook_additional_context(text, hook_event_name="PostToolUse")


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


# ---- v0.8 on-pre-tool-use（tasks.md 直写提醒 + task-swarm 受控路径阻断） ----

def _task_swarm_protected_reason(spec_dir: Path, edited: Path) -> Optional[str]:
    """若 edited 落在 task-swarm 管理路径下（state.json / agent task.md /
    agent outbox/*），返回简短的拒绝标签；否则返回 None。

    阻断动机：这些文件是 task_swarm.py advance/writeback 的内部状态与产物。
    主代理直接 Edit 会破坏状态机契约（典型事故：state in_flight 与磁盘
    agent 目录的 round 号对不上时，手工抹平 state.json 反而越改越乱）。
    所有变更必须通过 task_swarm.py CLI 走。
    """
    try:
        ts_root = (spec_dir / ".task-swarm" / "runs").resolve()
    except Exception:
        return None
    try:
        rel = edited.relative_to(ts_root)
    except ValueError:
        return None
    parts = rel.parts
    if len(parts) < 2:
        return None
    # parts[0] = <run_id>
    if parts[1] == "state.json":
        return "state.json"
    if parts[1] == "agents" and len(parts) >= 4:
        # parts[2] = <agent_key>
        if parts[3] == "task.md":
            return "agent task.md"
        if parts[3] == "outbox":
            return "agent outbox"
    return None


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
    if sess.get("mode") != "active":
        return
    run_id = sess.get("task_swarm_run_id")
    if not run_id:
        return
    spec_dir_str = sess.get("active_spec_dir")
    if not spec_dir_str:
        return

    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return
    file_path = tool_input.get("file_path") or ""
    if not file_path or not isinstance(file_path, str):
        return

    try:
        edited = Path(file_path).resolve()
    except Exception:
        return
    spec_dir = Path(spec_dir_str)

    # 强阻断：task-swarm 受控路径（state.json / agent task.md / agent outbox/*）
    protected = _task_swarm_protected_reason(spec_dir, edited)
    if protected:
        if protected == "state.json":
            target_hint = "task_swarm.py advance --run <run> --phase <phase>"
            why = (
                "`state.json` 是 task_swarm.py 状态机的唯一事实来源。手工 Edit 会让\n"
                "in_flight / done / phase / round 与磁盘 agent 目录脱节（已知事故：\n"
                "state 是 r2、磁盘是 r3 时，手工把 r2 改成 r3 抹平差异 → 再 advance\n"
                "时状态机走错分支 → validator/coder 名字越漂越远）。"
            )
        elif protected == "agent task.md":
            target_hint = "task_swarm.py advance（让状态机重新 render prompt）"
            why = (
                "`agents/<key>/task.md` 是 task_swarm.py 为 subagent 生成的 prompt。\n"
                "主代理改它不会让 subagent 重新读——只会让产物与意图脱节。"
            )
        else:  # agent outbox
            target_hint = "重新 fork 对应 subagent 让它输出合规产物"
            why = (
                "`agents/<key>/outbox/*` 是 subagent 的产物。主代理手工补 STATUS / 改\n"
                "result.md 等同于伪造 subagent 工作，advance 解析时看似 ok，但实际\n"
                "代码未改。请重新 fork subagent 或汇报 task_swarm.py 解析 bug。"
            )
        reason = (
            f"specode 阻断：主代理不得直接 Edit/Write task-swarm 受控路径"
            f"（{protected}）。\n\n"
            f"文件: {edited}\n"
            f"run_id: {run_id}\n\n"
            f"{why}\n\n"
            f"正确路径: {target_hint}\n"
        )
        sys.stderr.write(reason)
        sys.exit(2)

    # 0.10.21+：tasks.md 直写从软提醒升级为强阻断
    # 理由：login-page 现场显示主代理见 writeback 越界报错就手工 Edit tasks.md
    # 把 `[ ]` 改成 `[x]`，破坏了 state.json 与 tasks.md 行号一致性，后续
    # writeback 永远过不去。跟 state.json / outbox 同等待遇——只能走 CLI。
    try:
        tasks_md = (spec_dir / "tasks.md").resolve()
    except Exception:
        return

    if edited != tasks_md:
        return

    reason = (
        f"specode 阻断：主代理不得直接 Edit/Write `tasks.md`\n\n"
        f"文件: {edited}\n"
        f"run_id: {run_id}\n\n"
        "`tasks.md` 在 task-swarm run 进行中是受控产物——所有 checkbox toggle "
        "（`[ ]` → `[x]`）和评审注释块都必须通过 `task_swarm.py writeback` CLI 走，\n"
        "走 line-safe diff 算法保证 state.json 行号引用不被破坏。\n\n"
        "已知反模式：见 writeback 越界报错就手工改 tasks.md → state.json 行号失效 → 后续\n"
        "writeback 永远过不去 → 主代理陷入死循环（参 0.10.13 user-login / 0.10.21 login-page 事故）。\n\n"
        "正确路径: task_swarm.py writeback --run <run_id> --group <N>\n"
        "若 writeback 本身报越界，请保留现场报告用户，让 task-swarm 算法层修，**不要**\n"
        "手工抹平。\n"
    )
    sys.stderr.write(reason)
    sys.exit(2)
