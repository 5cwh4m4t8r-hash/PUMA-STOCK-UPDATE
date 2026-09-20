from puma_trader.market_path import analyze_market_path, find_box_before
from puma_trader.swing import SwingSettings


def b(i,o,h,l,c,v):
    return {"date":str(i),"open":o,"high":h,"low":l,"close":c,"volume":v}


def base_box(n=26):
    rows=[]
    for i in range(35):
        p=80+i*0.35
        rows.append(b(i,p-0.2,p+0.8,p-0.8,p,1000))
    for k in range(n):
        c=100+((k%6)-3)*0.55
        h=108.5 if k in (2,10,18,25) else c+1.0
        l=92.0 if k in (5,13,21) else c-1.0
        rows.append(b(35+k,c-0.2,h,l,c,1000+(k%3)*40))
    return rows


def test_real_box_is_found_with_nonfixed_duration():
    rows=base_box()
    s=SwingSettings()
    x=find_box_before(rows,len(rows)-1,s)
    assert x is not None
    assert 10 <= x["period"] < 60
    assert x["top_touches"] >= 2
    assert x["bottom_touches"] >= 2
    assert x["alternations"] >= 2


def test_box_breakout_accepts_300pct_previous_bar():
    rows=base_box()
    # 300%+ vs previous bar, less strict than demanding 300% of 20-bar average too.
    prev=rows[-1]["volume"]
    rows.append(b(61,101,114,100,112,prev*3.2))
    out=analyze_market_path(rows,SwingSettings())
    assert sum(out["path_breakout"]) == 1
    assert out["current"]["stage"] == "확정 돌파"


def test_pullback_is_marked_once_when_volume_dies():
    rows=base_box()
    rows.append(b(61,101,114,100,112,4200))
    rows.append(b(62,112,113,107,109,1700))
    rows.append(b(63,109,111,105,107,1200))
    out=analyze_market_path(rows,SwingSettings())
    assert sum(out["path_breakout"]) == 1
    assert sum(out["path_pullback"]) == 1
    assert out["current"]["stage"] in ("확정 눌림","눌림 확인 / 재상승 대기")


def test_rebreakout_after_pullback_needs_renewed_volume():
    rows=base_box()
    rows.append(b(61,101,114,100,112,4200))
    rows.append(b(62,112,113,107,109,1600))
    rows.append(b(63,109,111,105,107,1100))
    rows.append(b(64,108,119,107,118,4300))
    out=analyze_market_path(rows,SwingSettings())
    assert sum(out["path_breakout"]) == 1
    assert sum(out["path_pullback"]) == 1
    assert sum(out["path_rebreakout"]) == 1
    assert out["current"]["stage"] == "확정 재돌파"


def test_high_volume_decline_not_pullback():
    rows=base_box()
    rows.append(b(61,101,114,100,112,4200))
    rows.append(b(62,112,113,107,109,3500))
    rows.append(b(63,109,111,105,107,3200))
    out=analyze_market_path(rows,SwingSettings())
    assert sum(out["path_pullback"]) == 0
