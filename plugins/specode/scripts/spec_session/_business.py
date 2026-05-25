'''spec_session package 内部实现：业务子命令（cmd_*）+ _update_session_for_spec + _auto_pending_selector。

这些命令被 hooks.json 引导主代理调用，全部接 --session 参数；
任何写入失败必须回滚已变更的另一份文件 + 返回非零 exit。

不要直接运行本文件。stdlib-only。
'''
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from spec_session._io import (
    VALID_PHASES,
    _atomic_write_json,
    _emit_json,
    _ensure_spec_dir,
    _is_lock_stale,
    _now_iso,
    _session_short,
    read_session,
    read_spec_config,
    session_file_path,
    write_session_atomic,
    write_spec_config_atomic,
)


def _update_session_for_spec(session_id: str, spec_dir: Path, cfg: dict,
                              mode: str = "active",
                              lock_state: str = "ok",
                              pending_selector: Optional[str] = ...) -> dict:
    """构造 sessions/<id>.json 的常规更新。pending_selector=... 表示沿用 spec config 中的值。"""
    existing = read_session(session_id) or {}
    if pending_selector is ...:
        pending = cfg.get("pending_selector")
    else:
        pending = pending_selector
    payload = {
        "session_id": session_id,
        "started_at": existing.get("started_at") or _now_iso(),
        "last_activity_at": _now_iso(),
        "ended_at": None,
        "mode": mode,
        "active_spec_slug": cfg.get("slug"),
        "active_spec_dir": str(spec_dir),
        "spec_id": cfg.get("specId"),
        "phase": cfg.get("phase"),
        "lock_state": lock_state,
        "task_swarm_run_id": existing.get("task_swarm_run_id"),
        "pending_selector": pending,
    }
    return payload


def cmd_acquire(args: argparse.Namespace) -> int:
    spec_dir = _ensure_spec_dir(args.spec)
    cfg = read_spec_config(spec_dir)
    if cfg is None:
        sys.stderr.write(f"无法读取 {spec_dir}/.config.json\n")
        return 1

    now = _now_iso()
    lock = cfg.get("lock") or {}
    holder = lock.get("holder")

    if holder and holder != args.session and not _is_lock_stale(lock) and not args.force:
        _emit_json({
            "ok": False,
            "reason": "LockHeld",
            "holder": holder,
            "last_heartbeat_at": lock.get("last_heartbeat_at"),
        })
        return 4

    # 备份用于回滚
    prior_cfg = json.loads(json.dumps(cfg))
    prior_session_blob: Optional[str] = None
    sp = session_file_path(args.session)
    if sp.exists():
        try:
            prior_session_blob = sp.read_text(encoding="utf-8")
        except Exception:
            prior_session_blob = None

    cfg["lock"] = {
        "holder": args.session,
        "acquired_at": now,
        "last_heartbeat_at": now,
    }
    try:
        write_spec_config_atomic(spec_dir, cfg)
    except Exception as e:
        sys.stderr.write(f"写入 spec config 失败：{e}\n")
        return 1

    try:
        session_payload = _update_session_for_spec(args.session, spec_dir, cfg,
                                                   mode="active", lock_state="ok")
        write_session_atomic(args.session, session_payload)
    except Exception as e:
        # 回滚 spec config
        try:
            write_spec_config_atomic(spec_dir, prior_cfg)
        except Exception:
            pass
        sys.stderr.write(f"写入 sessions 失败，已回滚 spec config：{e}\n")
        return 1

    _emit_json({"ok": True, "holder": args.session, "acquired_at": now})
    return 0


def cmd_release(args: argparse.Namespace) -> int:
    spec_dir = _ensure_spec_dir(args.spec)
    cfg = read_spec_config(spec_dir)
    if cfg is None:
        sys.stderr.write(f"无法读取 {spec_dir}/.config.json\n")
        return 0  # release 容忍：spec config 缺失视作已释放
    prior_cfg = json.loads(json.dumps(cfg))
    lock = cfg.get("lock") or {}
    if lock.get("holder") == args.session:
        cfg["lock"] = None
        try:
            write_spec_config_atomic(spec_dir, cfg)
        except Exception as e:
            sys.stderr.write(f"释放锁写入失败：{e}\n")
            return 1
    # 更新 sessions
    try:
        existing = read_session(args.session) or {}
        existing["last_activity_at"] = _now_iso()
        existing["lock_state"] = "released"
        write_session_atomic(args.session, existing)
    except Exception as e:
        # 回滚 spec config
        try:
            write_spec_config_atomic(spec_dir, prior_cfg)
        except Exception:
            pass
        sys.stderr.write(f"写入 sessions 失败，已回滚 spec config：{e}\n")
        return 1
    _emit_json({"ok": True, "released_at": _now_iso()})
    return 0


def cmd_heartbeat(args: argparse.Namespace) -> int:
    spec_dir = _ensure_spec_dir(args.spec)
    cfg = read_spec_config(spec_dir)
    if cfg is None:
        sys.stderr.write(f"无法读取 {spec_dir}/.config.json\n")
        return 1
    lock = cfg.get("lock") or {}
    if lock.get("holder") != args.session:
        _emit_json({"ok": False, "reason": "lock_lost", "holder": lock.get("holder")})
        return 1
    prior_cfg = json.loads(json.dumps(cfg))
    now = _now_iso()
    cfg["lock"]["last_heartbeat_at"] = now
    try:
        write_spec_config_atomic(spec_dir, cfg)
    except Exception as e:
        sys.stderr.write(f"heartbeat 写入失败：{e}\n")
        return 1
    try:
        existing = read_session(args.session) or {}
        existing["last_activity_at"] = now
        existing["lock_state"] = "ok"
        write_session_atomic(args.session, existing)
    except Exception as e:
        try:
            write_spec_config_atomic(spec_dir, prior_cfg)
        except Exception:
            pass
        sys.stderr.write(f"heartbeat sessions 写入失败，已回滚：{e}\n")
        return 1
    _emit_json({"ok": True, "last_heartbeat_at": now})
    return 0


def cmd_verify_lock(args: argparse.Namespace) -> int:
    spec_dir = _ensure_spec_dir(args.spec)
    cfg = read_spec_config(spec_dir)
    if cfg is None:
        sys.stderr.write(f"无法读取 {spec_dir}/.config.json\n")
        return 3
    lock = cfg.get("lock") or {}
    holder = lock.get("holder")
    if not holder:
        _emit_json({"ok": False, "reason": "not_held"})
        return 3
    if holder != args.session:
        if _is_lock_stale(lock):
            _emit_json({"ok": False, "reason": "stale_lock", "holder": holder})
            return 3
        _emit_json({"ok": False, "reason": "evicted", "holder": holder})
        return 3
    _emit_json({"ok": True, "holder": holder, "last_heartbeat_at": lock.get("last_heartbeat_at")})
    return 0


def cmd_phase_transition(args: argparse.Namespace) -> int:
    if args.frm not in VALID_PHASES or args.to not in VALID_PHASES:
        sys.stderr.write(f"非法 phase：{args.frm} → {args.to}\n")
        return 1
    spec_dir = _ensure_spec_dir(args.spec)
    cfg = read_spec_config(spec_dir)
    if cfg is None:
        sys.stderr.write(f"无法读取 {spec_dir}/.config.json\n")
        return 1
    lock = cfg.get("lock") or {}
    if lock.get("holder") != args.session:
        _emit_json({"ok": False, "reason": "lock_lost"})
        return 1
    if cfg.get("phase") != args.frm:
        _emit_json({
            "ok": False,
            "reason": "phase_mismatch",
            "current": cfg.get("phase"),
            "expected_from": args.frm,
        })
        return 1
    prior_cfg = json.loads(json.dumps(cfg))
    prior_session = read_session(args.session)
    cfg["phase"] = args.to
    # 自动推断 pending_selector
    auto = _auto_pending_selector(args.to, cfg)
    cfg["pending_selector"] = auto
    try:
        write_spec_config_atomic(spec_dir, cfg)
    except Exception as e:
        sys.stderr.write(f"phase-transition 写 spec config 失败：{e}\n")
        return 1
    try:
        payload = _update_session_for_spec(args.session, spec_dir, cfg,
                                           mode="active", lock_state="ok",
                                           pending_selector=auto)
        write_session_atomic(args.session, payload)
    except Exception as e:
        try:
            write_spec_config_atomic(spec_dir, prior_cfg)
            if prior_session is not None:
                write_session_atomic(args.session, prior_session)
        except Exception:
            pass
        sys.stderr.write(f"phase-transition 写 sessions 失败，已回滚：{e}\n")
        return 1
    _emit_json({"ok": True, "phase": args.to, "pending_selector": auto})
    return 0


def _auto_pending_selector(phase: str, cfg: dict) -> Optional[str]:
    """根据 phase 推断默认 pending_selector（命令层可显式覆写）。"""
    workflow = cfg.get("workflow")
    if phase == "intake":
        return "workflow-choice"
    if phase == "requirements":
        return "doc-confirm-requirements"
    if phase == "bugfix":
        return "doc-confirm-bugfix"
    if phase == "design":
        return "doc-confirm-design"
    if phase == "tasks":
        return "tasks-execution"
    if phase == "implementation":
        return None
    if phase == "acceptance":
        return "acceptance-gate"
    if phase == "iteration":
        return "iteration-scope"
    return None


def cmd_load(args: argparse.Namespace) -> int:
    spec_dir = _ensure_spec_dir(args.spec)
    cfg = read_spec_config(spec_dir)
    if cfg is None:
        sys.stderr.write(f"无法读取 {spec_dir}/.config.json\n")
        return 1
    _emit_json({
        "ok": True,
        "spec_dir": str(spec_dir),
        "config": cfg,
    })
    return 0


def cmd_continue(args: argparse.Namespace) -> int:
    spec_dir = _ensure_spec_dir(args.spec)
    cfg = read_spec_config(spec_dir)
    if cfg is None:
        sys.stderr.write(f"无法读取 {spec_dir}/.config.json\n")
        return 1
    lock = cfg.get("lock") or {}
    holder = lock.get("holder")
    mode = "active"
    lock_state = "ok"
    pending = cfg.get("pending_selector")

    if holder and holder != args.session and not _is_lock_stale(lock) and not args.force:
        if args.readonly:
            mode = "readonly"
            lock_state = "readonly"
        else:
            # 提示走 takeover selector
            cfg["pending_selector"] = "takeover-options"
            try:
                write_spec_config_atomic(spec_dir, cfg)
            except Exception as e:
                sys.stderr.write(f"写 spec config 失败：{e}\n")
                return 1
            try:
                payload = _update_session_for_spec(args.session, spec_dir, cfg,
                                                   mode="readonly", lock_state="readonly",
                                                   pending_selector="takeover-options")
                write_session_atomic(args.session, payload)
            except Exception as e:
                sys.stderr.write(f"写 sessions 失败：{e}\n")
                return 1
            _emit_json({
                "ok": False,
                "reason": "LockHeld",
                "holder": holder,
                "pending_selector": "takeover-options",
                "spec_dir": str(spec_dir),
            })
            return 4
    else:
        # 抢锁（force / stale / 同 session / 无 holder）
        prior_cfg = json.loads(json.dumps(cfg))
        now = _now_iso()
        cfg["lock"] = {
            "holder": args.session,
            "acquired_at": now,
            "last_heartbeat_at": now,
        }
        try:
            write_spec_config_atomic(spec_dir, cfg)
        except Exception as e:
            sys.stderr.write(f"写 spec config 失败：{e}\n")
            return 1
        try:
            payload = _update_session_for_spec(args.session, spec_dir, cfg,
                                               mode=mode, lock_state=lock_state,
                                               pending_selector=pending)
            write_session_atomic(args.session, payload)
        except Exception as e:
            try:
                write_spec_config_atomic(spec_dir, prior_cfg)
            except Exception:
                pass
            sys.stderr.write(f"写 sessions 失败，已回滚 spec config：{e}\n")
            return 1
        # 更新 active-pointer
        try:
            root = Path(cfg.get("doc_root") or spec_dir.parent.parent)
            active_path = root / ".active-specode.json"
            _atomic_write_json(active_path, {
                "active_spec_slug": cfg.get("slug"),
                "active_spec_dir": str(spec_dir),
                "specId": cfg.get("specId"),
                "updatedAt": now,
                "session_id": args.session,
            })
        except Exception:
            pass

    _emit_json({
        "ok": True,
        "spec_dir": str(spec_dir),
        "mode": mode,
        "phase": cfg.get("phase"),
        "pending_selector": pending,
    })
    return 0


def cmd_end(args: argparse.Namespace) -> int:
    existing = read_session(args.session)
    if existing is None:
        # 即使 sessions 文件不存在，也写一份 ended 状态，便于排查
        existing = {
            "session_id": args.session,
            "started_at": _now_iso(),
        }
    spec_dir_str = existing.get("active_spec_dir")
    prior_cfg: Optional[dict] = None
    spec_dir: Optional[Path] = None
    if spec_dir_str:
        try:
            spec_dir = Path(spec_dir_str)
            if spec_dir.exists():
                cfg = read_spec_config(spec_dir)
                if cfg is not None:
                    prior_cfg = json.loads(json.dumps(cfg))
                    lock = cfg.get("lock") or {}
                    if lock.get("holder") == args.session:
                        cfg["lock"] = None
                        try:
                            write_spec_config_atomic(spec_dir, cfg)
                        except Exception as e:
                            sys.stderr.write(f"释锁写入失败：{e}\n")
                            return 1
        except Exception as e:
            sys.stderr.write(f"end 读取 spec config 出错：{e}\n")

    existing["mode"] = "ended"
    existing["ended_at"] = _now_iso()
    existing["lock_state"] = "released"
    existing["pending_selector"] = None
    # 对齐 end.md 文档：清 active_spec_* / task_swarm_run_id
    existing["active_spec_slug"] = None
    existing["active_spec_dir"] = None
    existing["spec_id"] = None
    existing["phase"] = None
    existing["task_swarm_run_id"] = None
    # 标记：下一次 UserPromptSubmit 时由 hook 注入一次性反向提醒，
    # 抵消此前 N 个 turn 注入的 STATUS_FOOTER_TEMPLATE / SPEC_MODE_CONTINUE_REMINDER
    existing["post_end_reminder_pending"] = True
    try:
        write_session_atomic(args.session, existing)
    except Exception as e:
        # 回滚 spec config
        if spec_dir is not None and prior_cfg is not None:
            try:
                write_spec_config_atomic(spec_dir, prior_cfg)
            except Exception:
                pass
        sys.stderr.write(f"sessions 写入失败，已回滚：{e}\n")
        return 1

    _emit_json({"ok": True, "ended_at": existing["ended_at"]})
    return 0


def cmd_set_project_root(args: argparse.Namespace) -> int:
    """0.10.15+：写 .config.json.project_root + 推进 pending_selector→workflow-choice。

    由 project-root-choice selector 选定后由主代理调用。

    args:
      --spec <dir>       spec 目录
      --session <id>     lock holder 必须是当前 session
      --root <path>      绝对路径；不存在则 mkdir -p；存在但非目录则 exit 1

    幂等：重复调用以最后一次为准。
    """
    spec_dir = Path(args.spec)
    if not spec_dir.exists():
        sys.stderr.write(f"spec 目录不存在：{spec_dir}\n")
        return 1
    cfg = read_spec_config(spec_dir)
    if cfg is None:
        sys.stderr.write(f"无法读取 {spec_dir}/.config.json\n")
        return 1
    lock = cfg.get("lock") or {}
    if lock.get("holder") != args.session:
        sys.stderr.write(
            f"lock holder 不是当前 session "
            f"(holder={_session_short(lock.get('holder'))} vs current={_session_short(args.session)})\n"
        )
        return 1

    root_path = Path(args.root)
    if not root_path.is_absolute():
        sys.stderr.write(f"--root 必须是绝对路径，收到：{args.root!r}\n")
        return 1
    if root_path.exists():
        if not root_path.is_dir():
            sys.stderr.write(f"--root 存在但不是目录：{root_path}\n")
            return 1
    else:
        # 自动创建（覆盖"cwd/slug 新项目子目录"场景；自定义路径也可借此创建）
        try:
            root_path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            sys.stderr.write(f"创建 --root 目录失败：{root_path}：{e}\n")
            return 1

    prior_cfg = json.loads(json.dumps(cfg))
    cfg["project_root"] = str(root_path)
    cfg["pending_selector"] = "workflow-choice"
    try:
        write_spec_config_atomic(spec_dir, cfg)
    except Exception as e:
        sys.stderr.write(f"写 spec config 失败：{e}\n")
        return 1

    # 同步 session 的 pending_selector
    sess = read_session(args.session)
    if sess is not None:
        sess["pending_selector"] = "workflow-choice"
        sess["last_activity_at"] = _now_iso()
        try:
            write_session_atomic(args.session, sess)
        except Exception as e:
            # 回滚 spec config
            try:
                write_spec_config_atomic(spec_dir, prior_cfg)
            except Exception:
                pass
            sys.stderr.write(f"写 sessions 失败，已回滚 spec config：{e}\n")
            return 1

    _emit_json({
        "ok": True,
        "project_root": str(root_path),
        "pending_selector": "workflow-choice",
        "spec_dir": str(spec_dir),
    })
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    sess = read_session(args.session)
    if sess is None:
        _emit_json({"ok": False, "reason": "session_not_found", "session_id": args.session})
        return 0
    payload = {"ok": True, "session": sess}
    spec_dir_str = sess.get("active_spec_dir")
    if spec_dir_str:
        try:
            cfg = read_spec_config(Path(spec_dir_str))
            if cfg is not None:
                payload["spec_config"] = cfg
        except Exception:
            pass
    _emit_json(payload)
    return 0


def cmd_read_session(args: argparse.Namespace) -> int:
    sess = read_session(args.session)
    if sess is None:
        _emit_json({"ok": False, "reason": "session_not_found"})
        return 0
    _emit_json(sess)
    return 0


def cmd_list_specs(args: argparse.Namespace) -> int:
    """列出当前 doc_root 下所有 spec 的状态摘要。

    输出 JSON:
      {ok, root, source, specs: [...], reason?}
    每个 spec 元素：
      {slug, dir, specId, displayName, phase, iterationRound,
       lock_state, holder, last_heartbeat_at, pending_selector,
       mtimes: {...}}
    """
    import datetime as _dt
    try:
        import spec_vault  # type: ignore
    except Exception as e:
        _emit_json({
            "ok": False,
            "reason": f"spec_vault_import_failed: {e}",
            "root": None,
            "source": "error",
            "specs": [],
        })
        return 0

    override = args.root
    try:
        root, source = spec_vault.resolve_doc_root(override)
    except Exception as e:
        _emit_json({
            "ok": False,
            "reason": f"resolve_doc_root_failed: {e}",
            "root": None,
            "source": "error",
            "specs": [],
        })
        return 0

    if root is None:
        _emit_json({
            "ok": False,
            "reason": "no_doc_root",
            "root": None,
            "source": source,
            "specs": [],
        })
        return 0

    specs_dir = Path(root) / "specs"
    if not specs_dir.exists() or not specs_dir.is_dir():
        _emit_json({
            "ok": True,
            "root": str(root),
            "source": source,
            "specs": [],
        })
        return 0

    spec_doc_names = [
        "requirements.md",
        "bugfix.md",
        "design.md",
        "tasks.md",
        "implementation-log.md",
    ]

    entries: list[dict] = []
    try:
        children = sorted(specs_dir.iterdir(), key=lambda p: p.name)
    except Exception:
        children = []

    for child in children:
        if not child.is_dir():
            continue
        cfg_path = child / ".config.json"
        if not cfg_path.exists():
            continue
        try:
            with cfg_path.open("r", encoding="utf-8") as fh:
                cfg = json.load(fh)
            if not isinstance(cfg, dict):
                continue
        except Exception:
            continue

        lock = cfg.get("lock") or {}
        # 业务侧实际字段名是 holder；兼容历史 session_id / claude_session_id 兜底
        holder_id = (
            lock.get("holder") or lock.get("session_id") or lock.get("claude_session_id")
            if isinstance(lock, dict) else None
        )
        if holder_id:
            if _is_lock_stale(lock):
                lock_state = "stale"
            else:
                lock_state = "held"
        else:
            lock_state = "free"
        holder_short = holder_id[:8] if isinstance(holder_id, str) and holder_id else None

        mtimes: dict[str, str] = {}
        for name in spec_doc_names:
            doc_path = child / name
            try:
                if doc_path.exists():
                    ts = doc_path.stat().st_mtime
                    mtimes[name] = (
                        _dt.datetime.utcfromtimestamp(ts)
                        .strftime("%Y-%m-%dT%H:%M:%SZ")
                    )
            except Exception:
                continue

        display_name = cfg.get("displayName") or cfg.get("requirementName")

        entries.append({
            "slug": cfg.get("slug") or child.name,
            "dir": str(child),
            "specId": cfg.get("specId"),
            "displayName": display_name,
            "phase": cfg.get("phase"),
            "iterationRound": cfg.get("iterationRound", 0),
            "lock_state": lock_state,
            "holder": holder_short,
            "last_heartbeat_at": lock.get("last_heartbeat_at") if isinstance(lock, dict) else None,
            "pending_selector": cfg.get("pending_selector"),
            "mtimes": mtimes,
        })

    _emit_json({
        "ok": True,
        "root": str(root),
        "source": source,
        "specs": entries,
    })
    return 0
