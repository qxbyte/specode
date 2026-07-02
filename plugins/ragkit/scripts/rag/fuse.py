"""Reciprocal Rank Fusion across recall channels."""
from __future__ import annotations

RRF_K = 60


def rrf_fuse(rankings: dict[str, list[str]], k: int = RRF_K) -> list[dict]:
    scores: dict[str, float] = {}
    ranked_by: dict[str, list[str]] = {}
    for channel in sorted(rankings):
        for rank, kid in enumerate(rankings[channel]):
            scores[kid] = scores.get(kid, 0.0) + 1.0 / (k + rank + 1)
            ranked_by.setdefault(kid, []).append(channel)
    fused = [
        {"knowledge_id": kid, "rrf_score": round(s, 6), "ranked_by": ranked_by[kid]}
        for kid, s in scores.items()
    ]
    fused.sort(key=lambda x: (-x["rrf_score"], x["knowledge_id"]))
    return fused
