from collections import Counter
from collections.abc import Mapping
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

WEEKDAY_ALIASES = {
    "sunday": "weekday:1",
    "星期日": "weekday:1",
    "星期天": "weekday:1",
    "monday": "weekday:2",
    "星期一": "weekday:2",
    "tuesday": "weekday:3",
    "星期二": "weekday:3",
    "wednesday": "weekday:4",
    "星期三": "weekday:4",
    "thursday": "weekday:5",
    "星期四": "weekday:5",
    "friday": "weekday:6",
    "星期五": "weekday:6",
    "saturday": "weekday:7",
    "星期六": "weekday:7",
}


def exact_match(expected: str, actual: str) -> float:
    return float(expected.strip() == actual.strip())


def retrieval_hit(expected_source: str, retrieved_sources: list[str], *, k: int = 3) -> float:
    return float(expected_source in retrieved_sources[:k])


def normalize_result_value(
    value: object,
    *,
    normalizers: set[str] | None = None,
    numeric_places: int = 2,
) -> str:
    active_normalizers = normalizers or set()
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if "weekday" in active_normalizers:
        if isinstance(value, str):
            weekday = WEEKDAY_ALIASES.get(value.strip().casefold())
            if weekday:
                return weekday
        if isinstance(value, (int, float, Decimal)) and Decimal(str(value)) % 1 == 0:
            weekday_number = int(value)
            if 1 <= weekday_number <= 7:
                return f"weekday:{weekday_number}"
    if isinstance(value, (int, float, Decimal)):
        quantum = Decimal(1).scaleb(-numeric_places)
        decimal_value = Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP).normalize()
        return format(decimal_value, "f")
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def result_values_match(
    generated_rows: list[dict[str, Any]],
    reference_rows: list[dict[str, Any]],
    *,
    comparison: Mapping[str, Any] | None = None,
) -> bool:
    """Compare result semantics while keeping case-specific rules explicit and auditable."""
    if len(generated_rows) != len(reference_rows):
        return False
    options = comparison or {}
    ignored_reference_columns = {
        str(column) for column in options.get("ignore_reference_columns", [])
    }
    normalizers = {str(name) for name in options.get("normalizers", [])}
    numeric_places = int(options.get("numeric_places", 2))

    def values(row: dict[str, Any], *, reference: bool) -> Counter[str]:
        return Counter(
            normalize_result_value(
                value,
                normalizers=normalizers,
                numeric_places=numeric_places,
            )
            for key, value in row.items()
            if not reference or key not in ignored_reference_columns
        )

    remaining = [
        values(row, reference=False)
        for row in generated_rows
    ]
    for reference_row in reference_rows:
        expected = values(reference_row, reference=True)
        match_index = next(
            (index for index, actual in enumerate(remaining) if expected <= actual),
            None,
        )
        if match_index is None:
            return False
        remaining.pop(match_index)
    return True
