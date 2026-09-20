from puma_trader.signals import build_arrow_signals


def test_arrow_signal_shapes_and_lengths():
    candles = []
    p = 1000.0
    for i in range(520):
        p *= 1.0004
        if i in (460, 480, 500):
            p *= 1.08
        candles.append({
            "open": p * 0.995,
            "high": p * 1.01,
            "low": p * 0.99,
            "close": p,
            "volume": 1000 + i,
            "date": f"2026{i%12+1:02d}{i%28+1:02d}",
        })
    out = build_arrow_signals(candles)
    for key in ("signal_pink", "signal_blue", "signal_red", "signal_sar", "signal_bb40_22"):
        assert len(out[key]) == len(candles)
    assert all(isinstance(x, bool) for x in out["signal_blue"])
