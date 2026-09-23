from puma_trader.conditions import (
    PUMA_DANTA_CONDITION_NAMES,
    is_puma_danta_condition,
    select_puma_conditions,
    update_candidate_source,
)


def test_exact_day_search_bundle_has_seven_sources():
    assert PUMA_DANTA_CONDITION_NAMES == (
        "단타단타(시원놈)",
        "5분봉_단타(시원놈)",
        "단타1",
        "시초가1번",
        "시초가1-1번",
        "시초가2번",
        "시초가멀티",
    )


def test_day_bundle_selects_all_available_sources_not_only_danta1():
    rows = [
        ("11", "단타1"),
        ("12", "시초가2번"),
        ("13", "5분봉_단타(시원놈)"),
        ("14", "스윙검색기"),
        ("15", "단타단타(시원놈)"),
    ]
    selected = select_puma_conditions(rows, PUMA_DANTA_CONDITION_NAMES)
    assert selected == [
        ("11", "단타1"),
        ("12", "시초가2번"),
        ("13", "5분봉_단타(시원놈)"),
        ("15", "단타단타(시원놈)"),
    ]
    assert all(is_puma_danta_condition(name) for _, name in selected)


def test_same_stock_from_multiple_day_searchers_is_one_candidate():
    candidates = {}
    first = update_candidate_source(
        candidates,
        seq="11",
        condition_name="단타1",
        code="005930",
        stock_name="삼성전자",
        active=True,
        entry_event=False,
        now="09:01:00",
    )
    second = update_candidate_source(
        candidates,
        seq="12",
        condition_name="시초가2번",
        code="005930",
        stock_name="삼성전자",
        active=True,
        entry_event=False,
        now="09:01:03",
    )
    assert len(candidates) == 1
    assert first is second
    assert second["source_count"] == 2
    assert set(second["source_names"]) == {"단타1", "시초가2번"}
