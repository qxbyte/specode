"""Index persistence under <kb>/.ragkit/ (chunks.json / vectors.npy / manifest / model_id)."""
from __future__ import annotations

import json
import time
from pathlib import Path

INDEX_DIR = ".ragkit"
SCHEMA_VERSION = "1.0"


def index_dir(kb_root: Path) -> Path:
    return kb_root / INDEX_DIR


def save_index(kb_root: Path, chunks: list, vectors, model_id: str) -> None:
    import numpy as np

    d = index_dir(kb_root)
    d.mkdir(parents=True, exist_ok=True)
    (d / "chunks.json").write_text(json.dumps({
        "schema_version": SCHEMA_VERSION,
        "model_id": model_id,
        "n_chunks": len(chunks),
        "chunks": [c.to_dict() for c in chunks],
    }, ensure_ascii=False), encoding="utf-8")
    vec_path = d / "vectors.npy"
    if vectors is not None:
        np.save(vec_path, vectors)
    elif vec_path.is_file():
        vec_path.unlink()
    (d / "model_id.txt").write_text(model_id + "\n", encoding="utf-8")
    (d / "manifest.json").write_text(json.dumps({
        "built_at": time.time(),
        "hashes": {c.chunk_id: c.text_hash for c in chunks},
    }, ensure_ascii=False), encoding="utf-8")
    ensure_gitignore(kb_root)


def load_chunks(kb_root: Path) -> list[dict]:
    p = index_dir(kb_root) / "chunks.json"
    if not p.is_file():
        return []
    return json.loads(p.read_text(encoding="utf-8")).get("chunks", [])


def load_vectors(kb_root: Path):
    import numpy as np

    p = index_dir(kb_root) / "vectors.npy"
    return np.load(p) if p.is_file() else None


def load_model_id(kb_root: Path) -> str:
    p = index_dir(kb_root) / "model_id.txt"
    return p.read_text(encoding="utf-8").strip() if p.is_file() else ""


def load_manifest(kb_root: Path) -> dict:
    p = index_dir(kb_root) / "manifest.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


def ensure_gitignore(kb_root: Path) -> None:
    gi = kb_root / ".gitignore"
    line = INDEX_DIR + "/"
    existing = gi.read_text(encoding="utf-8").splitlines() if gi.is_file() else []
    if line not in existing:
        gi.write_text("\n".join(existing + [line]) + "\n", encoding="utf-8")
