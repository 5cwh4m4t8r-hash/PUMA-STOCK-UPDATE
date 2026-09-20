from types import SimpleNamespace

from puma_trader.entry_signal import evaluate_core_entry
from puma_trader.watermelon_proxy import build_puma_watermelon


def _c(p=100.0, v=1000.0):
    return {"open":p,"high":p*1.01,"low":p*.99,"close":p,"volume":v,"date":"20260918"}


def test_day_core_signal_explains_missing_conditions():
    candles=[_c(100+i*.1, 1000+i) for i in range(70)]
    series={
        "candles":candles,
        "ema5":[None]*65+[100,101,102,103,104],
        "ema20":[None]*69+[100],
    }
    a=SimpleNamespace(in_time=False,kijun=99,breakout=False,pullback_hold=True,volume_ratio_5m=1.3)
    sig=evaluate_core_entry(a,series,"DAY")
    assert sig.active is False
    assert "08:50~10:00 검색시간" in sig.missing
    assert "미충족" in sig.status_text


def test_watermelon_is_sparse_and_has_display_array():
    candles=[]
    p=1000.0
    for i in range(520):
        p*=1.0002
        candles.append({"open":p*.998,"high":p*1.01,"low":p*.99,"close":p,"volume":1000+(6000 if i%37==0 else 0),"date":str(i)})
    out=build_puma_watermelon(candles,{})
    assert len(out["watermelon_display"]) == len(candles)
    idx=[i for i,x in enumerate(out["watermelon_display"]) if x]
    assert all(b-a>=20 for a,b in zip(idx,idx[1:]))
