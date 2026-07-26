from app.evaluation.metrics import result_values_match


def test_result_comparison_allows_extra_presentation_columns() -> None:
    generated = [
        {"store_id": 1, "store_name": "华东一店", "completion_rate": 88.5},
        {"store_id": 2, "store_name": "华南一店", "completion_rate": 91.2},
    ]
    reference = [
        {"store_name": "华南一店", "target_completion_rate": 91.2},
        {"store_name": "华东一店", "target_completion_rate": 88.5},
    ]

    assert result_values_match(generated, reference)


def test_result_comparison_rejects_wrong_metric_value() -> None:
    generated = [{"region": "华东", "revenue": 100}]
    reference = [{"region": "华东", "revenue": 101}]

    assert not result_values_match(generated, reference)


def test_normalizes_weekday_names_when_case_requests_it() -> None:
    generated = [{"day_of_week": "Saturday", "revenue": 123.456}]
    reference = [{"weekday_number": 7, "revenue": 123.46}]

    assert result_values_match(
        generated,
        reference,
        comparison={"normalizers": ["weekday"]},
    )


def test_ignores_only_explicit_optional_reference_columns() -> None:
    generated = [{"store_name": "华东一店", "product_name": "商品 A"}]
    reference = [{"store_name": "华东一店", "product_name": "商品 A", "stock_qty": 0}]

    assert not result_values_match(generated, reference)
    assert result_values_match(
        generated,
        reference,
        comparison={"ignore_reference_columns": ["stock_qty"]},
    )
