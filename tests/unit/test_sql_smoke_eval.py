from scripts.evaluate_sql_smoke import result_values_match


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
