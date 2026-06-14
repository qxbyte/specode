'''spec_session._selector_skeleton — SELECTOR_PROMPTS 的结构化大纲常量 + helpers。

用途：
  1. `_hooks.py:hook_on_pre_tool_use` 拦截 AskUserQuestion 时按 outline 校验主代理
     传的 questions / options 参数是否合规——0.10.27 起 selector hallucinate
     （如把 workflow-choice 三选项 invent 成 TDD/RAPID/TASK_SWARM）会被 exit 2 阻断。
  2. `_hooks.py:hook_on_user_prompt` 把固定 selector 的 verbatim labels 注入
     `additionalContext` 作为 cheat sheet，让主代理在调 AskUserQuestion 前看到铁律名单。

为什么是常量而不是运行时解析：
  PreToolUse hook budget <100ms（详 CONTRIBUTING §Performance budget），常量字典在
  import 时直接进内存，零 IO 零解析。同 _template_skeleton.py 设计。

如何同步：
  SELECTOR_PROMPTS 改动后跑 `python3 scripts/_gen_selector_outlines.py` 拿到期望字面常量
  → 复制粘贴覆盖本文件下方 SELECTOR_OUTLINES。
  `tests/test_selector_outlines_drift.py` 每次跑测试自动比对，模板改了忘 regen 会红。

11 个 selector 中 10 个 kind=fixed（labels 集合 verbatim 比对）、1 个 kind=dynamic
（clarification-wizard，labels 由主代理动态生成；只校验 questions 数量 / multiSelect /
最小 options 等结构约束）。

stdlib-only。
'''
from __future__ import annotations

import re
from typing import Optional


_QUESTION_RE = re.compile(r"^\s*-?\s*question:\s*\"(.+?)\"\s*$", re.MULTILINE)
_HEADER_RE = re.compile(r"^\s*header:\s*\"(.+?)\"\s*$", re.MULTILINE)
_MULTI_RE = re.compile(r"^\s*multiSelect:\s*(true|false)\s*$", re.MULTILINE)
_LABEL_RE = re.compile(r"^\s*-\s*label:\s*\"(.+?)\"\s*$", re.MULTILINE)
_DYNAMIC_MARKERS = ("自行生成", "由你结合", "由你设计")


def parse_selector_outline(prompt_text: str) -> dict:
    """从 SELECTOR_PROMPTS 单条字符串解析 outline。

    返回 fixed 形：{"kind":"fixed","question":..,"header":..,"multi_select":bool,"labels":[..]}
    或 dynamic 形：{"kind":"dynamic","min_questions":2,"max_questions":4,
                  "multi_select":false,"min_options_per_question":2}

    dynamic 标识：模板文本含 "自行生成" / "由你结合" / "由你设计" 之一。
    """
    if any(marker in prompt_text for marker in _DYNAMIC_MARKERS):
        return {
            "kind": "dynamic",
            "min_questions": 2,
            "max_questions": 4,
            "multi_select": False,
            "min_options_per_question": 2,
        }
    q = _QUESTION_RE.search(prompt_text)
    h = _HEADER_RE.search(prompt_text)
    m = _MULTI_RE.search(prompt_text)
    labels = _LABEL_RE.findall(prompt_text)
    return {
        "kind": "fixed",
        "question": q.group(1) if q else "",
        "header": h.group(1) if h else "",
        "multi_select": (m.group(1) == "true") if m else False,
        "labels": labels,
    }


def parse_all_selectors(selector_prompts: dict) -> dict:
    """批量解析整个 SELECTOR_PROMPTS 字典。给 codegen 与 drift 测试用。"""
    return {k: parse_selector_outline(v) for k, v in selector_prompts.items()}


def format_selector_cheatsheet(key: str, outline: Optional[dict] = None) -> str:
    """渲染 selector outline 为 markdown cheat sheet（注入 UserPromptSubmit context）。"""
    if outline is None:
        outline = SELECTOR_OUTLINES.get(key)
    if outline is None:
        return ""
    if outline.get("kind") == "dynamic":
        n_min = outline.get("min_questions", 2)
        n_max = outline.get("max_questions", 4)
        opt_min = outline.get("min_options_per_question", 2)
        return (
            f"## AskUserQuestion 参数铁律 — `{key}`（dynamic）\n\n"
            f"本 selector 子问题与 label/description **由你结合源需求 + 用户输入动态生成**，"
            "但结构必须满足：\n\n"
            f"- `questions` 数组长度 {n_min}–{n_max}\n"
            "- 每个 question `multiSelect=false`\n"
            f"- 每个 question 至少 {opt_min} 个 `options`\n\n"
            "PreToolUse hook 会校验上述结构；违反 → exit 2 阻断。\n"
        )
    q = outline.get("question", "")
    h = outline.get("header", "")
    multi = outline.get("multi_select", False)
    labels = outline.get("labels", [])
    lines = [
        f"## AskUserQuestion 参数铁律 — `{key}`（fixed）",
        "",
        "调用 `AskUserQuestion` 时**必须 verbatim 传入**下列参数（一字不差，禁止改写 / 翻译 / 简化）：",
        "",
        f"- `question`: \"{q}\"",
        f"- `header`: \"{h}\"",
        f"- `multiSelect`: {str(multi).lower()}",
        "- `options[*].label`（集合相等，禁止改名 / 缺失 / 新增）:",
    ]
    for lbl in labels:
        lines.append(f"  - \"{lbl}\"")
    lines.extend([
        "",
        "**`description` 字段**：详见 `_selectors.py SELECTOR_PROMPTS['" + key + "']`，逐字复制对应 description；"
        "禁止凭主代理理解改写。",
        "",
        "PreToolUse hook 会做 verbatim 集合比对——label 缺失 / hallucinate（如把 workflow-choice 三选项 "
        "invent 成 \"TDD/RAPID/TASK_SWARM\"）→ exit 2 阻断。",
    ])
    return "\n".join(lines) + "\n"


def validate_ask_user_question_input(
    pending_selector: str,
    tool_input: dict,
    outline: Optional[dict] = None,
) -> Optional[str]:
    """校验主代理传给 AskUserQuestion 的 tool_input 是否符合 pending selector outline。

    返回 None = 合规；返回非空字符串 = 违规原因（用作 PreToolUse exit 2 的 stderr）。
    """
    if outline is None:
        outline = SELECTOR_OUTLINES.get(pending_selector)
    if outline is None:
        return None
    questions = tool_input.get("questions") or []
    if not isinstance(questions, list) or not questions:
        return (
            f"AskUserQuestion `questions` 数组为空（pending_selector={pending_selector}）。\n"
            f"请按 `_selectors.py SELECTOR_PROMPTS['{pending_selector}']` 的 yaml 块 verbatim 传入。"
        )
    if outline.get("kind") == "dynamic":
        n = len(questions)
        n_min = outline.get("min_questions", 2)
        n_max = outline.get("max_questions", 4)
        if not (n_min <= n <= n_max):
            return (
                f"`{pending_selector}` 必须传 {n_min}–{n_max} 个 question，当前 {n} 个。"
            )
        min_opts = outline.get("min_options_per_question", 2)
        for i, q in enumerate(questions):
            if not isinstance(q, dict):
                return f"question[{i}] 不是 dict。"
            if q.get("multiSelect") is True:
                return f"question[{i}] `multiSelect` 必须为 false（动态 selector 限制）。"
            opts = q.get("options") or []
            if len(opts) < min_opts:
                return f"question[{i}] `options` 必须 ≥ {min_opts} 个，当前 {len(opts)} 个。"
        return None
    # fixed
    if len(questions) != 1:
        return (
            f"固定 selector `{pending_selector}` 必须 1 个 question，当前 {len(questions)} 个。"
        )
    q = questions[0]
    if not isinstance(q, dict):
        return f"question[0] 不是 dict。"
    actual_multi = bool(q.get("multiSelect", False))
    expected_multi = bool(outline.get("multi_select", False))
    if actual_multi != expected_multi:
        return (
            f"`{pending_selector}` `multiSelect` 必须 {str(expected_multi).lower()}，"
            f"实际 {str(actual_multi).lower()}。"
        )
    opts = q.get("options") or []
    actual_labels = set()
    for opt in opts:
        if isinstance(opt, dict):
            lbl = opt.get("label")
            if isinstance(lbl, str):
                actual_labels.add(lbl)
    expected_labels = set(outline.get("labels", []))
    if actual_labels != expected_labels:
        missing = sorted(expected_labels - actual_labels)
        unknown = sorted(actual_labels - expected_labels)
        parts = []
        if missing:
            parts.append(f"缺失 label：{missing}")
        if unknown:
            parts.append(f"含未知 label（疑似 hallucinate）：{unknown}")
        return (
            f"`{pending_selector}` options labels 集合与模板不一致——{'，'.join(parts)}。\n"
            f"应使用的 label 集合（verbatim）：{sorted(expected_labels)}\n"
            f"详见 `_selectors.py SELECTOR_PROMPTS['{pending_selector}']`，禁止改写。"
        )
    return None


# =========================================================================
# >>> BEGIN AUTO-MAINTAINED: SELECTOR_OUTLINES
# Selector 大纲常量。SELECTOR_PROMPTS 改动后跑 `scripts/_gen_selector_outlines.py`
# 重生并粘贴覆盖此块。`tests/test_selector_outlines_drift.py` 守门。
# =========================================================================

SELECTOR_OUTLINES: dict[str, dict] = {
    "project-root-choice": {
        "kind": "fixed",
        "question": "代码写到哪个目录？project_root 决定 coder / 实现 agent 的 cwd",
        "header": "项目目录",
        "multi_select": False,
        "labels": [
            "cwd（在已有项目里迭代）",
            "cwd/slug（新项目子目录）",
            "自定义路径",
        ],
    },
    "workflow-choice": {
        "kind": "fixed",
        "question": "工作流选择 —— 决定走哪条 spec 流程？",
        "header": "工作流选择",
        "multi_select": False,
        "labels": [
            "Requirements first",
            "Technical Design first",
            "Bugfix",
        ],
    },
    "clarification-wizard": {
        "kind": "dynamic",
        "min_questions": 2,
        "max_questions": 4,
        "multi_select": False,
        "min_options_per_question": 2,
    },
    "clarification-done": {
        "kind": "fixed",
        "question": "需求澄清是否完成？",
        "header": "澄清完成?",
        "multi_select": False,
        "labels": [
            "进入下一阶段（推荐）",
            "继续澄清",
        ],
    },
    "doc-confirm-requirements": {
        "kind": "fixed",
        "question": "requirements.md 已生成。下一步？",
        "header": "需求确认",
        "multi_select": False,
        "labels": [
            "确认（推荐）",
            "查看全文",
            "继续沟通",
        ],
    },
    "doc-confirm-bugfix": {
        "kind": "fixed",
        "question": "bugfix.md 已生成。下一步？",
        "header": "缺陷确认",
        "multi_select": False,
        "labels": [
            "确认（推荐）",
            "查看全文",
            "继续沟通",
        ],
    },
    "doc-confirm-design": {
        "kind": "fixed",
        "question": "design.md 已生成。下一步？",
        "header": "设计确认",
        "multi_select": False,
        "labels": [
            "确认（推荐）",
            "查看全文",
            "继续沟通",
        ],
    },
    "tasks-execution": {
        "kind": "fixed",
        "question": "tasks.md 已生成。怎么执行？",
        "header": "执行方式",
        "multi_select": False,
        "labels": [
            "用 task-swarm plugin 执行（独立）",
            "顺序执行（同时处理 optional）",
            "暂停 / 调整 tasks.md",
        ],
    },
    "takeover-options": {
        "kind": "fixed",
        "question": "该 spec 已被其他会话窗口持有，怎么处理？",
        "header": "接管选项",
        "multi_select": False,
        "labels": [
            "强制接管",
            "只读查看",
            "取消",
        ],
    },
    "acceptance-gate": {
        "kind": "fixed",
        "question": "验收结论？",
        "header": "验收门",
        "multi_select": False,
        "labels": [
            "验收通过，进入 iteration（推荐）",
            "继续修改",
        ],
    },
    "iteration-scope": {
        "kind": "fixed",
        "question": "本轮 iteration 要调整哪些文档/动作？（可多选）",
        "header": "迭代范围",
        "multi_select": True,
        "labels": [
            "改 requirements",
            "改 design",
            "改 tasks",
            "重跑测试",
        ],
    },
}

# >>> END AUTO-MAINTAINED
