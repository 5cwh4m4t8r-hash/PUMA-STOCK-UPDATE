from puma_trader.signals import build_arrow_signals


def test_black_signal_array_available():
    candles = []
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
    assert all(isinstance(x, bool) for x in s["signal_black"])
