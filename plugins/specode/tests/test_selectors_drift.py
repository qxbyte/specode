"""references/selectors.md 与 SELECTOR_PROMPTS 必须 byte-identical。

selectors.md 是文档来源、_ss_selectors.py 的 SELECTOR_PROMPTS 是 hook 注入时实际
拿出来拼字符串的运行时常量库（0.10.22 拆分前在 spec_session.py 里）。两边漂移会
导致："文档说选项 A/B/C，运行时注入 A/B/D"——主代理按 hook 内容调 AskUserQuestion，
用户体验跟文档对不上。

本套测试在 pytest 阶段自动比对：
- runtime keys 必须与 selectors.md 中 ### / #### 反引号标题命中的 key 集合一致
- 每个 selector 的 ```text 块内容必须与 SELECTOR_PROMPTS[key] 字符串 strip 后逐字相等
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = REPO_ROOT / "plugins" / "specode" / "scripts" / "_ss_selectors.py"
SELECTORS_MD = REPO_ROOT / "plugins" / "specode" / "skills" / "specode" / "references" / "selectors.md"


def _load_runtime_prompts() -> dict[str, str]:
    src = SCRIPTS.read_text(encoding="utf-8")
    m = re.search(
        r"SELECTOR_PROMPTS:\s*dict\[str,\s*str\]\s*=\s*\{(.*?)\n\}\s*$",
        src,
        re.DOTALL | re.MULTILINE,
    )
    assert m, "SELECTOR_PROMPTS dict not found in _ss_selectors.py"
    body = m.group(1)
    prompts: dict[str, str] = {}
    for km in re.finditer(r'"([a-z-]+)":\s*"""(.*?)""",', body, re.DOTALL):
        prompts[km.group(1)] = km.group(2).strip()
    return prompts


def _load_doc_prompts() -> dict[str, str]:
    """提取 selectors.md 中每个 H3 / H4 反引号 selector key 紧随其后的 ```text 块。

    支持两种结构：
      ### A1 `key` — 描述           （单 key 一节）
      ### A3 `doc-confirm-{...}`    （多 key 共享节，下挂多个 #### `key` 子节）
    第一种 H3 自带 ```text；第二种 H3 是分组介绍 + 多个 H4 各自有 ```text。
    """
    md = SELECTORS_MD.read_text(encoding="utf-8")
    prompts: dict[str, str] = {}
    pattern = re.compile(
        r"^(#{3,4})\s+[^\n]*?`([a-z][a-z0-9-]+)`[^\n]*\n(.*?)(?=^#{3,4}\s|\Z)",
        re.DOTALL | re.MULTILINE,
    )
    for m in pattern.finditer(md):
        key = m.group(2)
        section = m.group(3)
        cm = re.search(r"```text\n(.*?)```", section, re.DOTALL)
        if cm:
            prompts[key] = cm.group(1).strip()
    return prompts


def test_keys_match():
    py = _load_runtime_prompts()
    md = _load_doc_prompts()
    extra_py = set(py) - set(md)
    extra_md = set(md) - set(py)
    msg = []
    if extra_py:
        msg.append(
            "Selectors in SELECTOR_PROMPTS but missing in selectors.md "
            "(need a ### / #### header with `key` + ```text block): "
            f"{sorted(extra_py)}"
        )
    if extra_md:
        msg.append(
            "Selectors in selectors.md but not in SELECTOR_PROMPTS runtime: "
            f"{sorted(extra_md)} — either delete the orphan or add it to spec_session.py"
        )
    assert not msg, "\n".join(msg)


@pytest.mark.parametrize("key", sorted(_load_runtime_prompts()))
def test_byte_identical(key):
    py = _load_runtime_prompts()
    md = _load_doc_prompts()
    if key not in md:
        pytest.skip(f"selector {key} has no doc block — covered by test_keys_match")
    a = py[key]
    b = md[key]
    if a == b:
        return
    for i, (ca, cb) in enumerate(zip(a, b)):
        if ca != cb:
            cs = max(0, i - 40)
            ce = i + 80
            pytest.fail(
                f"Drift in selector '{key}' at char {i} "
                f"(spec_session.py={len(a)} chars, selectors.md={len(b)} chars):\n"
                f"  py: ...{a[cs:ce]!r}\n"
                f"  md: ...{b[cs:ce]!r}"
            )
    shorter = min(len(a), len(b))
    longer = a if len(a) > len(b) else b
    who = "spec_session.py" if len(a) > len(b) else "selectors.md"
    pytest.fail(
        f"Drift in selector '{key}': {who} has extra {len(longer) - shorter} chars "
        f"at tail:\n  extra: {longer[shorter:shorter+200]!r}"
    )
