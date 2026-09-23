from puma_trader.models import Position, StrategySettings
from puma_trader.strategy import evaluate_sell


def test_body_rebreak_stop_uses_pullback_low_label():
    pos = Position(
        code="000001",
        name="TEST",
        qty=10,
        entry_price=11000,
        highest_price=11000,
        opened_at="2026-09-24T09:20:00",
        stop_price=10500,
        entry_kind="BODY_REBREAK",
    )
    should_sell, reason = evaluate_sell(pos, 10500, StrategySettings())
    assert should_sell is True
    assert "직전 차 저점" in reason


def test_pullback_stop_keeps_basis_open_label():
    pos = Position(
        code="000001",
        name="TEST",
        qty=10,
        entry_price=10300,
        highest_price=10300,
        opened_at="2026-09-24T09:10:00",
        stop_price=10000,
        entry_kind="PULLBACK",
    )
    should_sell, reason = evaluate_sell(pos, 10000, StrategySettings())
    assert should_sell is True
    assert "기준봉 시가" in reason
