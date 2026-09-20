from datetime import datetime, timedelta

from puma_trader.danta import analyze_danta


def _minute_rows():
    rows = []
    start = datetime(2026, 9, 18, 8, 55)
    price = 10000.0
    for i in range(90):
        t = start + timedelta(minutes=5 * i)
        op = price
        price *= 1.0015
        rows.append({
            "cntr_tm": t.strftime("%Y%m%d%H%M%S"),
            "open_pric": str(int(op)),
            "high_pric": str(int(price * 1.002)),
            "low_pric": str(int(op * 0.999)),
            "cur_prc": str(int(price)),
            "trde_qty": str(10000 + i * 250),
        })
    return list(reversed(rows))


def _daily_rows():
    rows = []
    start = datetime(2026, 9, 10)
    for i in range(7):
        d = start + timedelta(days=i)
        rows.append({
            "dt": d.strftime("%Y%m%d"),
            "open_pric": "9500",
            "high_pric": "10500",
            "low_pric": "9400",
            "cur_prc": "10000",
            "trde_qty": "500000",
        })
    return list(reversed(rows))


def test_danta_returns_score_and_details():
    result, series = analyze_danta(
        _minute_rows(),
        _daily_rows(),
        now=datetime(2026, 9, 18, 9, 20),
    )
    assert 0 <= result.score <= 100
    assert "5분 기준선" in result.details
    assert "ema5" in series
    assert "kijun" in series
