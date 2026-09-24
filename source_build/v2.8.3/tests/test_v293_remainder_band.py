from datetime import datetime

from puma_trader.models import Position, StrategySettings
from puma_trader.strategy import evaluate_sell


def pos():
    return Position(
        code="000001",
        name="TEST",
        qty=5,
        entry_price=96,
        highest_price=100,
        opened_at="2026-09-24T09:10:00",
        stop_price=90,
        entry_kind="PULLBACK",
        partial_taken=True,
        partial_price=100,
        partial_time="2026-09-24T09:30:00",
    )


def test_remainder_plus_2_percent_sells_immediately():
    p = pos()
    sell, reason = evaluate_sell(
        p, 102, StrategySettings(force_exit_enabled=False, gabojago_trend_tracking_enabled=False, gabojago_force_exit_time="23:59"),
        bar_key="202609240940", previous_bar_close=101,
    )
    assert sell is True
    assert "+2.0%" in reason


def test_minus_2_percent_waits_one_full_next_bar():
    p = pos()
    settings = StrategySettings(force_exit_enabled=False, gabojago_trend_tracking_enabled=False, gabojago_force_exit_time="23:59")

    sell, _ = evaluate_sell(
        p, 98, settings, bar_key="202609240940", previous_bar_close=99,
    )
    assert sell is False
    assert p.remainder_down_trigger_bar == "202609240940"
    assert p.remainder_down_wait_bar == ""

    sell, _ = evaluate_sell(
        p, 97, settings, bar_key="202609240945", previous_bar_close=97.5,
    )
    assert sell is False
    assert p.remainder_down_wait_bar == "202609240945"

    # 확인봉(09:45)이 진행 중일 때는 더 빠져도 즉시 매도하지 않는다.
    sell, _ = evaluate_sell(
        p, 96, settings, bar_key="202609240945", previous_bar_close=97.5,
    )
    assert sell is False

    # 09:50 새 봉이 시작되면 완성된 09:45 봉 종가로 확정한다.
    sell, reason = evaluate_sell(
        p, 96, settings, bar_key="202609240950", previous_bar_close=97.5,
    )
    assert sell is True
    assert "다음봉 미회복" in reason


def test_minus_2_percent_recovery_cancels_down_state():
    p = pos()
    settings = StrategySettings(force_exit_enabled=False, gabojago_trend_tracking_enabled=False, gabojago_force_exit_time="23:59")
    evaluate_sell(p, 98, settings, bar_key="202609240940", previous_bar_close=99)
    evaluate_sell(p, 97.5, settings, bar_key="202609240945", previous_bar_close=97.8)

    sell, reason = evaluate_sell(
        p, 99, settings, bar_key="202609240950", previous_bar_close=98.5,
    )
    assert sell is False
    assert "회복 확인" in reason
    assert p.remainder_down_trigger_bar == ""
    assert p.remainder_down_wait_bar == ""


def test_no_11am_forced_exit_anymore():
    p = pos()
    settings = StrategySettings(force_exit_enabled=False, gabojago_trend_tracking_enabled=False, gabojago_force_exit_time="23:59")
    sell, reason = evaluate_sell(
        p, 100, settings,
        now=datetime(2026, 9, 24, 11, 30),
        bar_key="202609241130",
        previous_bar_close=100,
    )
    assert sell is False
    assert "잔량 보유" in reason
