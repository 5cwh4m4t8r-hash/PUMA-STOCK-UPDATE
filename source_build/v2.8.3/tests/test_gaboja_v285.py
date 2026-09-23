from datetime import datetime, timedelta

from puma_trader.gaboja import evaluate_gaboja
from puma_trader.models import Position, StrategySettings
from puma_trader.strategy import evaluate_sell


def _d(date, o, h, l, c, v):
    return {"date": date, "open": o, "high": h, "low": l, "close": c, "volume": v}


def _daily():
    rows = []
    start = datetime(2025, 1, 1)
    for i in range(55):
        dt = (start + timedelta(days=i)).strftime("%Y%m%d")
        rows.append(_d(dt, 100, 101, 99, 100, 1000))
    rows[-6:-1] = [
        _d("20260916", 100, 104, 99, 100, 1000),
        _d("20260917", 100, 104, 99, 100, 1000),
        _d("20260918", 100, 104, 99, 100, 1000),
        _d("20260921", 100, 104, 99, 100, 1000),
        _d("20260922", 100, 104, 99, 100, 1000),
    ]
    rows[-1] = _d("20260923", 106, 125, 106, 124, 3500)
    return rows


def _minute(body_break=True, day="20260923"):
    rows = [
        _d(day+"090000", 106, 107, 105.8, 106.5, 600),
        _d(day+"090500", 106.5, 109, 106.4, 108.8, 700),
        _d(day+"091000", 108.8, 113, 108.7, 112.5, 1400),
        _d(day+"091500", 112.0, 112.3, 110.0, 111.6, 500),
    ]
    if body_break:
        rows.append(_d(day+"092000", 112.2, 114.5, 112.0, 114.0, 800))
    return rows


def test_pullback_and_body_rebreak_are_only_entries():
    pull = evaluate_gaboja(_minute(False), _daily(), now=datetime(2026, 9, 23, 9, 15))
    assert pull.passed and pull.entry_kind == "PULLBACK"
    body = evaluate_gaboja(_minute(True), _daily(), now=datetime(2026, 9, 23, 9, 20))
    assert body.passed and body.entry_kind == "BODY_REBREAK"


def test_no_real_entry_before_0900_even_scan_starts_0850():
    sig = evaluate_gaboja(_minute(True), _daily(), now=datetime(2026, 9, 23, 8, 55))
    assert not sig.passed
    assert "장 시작 전" in sig.reason


def test_stale_previous_day_bars_cannot_trigger_today():
    sig = evaluate_gaboja(_minute(True, day="20260922"), _daily(), now=datetime(2026, 9, 23, 9, 20))
    assert not sig.passed
    assert "당일 5분봉 대기" in sig.reason


def test_no_trailing_before_four_percent_half_take():
    s = StrategySettings(take_profit_pct=4.0, trailing_gap_pct=1.2)
    p = Position("000001", "T", 10, 10000, 10350, "now", stop_price=9000, partial_taken=False)
    sell, reason = evaluate_sell(p, 10220, s, now=datetime(2026,9,23,10,0))
    assert sell is False, reason


def test_trailing_is_active_only_after_half_take_even_below_two_percent():
    s = StrategySettings(take_profit_pct=4.0, trailing_gap_pct=1.2)
    p = Position("000001", "T", 5, 10000, 10400, "now", stop_price=9000, partial_taken=True)
    sell, reason = evaluate_sell(p, 10250, s, now=datetime(2026,9,23,10,0))
    assert sell is True
    assert "잔량 트레일링" in reason


def test_basis_open_stop_has_priority():
    s = StrategySettings()
    p = Position("000001", "T", 5, 10000, 10400, "now", stop_price=9500, partial_taken=True)
    sell, reason = evaluate_sell(p, 9490, s, now=datetime(2026,9,23,10,0))
    assert sell is True
    assert "기준봉 시가" in reason
