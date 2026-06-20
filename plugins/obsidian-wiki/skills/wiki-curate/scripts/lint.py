#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""wiki-curate 内容体检：确定性检查 Wiki 区内容笔记的健康度。"""
import os, sys, re, argparse
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "lib"))
import wikicommon as wc


def has_purpose(text, heading="用途"):
    pattern = re.compile(r"^##\s+%s\s*$" % re.escape(heading), re.M)
    return bool(pattern.search(text))


def missing_purpose(vault, cfg):
    heading = cfg["lint"].get("purpose_heading", "用途")
    dirs = cfg["lint"]["purpose_dirs"]
    skip = cfg["skip_dirs"]
    out = []
    for p in wc.iter_md(vault, dirs, skip):
        if os.path.basename(p) == "README.md":
            continue
        if not has_purpose(wc.read_text(p), heading):
            out.append(wc.rel(vault, p))
    return sorted(out)


def duplicate_basenames(vault, cfg):
    skip = cfg["skip_dirs"]
    groups = {}
    for p in wc.iter_md(vault, None, skip):
        groups.setdefault(os.path.basename(p), []).append(wc.rel(vault, p))
    return {b: sorted(rels) for b, rels in groups.items() if len(rels) > 1}


def _all_referenced(vault, cfg):
    skip = cfg["skip_dirs"]
    basenames, paths = set(), set()
    for p in wc.iter_md(vault, None, skip):
        self_rel = wc.rel(vault, p)[:-3]
        self_base = os.path.basename(self_rel)
        for tgt in wc.link_targets(wc.read_text(p)):
            tgt_noext = tgt[:-3] if tgt.endswith(".md") else tgt
            if tgt_noext == self_rel or tgt_noext == self_base:
                continue
            paths.add(tgt_noext)
            basenames.add(os.path.basename(tgt_noext))
    return basenames, paths


def orphans(vault, cfg):
    ref_basenames, ref_paths = _all_referenced(vault, cfg)
    dirs = cfg["lint"]["orphan_dirs"]
    skip = cfg["skip_dirs"]
    out = []
    for p in wc.iter_md(vault, dirs, skip):
        if os.path.basename(p) == "README.md":
            continue
        rel_noext = wc.rel(vault, p)[:-3]
        base = os.path.basename(rel_noext)
        if base in ref_basenames or rel_noext in ref_paths:
            continue
        out.append(wc.rel(vault, p))
    return sorted(out)


def frontmatter_issues(vault, cfg):
    dirs = cfg["lint"]["purpose_dirs"]
    skip = cfg["skip_dirs"]
    required = cfg["lint"]["required_frontmatter"]
    out = []
    for p in wc.iter_md(vault, dirs, skip):
        if os.path.basename(p) == "README.md":
            continue
        keys = wc.frontmatter_keys(wc.read_text(p))
        missing = [k for k in required if k not in keys]
        if missing:
            out.append((wc.rel(vault, p), missing))
    return sorted(out)


def lint(vault, cfg):
    return {
        "missing_purpose": missing_purpose(vault, cfg),
        "duplicate_basenames": duplicate_basenames(vault, cfg),
        "orphans": orphans(vault, cfg),
        "frontmatter_issues": frontmatter_issues(vault, cfg),
    }


def render_report(res):
    lines = [
        '# wiki-curate 内容体检报告', '',
        '> `/wiki-curate lint` 生成；只读。**坏链与结构漂移请运行 `/wiki-struct check`**。', '',
        '## 概览', '',
        '- 缺"用途"段：%d' % len(res['missing_purpose']),
        '- 重复 basename：%d' % len(res['duplicate_basenames']),
        '- 孤儿（无反链）：%d' % len(res['orphans']),
        '- frontmatter 缺字段：%d' % len(res['frontmatter_issues']), '',
    ]
    lines += ['## 缺"用途"段', ''] + (['- `%s`' % x for x in res['missing_purpose']] or ['_（无）_']) + ['']
    lines += ['## 重复 basename', '']
    if res['duplicate_basenames']:
        for b, rels in sorted(res['duplicate_basenames'].items()):
            lines.append('- `%s`：%s' % (b, '、'.join('`%s`' % r for r in rels)))
    else:
        lines.append('_（无）_')
    lines += ['', '## 孤儿（无反链）', ''] + (['- `%s`' % x for x in res['orphans']] or ['_（无）_']) + ['']
    lines += ['## frontmatter 缺字段', '']
    if res['frontmatter_issues']:
        lines += ['- `%s`：缺 %s' % (r, '、'.join(m)) for r, m in res['frontmatter_issues']]
    else:
        lines.append('_（无）_')
    lines.append('')
    return '\n'.join(lines)


def write_report(vault, cfg, res):
    path = os.path.join(vault, cfg["system_dir"], "lint-report.md")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(render_report(res))
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(prog="lint")
    ap.add_argument("command", nargs="?", default="lint", choices=["lint"])
    ap.add_argument("--vault", default=None)
    args = ap.parse_args(argv)
    vault = wc.require_vault(args.vault)
    cfg = wc.load_config(vault)
    res = lint(vault, cfg)
    rp = write_report(vault, cfg, res)
    print("lint 完成：缺用途 %d，重复 basename %d，孤儿 %d，frontmatter 缺字段 %d"
          % (len(res['missing_purpose']), len(res['duplicate_basenames']),
             len(res['orphans']), len(res['frontmatter_issues'])))
    print("报告：%s" % rp)


if __name__ == "__main__":
    main()
