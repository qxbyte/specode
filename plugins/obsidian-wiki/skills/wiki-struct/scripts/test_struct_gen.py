# -*- coding: utf-8 -*-
import os
import shutil
import tempfile
import unittest
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "lib"))
import struct_gen as sg


def make_vault(tree):
    """tree: dict 路径->内容；返回临时 vault 根目录。"""
    root = tempfile.mkdtemp(prefix="wsvault-")
    for rel, content in tree.items():
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
    return root


def _minimal_cfg(extra_dirs=None):
    """返回最小 config dict，仅含基本字段。"""
    dirs = extra_dirs if extra_dirs is not None else [
        {"dir": "00-Index", "emoji": "🗂️", "desc": "索引", "callout": "abstract",
         "readme": False, "partition": False, "sensitive": False},
        {"dir": "01-Concepts", "emoji": "📘", "desc": "概念", "callout": "note",
         "readme": True, "partition": True, "sensitive": False},
    ]
    return {
        "index_dir": "00-Index",
        "home_file": "00-Index/Home.md",
        "system_dir": "00-Index/_system",
        "skip_dirs": [".obsidian", "skills"],
        "structure": {"dirs": dirs},
    }


class MarkerTest(unittest.TestCase):
    SAMPLE = ("前言\n"
              "<!-- wiki-struct:tree start -->\n旧内容\n<!-- wiki-struct:tree end -->\n"
              "后语\n")

    def test_has_block(self):
        self.assertTrue(sg.has_block(self.SAMPLE))
        self.assertFalse(sg.has_block("无 marker"))

    def test_get_block(self):
        self.assertEqual(sg.get_block(self.SAMPLE), "旧内容")
        self.assertIsNone(sg.get_block("无"))

    def test_replace_block_preserves_outside(self):
        out = sg.replace_block(self.SAMPLE, "新内容")
        self.assertIn("前言", out)
        self.assertIn("后语", out)
        self.assertEqual(sg.get_block(out), "新内容")

    def test_replace_no_marker_raises(self):
        with self.assertRaises(ValueError):
            sg.replace_block("无 marker", "x")

    def test_replace_unbalanced_raises(self):
        bad = "只有 <!-- wiki-struct:tree start --> 没结尾"
        with self.assertRaises(ValueError):
            sg.replace_block(bad, "x")

    def test_replace_reversed_raises(self):
        bad = ("<!-- wiki-struct:tree end -->\n"
               "<!-- wiki-struct:tree start -->\n")
        with self.assertRaises(ValueError):
            sg.replace_block(bad, "x")


class WalkTest(unittest.TestCase):
    def setUp(self):
        self.v = make_vault({
            "A/README.md": "x",
            "A/sub/note1.md": "x",
            "A/sub/note2.md": "x",
            "A/empty/.keep": "x",          # 无 md 的目录
            "A/skills/SKILL.md": "x",      # 必须被跳过
            "A/.obsidian/cfg.md": "x",     # 必须被跳过
        })
        self.addCleanup(shutil.rmtree, self.v, True)
        self.skip = ["skills", ".obsidian"]

    def test_rel(self):
        import wikicommon as wc
        self.assertEqual(wc.rel(self.v, os.path.join(self.v, "A", "x.md")), "A/x.md")

    def test_has_md(self):
        self.assertTrue(sg._has_md(os.path.join(self.v, "A", "sub")))
        self.assertFalse(sg._has_md(os.path.join(self.v, "A", "empty")))

    def test_walk_skips_and_orders(self):
        lines = sg.walk_tree(self.v, os.path.join(self.v, "A"), 0, self.skip)
        text = "\n".join(lines)
        self.assertIn("- **sub/**", text)
        self.assertIn("[[A/sub/note1|note1]]", text)
        self.assertNotIn("skills", text)        # skills 子树跳过
        self.assertNotIn("empty", text)         # 空目录跳过
        self.assertNotIn(".obsidian", text)
        # 文件夹排在文件前；缩进 4 空格
        self.assertIn("    - [[A/sub/note1|note1]]", text)

    def test_walk_skip_self(self):
        lines = sg.walk_tree(self.v, os.path.join(self.v, "A"), 0, self.skip,
                             skip_self_rel="A/README.md")
        self.assertNotIn("[[A/README|README]]", "\n".join(lines))

    def test_count_md(self):
        # A/README.md + A/sub/note1 + note2 = 3（skills/.obsidian 跳过）
        self.assertEqual(sg.count_md(self.v, os.path.join(self.v, "A"), self.skip), 3)


class RenderTest(unittest.TestCase):
    def setUp(self):
        self.v = make_vault({
            "00-Index/Home.md": "x",
            "01-Concepts/README.md": "x",
            "01-Concepts/a.md": "x",
            "01-Concepts/Java/b.md": "x",
            "00-Index/01-Concepts.md": "x",
        })
        self.addCleanup(shutil.rmtree, self.v, True)
        self.cfg = _minimal_cfg()
        self.skip = self.cfg["skip_dirs"]

    def test_render_dir_list_plain(self):
        out = sg.render_dir_list(self.v, "01-Concepts", self.skip,
                                 skip_self_rel="01-Concepts/README.md")
        self.assertIn("- **Java/**", out)
        self.assertIn("[[01-Concepts/a|a]]", out)
        self.assertNotIn("[[01-Concepts/README|README]]", out)  # 跳过自身
        self.assertNotIn("> ", out)                              # 普通列表，无 callout 前缀

    def test_render_dir_list_empty(self):
        v2 = make_vault({"08-Sources/README.md": "x"})
        self.addCleanup(shutil.rmtree, v2, True)
        out = sg.render_dir_list(v2, "08-Sources", self.skip,
                                 skip_self_rel="08-Sources/README.md")
        self.assertIn("暂无", out)

    def test_render_home_callouts(self):
        out = sg.render_home(self.v, self.cfg)
        self.assertIn("> [!tip] 用法", out)
        self.assertIn("> [!abstract]- 🗂️ 00-Index", out)
        self.assertIn("> [!note]- 📘 01-Concepts", out)
        self.assertIn("· 分区索引 [[00-Index/01-Concepts|↗]]", out)
        self.assertIn("> - **Java/**", out)                      # callout 内树带 "> " 前缀
        self.assertNotIn("[[00-Index/Home|Home]]", out)          # Home 自身不进树

    def test_render_home_uses_config_dirs(self):
        cfg = {"index_dir": "00-Index", "skip_dirs": [".obsidian", "skills"],
               "home_file": "00-Index/Home.md",
               "system_dir": "00-Index/_system",
               "structure": {"dirs": [
                   {"dir": "01-Concepts", "emoji": "📘", "desc": "概念",
                    "callout": "note", "readme": True, "partition": True, "sensitive": False}
               ]}}
        v = make_vault({"01-Concepts/a.md": "x", "00-Index/Home.md": "x"})
        self.addCleanup(shutil.rmtree, v, True)
        out = sg.render_home(v, cfg)
        self.assertIn("📘 01-Concepts", out)
        self.assertIn("· 分区索引 [[00-Index/01-Concepts|↗]]", out)


class CheckTest(unittest.TestCase):
    def _vault_with_markers(self, home_inner):
        wrap = ("---\n类型: 索引\n---\n## 目录树\n"
                "<!-- wiki-struct:tree start -->\n%s\n<!-- wiki-struct:tree end -->\n")
        return make_vault({
            "00-Index/Home.md": wrap % home_inner,
            "00-Index/_system/.keep": "x",
            "01-Concepts/README.md": wrap % "stale",
            "01-Concepts/a.md": "x",
            "00-Index/01-Concepts.md": wrap % "stale",
        })

    def test_check_reports_drift(self):
        v = self._vault_with_markers("stale-home")
        self.addCleanup(shutil.rmtree, v, True)
        r = sg.check(v, _minimal_cfg())
        self.assertTrue(any("Home.md" in x for x in r["drift"]))
        self.assertTrue(any("01-Concepts/README.md" in x for x in r["drift"]))

    def test_check_reports_missing_marker(self):
        v = make_vault({"00-Index/Home.md": "无 marker\n",
                        "00-Index/_system/.keep": "x"})
        self.addCleanup(shutil.rmtree, v, True)
        r = sg.check(v, _minimal_cfg())
        self.assertTrue(any("Home.md" in x for x in r["missing_marker"]))

    def test_check_reports_missing_file(self):
        v = make_vault({"00-Index/_system/.keep": "x"})  # 无 Home.md
        self.addCleanup(shutil.rmtree, v, True)
        r = sg.check(v, _minimal_cfg())
        self.assertTrue(any("Home.md" in x for x in r["missing_file"]))


class ApplyTest(unittest.TestCase):
    def setUp(self):
        wrap = ("## 目录树\n<!-- wiki-struct:tree start -->\nstale\n<!-- wiki-struct:tree end -->\n人工尾部\n")
        self.v = make_vault({
            "00-Index/Home.md": wrap,
            "01-Concepts/README.md": wrap,
            "01-Concepts/a.md": "x",
            "00-Index/01-Concepts.md": wrap,
        })
        self.addCleanup(shutil.rmtree, self.v, True)
        self.cfg = _minimal_cfg()

    def test_apply_updates_block_and_keeps_outside(self):
        changed = sg.apply(self.v, self.cfg, scope="all")
        self.assertTrue(any("Home.md" in c for c in changed))
        with open(os.path.join(self.v, "00-Index/Home.md"), encoding="utf-8") as f:
            home = f.read()
        self.assertIn("人工尾部", home)                 # marker 外保留
        self.assertIn("> [!note]- 📘 01-Concepts", sg.get_block(home))

    def test_apply_scope_partitions_only(self):
        changed = sg.apply(self.v, self.cfg, scope="partitions")
        self.assertTrue(all("00-Index/01-Concepts.md" in c or "00-Index" in c for c in changed))
        # README 未被改
        self.assertNotIn("01-Concepts/README.md", changed)

    def test_apply_skips_files_without_marker(self):
        v = make_vault({"00-Index/Home.md": "无 marker\n", "01-Concepts/README.md": "x", "01-Concepts/a.md": "x"})
        self.addCleanup(shutil.rmtree, v, True)
        changed = sg.apply(v, _minimal_cfg(), scope="all")
        self.assertEqual(changed, [])

    def test_apply_scope_home(self):
        changed = sg.apply(self.v, self.cfg, scope="home")
        # Only Home.md should be changed
        self.assertTrue(any("Home.md" in c for c in changed))
        self.assertFalse(any("README.md" in c for c in changed))
        self.assertFalse(any("01-Concepts.md" in c for c in changed))

    def test_apply_scope_readmes(self):
        changed = sg.apply(self.v, self.cfg, scope="readmes")
        # Only README.md should be changed, not the partition page or Home
        self.assertTrue(any("README.md" in c for c in changed))
        self.assertFalse(any("Home.md" in c for c in changed))
        self.assertFalse(any("00-Index/01-Concepts.md" in c for c in changed))


class BrokenLinkTest(unittest.TestCase):
    def setUp(self):
        self.v = make_vault({
            "01-Concepts/a.md": "见 [[01-Concepts/b|B]] 和 [[01-Concepts/missing|缺]]\n",
            "01-Concepts/b.md": "x",
            "01-Concepts/img.md": "![[_scaffold/附件/p.png]]\n",
            "_scaffold/附件/p.png": "binary",
            "01-Concepts/code.md": "```\n[[01-Concepts/incode]]\n```\n",   # 代码块内跳过
            "01-Concepts/tbl.md": "| [[01-Concepts/b\\|B]] |\n",           # 表格转义 \|
            "00-Index/_system/lint-report.md": "[[谁知道/不存在]]\n",       # _system 报告跳过
        })
        self.addCleanup(shutil.rmtree, self.v, True)
        self.cfg = _minimal_cfg()
        self.skip = self.cfg["skip_dirs"]

    def test_broken_detects_only_real(self):
        broken = sg.find_broken_links(self.v, self.skip, system_dir=self.cfg["system_dir"])
        targets = [t for _f, t in broken]
        self.assertIn("01-Concepts/missing", targets)
        self.assertNotIn("01-Concepts/b", targets)          # 存在
        self.assertNotIn("_scaffold/附件/p.png", targets)    # 图片存在
        self.assertNotIn("01-Concepts/incode", targets)     # 代码块内
        self.assertFalse(any("谁知道" in t for t in targets))  # _system 跳过

    def test_check_includes_broken(self):
        r = sg.check(self.v, self.cfg)
        self.assertIn("broken", r)

    def test_find_broken_links_uses_config_system_dir(self):
        v = make_vault({
            "01-Concepts/a.md": "见 [[01-Concepts/missing|缺]]\n",
            "Idx/_sys/report.md": "[[谁知道/不存在]]\n",   # 自定义 system_dir 下的报告应被跳过
        })
        self.addCleanup(shutil.rmtree, v, True)
        broken = sg.find_broken_links(v, [".obsidian", "skills"], system_dir="Idx/_sys")
        targets = [t for _f, t in broken]
        self.assertIn("01-Concepts/missing", targets)
        self.assertFalse(any("谁知道" in t for t in targets))   # 自定义 system_dir 被跳过


class ReportTest(unittest.TestCase):
    def test_render_report_sections(self):
        res = {"drift": ["00-Index/Home.md"], "missing_marker": ["01-Concepts/README.md"],
               "missing_file": [], "broken": [("a.md", "x/y")]}
        md = sg.render_report(res)
        self.assertIn("# wiki-struct 结构体检报告", md)
        self.assertIn("00-Index/Home.md", md)
        self.assertIn("缺 marker", md)
        self.assertIn("x/y", md)


if __name__ == "__main__":
    unittest.main()
