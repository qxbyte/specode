"""Tests for spec_lint.py:rule_template_structure。

每条用例都通过 spec_init.py 拿到"干净的"模板文档，再针对性改写章节集合，
确认新规则对 mandatory 缺失 / unknown 新增 / dynamic 前缀 / optional 删除
等四种情况的判定符合预期。
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
    _write_text(
        spec_dir / "tasks.md",
        "# 任务\n\n"
        "## 概述\n\n占位。\n\n"
        "## 阶段 1: 占位\n\n- [ ] 1.1 占位\n\n"
        "## 测试要点\n\n占位。\n\n"
        "## 验收\n\n占位。\n",
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


def test_template_structure_dynamic_phase_prefix_silent(run_script, doc_root):
    """tasks.md 的 `## 阶段 N: …` 动态前缀应被视为合规（数量任意）。"""
    sd = doc_root / "specs" / "tmpl-stages"
    sd.mkdir(parents=True, exist_ok=True)
    _write_text(
        sd / "tasks.md",
        "# 任务\n\n"
        "## 概述\n\n占。\n\n"
        "## 阶段 1: 起步\n\n- [ ] 1.1\n\n"
        "## 阶段 2: 推进\n\n- [ ] 2.1\n\n"
        "## 阶段 3: 收尾\n\n- [ ] 3.1\n\n"
        "## 测试要点\n\n占。\n\n"
        "## 验收\n\n占。\n",
    )
    cp = run_script("spec_lint.py", "--spec", str(sd))
    assert cp.returncode == 0
    assert "tmpl" not in cp.stdout, cp.stdout


def test_template_structure_phase_label_without_number_is_unknown(run_script, doc_root):
    """前缀必须严格匹配 `阶段 N:`——`阶段 X:`（X 非数字）不应被视为 dynamic 合规。"""
    sd = doc_root / "specs" / "tmpl-bad-stage"
    sd.mkdir(parents=True, exist_ok=True)
    _write_text(
        sd / "tasks.md",
        "# 任务\n\n"
        "## 概述\n\n占。\n\n"
        "## 阶段 alpha: 不规范\n\n- [ ] x\n\n"
        "## 测试要点\n\n占。\n\n"
        "## 验收\n\n占。\n",
    )
    cp = run_script("spec_lint.py", "--spec", str(sd))
    assert cp.returncode == 0
    assert "tmpl" in cp.stdout
    assert "阶段 alpha" in cp.stdout


def test_template_structure_missing_file_skipped(run_script, doc_root):
    """文档不存在不报：bugfix.md 缺失不影响 requirements-flavored spec。"""
    sd = doc_root / "specs" / "tmpl-no-bugfix"
    _stub_minimal_spec(sd)
    cp = run_script("spec_lint.py", "--spec", str(sd))
    assert cp.returncode == 0
    # 整个 stdout 里完全没有 bugfix.md 相关
    assert "bugfix.md" not in cp.stdout, cp.stdout
