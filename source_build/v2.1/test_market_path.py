from puma_trader.market_path import analyze_market_path, find_box_before
from puma_trader.swing import SwingSettings


def _bar(i, close, high, low, volume, open_=None):
    return {
        "date": f"2026{(i//28)%12+1:02d}{i%28+1:02d}",
        "open": float(close if open_ is None else open_),
        "high": float(high),
        "low": float(low),
        "close": float(close),
        "volume": float(volume),
    }


def _box_rows(n=90):
    rows=[]
    for i in range(n):
        close=100 + ((i % 7)-3)*0.45
        rows.append(_bar(i, close, 104.5 if i%9==0 else close+1.2, 95.5 if i%11==0 else close-1.2, 1000+(i%5)*30))
    return rows


def test_dynamic_box_uses_60_to_112_bars():
    rows=_box_rows(90)
    s=SwingSettings()
    s.box_period_min=60
    s.box_period_max=112
    s.box_width_pct=25.0
    b=find_box_before(rows,len(rows)-1,s)
    assert b is not None
    assert 60 <= b["period"] <= 112
    assert b["top_touches"] >= 3
    assert b["bottom_touches"] >= 3


def test_breakout_pullback_with_dead_volume_is_active():
    rows=_box_rows(90)
    rows.append(_bar(90,112,114,103,4200,open_=103))
    rows.append(_bar(91,109,112,105,1500,open_=111))
    rows.append(_bar(92,107,110,104,1000,open_=109))
    rows.append(_bar(93,106,109,103.5,800,open_=107))
    s=SwingSettings()
    s.breakout_volume_ratio=3.0
    s.rebreak_volume_ratio=3.0
    out=analyze_market_path(rows,s)
    assert out["current"]["active"] is True
    assert out["current"]["stage"] == "돌파 후 거래량 감소 눌림"
    assert out["current"]["pullback_volume_ratio"] <= 0.55


def test_rebreakout_requires_renewed_volume():
    rows=_box_rows(90)
    rows.append(_bar(90,112,114,103,4200,open_=103))
    rows.append(_bar(91,108,111,104,1200,open_=111))
    rows.append(_bar(92,106,109,103.5,900,open_=108))
    rows.append(_bar(93,116,117,105,4500,open_=107))
    s=SwingSettings()
    s.breakout_volume_ratio=3.0
    s.rebreak_volume_ratio=3.0
    out=analyze_market_path(rows,s)
    assert out["current"]["active"] is True
    assert out["current"]["stage"] == "거래량 동반 재돌파"


def test_under_300_percent_breakout_is_rejected():
    rows=_box_rows(90)
    rows.append(_bar(90,112,114,103,2500,open_=103))
    out=analyze_market_path(rows,SwingSettings())
    assert out["path_breakout"][-1] is False
