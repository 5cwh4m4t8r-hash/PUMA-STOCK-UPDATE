from puma_trader.watermelon_proxy import build_puma_watermelon


def test_watermelon_proxy_lengths_and_sparse_display():
    candles = []
    price = 200.0
    for i in range(360):
        # steady decline -> bottom/base -> early rebound
        if i < 260:
            price *= 0.9975
        elif i < 330:
            price *= 1.0002
        else:
            price *= 1.004
        vol = 1000.0
        if i in (315, 326):
            vol = 2200.0
        candles.append({
            "open": price * 0.995,
            "high": price * 1.01,
            "low": price * 0.985,
            "close": price,
            "volume": vol,
            "date": str(i),
        })
    out = build_puma_watermelon(candles)
    n = len(candles)
    assert len(out["watermelon_stage"]) == n
    assert len(out["watermelon_display"]) == n
    hits = [i for i, x in enumerate(out["watermelon_display"]) if x]
    assert all((b-a) >= 20 for a,b in zip(hits,hits[1:]))
