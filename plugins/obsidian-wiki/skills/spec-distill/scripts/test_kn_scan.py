# -*- coding: utf-8 -*-
import os
import sys
import shutil
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "lib"))
import wikicommon as wc
import kn_scan as ks


def make_vault(tree):
    root = tempfile.mkdtemp(prefix="sdvault-")
    for rel, content in tree.items():
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
    return root


def minimal_cfg(**overrides):
    """Return a minimal config dict suitable for passing to kn_scan functions."""
    cfg = {
        "system_dir": "00-Index/_system",
        "knowledge": {
            "kb_root": "10-Work/知识库",
            "spec_in_candidates": ["SpecIn", "spec-in"],
            "spec_source_default": "windows-Public/specs",
            "memory_file": "MEMORY.md",
            "memory_reverse_section": "需求反向索引",
        }
    }
    for k, v in overrides.items():
        if isinstance(v, dict) and k in cfg and isinstance(cfg[k], dict):
            cfg[k].update(v)
        else:
            cfg[k] = v
    return cfg


class KeyTest(unittest.TestCase):
    def test_numeric_prefix(self):
        self.assertEqual(ks.project_key("114371-银行账号加密重构"), "114371")
        self.assertEqual(ks.project_key("128978-财务中台更换MQ订阅-wesure-fap"), "128978")

    def test_no_prefix(self):
        self.assertEqual(ks.project_key("小程序"), "小程序")

    def test_find_specin_root(self):
        v = make_vault({"SpecIn/README.md": "x"})
        self.addCleanup(shutil.rmtree, v, True)
        cfg = minimal_cfg()
        self.assertEqual(ks.find_specin_root(v, cfg), "SpecIn")
        v2 = make_vault({"spec-in/README.md": "x"})
        self.addCleanup(shutil.rmtree, v2, True)
        self.assertEqual(ks.find_specin_root(v2, cfg), "spec-in")

    def test_find_specin_root_uses_config_candidates(self):
        """find_specin_root iterates cfg["knowledge"]["spec_in_candidates"], not hardcoded names."""
        v = make_vault({"my-specs-in/README.md": "x"})
        self.addCleanup(shutil.rmtree, v, True)
        cfg = minimal_cfg(knowledge={"spec_in_candidates": ["my-specs-in", "SpecIn"],
                                     "kb_root": "10-Work/知识库",
                                     "spec_source_default": "windows-Public/specs",
                                     "memory_file": "MEMORY.md",
                                     "memory_reverse_section": "需求反向索引"})
        self.assertEqual(ks.find_specin_root(v, cfg), "my-specs-in")


class ParseMemoryTest(unittest.TestCase):
    MEM = (
        "# Knowledge Base Index — 新收付（fin）\n\n"
        "## 知识文档索引\n\n"
        "| 知识文档 | 摘要 | 关联需求 |\n"
        "|---|---|---|\n"
        "| [[A]] | a | 121659, 123000 |\n\n"
        "## 需求反向索引\n\n"
        "| 需求ID | 需求名称 | 关联知识 |\n"
        "|--------|----------|----------|\n"
        "| 114371 | 脱敏 | [[A]] |\n"
        "| 121659 | 授权 | [[A]], [[B]] |\n"
        "| 125577 | 关闭 | [[C]] |\n\n"
        "## 知识关联图\n\n```\n图\n```\n"
    )

    def test_extracts_only_reverse_index_ids(self):
        ids = ks.parse_memory_requirements(self.MEM)
        self.assertEqual(ids, {"114371", "121659", "125577"})

    def test_header_and_separator_skipped(self):
        ids = ks.parse_memory_requirements(self.MEM)
        self.assertNotIn("需求ID", ids)
        self.assertFalse(any(set(x) <= set("-: ") for x in ids))

    def test_multi_id_cell_split(self):
        mem = ("## 需求反向索引\n| 需求ID | x |\n|---|---|\n| 121659、123000 | y |\n")
        self.assertEqual(ks.parse_memory_requirements(mem), {"121659", "123000"})

    def test_parse_failure_returns_empty(self):
        self.assertEqual(ks.parse_memory_requirements("没有任何表格"), set())

    def test_empty_placeholder_skipped(self):
        mem = ("## 需求反向索引\n| 需求ID | x |\n|---|---|\n| <空> | y |\n")
        self.assertEqual(ks.parse_memory_requirements(mem), set())

    def test_table_after_next_section_not_picked_up(self):
        mem = (
            "## 需求反向索引\n| 需求ID | x |\n|---|---|\n| 111 | a |\n\n"
            "## 其他节\n| 需求ID | x |\n|---|---|\n| 999 | b |\n"
        )
        ids = ks.parse_memory_requirements(mem)
        self.assertEqual(ids, {"111"})
        self.assertNotIn("999", ids)

    def test_memory_reverse_section_from_config(self):
        """parse_memory_requirements uses the section name passed in, not hardcoded string."""
        mem = (
            "## 需求反向索引\n| 需求ID | x |\n|---|---|\n| 111 | a |\n\n"
            "## Requirement Index\n| 需求ID | x |\n|---|---|\n| 999 | b |\n"
        )
        # Default section name → only picks up 111
        ids_default = ks.parse_memory_requirements(mem)
        self.assertEqual(ids_default, {"111"})
        self.assertNotIn("999", ids_default)
        # Custom section name from config → only picks up 999
        ids_custom = ks.parse_memory_requirements(mem, reverse_section="Requirement Index")
        self.assertEqual(ids_custom, {"999"})
        self.assertNotIn("111", ids_custom)


class CoveredTest(unittest.TestCase):
    def setUp(self):
        fin = ("## 需求反向索引\n| 需求ID | x | y |\n|---|---|---|\n"
               "| 114371 | a | [[A]] |\n| 121659 | b | [[B]] |\n")
        sfmi = ("## 需求反向索引\n| 需求ID | x | y |\n|---|---|---|\n"
                "| 114371-Global | g | [[G]] |\n")
        self.v = make_vault({
            "10-Work/知识库/新收付（fin）/MEMORY.md": fin,
            "10-Work/知识库/SFMI 保险核心系统（Global）/MEMORY.md": sfmi,
        })
        self.addCleanup(shutil.rmtree, self.v, True)
        self.cfg = minimal_cfg()

    def test_union_and_mapping(self):
        ids, mapping = ks.covered_requirements(self.v, self.cfg)
        self.assertEqual(ids, {"114371", "121659", "114371-Global"})
        self.assertIn("新收付（fin）", mapping["114371"])
        self.assertIn("SFMI 保险核心系统（Global）", mapping["114371-Global"])

    def test_no_kb_dir(self):
        v = make_vault({"README.md": "x"})
        self.addCleanup(shutil.rmtree, v, True)
        ids, mapping = ks.covered_requirements(v, self.cfg)
        self.assertEqual(ids, set())
        self.assertEqual(mapping, {})

    def test_covered_uses_config_kb_root(self):
        """covered_requirements uses cfg["knowledge"]["kb_root"], not hardcoded path."""
        mem = ("## 需求反向索引\n| 需求ID | x |\n|---|---|\n| 999 | a |\n")
        v = make_vault({"custom-kb/sys/MEMORY.md": mem})
        self.addCleanup(shutil.rmtree, v, True)
        cfg = minimal_cfg(knowledge={"kb_root": "custom-kb",
                                     "spec_in_candidates": ["SpecIn", "spec-in"],
                                     "spec_source_default": "windows-Public/specs",
                                     "memory_file": "MEMORY.md",
                                     "memory_reverse_section": "需求反向索引"})
        ids, mapping = ks.covered_requirements(v, cfg)
        self.assertIn("999", ids)

    def test_covered_uses_config_memory_reverse_section(self):
        """covered_requirements reads the reverse section name from config."""
        mem = (
            "## 需求反向索引\n| 需求ID | x |\n|---|---|\n| 111 | a |\n\n"
            "## Custom Reverse Index\n| 需求ID | x |\n|---|---|\n| 999 | a |\n"
        )
        v = make_vault({"10-Work/知识库/sys/MEMORY.md": mem})
        self.addCleanup(shutil.rmtree, v, True)
        # With default section name: picks up 111
        cfg_default = minimal_cfg()
        ids_default, _ = ks.covered_requirements(v, cfg_default)
        self.assertIn("111", ids_default)
        self.assertNotIn("999", ids_default)
        # With custom section name from config: picks up 999
        cfg_custom = minimal_cfg(knowledge={"kb_root": "10-Work/知识库",
                                            "spec_in_candidates": ["SpecIn", "spec-in"],
                                            "spec_source_default": "windows-Public/specs",
                                            "memory_file": "MEMORY.md",
                                            "memory_reverse_section": "Custom Reverse Index"})
        ids_custom, _ = ks.covered_requirements(v, cfg_custom)
        self.assertIn("999", ids_custom)
        self.assertNotIn("111", ids_custom)


class ScanTest(unittest.TestCase):
    def setUp(self):
        fin = ("## 需求反向索引\n| 需求ID | x | y |\n|---|---|---|\n"
               "| 114371 | a | [[A]] |\n| 121659 | b | [[B]] |\n")
        self.v = make_vault({
            "10-Work/知识库/新收付（fin）/MEMORY.md": fin,
            "SpecIn/windows-Public/specs/114371-脱敏/design.md": "x",
            "SpecIn/windows-Public/specs/121659-授权/design.md": "x",
            "SpecIn/windows-Public/specs/116274-财务中台-fap/design.md": "x",
            "SpecIn/windows-Public/specs/小程序/design.md": "x",
        })
        self.addCleanup(shutil.rmtree, self.v, True)
        self.cfg = minimal_cfg()

    def test_list_projects(self):
        ps = ks.list_specin_projects(self.v, "SpecIn/windows-Public/specs")
        names = {n for n, k in ps}
        self.assertIn("116274-财务中台-fap", names)
        keys = dict(ps)
        self.assertEqual(keys["116274-财务中台-fap"], "116274")

    def test_scan_pending_vs_done(self):
        res = ks.scan(self.v, self.cfg, "SpecIn/windows-Public/specs")
        pending_keys = {k for n, k in res["pending"]}
        done_keys = {k for n, k in res["done"]}
        self.assertIn("116274", pending_keys)
        self.assertIn("小程序", pending_keys)
        self.assertEqual(done_keys, {"114371", "121659"})

    def test_scan_autodetects_source(self):
        res = ks.scan(self.v, self.cfg)  # 不传 source，自动探测 SpecIn/windows-Public/specs
        self.assertEqual(res["source"], "SpecIn/windows-Public/specs")

    def test_scan_no_specin_dir(self):
        v = make_vault({"10-Work/知识库/sys/MEMORY.md": "## 需求反向索引\n| 需求ID | x |\n|---|---|\n| 1 | a |\n"})
        self.addCleanup(shutil.rmtree, v, True)
        res = ks.scan(v, self.cfg)
        self.assertIsNone(res["source"])
        self.assertEqual(res["pending"], [])
        self.assertEqual(res["done"], [])
        self.assertEqual(res["covered_ids"], ["1"])

    def test_scan_uses_config_spec_source_default(self):
        """scan() builds default source from cfg["knowledge"]["spec_source_default"]."""
        mem = ("## 需求反向索引\n| 需求ID | x |\n|---|---|\n| 999 | a |\n")
        v = make_vault({
            "10-Work/知识库/sys/MEMORY.md": mem,
            "SpecIn/custom-source/111-proj/design.md": "x",
        })
        self.addCleanup(shutil.rmtree, v, True)
        cfg = minimal_cfg(knowledge={"kb_root": "10-Work/知识库",
                                     "spec_in_candidates": ["SpecIn", "spec-in"],
                                     "spec_source_default": "custom-source",
                                     "memory_file": "MEMORY.md",
                                     "memory_reverse_section": "需求反向索引"})
        res = ks.scan(v, cfg)
        self.assertEqual(res["source"], "SpecIn/custom-source")
        pending_keys = {k for n, k in res["pending"]}
        self.assertIn("111", pending_keys)


class ReportTest(unittest.TestCase):
    def test_render_report(self):
        res = {"source": "SpecIn/windows-Public/specs",
               "covered_ids": ["114371", "121659"],
               "systems": ["新收付（fin）"],
               "pending": [("116274-财务中台-fap", "116274"), ("小程序", "小程序")],
               "done": [("114371-脱敏", "114371")],
               "mapping": {"114371": ["新收付（fin）"]}}
        md = ks.render_report(res)
        self.assertIn("# spec-distill 增量报告", md)
        self.assertIn("116274-财务中台-fap", md)
        self.assertIn("待沉淀", md)
        self.assertIn("已覆盖", md)
        self.assertIn("SpecIn/windows-Public/specs", md)


if __name__ == "__main__":
    unittest.main()
