'''spec_session package 内部实现：B2 reference catalog hook。

按 user prompt 关键词在 active spec 内注入「考虑读 references/<X>.md」提醒。
description 即触发（superpowers 风格）：每个 reference 在文件头 YAML
frontmatter 写 `description: Use when ...`，告诉读者"何时该来这里"；本 hook
按预定义关键词表把命中的 reference 列出来，主代理自己决定是否要 Read。

激活门：仅当 sessions/<id>.json.mode=active 时触发；mode=readonly / idle /
ended 一律静默，避免在不应活动的状态下打扰。

性能预算：UserPromptSubmit budget 80ms。本 hook 全程纯预编译正则匹配 +
按命中 key 才读 frontmatter（最多 8 次 small file read），单次 <10ms。

不要直接运行本文件。stdlib-only。
'''
from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Optional

from spec_session._hooks import (
    _emit_hook_additional_context,
    _read_stdin_payload,
    _safe_hook,
)
from spec_session._io import read_session


_THIS_DIR = Path(__file__).resolve().parents[1]  # = scripts/（本文件在 scripts/spec_session/）
_REFERENCES_DIR = _THIS_DIR.parent / "skills" / "specode" / "references"


# key = reference 文件名（无 .md 后缀），value = 触发关键词 regex 列表
# 命中规则：prompt 内匹配任一 pattern 即命中该 key（一个 key 只列一次）
CATALOG: dict[str, list[str]] = {
    "lock-protocol": [
        r"\block\b", r"takeover", r"heartbeat", r"\bstale\b",
        r"接管", r"释锁", r"持锁", r"锁主", r"verify-lock",
    ],
    "obsidian": [
        r"\bvault\b", r"obsidian", r"doc[-_]?root",
        r"--set-vault", r"--detect-vault", r"--vault-status",
        r"specs?\s*目录", r"文档目录", r"spec\s*根目录",
    ],
    "iteration": [
        r"\biteration\b", r"迭代", r"acceptance.*?(继续|调整|修改)",
        r"验收后", r"再跑一轮",
    ],
    "selectors": [
        r"AskUserQuestion", r"\bselector\b", r"选择器", r"phase[- ]gate",
        r"chip[- ]tab",
    ],
    "workflow": [
        r"workflow[- ]choice", r"clarification", r"澄清",
        r"工作流选择", r"phase\s*转换", r"phase[- ]transition",
    ],
    "templates": [
        r"\bEARS\b", r"\bSHALL\b", r"traceability", r"_需求：",
        r"模板.*文档", r"requirements?\.md", r"design\.md",
    ],
    "task-swarm": [
        r"task[- ]swarm", r"\breviewer\b", r"\bvalidator\b",
        r"v[- ]?fix", r"p0[- ]?fix",
        r"@writes", r"@depends[- ]on", r"@reads",
        r"writeback", r"deadloop", r"task_swarm",
    ],
    "task-swarm-example": [
        r"tasks\.md.*?示例", r"task-swarm.*?例子",
        r"tasks\.md.*?例", r"task-swarm.*?demo",
    ],
}


# 预编译 + IGNORECASE，避免 hook 每次都重编译
_COMPILED: dict[str, list[re.Pattern]] = {
    k: [re.compile(p, re.IGNORECASE) for p in patterns]
    for k, patterns in CATALOG.items()
}


def _read_description(ref_key: str) -> Optional[str]:
    """从 references/<ref_key>.md YAML frontmatter 取 description 字段。

    无 frontmatter / 无 description / 读失败 → None（catalog 仍触发，
    只是注入文本里改用占位符）。
    """
    p = _REFERENCES_DIR / f"{ref_key}.md"
    if not p.exists():
        return None
    try:
        text = p.read_text(encoding="utf-8")
    except Exception:
        return None
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end < 0:
        return None
    fm = text[4:end]
    # 简易行解析：找以 'description:' 开头的行
    for line in fm.split("\n"):
        if line.startswith("description:"):
            return line[len("description:"):].strip()
    return None


def _match_refs(prompt: str) -> list[str]:
    """返回 prompt 命中的 reference key 列表（保序去重）。"""
    hits: list[str] = []
    for key, patterns in _COMPILED.items():
        for p in patterns:
            if p.search(prompt):
                hits.append(key)
                break  # 同 key 内任一 pattern 命中即可
    return hits


def _render_catalog_text(hits: list[str]) -> str:
    lines = [
        "## 📚 specode reference 提示",
        "",
        "你最新一轮输入命中下列关键词，对应 references 可能与本轮相关；",
        "如未读过请先 Read（路径相对于 plugin skills/specode/）：",
        "",
    ]
    for key in hits:
        desc = _read_description(key) or "（该 reference 暂无 description）"
        lines.append(f"- `references/{key}.md` — {desc}")
    lines.append("")
    lines.append(
        "提示仅供参考；是否需要 Read 由你结合 SKILL.md 与当前 phase 自行判断。"
    )
    return "\n".join(lines) + "\n"


@_safe_hook
def hook_on_user_prompt_catalog(args: argparse.Namespace) -> None:
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
    # 激活门：仅 active 模式触发；idle / ended / readonly 静默
    if sess.get("mode") != "active":
        return
    prompt = payload.get("prompt") or ""
    if not prompt:
        return
    hits = _match_refs(prompt)
    if not hits:
        return
    _emit_hook_additional_context(
        _render_catalog_text(hits),
        hook_event_name="UserPromptSubmit",
    )
