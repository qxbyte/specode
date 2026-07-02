"""End-to-end query pipeline: focus -> 3 channels -> RRF -> cards."""
from __future__ import annotations

from pathlib import Path

from . import backend, channels, fuse, store
from .tokenizer import extract_focus, tokenize

TOP_CHUNK_HITS = 50
DEFAULT_TOP = 8
ALL_CHANNELS = ["lexical", "metadata", "vector"]


def query_pipeline(kb_root: Path, query: str, top: int = DEFAULT_TOP,
                   channels_filter: list[str] | None = None) -> dict:
    chunks = store.load_chunks(kb_root)
    out: dict = {"query": query, "kb": str(kb_root),
                 "vector_channel": "skipped", "index_stale": False, "results": []}
    if not chunks:
        out["vector_channel"] = "no_index"
        out["focus"] = extract_focus(query)
        return out
    out["index_stale"] = index_stale(kb_root)
    focus = extract_focus(query)
    out["focus"] = focus
    qtokens = tokenize(focus)
    docs = channels.build_doc_index(chunks)
    active = channels_filter or ALL_CHANNELS
    rankings: dict[str, list[str]] = {}
    channel_scores: dict[str, dict] = {}
    if "lexical" in active:
        lex = channels.lexical_rank(docs, qtokens)
        rankings["lexical"] = [k for k, _ in lex]
        channel_scores["lexical"] = dict(lex)
    if "metadata" in active:
        md = channels.metadata_rank(docs, qtokens)
        rankings["metadata"] = [k for k, _ in md]
        channel_scores["metadata"] = dict(md)
    if "vector" in active:
        state, vec = _vector_rank(kb_root, chunks, focus)
        out["vector_channel"] = state
        if state == "ok":
            rankings["vector"] = [k for k, _ in vec]
            channel_scores["vector"] = dict(vec)
    fused = fuse.rrf_fuse(rankings)[:top]
    for row in fused:
        d = docs[row["knowledge_id"]]
        for key in ("category", "title", "description", "source", "source_path", "tags"):
            row[key] = d[key]
        row["channel_scores"] = {
            ch: sc[row["knowledge_id"]]
            for ch, sc in channel_scores.items() if row["knowledge_id"] in sc
        }
    out["results"] = fused
    return out


def _vector_rank(kb_root: Path, chunks: list[dict], focus_text: str):
    import numpy as np

    vectors = store.load_vectors(kb_root)
    if vectors is None or len(vectors) != len(chunks):
        cfg = backend.load_config(kb_root)
        kind, _ = backend.resolve(cfg)
        return ("no_backend" if kind == "none" else "no_vectors"), []
    stored = store.load_model_id(kb_root)
    kind, opts = backend.resolve(backend.load_config(kb_root))
    if kind == "none":
        return "no_backend", []
    if backend.model_id(kind, opts) != stored:
        return "model_mismatch", []
    q = backend.encode(kind, opts, [focus_text])[0]
    sims = vectors @ q
    order = np.argsort(-sims)[:TOP_CHUNK_HITS]
    best: dict[str, float] = {}
    for i in order:
        kid = chunks[int(i)]["knowledge_id"]
        s = round(float(sims[int(i)]), 4)
        if kid not in best or s > best[kid]:
            best[kid] = s
    ranked = sorted(best.items(), key=lambda x: (-x[1], x[0]))
    return "ok", ranked


def index_stale(kb_root: Path) -> bool:
    built_at = store.load_manifest(kb_root).get("built_at", 0)
    for sub in ("cases", "navigation"):
        d = kb_root / sub
        if d.is_dir():
            for md in d.glob("*.md"):
                if md.stat().st_mtime > built_at:
                    return True
    return False
