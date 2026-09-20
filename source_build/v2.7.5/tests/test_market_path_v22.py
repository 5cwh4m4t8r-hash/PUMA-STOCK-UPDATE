from puma_trader.market_path import analyze_market_path, find_box_before
from puma_trader.swing import SwingSettings


def bar(i, o, h, l, c, v):
    return {"date": str(i), "open":o, "high":h, "low":l, "close":c, "volume":v}


def trend_then_box():
    rows=[]
    p=70.0
    for i in range(55):
        p += 0.55
        rows.append(bar(i,p-0.3,p+0.8,p-0.8,p,1000))
    # 28-bar real horizontal support/resistance zone; not 60~112.
    for k in range(28):
        c=100 + ((k%6)-3)*0.65
        h=109.5 if k in (2,11,20,27) else c+1.2
        l=91.0 if k in (5,14,23) else c-1.2
        rows.append(bar(55+k,c-0.2,h,l,c,1000+(k%4)*30))
    return rows


def test_box_duration_is_chart_driven_not_fixed_60_112():
    rows=trend_then_box()
    s=SwingSettings()
    s.box_search_lookback=140
    b=find_box_before(rows,len(rows)-1,s)
    assert b is not None
    assert 12 <= b["period"] < 60
    assert b["top_touches"] >= 3
    assert b["bottom_touches"] >= 3
    assert b["alternations"] >= 2


def test_clear_trend_is_not_box():
    rows=[]
    p=100.0
    for i in range(90):
        p += 1.2
        rows.append(bar(i,p-0.3,p+0.8,p-0.8,p,1000))
    assert find_box_before(rows,len(rows)-1,SwingSettings()) is None


def test_sparse_breakout_pullback_rebreak_labels():
    rows=trend_then_box()
    # avg vol ~1000; clear 400% breakout
    rows.append(bar(83,100,116,99,114,4200))
    rows.append(bar(84,113,115,108,110,1200))
    rows.append(bar(85,110,112,106,108,900))   # two calm bars -> one pullback label
    rows.append(bar(86,108,112,107,111,850))
    rows.append(bar(87,111,119,110,118,4200))  # confirmed rebreak
    out=analyze_market_path(rows,SwingSettings())
    assert sum(out["path_breakout"]) == 1
    assert sum(out["path_pullback"]) == 1
    assert sum(out["path_rebreakout"]) == 1
    assert out["current"]["stage"] == "확정 재돌파"


def test_high_volume_pullback_is_not_confirmed():
    rows=trend_then_box()
    rows.append(bar(83,100,116,99,114,4200))
    rows.append(bar(84,113,115,108,110,3200))
    rows.append(bar(85,110,112,106,108,2900))
    out=analyze_market_path(rows,SwingSettings())
    assert sum(out["path_breakout"]) == 1
    assert sum(out["path_pullback"]) == 0
