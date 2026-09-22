from datetime import datetime, timedelta

from puma_trader.gabojago import evaluate_gabojago


def d(day, o, h, l, c, v):
    return {"dt": day, "open_pric": str(o), "high_pric": str(h), "low_pric": str(l), "cur_prc": str(c), "trde_qty": str(v)}


def m(ts, o, h, l, c, v):
    return {"cntr_tm": ts, "open_pric": str(o), "high_pric": str(h), "low_pric": str(l), "cur_prc": str(c), "trde_qty": str(v)}


def daily_rows():
    rows = []
    start = datetime(2024, 12, 20)
    price = 1000.0
    for i in range(500):
        day = (start + timedelta(days=i)).strftime("%Y%m%d")
        rows.append(d(day, price, price * 1.01, price * .99, price, 100000))
    target = "20260922"
    prev5_high = max(float(x["high_pric"]) for x in rows[-5:])
    rows.append(d(target, prev5_high * 1.01, prev5_high * 1.08, prev5_high * 1.005, prev5_high * 1.07, 350000))
    return list(reversed(rows))


def test_pullback_entry_only_when_stop_has_distance():
    rows = [
        m("20260922090000", 1100, 1140, 1095, 1135, 50000),
        m("20260922090500", 1135, 1170, 1130, 1165, 70000),
        m("20260922091000", 1165, 1168, 1148, 1152, 30000),
    ]
    x = evaluate_gabojago(list(reversed(rows)), daily_rows(), now=datetime(2026,9,22,9,10))
    assert x.passed is True
    assert x.entry_kind == "PULLBACK"
    assert x.basis_open > 0


def test_body_rebreak_requires_body_not_wick():
    base = [
        m("20260922090000", 1100, 1140, 1095, 1135, 50000),
        m("20260922090500", 1135, 1170, 1130, 1165, 70000),
        m("20260922091000", 1165, 1168, 1148, 1152, 30000),
    ]
    wick = base + [m("20260922091500", 1152, 1180, 1150, 1168, 50000)]
    x = evaluate_gabojago(list(reversed(wick)), daily_rows(), now=datetime(2026,9,22,9,15))
    assert x.passed is False

    body = base + [m("20260922091500", 1152, 1190, 1150, 1180, 50000)]
    y = evaluate_gabojago(list(reversed(body)), daily_rows(), now=datetime(2026,9,22,9,15))
    assert y.passed is True
    assert y.entry_kind == "BODY_REBREAK"
