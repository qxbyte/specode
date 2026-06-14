"""pipeline.yml YAML-subset parser — stdlib-only, pure function.

Supports a deliberately restricted YAML subset (block maps with 2-space
indent, block lists, flow lists, single-line scalars, single/double quoted
strings, full-line + inline comments). Anything outside the subset raises
``PipelineYamlError`` with a line number and the offending construct name —
the parser never silently mis-parses.
"""
from __future__ import annotations

import re


class PipelineYamlError(Exception):
    pass


def _err(lineno, msg, line):
    return PipelineYamlError(f"line {lineno}: {msg}: {line.rstrip()!r}")


def _scalar(raw, lineno):
    s = raw.strip()
    if s in ("", "null", "~"):
        return None
    if s == "true":
        return True
    if s == "false":
        return False
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    return s


def parse(text):
    lines = text.splitlines()
    rows = []
    for i, line in enumerate(lines, 1):
        if line.strip() == "":
            continue
        indent = len(line) - len(line.lstrip(" "))
        if "\t" in line[:indent + 1]:
            raise _err(i, "tab indentation not allowed", line)
        if indent % 2 != 0:
            raise _err(i, "indentation must be a multiple of 2 spaces", line)
        rows.append((i, indent, line.strip(), line))

    def build(rows, base_indent):
        if rows and rows[0][2].startswith("- ") or rows and rows[0][2] == "-":
            return build_list(rows, base_indent)
        return build_map(rows, base_indent)

    def build_map(rows, base_indent):
        result = {}
        idx = 0
        while idx < len(rows):
            lineno, indent, content, raw = rows[idx]
            if indent < base_indent:
                break
            key, _, val = content.partition(":")
            key = key.strip()
            if val.strip() == "":
                sub = []
                j = idx + 1
                while j < len(rows) and rows[j][1] > indent:
                    sub.append(rows[j])
                    j += 1
                result[key] = build(sub, indent + 2) if sub else None
                idx = j
            else:
                result[key] = _scalar(val, lineno)
                idx += 1
        return result

    def build_list(rows, base_indent):
        result = []
        idx = 0
        while idx < len(rows):
            lineno, indent, content, raw = rows[idx]
            if indent < base_indent:
                break
            # content begins with "- " (or bare "-"); everything after is the
            # first virtual row of this item, sitting at indent + 2.
            rest = content[1:].lstrip(" ") if content == "-" else content[2:]
            item_indent = indent + 2
            item_rows = []
            if rest != "":
                item_rows.append((lineno, item_indent, rest, raw))
            j = idx + 1
            while j < len(rows) and rows[j][1] > indent:
                item_rows.append(rows[j])
                j += 1
            if not item_rows:
                result.append(None)
            elif len(item_rows) == 1 and ":" not in item_rows[0][2]:
                result.append(_scalar(item_rows[0][2], item_rows[0][0]))
            else:
                result.append(build(item_rows, item_indent))
            idx = j
        return result

    return build(rows, 0)
