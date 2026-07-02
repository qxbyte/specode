from rag.channels import build_doc_index, lexical_rank, metadata_rank
from rag.chunker import chunk_kb
from rag.fuse import rrf_fuse
from rag.tokenizer import tokenize


def _docs(kb):
    return build_doc_index([c.to_dict() for c in chunk_kb(kb)])


def test_lexical_rank_field_weighting(kb):
    docs = _docs(kb)
    ranked = lexical_rank(docs, tokenize("银行账号脱敏 DesensitizeUtils"))
    assert ranked[0][0] == "114371-mask-rule"
    assert ranked[0][1] > 0


def test_metadata_rank_tag_hit(kb):
    docs = _docs(kb)
    ranked = metadata_rank(docs, tokenize("见费出单 收款"))
    assert ranked and ranked[0][0] == "cod-receipt-page"


def test_lexical_rank_empty_query(kb):
    assert lexical_rank(_docs(kb), []) == []


def test_rrf_fuse_rewards_multi_channel_agreement():
    fused = rrf_fuse({
        "lexical": ["a", "b", "c"],
        "metadata": ["b", "a"],
        "vector": ["b"],
    })
    assert fused[0]["knowledge_id"] == "b"
    assert fused[0]["ranked_by"] == ["lexical", "metadata", "vector"]
    assert fused[0]["rrf_score"] > fused[1]["rrf_score"]
