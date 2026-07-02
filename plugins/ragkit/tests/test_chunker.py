from pathlib import Path

from rag import frontmatter
from rag.chunker import approx_tokens, chunk_file, chunk_kb


def test_frontmatter_parse_inline_tags():
    meta, body = frontmatter.parse(
        "---\n标题: X\n类型: case\ntags: [a, b]\n描述: d\n---\n\n## S\n正文"
    )
    assert meta["标题"] == "X"
    assert meta["tags"] == ["a", "b"]
    assert body.startswith("## S")


def test_frontmatter_no_fence_returns_whole_body():
    meta, body = frontmatter.parse("just text")
    assert meta == {} and body == "just text"


def test_chunk_file_splits_h2_sections(kb):
    path = kb / "cases" / "114371-mask-rule.md"
    chunks = chunk_file(path, kb)
    assert [c.h2_title for c in chunks] == ["定位", "可复用经验 / 坑"]
    c = chunks[0]
    assert c.knowledge_id == "114371-mask-rule"
    assert c.category == "case"
    assert c.chunk_id == "114371-mask-rule/定位#0"
    assert c.text.startswith("114371-mask-rule / 定位")
    assert c.source_path == "cases/114371-mask-rule.md"
    assert "DesensitizeUtils" in c.tags[2]
    assert len(c.text_hash) == 40


def test_chunk_kb_covers_both_dirs(kb):
    ids = {c.knowledge_id for c in chunk_kb(kb)}
    assert ids == {"114371-mask-rule", "121659-authority-chain", "cod-receipt-page"}


def test_long_section_sliding_window(tmp_path):
    body = "---\n标题: L\n类型: case\ntags: [x]\n描述: d\n---\n\n## 长节\n" + ("字" * 5000)
    d = tmp_path / "kb" / "cases"
    d.mkdir(parents=True)
    (d / "long-doc.md").write_text(body, encoding="utf-8")
    chunks = chunk_file(d / "long-doc.md", tmp_path / "kb")
    assert len(chunks) > 1
    assert all(approx_tokens(c.text) <= 1100 for c in chunks)
    assert chunks[1].chunk_id == "long-doc/长节#1"
