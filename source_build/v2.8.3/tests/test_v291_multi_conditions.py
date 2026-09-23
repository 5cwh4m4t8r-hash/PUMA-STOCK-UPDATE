from puma_trader.conditions import (
    select_puma_conditions,
    update_candidate_source,
)


def test_selects_user_puma_condition_bundle():
    rows = [
        ("1", "단타단타(시원놈)"),
        ("2", "시초가멀티"),
        ("3", "5분봉_단타(시원놈)★"),
        ("4", "단타1"),
        ("5", "시초가2번"),
        ("6", "시초가1-1번"),
        ("7", "시초가1번"),
        ("8", "장기스윙"),
    ]
    selected = select_puma_conditions(rows)
    assert [x[0] for x in selected] == ["1", "2", "3", "4", "5", "6", "7"]


def test_single_searcher_candidate_is_fully_eligible():
    pool = {}
    item = update_candidate_source(
        pool,
        seq="1", condition_name="단타1", code="005930",
        stock_name="삼성전자", active=True, entry_event=True, now="09:05:00",
    )
    assert item["active"] is True
    assert item["entry_event"] is True
    assert item["source_count"] == 1


def test_overlap_is_metadata_not_requirement():
    pool = {}
    update_candidate_source(
        pool,
        seq="1", condition_name="단타1", code="005930",
        stock_name="삼성전자", active=True, entry_event=True, now="09:05:00",
    )
    item = update_candidate_source(
        pool,
        seq="2", condition_name="시초가1번", code="005930",
        stock_name="삼성전자", active=True, entry_event=True, now="09:06:00",
    )
    assert item["active"] is True
    assert item["entry_event"] is True
    assert item["source_count"] == 2


def test_exit_from_one_searcher_keeps_other_source_active():
    pool = {}
    update_candidate_source(
        pool,
        seq="1", condition_name="단타1", code="005930",
        stock_name="삼성전자", active=True, entry_event=True, now="09:05:00",
    )
    update_candidate_source(
        pool,
        seq="2", condition_name="시초가1번", code="005930",
        stock_name="삼성전자", active=True, entry_event=True, now="09:06:00",
    )
    item = update_candidate_source(
        pool,
        seq="1", condition_name="단타1", code="005930",
        stock_name="삼성전자", active=False, entry_event=False, now="09:07:00",
    )
    assert item["active"] is True
    assert item["source_count"] == 1
    assert item["entry_event"] is True
