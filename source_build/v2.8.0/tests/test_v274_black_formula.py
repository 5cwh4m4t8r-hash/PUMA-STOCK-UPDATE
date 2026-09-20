from puma_trader.signals import build_arrow_signals, latest_signal_reason


def test_black_arrow_exact_user_formula_fires():
    candles=[]
    for i in range(500):
        close=100.0
        volume=1000.0
        if i == 499:
            close=108.5
            volume=2000.0
        candles.append({
            "open":100.0,
            "high":max(101.0,close*1.01),
            "low":99.0,
            "close":close,
            "volume":volume,
            "date":str(i),
        })
    out=build_arrow_signals(candles)
    assert out["signal_black"][-1] is True
    series={"candles":candles, **out}
    assert "224이격" in latest_signal_reason(series)


def test_black_arrow_rejects_overextended_disparity():
    candles=[]
    for i in range(500):
        close=100.0
        volume=1000.0
        if i == 499:
            close=120.0
            volume=3000.0
        candles.append({
            "open":100.0,
            "high":max(101.0,close*1.01),
            "low":99.0,
            "close":close,
            "volume":volume,
            "date":str(i),
        })
    out=build_arrow_signals(candles)
    assert out["signal_black"][-1] is False
