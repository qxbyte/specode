"""Parse distill knowledge-point frontmatter (标题/类型/来源/tags/描述)."""
from __future__ import annotations

import re

_FENCE = re.compile(r"^---\s*$")


def parse(text: str) -> tuple[dict, str]:
    lines = text.splitlines()
    if not lines or not _FENCE.match(lines[0]):
        return {}, text
    meta: dict = {}
    for i in range(1, len(lines)):
        if _FENCE.match(lines[i]):
            return meta, "\n".join(lines[i + 1:]).lstrip("\n")
        key, sep, value = lines[i].partition(":")
        if sep:
            meta[key.strip()] = _parse_value(value.strip())
    return {}, text  # unclosed fence: treat whole file as body


def _parse_value(value: str):
    if value.startswith("[") and value.endswith("]"):
        return [v.strip() for v in value[1:-1].split(",") if v.strip()]
    return value
