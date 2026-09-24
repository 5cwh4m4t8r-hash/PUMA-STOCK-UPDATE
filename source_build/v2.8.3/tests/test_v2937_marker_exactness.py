from puma_trader.market_path import analyze_market_path, clear_market_path_cache
from puma_trader.swing import SwingSettings
from puma_trader.bowl import BowlSettings, _find_bowl3_pullback


def b(i, o, h, l, c, v=1000):
    return {"date": str(i), "open": o, "high": h, "low": l, "close": c, "volume": v}


def strict_bottom_box():
    rows = []
    for i in range(240):
        rows.append(b(i, 120, 121, 119, 120, 1000))
    for k in range(30):
        c = 90 + ((k % 4) - 1.5) * 0.4
        h = 97 if k in (1, 9, 17, 25) else c + 1.0
        l = 84 if k in (5, 13, 21, 29) else c - 1.0
        rows.append(b(240 + k, c - 0.2, h, l, c, 1000))
    return rows


def test_gap_above_structure_and_long_ma_is_not_body_breakout():
    clear_market_path_cache()
    rows = strict_bottom_box()
    # Opens already above the expected resistance/long-MA zone: gap, not body breakout.
    rows.append(b(270, 116, 121, 115, 120, 5000))
    out = analyze_market_path(rows, SwingSettings())
    assert sum(out["path_breakout"]) == 0


def test_low_volume_body_cross_is_not_confirmed_breakout():
    clear_market_path_cache()
    rows = strict_bottom_box()
    rows.append(b(270, 90, 117, 89, 115, 1800))  # < 3x prev / 20-bar avg
    out = analyze_market_path(rows, SwingSettings())
    assert sum(out["path_breakout"]) == 0


def test_exact_breakout_and_structure_top_pullback_are_marked_on_real_bars():
    clear_market_path_cache()
    rows = strict_bottom_box()
    rows.append(b(270, 90, 117, 89, 115, 4000))
    rows.append(b(271, 114, 115, 96.0, 108, 500))
    out = analyze_market_path(rows, SwingSettings())

    assert out["path_breakout"][270] is True
    assert out["path_pullback"][271] is True
    assert out["path_pullback_source"][271] in ("공구리상단", "112EMA", "224EMA")
    assert out["path_pullback_value"][271] > 0


def test_bowl3_uses_support_closest_to_actual_low_when_multiple_hold():
    settings = BowlSettings()
    candles = [
        b(0, 98, 100, 97, 99),
        b(1, 99, 106, 98.5, 105),   # breakout reference, open=99
        b(2, 104, 105, 94.8, 101),  # bearish; low is much closer to EMA112=95 than ref open=99
    ]
    e112 = [95.0, 95.0, 95.0]
    pull = _find_bowl3_pullback(candles, e112, 1, settings, end_idx=len(candles))
    assert pull is not None
    assert pull["index"] == 2
    assert pull["source"] == "112EMA"
    assert pull["value"] == 95.0
