from puma_trader.probability import estimate_from_flags
from puma_trader.watermelon_proxy import build_puma_watermelon


def _candles(n=700):
    rows=[]
    p=1000.0
    for i in range(n):
        p *= 1.0005
        if i % 90 == 0 and i:
            p *= 1.08
        rows.append({
            "open": p*.997,
            "high": p*1.015,
            "low": p*.985,
            "close": p,
            "volume": 1000 + (4000 if i%90==0 else i%50),
            "date": f"2026{(i//28)%12+1:02d}{i%28+1:02d}",
        })
    return rows


def test_watermelon_shape():
    c=_candles()
    out=build_puma_watermelon(c)
    assert len(out["watermelon_stage"]) == len(c)
    assert set(out["watermelon_stage"]).issubset({0,1,2,3})


def test_probability_no_fake_number_when_no_samples():
    c=_candles(100)
    e=estimate_from_flags(c,[False]*len(c),horizon_bars=10,tp_pct=4,sl_pct=2)
    assert e.probability is None
    assert e.verdict == "판단 유보"
