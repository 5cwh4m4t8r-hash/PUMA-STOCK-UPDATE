import puma_trader.market_path as mp
from puma_trader.swing import SwingSettings


def _rows(n=700):
    out=[]
    p=100.0
    for i in range(n):
        p += (0.2 if i%7<4 else -0.18)
        out.append({
            "date":str(i),
            "open":p-0.1,
            "high":p+1.0,
            "low":p-1.0,
            "close":p,
            "volume":1000.0,
        })
    return out


def test_low_volume_bars_do_not_run_expensive_box_search(monkeypatch):
    rows=_rows()
    mp.clear_market_path_cache()
    calls={"n":0}
    original=mp._structure_before

    def wrapped(*args, **kwargs):
        calls["n"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(mp, "_structure_before", wrapped)
    mp.analyze_market_path(rows, SwingSettings())
    assert calls["n"] == 0


def test_market_path_reuses_same_candle_result():
    rows=_rows(500)
    mp.clear_market_path_cache()
    s=SwingSettings()
    a=mp.analyze_market_path(rows,s)
    b=mp.analyze_market_path(rows,s)
    assert a is b
