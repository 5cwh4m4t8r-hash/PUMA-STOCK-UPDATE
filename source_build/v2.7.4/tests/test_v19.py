from puma_trader.swing import SwingSettings, detect_breakout_pullback


def _c(date, o, h, l, c, v):
    return {"date": date, "open": o, "high": h, "low": l, "close": c, "volume": v}


def test_breakout_pullback_pattern_like_ytn():
    rows=[]
    p=2000.0
    # quiet base
    for i in range(25):
        rows.append(_c(f"202608{i+1:02d}", p, p+20, p-20, p+5, 10000+i*100))
    # explosive 기준봉, then volatile pullback with contracting volume and base hold
    rows += [
        _c("20260914", 1969, 2500, 1963, 2030, 2497665),
        _c("20260915", 2135, 2635, 2075, 2635, 1011107),
        _c("20260916", 2995, 3160, 2350, 2390, 4425959),
        _c("20260917", 2445, 2605, 2345, 2390, 2141645),
        _c("20260918", 2380, 2445, 2265, 2305, 760217),
    ]
    out=detect_breakout_pullback(rows)
    assert out["confirmed"] is True
    assert out["impulse_index"] >= 0
    assert out["quality"] >= 60
    assert out["current_above_impulse_open"] is True


def test_no_breakout_pullback_without_impulse():
    rows=[_c(f"202608{i+1:02d}",100,102,98,101,10000) for i in range(35)]
    out=detect_breakout_pullback(rows)
    assert out["confirmed"] is False
