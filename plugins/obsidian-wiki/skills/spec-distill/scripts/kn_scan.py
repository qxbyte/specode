#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""spec-distill 增量检测：找出 SpecIn 中尚未进入任何系统 MEMORY 的项目。"""
import os, sys, re, argparse
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "lib"))
import wikicommon as wc


def find_specin_root(vault, cfg):
    for name in cfg["knowledge"]["spec_in_candidates"]:
        if os.path.isdir(os.path.join(vault, name)):
            return name
    return None


def project_key(dirname):
    m = re.match(r"(\d+)-", dirname)
    return m.group(1) if m else dirname


_ID_HEADERS = ("需求ID", "需求号", "需求 ID")


def parse_memory_requirements(text, reverse_section="需求反向索引"):
    ids = set()
    in_section = False
    section_names = {reverse_section, "需求索引"}
    for ln in text.split("\n"):
        s = ln.strip()
        if s.startswith("## "):  # 有意只认二级标题；MEMORY 模板里小节都是 ##
            in_section = s.lstrip("#").strip() in section_names
            continue
        if not in_section or not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if not cells:
            continue
        first = cells[0]
        if first in _ID_HEADERS or first == "":
            continue
        if set(first) <= set("-: "):  # 分隔行 |---|
            continue
        for part in re.split(r"[,，、\s]+", first):
            part = part.strip()
            if part and part not in ("<空>", "-"):
                ids.add(part)
    return ids


def covered_requirements(vault, cfg):
    kb = os.path.join(vault, cfg["knowledge"]["kb_root"])
    memory_file = cfg["knowledge"]["memory_file"]
    reverse_section = cfg["knowledge"]["memory_reverse_section"]
    allids = set()
    mapping = {}
    if not os.path.isdir(kb):
        return allids, mapping
    for sysname in sorted(os.listdir(kb)):
        mpath = os.path.join(kb, sysname, memory_file)
        if not os.path.isfile(mpath):
            continue
        for rid in parse_memory_requirements(wc.read_text(mpath), reverse_section):
            allids.add(rid)
            mapping.setdefault(rid, []).append(sysname)
    return allids, mapping


def list_specin_projects(vault, source_rel):
    src = os.path.join(vault, source_rel)
    out = []
    if not os.path.isdir(src):
        return out
    for name in sorted(os.listdir(src)):
        if os.path.isdir(os.path.join(src, name)):
            out.append((name, project_key(name)))
    return out


def scan(vault, cfg, source_rel=None):
    if source_rel is None:
        root = find_specin_root(vault, cfg)
        # 用正斜杠拼相对路径：Windows 的 os.path/open/listdir 都接受 '/'，且报告显示更干净（Obsidian 路径惯例）。不要改成 os.path.join，否则 Windows 上会变反斜杠。
        source_rel = (root + "/" + cfg["knowledge"]["spec_source_default"]) if root else None
    covered_ids, mapping = covered_requirements(vault, cfg)
    projects = list_specin_projects(vault, source_rel) if source_rel else []
    pending, done = [], []
    for name, key in projects:
        (done if key in covered_ids else pending).append((name, key))
    systems = sorted({s for ss in mapping.values() for s in ss})
    return {"source": source_rel, "covered_ids": sorted(covered_ids),
            "systems": systems, "pending": pending, "done": done, "mapping": mapping}


def render_report(res):
    L = ["# spec-distill 增量报告", "",
         "> `/spec-distill scan` 生成；只读，不代表已写入。", "",
         "## 概览", "",
         "- 源目录：`%s`" % (res["source"] or "（未找到 SpecIn）"),
         "- 已有系统：%s" % ("、".join(res["systems"]) or "（无）"),
         "- 已覆盖需求号：%d" % len(res["covered_ids"]),
         "- 待沉淀项目：%d" % len(res["pending"]), "",
         "## 待沉淀项目", ""]
    if res["pending"]:
        L += ["- `%s`（key: %s）" % (n, k) for n, k in res["pending"]]
    else:
        L.append("_（无）_")
    L += ["", "## 已覆盖项目", ""]
    if res["done"]:
        L += ["- `%s`（key: %s）" % (n, k) for n, k in res["done"]]
    else:
        L.append("_（无）_")
    L.append("")
    return "\n".join(L)


def write_report(vault, cfg, res):
    path = os.path.join(vault, cfg["system_dir"], "spec-distill-report.md")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(render_report(res))
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(prog="kn_scan")
    ap.add_argument("command", nargs="?", default="scan", choices=["scan"])
    ap.add_argument("--source", default=None)
    ap.add_argument("--vault", default=None)
    args = ap.parse_args(argv)
    vault = wc.require_vault(args.vault)
    cfg = wc.load_config(vault)
    res = scan(vault, cfg, args.source)
    rp = write_report(vault, cfg, res)
    print("scan 完成：待沉淀 %d，已覆盖需求号 %d，系统 %d"
          % (len(res["pending"]), len(res["covered_ids"]), len(res["systems"])))
    print("源：%s" % (res["source"] or "（未找到 SpecIn）"))
    print("报告：%s" % rp)


if __name__ == "__main__":
    main()
