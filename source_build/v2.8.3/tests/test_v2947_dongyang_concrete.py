from pathlib import Path

from puma_trader.market_path import _fallback_hill, find_box_before
from puma_trader.swing import SwingSettings


def b(i, o, h, l, c, v=1000):
    return {
        "date": str(i),
        "open": float(o),
        "high": float(h),
        "low": float(l),
        "close": float(c),
        "volume": float(v),
    }


def wave(start, count, low=90.0, high=100.0):
    rows = []
    for i in range(count):
        phase = i % 8
        if phase in (0, 1):
            close = 98.5
            h = high
            l = 96.0
        elif phase in (4, 5):
            close = 91.5
            h = 94.0
            l = low
        else:
            close = 95.0
            h = 97.0
            l = 93.0
        rows.append(b(start + i, close - 0.4, h, l, close, 1000))
    return rows


def test_second_concrete_search_cannot_reach_through_previous_reference_bar():
    candles = wave(0, 70, 90, 100)
    previous_reference = len(candles)
    candles.append(b(previous_reference, 99, 118, 98, 116, 5000))

    # New independent base after the prior strong launch.
    second_start = len(candles)
    candles += wave(second_start, 48, 72, 82)

    unrestricted = find_box_before(candles, len(candles) - 1, SwingSettings())
    restricted = find_box_before(
        candles,
        len(candles) - 1,
        SwingSettings(),
        start_floor=previous_reference + 1,
    )

    assert restricted is not None
    assert restricted["start"] >= previous_reference + 1
    assert restricted["end"] >= second_start
    if unrestricted is not None and unrestricted["start"] < previous_reference:
        assert restricted["start"] > unrestricted["start"]


def test_previous_high_uses_actual_last_touch_not_search_end():
    candles = wave(0, 40, 90, 100)
    # Tail bars no longer touch the upper hill.
    for i in range(40, 48):
        candles.append(b(i, 94.0, 96.0, 92.0, 94.5, 900))

    hill = _fallback_hill(candles, len(candles) - 1, SwingSettings())
    assert hill is not None
    assert "last_top_touch_idx" in hill
    assert hill["last_top_touch_idx"] < hill["end"]


def test_historical_scan_is_cycle_isolated_for_dongyang_type_repeated_launches():
    src = Path("puma_trader/market_path.py").read_text(encoding="utf-8")
    assert "search_floor = max(0, last_strong_ref + 1)" in src
    assert "start_floor=search_floor" in src
    assert "last_top_touch_idx" in src
    assert "hill_touch >= max(start, end - 20)" in src
