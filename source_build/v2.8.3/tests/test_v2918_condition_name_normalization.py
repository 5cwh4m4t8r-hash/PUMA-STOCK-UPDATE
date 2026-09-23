from puma_trader.conditions import (
    PUMA_DANTA_CONDITION_NAMES,
    normalize_condition_name,
    select_puma_conditions,
)


def test_five_minute_day_search_matches_format_variants():
    expected = normalize_condition_name("5분봉_단타(시원놈)")
    assert normalize_condition_name("5분봉 단타(시원놈)") == expected
    assert normalize_condition_name("5분봉 단타 시원놈") == expected
    assert normalize_condition_name("★ 5분봉-단타（시원놈） ☆") == expected


def test_bundle_selector_accepts_five_minute_variant():
    rows = [
        ("1", "단타1"),
        ("2", "5분봉 단타 시원놈"),
        ("3", "시초가2번"),
    ]
    selected = select_puma_conditions(rows, PUMA_DANTA_CONDITION_NAMES)
    assert ("2", "5분봉 단타 시원놈") in selected
