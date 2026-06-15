'''spec_session._template_skeleton — 模板章节大纲常量 + 解析/格式化 helpers。

用途：
  1. `_hooks.py:hook_on_pre_tool_use` 在主代理 Write 3 份核心文档（requirements.md /
     bugfix.md / design.md）之一时注入章节铁律提醒。
  2. `spec_lint.py:rule_template_structure` 对 spec-dir 现有文档校验章节集合
     与 `assets/templates/<phase>.md` 一致（缺 mandatory / 多 unknown 报 WARNING）。

为什么是常量而不是运行时解析：
  PreToolUse hook budget <100ms（详 CONTRIBUTING §Performance budget）。Python 冷启
  动 + import 链路已吃掉 60-90ms，留给业务的预算只剩 20-40ms。常量字典在 import
  时直接进内存（O(1) 查表，零 IO 零解析），远低于运行时读核心模板 + 正则解析的
  5-15ms。

如何同步：
  模板章节改动后跑 `python3 scripts/_gen_template_outline.py` 拿到期望的字面常量
  → 复制粘贴覆盖本文件下方的 TEMPLATE_OUTLINES。
  `tests/test_template_outlines_drift.py` 每次跑测试时自动 parse assets/templates/
  并断言与本字典一致，模板改了忘 regen 会红。

stdlib-only。
'''
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional


_H2_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_OPTIONAL_MARK = "（可选"   # 命中 "（可选）" 或 "（可选，仅 UI 类需求）" 等


def extract_h2_titles(text: str) -> list[str]:
    """从 markdown 抽所有 `## ` 二级标题（不含 `### `+），保留出现顺序。

    标题文本剥两端空白；不剥 `（可选）` 之类标记（caller 自己分类）。
    """
    return [m.group(1).strip() for m in _H2_RE.finditer(text)]


def parse_template_outline(template_text: str) -> dict[str, list[str]]:
    """解析单份模板，抽 mandatory / optional / dynamic_prefixes。

    规则：
      - 标题含 `（可选` 字面 → optional
      - 其余 → mandatory
      - 出现顺序保留（用于诊断输出，不参与集合比对）
      - dynamic_prefixes 当前所有核心模板均为空（动态前缀已随 tasks.md 移除）；
        字段保留以兼容 TEMPLATE_OUTLINES 结构与 drift 测试。
    """
    mandatory: list[str] = []
    optional: list[str] = []
    dynamic_prefixes: list[str] = []
    for title in extract_h2_titles(template_text):
        if _OPTIONAL_MARK in title:
            optional.append(title)
        else:
            mandatory.append(title)
    return {
        "mandatory": mandatory,
        "optional": optional,
        "dynamic_prefixes": dynamic_prefixes,
    }


def parse_templates_dir(templates_dir: Path) -> dict[str, dict[str, list[str]]]:
    """读 `<templates_dir>/{requirements,bugfix,design}.md` 并解析为 outline 字典。

    用于 codegen 入口与 drift 测试；不在 hook 运行时调用。
    """
    out: dict[str, dict[str, list[str]]] = {}
    for name in ("requirements.md", "bugfix.md", "design.md"):
        p = templates_dir / name
        text = p.read_text(encoding="utf-8")
        out[name] = parse_template_outline(text)
    return out


def matches_template_section(title: str, outline: dict[str, list[str]]) -> bool:
    """章节标题是否合规（在 mandatory / optional 名单内）。"""
    if title in outline.get("mandatory", []):
        return True
    if title in outline.get("optional", []):
        return True
    return False


def format_outline_notice(phase_md_name: str, outline: Optional[dict[str, list[str]]] = None) -> str:
    """渲染 PreToolUse Write 时的 additionalContext 文案。

    outline 可不传，缺省查表 TEMPLATE_OUTLINES；不在表里返回兜底文案。
    """
    if outline is None:
        outline = TEMPLATE_OUTLINES.get(phase_md_name)
    if outline is None:
        return (
            f"## ⚠️ 正在写入 `{phase_md_name}`\n\n"
            "未在 specode 模板章节字典中找到对应条目；请参考 "
            "`${CLAUDE_PLUGIN_ROOT}/assets/templates/` 下同名模板的章节结构。"
        )

    mand = outline.get("mandatory") or []
    opt = outline.get("optional") or []
    dyn = outline.get("dynamic_prefixes") or []

    lines = [
        f"## ⚠️ 正在写入 `{phase_md_name}` —— 模板章节铁律",
        "",
        f"`assets/templates/{phase_md_name}` 的 `## ` 二级章节标题**必须 verbatim 保留**——"
        "禁止改名 / 合并 / 拆分 / 调整顺序 / 新增未列出的章节。",
        "",
        "- **mandatory（必须保留，缺一即触发 spec_lint WARNING）**：",
    ]
    if mand:
        lines.extend(f"  - {t}" for t in mand)
    else:
        lines.append("  - （无）")

    if opt:
        lines.extend([
            "",
            "- **optional（可整段删，但不可只留标题留空）**：",
        ])
        lines.extend(f"  - {t}" for t in opt)

    if dyn:
        lines.extend([
            "",
            "- **dynamic（按需重复，标题须匹配前缀）**：",
        ])
        lines.extend(f"  - {label}" for label in dyn)

    lines.extend([
        "",
        "正文是叙事示例 / EARS 占位 —— 按 source_text 替换为实际内容；标题本身不动。",
        "下次 phase-transition / acceptance 由 `spec_lint rule_template_structure` 复核章节集合。"
        "详见 `skills/specode/references/templates.md` §模板章节铁律。",
    ])
    return "\n".join(lines) + "\n"


# =========================================================================
# >>> BEGIN AUTO-MAINTAINED: TEMPLATE_OUTLINES
# 模板章节大纲。模板改动后跑 `scripts/_gen_template_outline.py` 重新计算并粘贴。
# `tests/test_template_outlines_drift.py` 守住与 assets/templates/*.md 的一致性。
# =========================================================================

TEMPLATE_OUTLINES: dict[str, dict[str, list[str]]] = {
    "requirements.md": {
        "mandatory": [
            "一、背景 / 目标 / 范围",
            "二、目标用户与场景",
            "三、待澄清问题",
            "四、需求详述",
        ],
        "optional": [
            "五、非功能 / 约束（可选）",
            "六、依赖与风险（可选）",
            "七、UI 交互细节（可选，仅 UI 类需求）",
        ],
        "dynamic_prefixes": [],
    },
    "bugfix.md": {
        "mandatory": [
            "一、问题陈述",
            "二、复现路径",
            "三、影响范围",
            "四、证据",
            "五、待澄清问题",
            "六、根因分析",
            "七、修复方向",
            "八、回归保护",
        ],
        "optional": [
            "九、验收要点（可选）",
        ],
        "dynamic_prefixes": [],
    },
    "design.md": {
        "mandatory": [
            "概述",
            "架构",
            "组件与接口",
            "数据模型",
            "流程",
            "错误处理",
            "安全与隐私",
            "性能与可靠性",
            "测试策略",
            "正确性属性",
            "风险",
            "待确认问题",
        ],
        "optional": [],
        "dynamic_prefixes": [],
    },
}

# >>> END AUTO-MAINTAINED
