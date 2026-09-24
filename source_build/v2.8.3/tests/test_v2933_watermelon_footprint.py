from puma_trader.watermelon_proxy import (
    _rolling_avg,
    _volume_footprint,
    build_puma_watermelon,
)


def _base(n=80):
    rows = []
    price = 100.0
    for i in range(n):
        price *= 0.997
        rows.append({
            "date": str(i),
            "open": price * 1.002,
            "high": price * 1.015,
            "low": price * 0.985,
            "close": price,
            "volume": 1000.0,
        })
    return rows


def test_ordinary_volume_is_not_large_money_footprint():
    candles = _base(30)
    vols = [c["volume"] for c in candles]
    candles[-1]["volume"] = 1200.0
    vols[-1] = 1200.0
    v20 = _rolling_avg(vols, 20)
    fp = _volume_footprint(candles, vols, v20, len(candles) - 1)
    assert fp["abnormal"] is False


def test_high_volume_big_bear_is_absorption_footprint():
    candles = _base(30)
    i = len(candles) - 1
    candles[i].update({
        "open": 100.0,
        "high": 101.0,
        "low": 84.0,
        "close": 86.0,
        "volume": 4200.0,
    })
    vols = [c["volume"] for c in candles]
    v20 = _rolling_avg(vols, 20)
    fp = _volume_footprint(candles, vols, v20, i)
    assert fp["abnormal"] is True
    assert fp["absorption"] is True
    assert fp["big_bear"] is True
    assert fp["pattern"] == "대량 장대음봉"


def test_muted_price_with_abnormal_volume_is_absorption_footprint():
    candles = _base(30)
    i = len(candles) - 1
    prev = candles[i - 1]["close"]
    candles[i].update({
        "open": prev * 0.995,
        "high": prev * 1.02,
        "low": prev * 0.98,
        "close": prev * 1.01,
        "volume": 2200.0,
    })
    vols = [c["volume"] for c in candles]
    v20 = _rolling_avg(vols, 20)
    fp = _volume_footprint(candles, vols, v20, i)
    assert fp["abnormal"] is True
    assert fp["absorption"] is True
    assert fp["muted"] is True


def test_watermelon_exposes_large_money_footprint_arrays():
    candles = _base(360)
    for i in (320, 335):
        candles[i]["volume"] = 2800.0
        candles[i]["high"] *= 1.08
    out = build_puma_watermelon(candles)
    n = len(candles)
    assert len(out["watermelon_footprint_score"]) == n
    assert len(out["watermelon_footprint_reason"]) == n
    assert all(0 <= int(x) <= 100 for x in out["watermelon_footprint_score"])
