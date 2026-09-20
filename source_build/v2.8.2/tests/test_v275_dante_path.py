from puma_trader.market_path import analyze_market_path, find_box_before, clear_market_path_cache
from puma_trader.swing import SwingSettings


def b(i,o,h,l,c,v=1000):
    return {"date":str(i),"open":o,"high":h,"low":l,"close":c,"volume":v}


def strict_bottom_box():
    rows=[]
    for i in range(240):
        rows.append(b(i,120,121,119,120,1000))
    for k in range(30):
        c=90 + ((k % 4)-1.5)*0.4
        h=97 if k in (1,9,17,25) else c+1.0
        l=84 if k in (5,13,21,29) else c-1.0
        rows.append(b(240+k,c-0.2,h,l,c,1000))
    return rows


def bowl3_box():
    rows=[]
    for i in range(240):
        rows.append(b(i,130,131,129,130,1000))
    for i in range(70):
        rows.append(b(240+i,100,101,99,100,1000))
    for k in range(30):
        c=100 + ((k%4)-1.5)*0.45
        h=107 if k in (1,9,17,25) else c+1.0
        l=94 if k in (5,13,21,29) else c-1.0
        rows.append(b(310+k,c-0.2,h,l,c,1000))
    return rows


def test_concrete_box_is_dynamic_and_repeated():
    clear_market_path_cache()
    rows=strict_bottom_box()
    s=SwingSettings()
    x=find_box_before(rows,len(rows)-1,s)
    assert x is not None
    assert 12 <= x["period"] < 60
    assert x["top_touches"] >= 3
    assert x["bottom_touches"] >= 3
    assert x["alternations"] >= 3
    assert x["drift_pct"] <= s.box_max_drift_pct


def test_plain_box_break_without_112_224_cross_is_not_breakout():
    clear_market_path_cache()
    rows=strict_bottom_box()
    rows.append(b(270,91,101,90,99,1800))
    out=analyze_market_path(rows,SwingSettings())
    assert sum(out["path_breakout"]) == 0


def test_bottom_112_break_and_structure_break_is_confirmed():
    clear_market_path_cache()
    rows=strict_bottom_box()
    rows.append(b(270,90,117,89,115,1800))
    out=analyze_market_path(rows,SwingSettings())
    assert sum(out["path_breakout"]) == 1
    idx=out["path_breakout"].index(True)
    assert out["path_breakout_ma"][idx] in (112,224)
    assert out["current"]["context_name"] == "바닥권"
    assert out["current"]["stage"] == "확정 돌파"


def test_pullback_requires_bearish_ma_touch_and_dead_volume():
    clear_market_path_cache()
    rows=strict_bottom_box()
    rows.append(b(270,90,117,89,115,1800))
    rows.append(b(271,114,115,106,108,500))
    out=analyze_market_path(rows,SwingSettings())
    assert sum(out["path_breakout"]) == 1
    assert sum(out["path_pullback"]) == 1
    pidx=out["path_pullback"].index(True)
    assert out["path_pullback_ma"][pidx] in (112,224)
    assert out["current"]["stage"] in ("확정 눌림","확정 눌림 / 재상승 대기")


def test_green_or_high_volume_retrace_is_not_pullback():
    clear_market_path_cache()
    rows=strict_bottom_box()
    rows.append(b(270,90,117,89,115,1800))
    rows.append(b(271,107,112,106,111,400))
    rows.append(b(272,114,115,106,108,1700))
    out=analyze_market_path(rows,SwingSettings())
    assert sum(out["path_pullback"]) == 0


def test_rebreak_only_after_valid_ma_pullback():
    clear_market_path_cache()
    rows=strict_bottom_box()
    rows.append(b(270,90,117,89,115,1800))
    rows.append(b(271,114,115,106,108,500))
    rows.append(b(272,109,121,108,120,4000))
    out=analyze_market_path(rows,SwingSettings())
    assert sum(out["path_breakout"]) == 1
    assert sum(out["path_pullback"]) == 1
    assert sum(out["path_rebreakout"]) == 1
    assert out["current"]["stage"] == "확정 재돌파"


def test_bowl3_context_can_confirm_long_ma_breakout():
    clear_market_path_cache()
    rows=bowl3_box()
    rows.append(b(340,100,122,99,120,1800))
    out=analyze_market_path(rows,SwingSettings())
    assert sum(out["path_breakout"]) == 1
    assert out["current"]["context_name"] in ("밥그릇3","바닥권")
