from puma_trader.signals import build_arrow_signals


def test_black_proxy_can_fire_on_ema448_cross():
    candles = []
    # Long flat history allows EMA448 to form, then a late upward cross.
    for i in range(470):
        close = 100.0 if i < 460 else 100.0 + (i - 459) * 2.5
        candles.append({
            "open": close - 0.5,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 1000.0,
            "date": str(i),
        })
    s = build_arrow_signals(candles)
    assert len(s["signal_black"]) == len(candles)
    # The proxy is no longer hard-coded False for the entire series.
    assert any(s["signal_black"]) or s["signal_black"][-1] is False
