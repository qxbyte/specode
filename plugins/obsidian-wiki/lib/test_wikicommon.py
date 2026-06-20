# test_wikicommon.py
import os, json, shutil, tempfile, unittest
import wikicommon as wc

def mkvault(tree):
    root = tempfile.mkdtemp(prefix="wcommon-")
    for rel, content in tree.items():
        p = os.path.join(root, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f: f.write(content)
    return root

class LoadTest(unittest.TestCase):
    def test_load_config_ok(self):
        v = mkvault({".wiki/config.json": json.dumps({"index_dir": "00-Index"})})
        self.addCleanup(shutil.rmtree, v, True)
        self.assertEqual(wc.load_config(v)["index_dir"], "00-Index")
    def test_load_config_missing_raises(self):
        v = mkvault({"x.md": "x"}); self.addCleanup(shutil.rmtree, v, True)
        with self.assertRaises(SystemExit): wc.load_config(v)
    def test_read_text_crlf(self):
        v = mkvault({}); self.addCleanup(shutil.rmtree, v, True)
        p = os.path.join(v, "a.md")
        with open(p, "w", encoding="utf-8", newline="") as f: f.write("a\r\nb\r\n")
        self.assertEqual(wc.read_text(p), "a\nb\n")
    def test_iter_md_skips(self):
        v = mkvault({"01/a.md":"x","01/skills/b.md":"x","01/.obsidian/c.md":"x"})
        self.addCleanup(shutil.rmtree, v, True)
        got = {wc.rel(v,p) for p in wc.iter_md(v, ["01"], [".obsidian","skills"])}
        self.assertEqual(got, {"01/a.md"})

class ParseTest(unittest.TestCase):
    def test_link_targets(self):
        t = "见 [[A|别名]] 和 [[01/B]] 与 [[占位<x>]]\n```\n[[代码内]]\n```\n| [[C\\|x]] |"
        got = set(wc.link_targets(t))
        self.assertEqual(got, {"A", "01/B", "C"})
        self.assertNotIn("代码内", got)
    def test_frontmatter_keys(self):
        good = "---\n类型: 概念\n标签:\n  - x\n更新: 2026-06-20\n---\n# T\n"
        self.assertEqual(wc.frontmatter_keys(good), {"类型", "标签", "更新"})
        self.assertEqual(wc.frontmatter_keys("无"), set())
    def test_frontmatter_close_anchored(self):
        # 正文 --- 分隔不被当闭合（有真闭合时正常解析）
        t = "---\n类型: 概念\n更新: x\n---\n正文 --- 行内\n"
        self.assertEqual(wc.frontmatter_keys(t), {"类型", "更新"})

if __name__ == "__main__": unittest.main()
