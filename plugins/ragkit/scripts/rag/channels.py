"""Lexical + metadata recall channels over the chunk index (doc-level aggregation)."""
from __future__ import annotations

import math
from collections import defaultdict

from .tokenizer import tokenize

FIELD_WEIGHTS = {"title": 3.0, "tags": 2.5, "description": 2.0, "body": 1.0}


def build_doc_index(chunks: list[dict]) -> dict[str, dict]:
    docs: dict[str, dict] = {}
    for c in chunks:
        d = docs.setdefault(c["knowledge_id"], {
            "knowledge_id": c["knowledge_id"],
            "category": c["category"],
            "title": c["title"],
            "tags": c["tags"],
            "source": c["source"],
            "description": c["description"],
            "source_path": c["source_path"],
            "fields": {
                "title": set(tokenize(c["title"])),
                "tags": {t for tag in c["tags"] for t in tokenize(tag)},
                "description": set(tokenize(c["description"])),
                "body": set(),
            },
        })
        d["fields"]["body"].update(tokenize(c["text"]))
    return docs


def lexical_rank(docs: dict[str, dict], query_tokens: list[str]) -> list[tuple[str, float]]:
    qs = set(query_tokens)
    if not qs or not docs:
        return []
    n = len(docs)
    df: dict[str, int] = defaultdict(int)
    for d in docs.values():
        all_tokens = set().union(*d["fields"].values())
        for t in qs:
            if t in all_tokens:
                df[t] += 1
    scored = []
    for kid, d in docs.items():
        score = 0.0
        for t in qs:
            idf = math.log(1 + n / (1 + df[t]))
            for fname, ftokens in d["fields"].items():
                if t in ftokens:
                    score += FIELD_WEIGHTS[fname] * idf
        if score > 0:
            scored.append((kid, round(score, 4)))
    scored.sort(key=lambda x: (-x[1], x[0]))
    return scored


def metadata_rank(docs: dict[str, dict], query_tokens: list[str]) -> list[tuple[str, float]]:
    """High-precision channel: whole-tag coverage > tag-token hit > 来源 hit."""
    qs = set(query_tokens)
    if not qs:
        return []
    scored = []
    for kid, d in docs.items():
        hits = 0.0
        for tag in d["tags"]:
            tag_tokens = set(tokenize(tag))
            if not tag_tokens:
                continue
            if tag_tokens <= qs:
                hits += 2.0
            elif tag_tokens & qs:
                hits += 0.5
        if set(tokenize(d["source"])) & qs:
            hits += 0.5
        if hits > 0:
            scored.append((kid, hits))
    scored.sort(key=lambda x: (-x[1], x[0]))
    return scored
