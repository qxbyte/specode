"""Tests for spec_lint.py:rule_template_structure。

每条用例都通过 spec_init.py 拿到"干净的"模板文档，再针对性改写章节集合，
确认新规则对 mandatory 缺失 / unknown 新增 / optional 删除等情况的判定符合
预期。M4 起 tasks.md 不再属于 specode 模板（无 dynamic 前缀场景）。
"""
from __future__ import annotations

import re
from pathlib import Path


def _write_text(p: Path, content: str) -> None:
    p.write_text(content, encoding="utf-8")


def _stub_minimal_spec(spec_dir: Path) -> None:
    """覆盖 spec_init 生成的文档为最小合规版本（只含 mandatory 章节，无 optional）。"""
    spec_dir.mkdir(parents=True, exist_ok=True)
    _write_text(
        spec_dir / "requirements.md",
        "# 需求文档\n\n"
        "## 一、背景 / 目标 / 范围\n\n占位。\n\n"
        "## 二、目标用户与场景\n\n占位。\n\n"
        "## 三、待澄清问题\n\n无。\n\n"
        "## 四、需求详述\n\n占位。\n",
    )


def test_template_structure_clean_minimal_spec(run_script, doc_root):
    sd = doc_root / "specs" / "tmpl-clean"
    _stub_minimal_spec(sd)
    cp = run_script("spec_lint.py", "--spec", str(sd))
    assert cp.returncode == 0
    assert "tmpl" not in cp.stdout, cp.stdout


def test_template_structure_missing_mandatory_warns(run_script, doc_root):
    sd = doc_root / "specs" / "tmpl-missing"
    _stub_minimal_spec(sd)
    # 删掉 "## 三、待澄清问题" 整节
    text = (sd / "requirements.md").read_text("utf-8")
    text = re.sub(
        r"## 三、待澄清问题\n\n.*?\n\n",
        "",
        text,
        count=1,
        flags=re.DOTALL,
    )
    _write_text(sd / "requirements.md", text)
    cp = run_script("spec_lint.py", "--spec", str(sd))
    assert cp.returncode == 0
    assert "tmpl" in cp.stdout
    assert "三、待澄清问题" in cp.stdout
    assert "mandatory" in cp.stdout


def test_template_structure_unknown_section_warns(run_script, doc_root):
    sd = doc_root / "specs" / "tmpl-unknown"
    _stub_minimal_spec(sd)
    text = (sd / "requirements.md").read_text("utf-8")
    # 在末尾添加一个未知章节
    text += "\n## 八、随便发挥的小节\n\n看着办。\n"
    _write_text(sd / "requirements.md", text)
    cp = run_script("spec_lint.py", "--spec", str(sd))
    assert cp.returncode == 0
    assert "tmpl" in cp.stdout
    assert "八、随便发挥的小节" in cp.stdout
    assert "未知章节" in cp.stdout


def test_template_structure_optional_deletion_silent(run_script, doc_root):
    """删 optional 章节不应该报；本身 minimal 已经 0 optional，加进去再删等于不变——
    所以这条用 bugfix.md 的 `九、验收要点（可选）` 验证：有 optional 章节时不报 unknown。"""
    sd = doc_root / "specs" / "tmpl-opt"
    sd.mkdir(parents=True, exist_ok=True)
    _write_text(
        sd / "bugfix.md",
        "# Bugfix\n\n"
        "## 一、问题陈述\n\n占。\n\n"
        "## 二、复现路径\n\n占。\n\n"
        "## 三、影响范围\n\n占。\n\n"
        "## 四、证据\n\n占。\n\n"
        "## 五、待澄清问题\n\n占。\n\n"
        "## 六、根因分析\n\n占。\n\n"
        "## 七、修复方向\n\n占。\n\n"
        "## 八、回归保护\n\n占。\n\n"
        # 不写「九、验收要点（可选）」——optional 删除应静默
    )
    cp = run_script("spec_lint.py", "--spec", str(sd))
    assert cp.returncode == 0
    assert "tmpl" not in cp.stdout, cp.stdout


def test_template_structure_optional_section_kept_is_clean(run_script, doc_root):
    """保留 optional 章节应被视为合规（在名单内，不报 unknown）。"""
    sd = doc_root / "specs" / "tmpl-opt-kept"
    sd.mkdir(parents=True, exist_ok=True)
    _write_text(
        sd / "requirements.md",
        "# 需求文档\n\n"
        "## 一、背景 / 目标 / 范围\n\n占。\n\n"
        "## 二、目标用户与场景\n\n占。\n\n"
        "## 三、待澄清问题\n\n无。\n\n"
        "## 四、需求详述\n\n占。\n\n"
        "## 五、非功能 / 约束（可选）\n\n占。\n\n"
        "## 六、依赖与风险（可选）\n\n占。\n",
    )
    cp = run_script("spec_lint.py", "--spec", str(sd))
    assert cp.returncode == 0
    assert "tmpl" not in cp.stdout, cp.stdout


def test_template_structure_tasks_md_ignored(run_script, doc_root):
    """M4 起 tasks.md 不在 TEMPLATE_OUTLINES 名单——即便存在也完全不被校验。"""
    sd = doc_root / "specs" / "tmpl-legacy-tasks"
    _stub_minimal_spec(sd)
    # 残留的旧 tasks.md（任意章节）不应触发 tmpl WARNING
    _write_text(
        sd / "tasks.md",
        "# 任务\n\n"
        "## 随便发挥的章节\n\n占。\n\n"
        "## 阶段 alpha: 不规范\n\n- [ ] x\n",
    )
    cp = run_script("spec_lint.py", "--spec", str(sd))
    assert cp.returncode == 0
    assert "tmpl" not in cp.stdout, cp.stdout
    assert "tasks.md" not in cp.stdout, cp.stdout


def test_template_structure_missing_file_skipped(run_script, doc_root):
    """文档不存在不报：bugfix.md 缺失不影响 requirements-flavored spec。"""
    sd = doc_root / "specs" / "tmpl-no-bugfix"
    _stub_minimal_spec(sd)
    cp = run_script("spec_lint.py", "--spec", str(sd))
    assert cp.returncode == 0
    # 整个 stdout 里完全没有 bugfix.md 相关
    assert "bugfix.md" not in cp.stdout, cp.stdout
