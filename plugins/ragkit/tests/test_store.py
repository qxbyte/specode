import numpy as np

from rag import store
from rag.chunker import chunk_kb


def test_save_and_load_roundtrip(kb):
    chunks = chunk_kb(kb)
    vecs = np.ones((len(chunks), 4), dtype="float32")
    store.save_index(kb, chunks, vecs, "dummy::dummy")
    assert store.load_model_id(kb) == "dummy::dummy"
    loaded = store.load_chunks(kb)
    assert [c["chunk_id"] for c in loaded] == [c.chunk_id for c in chunks]
    assert store.load_vectors(kb).shape == (len(chunks), 4)
    manifest = store.load_manifest(kb)
    assert manifest["hashes"][chunks[0].chunk_id] == chunks[0].text_hash
    assert manifest["built_at"] > 0


def test_save_without_vectors(kb):
    chunks = chunk_kb(kb)
    store.save_index(kb, chunks, None, "")
    assert store.load_vectors(kb) is None
    assert store.load_chunks(kb)


def test_gitignore_written_once(kb):
    chunks = chunk_kb(kb)
    store.save_index(kb, chunks, None, "")
    store.save_index(kb, chunks, None, "")
    lines = (kb / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert lines.count(".ragkit/") == 1
