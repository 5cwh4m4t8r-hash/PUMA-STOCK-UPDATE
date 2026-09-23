from datetime import datetime

from puma_trader.models import Position, StrategySettings
from puma_trader.strategy import evaluate_sell


def _pos(partial_price=10400):
    return Position(
        "000001", "TEST", 5, 10000, 10400, "now",
        stop_price=9500, entry_kind="PULLBACK", partial_taken=True,
        partial_price=partial_price, partial_time="2026-09-23T10:30:00",
    )


def test_after_half_take_up_sells_all():
    s=StrategySettings()
    sell, reason=evaluate_sell(_pos(), 10410, s, now=datetime(2026,9,23,10,31))
    assert sell is True
    assert "추가상승" in reason


def test_after_half_take_down_sells_all():
    s=StrategySettings()
    sell, reason=evaluate_sell(_pos(), 10390, s, now=datetime(2026,9,23,10,31))
    assert sell is True
    assert "하락" in reason


def test_equal_price_waits_before_11():
    s=StrategySettings()
    sell, reason=evaluate_sell(_pos(), 10400, s, now=datetime(2026,9,23,10,31))
    assert sell is False


def test_11_oclock_forces_remainder_exit():
    s=StrategySettings()
    sell, reason=evaluate_sell(_pos(), 10400, s, now=datetime(2026,9,23,11,0))
    assert sell is True
    assert "11:00" in reason


def test_basis_open_stop_still_has_priority():
    s=StrategySettings()
    sell, reason=evaluate_sell(_pos(), 9490, s, now=datetime(2026,9,23,10,31))
    assert sell is True
    assert "기준봉 시가" in reason


def test_old_partial_state_without_price_uses_four_percent_fallback():
    s=StrategySettings()
    p=Position("000001","TEST",5,10000,10400,"now",stop_price=9500,partial_taken=True)
    sell, reason=evaluate_sell(p,10410,s,now=datetime(2026,9,23,10,31))
    assert sell is True
