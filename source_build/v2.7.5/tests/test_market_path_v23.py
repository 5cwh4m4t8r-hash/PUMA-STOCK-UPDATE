from puma_trader.market_path import find_box_before
from puma_trader.swing import SwingSettings


def b(i,o,h,l,c,v):
    return {"date":str(i),"open":o,"high":h,"low":l,"close":c,"volume":v}


def base_box():
    rows=[]
    for i in range(40):
        p=80+i*0.3
        rows.append(b(i,p-0.2,p+0.8,p-0.8,p,1000))
    for k in range(32):
        c=100+((k%4)-1.5)*0.5
        h=108.5 if k in (1,9,17,25) else c+1.0
        l=92.0 if k in (5,13,21,29) else c-1.0
        rows.append(b(40+k,c-0.2,h,l,c,1000))
    return rows


def test_real_box_is_found_with_nonfixed_duration():
    rows=base_box()
    x=find_box_before(rows,len(rows)-1,SwingSettings())
    assert x is not None
    assert 12 <= x["period"] < 60
    assert x["top_touches"] >= 3
    assert x["bottom_touches"] >= 3
    assert x["alternations"] >= 3


def test_box_start_and_end_are_actual_boundary_touches():
    rows=base_box()
    x=find_box_before(rows,len(rows)-1,SwingSettings())
    assert x is not None
    assert x["start"] >= 40
    assert x["end"] <= len(rows)-1
