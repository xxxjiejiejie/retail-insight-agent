def exact_match(expected: str, actual: str) -> float:
    return float(expected.strip() == actual.strip())


def retrieval_hit(expected_source: str, retrieved_sources: list[str], *, k: int = 3) -> float:
    return float(expected_source in retrieved_sources[:k])

