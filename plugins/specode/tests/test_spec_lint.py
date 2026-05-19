"""Tests for spec_lint.py — 3 lint rules, all warning-only (exit 0)."""
from __future__ import annotations

from pathlib import Path

import pytest


def _bootstrap_spec_dir(doc_root: Path, slug: str = "lint-spec") -> Path:
    """Create a minimal spec directory with placeholder files."""
    sd = doc_root / "specs" / slug
    sd.mkdir(parents=True, exist_ok=True)
    (sd / "requirements.md").write_text(
        "# 需求文档\n\n## 需求 1\n\n### 需求 1.1\n\n"
        "WHEN 用户登录，THE System SHALL 返回 token。\n",
        encoding="utf-8",
    )
    (sd / "tasks.md").write_text(
        "# 任务\n\n- [ ] 1. 实现登录 _需求：1.1_\n",
        encoding="utf-8",
    )
    (sd / "implementation-log.md").write_text(
        "# 实现记录\n\n## 2026-01-01 — 初始化\n\nspec 已初始化，文件 src/main.py 等待实现。这条 entry 写得很长足够 30 字。\n",
        encoding="utf-8",
    )
    return sd


def test_lint_clean_spec_has_zero_warnings(run_script, doc_root):
    sd = _bootstrap_spec_dir(doc_root, "clean")
    cp = run_script("spec_lint.py", "--spec", str(sd))
    assert cp.returncode == 0
    assert "0 warnings" in cp.stdout


def test_lint_trace_warns_for_orphan_tag(run_script, doc_root):
    sd = _bootstrap_spec_dir(doc_root, "orphan-tag")
    # tasks.md references 需求 1.99 — not present in requirements.md
    (sd / "tasks.md").write_text(
        "# 任务\n\n- [ ] 999. 看不见的任务 _需求：1.99_\n",
        encoding="utf-8",
    )
    cp = run_script("spec_lint.py", "--spec", str(sd))
    assert cp.returncode == 0
    assert "trace" in cp.stdout
    assert "1.99" in cp.stdout


def test_lint_log_short_entry_warns(run_script, doc_root):
    sd = _bootstrap_spec_dir(doc_root, "short-log")
    # Replace implementation-log with a short entry (< 30 chars, no file ref)
    (sd / "implementation-log.md").write_text(
        "# 实现记录\n\n## 2026-01-02 — 改了点东西\n\nok\n",
        encoding="utf-8",
    )
    cp = run_script("spec_lint.py", "--spec", str(sd))
    assert cp.returncode == 0
    assert "log" in cp.stdout
    # Either short body or missing file-ref warning may fire
    assert "implementation-log.md" in cp.stdout


def test_lint_ears_missing_trigger_warns(run_script, doc_root):
    sd = _bootstrap_spec_dir(doc_root, "ears-bad")
    # SHALL without WHEN/IF/WHILE/WHERE/WHENEVER
    (sd / "requirements.md").write_text(
        "# 需求文档\n\n## 需求 1\n\nThe System SHALL 处理所有请求。\n",
        encoding="utf-8",
    )
    cp = run_script("spec_lint.py", "--spec", str(sd))
    assert cp.returncode == 0
    assert "ears" in cp.stdout


def test_lint_always_exit_zero_even_with_many_warnings(run_script, doc_root):
    """Any/all 3 rules can fire and exit code is still 0."""
    sd = _bootstrap_spec_dir(doc_root, "all-bad")
    # Force every rule:
    (sd / "requirements.md").write_text(
        "# 需求\n\nThe System SHALL 处理一切。\n",
        encoding="utf-8",
    )
    (sd / "tasks.md").write_text(
        "# 任务\n\n- [ ] 1. xxx _需求：9.99_\n",
        encoding="utf-8",
    )
    (sd / "implementation-log.md").write_text(
        "# log\n\n## 2026-01-03 — \n\nshort\n",
        encoding="utf-8",
    )
    cp = run_script("spec_lint.py", "--spec", str(sd))
    assert cp.returncode == 0
    # All 3 rule names appear
    rule_hits = sum(1 for r in ("trace", "log", "ears") if r in cp.stdout)
    assert rule_hits == 3
