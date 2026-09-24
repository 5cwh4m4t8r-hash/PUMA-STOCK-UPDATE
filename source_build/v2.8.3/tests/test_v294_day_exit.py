from datetime import datetime

from puma_trader.models import Position, StrategySettings
from puma_trader.strategy import evaluate_sell


def _gaboja_position(partial=False):
    return Position(
        code="000001",
        name="TEST",
        qty=10,
        entry_price=10000,
        highest_price=10400,
        opened_at="2026-09-24T09:20:00",
        stop_price=9500,
        entry_kind="PULLBACK",
        partial_taken=partial,
        partial_price=10400 if partial else 0,
        partial_time="2026-09-24T10:00:00" if partial else "",
    )


def test_gaboja_force_exit_at_1520_before_partial():
    p = _gaboja_position(partial=False)
    sell, reason = evaluate_sell(
        p, 10450, StrategySettings(),
        now=datetime(2026, 9, 24, 15, 20),
        bar_key="202609241520",
        previous_bar_close=10400,
    )
    assert sell is True
    assert "15:20 전량청산" in reason


def test_gaboja_force_exit_at_1520_after_partial():
    p = _gaboja_position(partial=True)
    sell, reason = evaluate_sell(
        p, 10400, StrategySettings(),
        now=datetime(2026, 9, 24, 15, 25),
        bar_key="202609241525",
        previous_bar_close=10400,
    )
    assert sell is True
    assert "15:20 전량청산" in reason


def test_gaboja_not_forced_before_1520():
    p = _gaboja_position(partial=True)
    sell, reason = evaluate_sell(
        p, 10400, StrategySettings(),
        now=datetime(2026, 9, 24, 15, 19),
        bar_key="202609241515",
        previous_bar_close=10400,
    )
    assert sell is False
    assert "추세추적 보유" in reason
