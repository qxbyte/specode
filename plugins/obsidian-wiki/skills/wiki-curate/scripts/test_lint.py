# -*- coding: utf-8 -*-
import os
import shutil
import tempfile
import unittest
import lint as L


def make_vault(tree):
    root = tempfile.mkdtemp(prefix="wcvault-")
    for rel, content in tree.items():
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
    return root


def make_cfg(purpose_dirs=None, orphan_dirs=None, required_frontmatter=None,
             skip_dirs=None, purpose_heading="用途", system_dir="00-Index/_system"):
    """Build a minimal cfg dict for testing."""
    return {
        "system_dir": system_dir,
        "skip_dirs": skip_dirs if skip_dirs is not None else [".obsidian", "skills"],
        "lint": {
            "purpose_heading": purpose_heading,
            "purpose_dirs": purpose_dirs if purpose_dirs is not None else ["01-Concepts"],
            "orphan_dirs": orphan_dirs if orphan_dirs is not None else ["01-Concepts"],
            "required_frontmatter": required_frontmatter if required_frontmatter is not None else ["类型", "状态", "标签", "更新"],
            "sensitive_dirs": [],
        },
    }


class PurposeTest(unittest.TestCase):
    def test_has_purpose(self):
        self.assertTrue(L.has_purpose("# 标题\n\n## 用途\n\n说明\n"))
        self.assertFalse(L.has_purpose("# 标题\n\n## 说明\n"))

    def test_has_purpose_custom_heading(self):
        # purpose_heading comes from config — a note with a custom-named heading is accepted
        self.assertTrue(L.has_purpose("# Title\n\n## Purpose\n\nDesc\n", heading="Purpose"))
        self.assertFalse(L.has_purpose("# Title\n\n## 用途\n\nDesc\n", heading="Purpose"))

    def test_missing_purpose_only_lint_dirs(self):
        v = make_vault({
            "01-Concepts/good.md": "# G\n## 用途\nok\n",
            "01-Concepts/bad.md": "# B\n## 说明\n无用途\n",
            "07-Ideas/x.md": "# X\n无用途但只读目录\n",   # 不检查
        })
        self.addCleanup(shutil.rmtree, v, True)
        cfg = make_cfg(purpose_dirs=["01-Concepts"])
        miss = L.missing_purpose(v, cfg)
        self.assertIn("01-Concepts/bad.md", miss)
        self.assertNotIn("01-Concepts/good.md", miss)
        self.assertNotIn("07-Ideas/x.md", miss)

    def test_missing_purpose_readme_skip(self):
        v = make_vault({
            "01-Concepts/README.md": "# README\n无用途\n",
            "01-Concepts/note.md": "# N\n## 用途\nok\n",
        })
        self.addCleanup(shutil.rmtree, v, True)
        cfg = make_cfg(purpose_dirs=["01-Concepts"])
        miss = L.missing_purpose(v, cfg)
        self.assertNotIn("01-Concepts/README.md", miss)

    def test_purpose_heading_from_config(self):
        # When config specifies a custom purpose_heading, that heading is accepted
        v = make_vault({
            "01-Concepts/custom.md": "# T\n## Purpose\nok\n",   # uses custom heading
            "01-Concepts/wrong.md": "# T\n## 用途\nok\n",        # uses default heading — NOT accepted
        })
        self.addCleanup(shutil.rmtree, v, True)
        cfg = make_cfg(purpose_dirs=["01-Concepts"], purpose_heading="Purpose")
        miss = L.missing_purpose(v, cfg)
        self.assertNotIn("01-Concepts/custom.md", miss)   # custom heading accepted
        self.assertIn("01-Concepts/wrong.md", miss)       # default heading rejected when config differs


class DupTest(unittest.TestCase):
    def test_duplicate_basenames(self):
        v = make_vault({
            "01-Concepts/设计.md": "x",
            "05-Workflows/设计.md": "x",
            "01-Concepts/唯一.md": "x",
            "04-Tools/skills/wiki-curate/SKILL.md": "x",   # skills 跳过，不计
        })
        self.addCleanup(shutil.rmtree, v, True)
        cfg = make_cfg(skip_dirs=["skills"])
        dup = L.duplicate_basenames(v, cfg)
        self.assertIn("设计.md", dup)
        self.assertEqual(set(dup["设计.md"]), {"01-Concepts/设计.md", "05-Workflows/设计.md"})
        self.assertNotIn("唯一.md", dup)
        self.assertNotIn("SKILL.md", dup)


class FmTest(unittest.TestCase):
    GOOD = "---\n类型: 概念\n状态: 草稿\n标签:\n  - x\n更新: 2026-06-20\n---\n# T\n## 用途\nok\n"
    BAD = "---\n类型: 概念\n标签:\n  - x\n---\n# T\n## 用途\nok\n"  # 缺 状态/更新

    def test_frontmatter_issues(self):
        v = make_vault({"01-Concepts/good.md": self.GOOD, "01-Concepts/bad.md": self.BAD})
        self.addCleanup(shutil.rmtree, v, True)
        cfg = make_cfg(purpose_dirs=["01-Concepts"])
        issues = dict(L.frontmatter_issues(v, cfg))
        self.assertIn("01-Concepts/bad.md", issues)
        self.assertEqual(set(issues["01-Concepts/bad.md"]), {"状态", "更新"})
        self.assertNotIn("01-Concepts/good.md", issues)

    def test_frontmatter_crlf(self):
        v = make_vault({})
        self.addCleanup(shutil.rmtree, v, True)
        p = os.path.join(v, "01-Concepts", "crlf.md")
        os.makedirs(os.path.dirname(p))
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write("---\r\n类型: 概念\r\n状态: 草稿\r\n标签:\r\n  - x\r\n更新: 2026-06-20\r\n---\r\n# T\r\n## 用途\r\nok\r\n")
        cfg = make_cfg(purpose_dirs=["01-Concepts"])
        issues = dict(L.frontmatter_issues(v, cfg))
        self.assertNotIn("01-Concepts/crlf.md", issues)   # CRLF 不应导致误报缺字段

    def test_frontmatter_anchored_close(self):
        # 正文里的 --- 分隔行不被当作闭合（有真闭合时正常解析）
        text = "---\n类型: 概念\n状态: 草稿\n标签:\n  - x\n更新: 2026-06-20\n---\n正文 --- 行内\n"
        v = make_vault({"01-Concepts/anchor.md": text})
        self.addCleanup(shutil.rmtree, v, True)
        cfg = make_cfg(purpose_dirs=["01-Concepts"])
        issues = dict(L.frontmatter_issues(v, cfg))
        self.assertNotIn("01-Concepts/anchor.md", issues)

    def test_frontmatter_missing_keys(self):
        # Only the keys that are missing should be reported
        text = "---\n类型: 概念\n---\n# T\n## 用途\nok\n"  # 缺 状态/标签/更新
        v = make_vault({"01-Concepts/partial.md": text})
        self.addCleanup(shutil.rmtree, v, True)
        cfg = make_cfg(purpose_dirs=["01-Concepts"])
        issues = dict(L.frontmatter_issues(v, cfg))
        self.assertIn("01-Concepts/partial.md", issues)
        self.assertEqual(set(issues["01-Concepts/partial.md"]), {"状态", "标签", "更新"})


class OrphanTest(unittest.TestCase):
    def test_orphans(self):
        v = make_vault({
            "01-Concepts/被引.md": "# 被引\n## 用途\nx\n",
            "01-Concepts/引用者.md": "# 引用者\n## 用途\n见 [[被引]]\n",
            "01-Concepts/孤儿.md": "# 孤儿\n## 用途\n没人链我\n",
            "01-Concepts/README.md": "索引不算孤儿\n",
            "05-Workflows/路径引.md": "# x\n## 用途\n见 [[01-Concepts/路径目标|别名]]\n",
            "01-Concepts/路径目标.md": "# 路径目标\n## 用途\nx\n",
        })
        self.addCleanup(shutil.rmtree, v, True)
        cfg = make_cfg(orphan_dirs=["01-Concepts"])
        orph = L.orphans(v, cfg)
        self.assertIn("01-Concepts/孤儿.md", orph)
        self.assertNotIn("01-Concepts/被引.md", orph)         # 被 basename 链
        self.assertNotIn("01-Concepts/路径目标.md", orph)      # 被全路径链
        self.assertNotIn("01-Concepts/README.md", orph)        # README 排除

    def test_link_in_code_fence_ignored(self):
        v = make_vault({
            "01-Concepts/孤儿.md": "# 孤儿\n## 用途\nx\n",
            "01-Concepts/假引用.md": "# x\n## 用途\n```\n[[孤儿]]\n```\n",
        })
        self.addCleanup(shutil.rmtree, v, True)
        cfg = make_cfg(orphan_dirs=["01-Concepts"])
        self.assertIn("01-Concepts/孤儿.md", L.orphans(v, cfg))     # 代码块内引用不算

    def test_self_link_still_orphan(self):
        v = make_vault({"01-Concepts/孤儿.md": "# 孤儿\n## 用途\n见 [[孤儿]]\n"})
        self.addCleanup(shutil.rmtree, v, True)
        cfg = make_cfg(orphan_dirs=["01-Concepts"])
        self.assertIn("01-Concepts/孤儿.md", L.orphans(v, cfg))


class LintAggTest(unittest.TestCase):
    def test_lint_keys(self):
        v = make_vault({"01-Concepts/a.md": "# a\n无用途\n"})
        self.addCleanup(shutil.rmtree, v, True)
        cfg = make_cfg()
        res = L.lint(v, cfg)
        self.assertEqual(set(res.keys()),
                         {"missing_purpose", "duplicate_basenames", "orphans", "frontmatter_issues"})
        self.assertIn("01-Concepts/a.md", res["missing_purpose"])

    def test_render_report(self):
        res = {"missing_purpose": ["01-Concepts/a.md"], "duplicate_basenames": {"设计.md": ["x/设计.md", "y/设计.md"]},
               "orphans": ["02-Models/o.md"], "frontmatter_issues": [("01-Concepts/a.md", ["更新"])]}
        md = L.render_report(res)
        self.assertIn("# wiki-curate 内容体检报告", md)
        self.assertIn("01-Concepts/a.md", md)
        self.assertIn("设计.md", md)
        self.assertIn("坏链与结构漂移请运行 `/wiki-struct check`", md)


if __name__ == "__main__":
    unittest.main()
