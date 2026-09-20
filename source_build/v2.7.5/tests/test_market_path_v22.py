from puma_trader.market_path import find_box_before
from puma_trader.swing import SwingSettings


def bar(i,o,h,l,c,v):
    return {"date":str(i),"open":o,"high":h,"low":l,"close":c,"volume":v}


def trend_then_box():
    rows=[]
    p=70.0
    for i in range(55):
        p += 0.55
        rows.append(bar(i,p-0.3,p+0.8,p-0.8,p,1000))
    for k in range(32):
        c=100+((k%4)-1.5)*0.55
        h=109.5 if k in (1,9,17,25) else c+1.0
        l=91.0 if k in (5,13,21,29) else c-1.0
        rows.append(bar(55+k,c-0.2,h,l,c,1000))
    return rows


def test_box_duration_is_chart_driven_not_fixed_60_112():
    rows=trend_then_box()
    b=find_box_before(rows,len(rows)-1,SwingSettings())
    assert b is not None
    assert 12 <= b["period"] < 60
    assert b["top_touches"] >= 3
    assert b["bottom_touches"] >= 3
    assert b["alternations"] >= 3


def test_clear_trend_is_not_box():
    rows=[]
    p=100.0
    for i in range(120):
        p += 1.2
        rows.append(bar(i,p-0.3,p+0.8,p-0.8,p,1000))
    assert find_box_before(rows,len(rows)-1,SwingSettings()) is None
