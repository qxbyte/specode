"""selectors.md §8 场景总览表 与 SELECTOR_PROMPTS 11 keys 必须一一对应。

`spec_session/_selectors.py` 的 `SELECTOR_PROMPTS` 字典是 selector 模板的
**单一事实源**——hook 在 `UserPromptSubmit` 时按 `pending_selector` 命中
key 取出对应字符串值，做占位符替换后注入 `additionalContext`。

`selectors.md` 的 §8 场景常量库总览表是这些 key 的目录索引（每行含 §章节号
/ key / 类型 / 触发 phase / header / _selectors.py 行号），让人类读 SKILL.md
/ 其他 reference 时能快速跳到代码里的具体模板字面量。

本套测试在 pytest 阶段自动比对：
- selectors.md 总览表中每行的 key 都在 SELECTOR_PROMPTS 里
- 反向：SELECTOR_PROMPTS 的每个 key 都在总览表里出现一次

不再做"selectors.md ```text 块与字典字面量 byte-identical"全文对账（重构前
有 ~440 行的字面量副本两边维护，drift test 报警时两边都得改、PR 双份 diff；
重构后单一事实源在 _selectors.py，selectors.md 只索引，无 byte-level 副本）。
"""
from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SELECTORS_PY = REPO_ROOT / "plugins" / "specode" / "scripts" / "spec_session" / "_selectors.py"
SELECTORS_MD = REPO_ROOT / "plugins" / "specode" / "skills" / "specode" / "references" / "selectors.md"


def _load_runtime_keys() -> set[str]:
    """从 SELECTOR_PROMPTS 字典字面量里提取所有 key。"""
    src = SELECTORS_PY.read_text(encoding="utf-8")
    m = re.search(
        r"SELECTOR_PROMPTS:\s*dict\[str,\s*str\]\s*=\s*\{(.*?)\n\}\s*$",
        src,
        re.DOTALL | re.MULTILINE,
    )
    assert m, "SELECTOR_PROMPTS dict not found in spec_session/_selectors.py"
    body = m.group(1)
    return set(re.findall(r'"([a-z][a-z0-9-]+)":\s*"""', body))


def _load_doc_keys() -> set[str]:
    r"""从 selectors.md §8 场景常量库总览表的 markdown table 提取 key 列。

    表格行形如 `| §A0 | \`project-root-choice\` | A | ... |`，第 2 列加了
    反引号包裹 key——挑这一列。
    """
    md = SELECTORS_MD.read_text(encoding="utf-8")
    # 限定在 "## 8 个固定场景常量库" 节内（避免误抓其他章节里的反引号）
    sec_match = re.search(
        r"^##\s*8 个固定场景常量库\s*$(.*?)(?=^##\s|\Z)",
        md,
        re.DOTALL | re.MULTILINE,
    )
    assert sec_match, "selectors.md §8 场景常量库 section header not found"
    section = sec_match.group(1)
    keys: set[str] = set()
    # 匹配总览表行：第二个 |...| 字段含 `key`
    for line in section.splitlines():
        if not line.startswith("| §"):
            continue
        m = re.search(r"\|\s*`([a-z][a-z0-9-]+)`\s*\|", line)
        if m:
            keys.add(m.group(1))
    return keys


def test_overview_table_matches_runtime_keys():
    py_keys = _load_runtime_keys()
    md_keys = _load_doc_keys()
    assert py_keys, "no keys parsed from SELECTOR_PROMPTS"
    assert md_keys, "no keys parsed from selectors.md §8 overview table"

    extra_py = py_keys - md_keys
    extra_md = md_keys - py_keys
    msg: list[str] = []
    if extra_py:
        msg.append(
            "Keys in SELECTOR_PROMPTS but missing from selectors.md overview "
            f"table: {sorted(extra_py)} — add a row to the §8 table"
        )
    if extra_md:
        msg.append(
            "Keys in selectors.md overview but not in SELECTOR_PROMPTS: "
            f"{sorted(extra_md)} — either delete the orphan row or add the "
            "key to _selectors.py"
        )
    assert not msg, "\n".join(msg)


def test_expected_key_count():
    """Sanity check: 11 keys total (8 scenes; doc-confirm-* contributes 3 variants).

    Catches a class of regressions where someone accidentally drops a key from
    SELECTOR_PROMPTS without realizing it.
    """
    py_keys = _load_runtime_keys()
    assert len(py_keys) == 11, (
        f"expected 11 SELECTOR_PROMPTS keys (8 scenes + 2 extra doc-confirm "
        f"variants); got {len(py_keys)}: {sorted(py_keys)}"
    )
