from puma_trader.indicators import hero_eavg
from puma_trader.market_path import _ema_series
from puma_trader.signals import _ema as signal_ema, build_arrow_signals
from puma_trader.swing import ema as swing_ema
from puma_trader.swing_reference import _ema as reference_ema
from puma_trader.watermelon_proxy import _ema as watermelon_ema


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
        assert watermelon_ema(values, period) == expected


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




def test_black_disparity_uses_exponential_ema224():
    candles = _trend_candles(700)
    out = build_arrow_signals(candles)
    closes = [float(c["close"]) for c in candles]
    e224 = signal_ema(closes, 224)
    assert e224[-1] is not None
    disparity = closes[-1] / float(e224[-1]) * 100.0
    assert disparity > 100.0


def test_arrow_diagnostics_expose_exact_formula_inputs():
    candles = _trend_candles(700)
    out = build_arrow_signals(candles)
    n = len(candles)
    for key in (
        "signal_ema112", "signal_ema224", "signal_ema448",
        "signal_x_bb40_22", "signal_x_ema112", "signal_x_ema224", "signal_x_ema448",
        "signal_sar_ok", "signal_vema40", "signal_disparity224",
    ):
        assert key in out
        assert len(out[key]) == n
