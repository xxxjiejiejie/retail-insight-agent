from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from typing import Any


def exact_match(expected: str, actual: str) -> float:
    return float(expected.strip() == actual.strip())


def retrieval_hit(expected_source: str, retrieved_sources: list[str], *, k: int = 3) -> float:
    return float(expected_source in retrieved_sources[:k])


def normalize_result_value(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float, Decimal)):
        decimal_value = Decimal(str(value)).normalize()
        return format(decimal_value, "f")
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def result_values_match(
    generated_rows: list[dict[str, Any]],
    reference_rows: list[dict[str, Any]],
) -> bool:
    """Compare values, allowing harmless extra presentation columns and row order."""
    if len(generated_rows) != len(reference_rows):
        return False
    remaining = [
        Counter(normalize_result_value(value) for value in row.values())
        for row in generated_rows
    ]
    for reference_row in reference_rows:
        expected = Counter(normalize_result_value(value) for value in reference_row.values())
        match_index = next(
            (index for index, actual in enumerate(remaining) if expected <= actual),
            None,
        )
        if match_index is None:
            return False
        remaining.pop(match_index)
    return True
