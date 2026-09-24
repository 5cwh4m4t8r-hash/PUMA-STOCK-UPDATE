from datetime import datetime

from puma_trader.broker import SimBroker
from puma_trader.engine import TradeEngine, _gaboja_trend_stop_from_rows
from puma_trader.models import Position, StrategySettings
from puma_trader.strategy import evaluate_sell


def _row(ts, op, hi, lo, cl, vol=1000):
    return {
        "cntr_tm": ts,
        "open_pric": str(op),
        "high_pric": str(hi),
        "low_pric": str(lo),
        "cur_prc": str(cl),
        "trde_qty": str(vol),
    }


def test_confirmed_higher_pullback_raises_stop_only():
    rows = [
        _row("20260917092500", 111, 113, 110, 112),  # live bar: ignored
        _row("20260917092000", 110, 112, 109, 111),
        _row("20260917091500", 107, 111, 107, 110),  # rebound confirms pullback
        _row("20260917091000", 109, 109, 106, 107),  # bearish pullback, low 106
        _row("20260917090500", 103, 110, 102, 109),
        _row("20260917090000", 100, 104, 99, 103),
    ]

    raised = _gaboja_trend_stop_from_rows(
        rows,
        current_bar_key="202609170925",
        timeframe=5,
        current_stop=95,
        entry_price=100,
    )
    assert raised == 106

    never_lower = _gaboja_trend_stop_from_rows(
        rows,
        current_bar_key="202609170925",
        timeframe=5,
        current_stop=107,
        entry_price=100,
    )
    assert never_lower == 107


def test_trend_mode_holds_after_partial_until_stop_or_1520():
    settings = StrategySettings(force_exit_enabled=False)
    pos = Position(
        code="042370",
        name="비츠로테크",
        qty=15,
        entry_price=100,
        highest_price=120,
        opened_at="2026-09-17T10:05:00",
        stop_price=106,
        entry_kind="BODY_REBREAK",
        partial_taken=True,
        partial_price=104,
        partial_time="2026-09-17T10:30:00",
    )

    sell, reason = evaluate_sell(
        pos, 120, settings,
        now=datetime(2026, 9, 17, 13, 5),
        bar_key="202609171305",
        previous_bar_close=119,
    )
    assert sell is False
    assert "추세추적" in reason

    sell, reason = evaluate_sell(
        pos, 120, settings,
        now=datetime(2026, 9, 17, 15, 20),
        bar_key="202609171520",
        previous_bar_close=119,
    )
    assert sell is True
    assert "15:20 전량청산" in reason


def test_plus_four_partial_sell_is_25_percent_and_keeps_75_percent():
    settings = StrategySettings()
    engine = TradeEngine(SimBroker(), settings)
    pos = Position(
        code="042370",
        name="비츠로테크",
        qty=20,
        entry_price=100,
        highest_price=104,
        opened_at="2026-09-17T10:05:00",
        stop_price=95,
        entry_kind="BODY_REBREAK",
    )

    result = engine._submit_partial_sell(
        "042370", pos, 104,
        "가보자 +4.0% 1차 25% 익절",
        sell_ratio=settings.gabojago_partial_sell_ratio,
    )
    assert result["status"] == "PARTIAL_SELL"
    assert pos.qty == 15
    assert pos.partial_taken is True
    assert pos.partial_price == 104


def test_gaboja_defaults_enable_trend_tracking():
    settings = StrategySettings()
    assert settings.gabojago_trend_tracking_enabled is True
    assert settings.gabojago_partial_sell_ratio == 0.25
    assert settings.gabojago_force_exit_time == "15:20"
