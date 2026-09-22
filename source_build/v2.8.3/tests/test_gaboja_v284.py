from datetime import datetime, timedelta

from puma_trader.gaboja import evaluate_gaboja


def _d(date, o, h, l, c, v):
    return {"date": date, "open": o, "high": h, "low": l, "close": c, "volume": v}


def _daily():
    rows = []
    # enough history for BB40 and EAVG context
    p = 100.0
    start = datetime(2025, 1, 1)
    for i in range(55):
        dt = (start + timedelta(days=i)).strftime("%Y%m%d")
        rows.append(_d(dt, p, p + 1, p - 1, p, 1000))
    # previous five stay below 105
    rows[-6:-1] = [
        _d("20260916", 100, 104, 99, 100, 1000),
        _d("20260917", 100, 104, 99, 100, 1000),
        _d("20260918", 100, 104, 99, 100, 1000),
        _d("20260921", 100, 104, 99, 100, 1000),
        _d("20260922", 100, 104, 99, 100, 1000),
    ]
    # gap above previous 5 highs, >3x volume, closes through long EAVG/BB area
    rows[-1] = _d("20260923", 106, 125, 106, 124, 3500)
    return rows


def _minute(body_break=True):
    rows = [
        _d("20260923090000", 106, 107, 105.8, 106.5, 500),
        _d("20260923090500", 106.5, 109, 106.4, 108.8, 600),
        _d("20260923091000", 108.8, 113, 108.7, 112.5, 1200),  # 영1
        _d("20260923091500", 112.0, 112.3, 110.0, 111.6, 500), # 차
    ]
    if body_break:
        rows.append(_d("20260923092000", 112.2, 114.5, 112.0, 114.0, 800))
    return rows


def test_gaboja_pullback_entry():
    sig = evaluate_gaboja(_minute(False), _daily(), now=datetime(2026,9,23,9,15))
    assert sig.passed is True
    assert sig.entry_kind == "PULLBACK"
    assert sig.basis_open == 106


def test_gaboja_body_rebreak_requires_body_cross():
    sig = evaluate_gaboja(_minute(True), _daily(), now=datetime(2026,9,23,9,20))
    assert sig.passed is True
    assert sig.entry_kind == "BODY_REBREAK"
    assert sig.young1_high == 113


def test_tail_only_break_is_rejected():
    rows = _minute(False)
    rows.append(_d("20260923092000", 112.0, 114.5, 111.8, 112.8, 800))
    sig = evaluate_gaboja(rows, _daily(), now=datetime(2026,9,23,9,20))
    assert sig.passed is False


def test_pullback_cannot_touch_basis_open():
    rows = _minute(False)
    rows[-1] = _d("20260923091500", 112.0, 112.2, 106.0, 110.0, 400)
    sig = evaluate_gaboja(rows, _daily(), now=datetime(2026,9,23,9,15))
    assert sig.passed is False
