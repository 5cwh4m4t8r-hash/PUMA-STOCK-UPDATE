from puma_trader.indicators import hero_eavg
from puma_trader.market_path import _ema_series
from puma_trader.signals import _avg, _ema as signal_ema, build_arrow_signals
from puma_trader.swing import ema as swing_ema
from puma_trader.swing_reference import _ema as reference_ema


def _trend_candles(n=700):
    rows = []
    price = 100.0
    for i in range(n):
        price *= 1.003
        rows.append({
            "date": f"{20200000 + i:08d}",
            "open": price * 0.996,
            "high": price * 1.006,
            "low": price * 0.994,
            "close": price,
            "volume": 1000.0 + i,
        })
    return rows


def test_all_long_ma_modules_use_same_hero_eavg():
    values = [100.0 + i * 0.7 + (i % 9) * 0.13 for i in range(700)]
    for period in (5, 20, 60, 112, 224, 448):
        expected = hero_eavg(values, period)
        assert signal_ema(values, period) == expected
        assert swing_ema(values, period) == expected
        assert _ema_series(values, period) == expected
        assert reference_ema(values, period) == expected


def test_extended_bullish_long_ma_context_suppresses_display_signals_only():
    candles = _trend_candles()
    out = build_arrow_signals(candles)

    assert out["long_trend_suppressed_now"] is True
    assert out["long_trend_suppressed"][-1] is True

    # Literal user formulas stay available as raw arrays for HTS comparison.
    for name in ("pink", "blue", "red", "black"):
        raw = out[f"signal_{name}_raw"]
        shown = out[f"signal_{name}"]
        assert len(raw) == len(candles)
        assert len(shown) == len(candles)
        assert shown[-1] is False


def test_black_disparity_uses_simple_avg_224():
    values = [100.0 + i for i in range(230)]
    avg = _avg(values, 224)
    eavg = signal_ema(values, 224)
    assert avg[222] is None
    assert avg[223] == sum(values[:224]) / 224.0
    # On a trending series AVG and EAVG are intentionally different.
    assert abs(float(avg[-1]) - float(eavg[-1])) > 1e-6

    candles = [
        {
            "date": str(i),
            "open": v - 0.2,
            "high": v + 0.5,
            "low": v - 0.5,
            "close": v,
            "volume": 1000.0 + i,
        }
        for i, v in enumerate(values)
    ]
    out = build_arrow_signals(candles)
    assert out["signal_disparity_avg224"] == avg
