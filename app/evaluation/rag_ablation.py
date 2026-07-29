from __future__ import annotations

import math
from collections.abc import Iterable, Mapping


def hit_at_k(
    ranked_chunk_ids: Iterable[str],
    relevant_chunks: Mapping[str, int],
    *,
    k: int = 5,
) -> float:
    """Return 1 when at least one relevant chunk is present in the first k results."""

    ranked = list(ranked_chunk_ids)[:k]
    return float(any(chunk_id in relevant_chunks for chunk_id in ranked))


def reciprocal_rank_at_k(
    ranked_chunk_ids: Iterable[str],
    relevant_chunks: Mapping[str, int],
    *,
    k: int = 5,
) -> float:
    """Return the reciprocal rank of the first relevant chunk in the first k results."""

    for rank, chunk_id in enumerate(list(ranked_chunk_ids)[:k], 1):
        if chunk_id in relevant_chunks:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(
    ranked_chunk_ids: Iterable[str],
    relevant_chunks: Mapping[str, int],
    *,
    k: int = 5,
) -> float:
    """Compute graded nDCG@k using chunk relevance labels from the ground truth."""

    ranked = list(ranked_chunk_ids)[:k]

    def dcg(grades: Iterable[int]) -> float:
        score = 0.0
        for rank, grade in enumerate(grades, 1):
            if grade > 0:
                score += (2.0**grade - 1.0) / math.log2(rank + 1)
        return score

    actual = dcg(relevant_chunks.get(chunk_id, 0) for chunk_id in ranked)
    ideal = dcg(sorted(relevant_chunks.values(), reverse=True)[:k])
    return actual / ideal if ideal else 0.0


def ranking_metrics(
    ranked_chunk_ids: Iterable[str],
    relevant_chunks: Mapping[str, int],
    *,
    k: int = 5,
) -> dict[str, float]:
    ranked = list(ranked_chunk_ids)
    return {
        f"hit_at_{k}": hit_at_k(ranked, relevant_chunks, k=k),
        f"mrr_at_{k}": reciprocal_rank_at_k(ranked, relevant_chunks, k=k),
        f"ndcg_at_{k}": ndcg_at_k(ranked, relevant_chunks, k=k),
    }
