"""Chunk knowledge-base markdown into embeddable units (H2 sections + sliding window)."""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from . import frontmatter

MAX_TOKENS = 1000
WINDOW_TOKENS = 500
WINDOW_OVERLAP = 50
_H2 = re.compile(r"^##\s+(.+)$", re.MULTILINE)
_CJK = re.compile(r"[一-鿿]")


@dataclass
class Chunk:
    chunk_id: str
    knowledge_id: str
    category: str
    title: str
    h2_title: str
    text: str
    source_path: str
    tags: list
    source: str
    description: str
    text_hash: str

    def to_dict(self) -> dict:
        return asdict(self)


def approx_tokens(text: str) -> int:
    cjk = len(_CJK.findall(text))
    return cjk // 2 + (len(text) - cjk) // 4


def chunk_file(path: Path, kb_root: Path) -> list[Chunk]:
    meta, body = frontmatter.parse(path.read_text(encoding="utf-8"))
    knowledge_id = path.stem
    category = str(meta.get("类型") or path.parent.name.rstrip("s"))
    tags = meta.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in re.split(r"[,，、]", tags) if t.strip()]
    title = str(meta.get("标题") or knowledge_id)
    out: list[Chunk] = []
    for h2_title, section in _split_sections(body):
        for i, win in enumerate(_windows(section)):
            text = f"{knowledge_id} / {h2_title}\n\n{win}"
            out.append(Chunk(
                chunk_id=f"{knowledge_id}/{h2_title}#{i}",
                knowledge_id=knowledge_id,
                category=category,
                title=title,
                h2_title=h2_title,
                text=text,
                source_path=path.relative_to(kb_root).as_posix(),
                tags=list(tags),
                source=str(meta.get("来源", "")),
                description=str(meta.get("描述", "")),
                text_hash=hashlib.sha1(text.encode("utf-8")).hexdigest(),
            ))
    return out


def chunk_kb(kb_root: Path) -> list[Chunk]:
    chunks: list[Chunk] = []
    for sub in ("cases", "navigation"):
        d = kb_root / sub
        if d.is_dir():
            for md in sorted(d.glob("*.md")):
                chunks.extend(chunk_file(md, kb_root))
    return chunks


def _split_sections(body: str):
    matches = list(_H2.finditer(body))
    if not matches:
        stripped = body.strip()
        if stripped:
            yield "_intro", stripped
        return
    pre = body[: matches[0].start()].strip()
    if pre:
        yield "_intro", pre
    for idx, m in enumerate(matches):
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(body)
        section = body[m.end():end].strip()
        if section:
            yield m.group(1).strip(), section


def _windows(text: str):
    if approx_tokens(text) <= MAX_TOKENS:
        yield text
        return
    ratio = len(text) / max(approx_tokens(text), 1)
    size = int(WINDOW_TOKENS * ratio)
    step = max(int((WINDOW_TOKENS - WINDOW_OVERLAP) * ratio), 1)
    for start in range(0, len(text), step):
        win = text[start:start + size]
        if win.strip():
            yield win
        if start + size >= len(text):
            break
