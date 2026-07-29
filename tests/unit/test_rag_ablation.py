from app.evaluation.rag_ablation import hit_at_k, ndcg_at_k, ranking_metrics, reciprocal_rank_at_k


def test_ranking_metrics_use_chunk_level_relevance() -> None:
    ranked = ["wrong", "supporting", "direct", "irrelevant"]
    relevance = {"direct": 2, "supporting": 1}

    assert hit_at_k(ranked, relevance, k=3) == 1.0
    assert reciprocal_rank_at_k(ranked, relevance, k=3) == 0.5
    assert 0 < ndcg_at_k(ranked, relevance, k=3) < 1
    metrics = ranking_metrics(ranked, relevance, k=3)
    assert set(metrics) == {"hit_at_3", "mrr_at_3", "ndcg_at_3"}


def test_ranking_metrics_return_zero_when_no_chunk_is_relevant() -> None:
    ranked = ["a", "b", "c"]
    assert ranking_metrics(ranked, {}, k=5) == {
        "hit_at_5": 0.0,
        "mrr_at_5": 0.0,
        "ndcg_at_5": 0.0,
    }
