#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""wiki-struct 结构层生成器：确定性重写结构文件的受管块。"""
import os
import re
import sys
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "lib"))
import wikicommon as wc

# ---------------------------------------------------------------------------
# Marker 函数（受管块读写）
# ---------------------------------------------------------------------------

def _markers(block_id):
    return ("<!-- wiki-struct:%s start -->" % block_id,
            "<!-- wiki-struct:%s end -->" % block_id)


def has_block(text, block_id="tree"):
    s, e = _markers(block_id)
    return s in text and e in text


def get_block(text, block_id="tree"):
    s, e = _markers(block_id)
    if s not in text or e not in text:
        return None
    start = text.index(s) + len(s)
    end = text.index(e)
    return text[start:end].strip("\n")


def replace_block(text, new_inner, block_id="tree"):
    s, e = _markers(block_id)
    sc, ec = text.count(s), text.count(e)
    if sc == 0 and ec == 0:
        raise ValueError("no-marker")
    if sc != 1 or ec != 1:
        raise ValueError("unbalanced-marker")
    start = text.index(s) + len(s)
    end = text.index(e)
    if end < start:
        raise ValueError("reversed-marker")
    return text[:start] + "\n" + new_inner.rstrip("\n") + "\n" + text[end:]

# ---------------------------------------------------------------------------
# 遍历器（walk_tree / _has_md / count_md）
# ---------------------------------------------------------------------------

def _has_md(absdir):
    for _root, _ds, files in os.walk(absdir):
        if any(f.endswith(".md") for f in files):
            return True
    return False


def _child_dirs(absdir, skip):
    try:
        entries = sorted(os.listdir(absdir))
    except OSError:
        return [], []
    dirs = [e for e in entries
            if os.path.isdir(os.path.join(absdir, e))
            and not e.startswith(".") and e not in skip]
    files = [e for e in entries
             if e.endswith(".md") and os.path.isfile(os.path.join(absdir, e))]
    return dirs, files


def walk_tree(vault, absdir, depth, skip, skip_self_rel=None):
    out = []
    dirs, files = _child_dirs(absdir, skip)
    pad = "    " * depth
    for d in dirs:
        full = os.path.join(absdir, d)
        if not _has_md(full):
            continue
        out.append("%s- **%s/**" % (pad, d))
        out.extend(walk_tree(vault, full, depth + 1, skip, skip_self_rel))
    for f in files:
        full = os.path.join(absdir, f)
        rel = wc.rel(vault, full)
        if skip_self_rel and rel == skip_self_rel:
            continue
        out.append("%s- [[%s|%s]]" % (pad, rel[:-3], f[:-3]))
    return out


def count_md(vault, absdir, skip, skip_self_rel=None):
    n = 0
    for root, ds, files in os.walk(absdir):
        ds[:] = [d for d in ds if not d.startswith(".") and d not in skip]
        for f in files:
            if not f.endswith(".md"):
                continue
            if skip_self_rel and wc.rel(vault, os.path.join(root, f)) == skip_self_rel:
                continue
            n += 1
    return n

# ---------------------------------------------------------------------------
# 渲染器（render_dir_list / render_home）
# ---------------------------------------------------------------------------

def render_dir_list(vault, dirname, skip, skip_self_rel=None):
    absdir = os.path.join(vault, dirname)
    lines = walk_tree(vault, absdir, 0, skip, skip_self_rel=skip_self_rel)
    return "\n".join(lines) if lines else "_（暂无文档）_"


def render_home(vault, cfg):
    index_dir = cfg["index_dir"]
    home_file = cfg["home_file"]
    skip = cfg["skip_dirs"]
    dirs = cfg["structure"]["dirs"]
    out = ["> [!tip] 用法",
           "> 点击下方任一目录标题可展开/折叠；标题右侧 `↗` 链接到该目录的分区索引。"]
    for entry in dirs:
        name = entry["dir"]
        absdir = os.path.join(vault, name)
        if not os.path.isdir(absdir):
            continue
        skip_rel = home_file if name == index_dir else None
        cnt = count_md(vault, absdir, skip, skip_self_rel=skip_rel)
        partition_link = ("%s/%s" % (index_dir, name)) if entry["partition"] else None
        suffix = (" · 分区索引 [[%s|↗]]" % partition_link) if partition_link else ""
        out.append("")
        out.append("> [!%s]- %s %s — %s（%d 篇）%s"
                   % (entry["callout"], entry["emoji"], name, entry["desc"], cnt, suffix))
        for ln in walk_tree(vault, absdir, 0, skip, skip_self_rel=home_file):
            out.append("> " + ln)
    return "\n".join(out)

# ---------------------------------------------------------------------------
# 结构文件映射 + check()
# ---------------------------------------------------------------------------

def structure_files(vault, cfg):
    index_dir = cfg["index_dir"]
    home_file = cfg["home_file"]
    skip = cfg["skip_dirs"]
    dirs = cfg["structure"]["dirs"]
    items = [("home", os.path.join(vault, home_file),
              lambda: render_home(vault, cfg))]
    for entry in dirs:
        name = entry["dir"]
        if entry["readme"]:
            items.append(("readme", os.path.join(vault, name, "README.md"),
                          (lambda n=name: render_dir_list(vault, n, skip,
                                                          skip_self_rel="%s/README.md" % n))))
        if entry["partition"]:
            items.append(("partition", os.path.join(vault, index_dir, name + ".md"),
                          (lambda n=name: render_dir_list(vault, n, skip))))
    return items


def check(vault, cfg):
    skip = cfg["skip_dirs"]
    res = {"drift": [], "missing_marker": [], "missing_file": [], "broken": []}
    for _kind, path, render in structure_files(vault, cfg):
        rel = wc.rel(vault, path)
        if not os.path.exists(path):
            res["missing_file"].append(rel)
            continue
        text = wc.read_text(path)
        if not has_block(text):
            res["missing_marker"].append(rel)
            continue
        if (get_block(text) or "").strip() != render().strip():
            res["drift"].append(rel)
    res["broken"] = find_broken_links(vault, skip, system_dir=cfg["system_dir"])
    return res

# ---------------------------------------------------------------------------
# apply() + scope
# ---------------------------------------------------------------------------

_SCOPE_KIND = {"home": "home", "readmes": "readme", "partitions": "partition"}


def apply(vault, cfg, scope="all"):
    skip = cfg["skip_dirs"]
    want_kind = None if scope == "all" else _SCOPE_KIND.get(scope)
    changed = []
    for kind, path, render in structure_files(vault, cfg):
        if want_kind and kind != want_kind:
            continue
        if not os.path.exists(path):
            continue
        text = wc.read_text(path)
        if not has_block(text):
            continue
        try:
            new = replace_block(text, render())
        except ValueError:
            print("skip malformed marker: %s" % wc.rel(vault, path))
            continue
        if new != text:
            with open(path, "w", encoding="utf-8") as f:
                f.write(new)
            changed.append(wc.rel(vault, path))
    return changed

# ---------------------------------------------------------------------------
# 坏链扫描（find_broken_links）
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(r"(?:```|~~~).*?(?:```|~~~)", re.S)
_LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


def _is_placeholder(target):
    return ("<" in target) or ("`" in target) or ("..." in target) \
        or target.startswith("路径/") or target.startswith("路径\\")


def find_broken_links(vault, skip, system_dir=None):
    broken = []
    for path in wc.iter_md(vault, None, skip):
        rel = wc.rel(vault, path)
        if system_dir and rel.startswith(system_dir.rstrip("/") + "/"):
            continue
        text = _FENCE_RE.sub("", wc.read_text(path))
        for raw in _LINK_RE.findall(text):
            tgt = raw.split("|")[0].split("#")[0].rstrip("\\").strip()
            if not tgt or "/" not in tgt or _is_placeholder(tgt):
                continue
            if os.path.exists(os.path.join(vault, tgt)) or \
               os.path.exists(os.path.join(vault, tgt + ".md")):
                continue
            broken.append((rel, tgt))
    return broken

# ---------------------------------------------------------------------------
# CLI + 报告写盘
# ---------------------------------------------------------------------------

def render_report(res):
    L = ["# wiki-struct 结构体检报告", "",
         "> 由 `/wiki-struct check` 生成；本报告只读，不代表已写入。", "",
         "## 概览", "",
         "- 需更新受管块：%d" % len(res["drift"]),
         "- 缺 marker（需 init）：%d" % len(res["missing_marker"]),
         "- 缺结构文件：%d" % len(res["missing_file"]),
         "- 坏链：%d" % len(res["broken"]), ""]
    def sect(title, items, fmt=lambda x: "- %s" % x):
        L.append("## " + title)
        L.append("")
        L.extend(fmt(x) for x in items) if items else L.append("_（无）_")
        L.append("")
    sect("需更新受管块", res["drift"])
    sect("缺 marker（需 init）", res["missing_marker"])
    sect("缺结构文件", res["missing_file"])
    sect("坏链", res["broken"], fmt=lambda t: "- `%s` → `%s`" % (t[0], t[1]))
    return "\n".join(L)


def write_report(vault, cfg, res):
    system_dir = cfg["system_dir"]
    path = os.path.join(vault, system_dir, "struct-report.md")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(render_report(res))
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(prog="struct_gen")
    ap.add_argument("command", choices=["check", "apply"])
    ap.add_argument("--scope", choices=["home", "readmes", "partitions", "all"], default="all")
    ap.add_argument("--vault", default=None)
    args = ap.parse_args(argv)
    vault = wc.require_vault(args.vault)
    cfg = wc.load_config(vault)
    if args.command == "check":
        res = check(vault, cfg)
        rp = write_report(vault, cfg, res)
        print("check 完成：需更新 %d，缺 marker %d，缺文件 %d，坏链 %d"
              % (len(res["drift"]), len(res["missing_marker"]),
                 len(res["missing_file"]), len(res["broken"])))
        print("报告：%s" % rp)
    else:
        changed = apply(vault, cfg, scope=args.scope)
        print("apply 完成：改动 %d 个结构文件" % len(changed))
        for c in changed:
            print("  - " + c)


if __name__ == "__main__":
    main()
