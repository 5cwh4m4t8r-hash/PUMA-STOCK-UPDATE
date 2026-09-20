from puma_trader.indicators import ichimoku_cloud


def test_ichimoku_future_shift():
    candles = []
    for i in range(100):
        p = 1000 + i * 3
        candles.append({
            "open": p - 2,
            "high": p + 10,
            "low": p - 10,
            "close": p,
            "volume": 1000,
            "date": f"20260{(i//28)+1:01d}{(i%28)+1:02d}",
        })
    out = ichimoku_cloud(candles)
    assert len(out["cloud_a"]) == 126
    assert len(out["cloud_b"]) == 126
    assert out["future_count"] == 26
    assert out["cloud_a"][-1] is not None
    assert out["cloud_b"][-1] is not None
