"""Reciprocal Rank Fusion。

RRF(d) = Σ_r 1/(k + rank_r(d))，rank 从 1 开始。
"""


def rrf_fuse(rankings: list[list[str]], k: int = 60, top_k: int = 40) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    ordered = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return ordered[:top_k]
