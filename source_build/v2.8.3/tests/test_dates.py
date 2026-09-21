from datetime import datetime, timedelta

from puma_trader.danta import available_minute_dates, analyze_danta_for_date, slice_series_for_date


def _rows():
    out = []
    for day in ("20260917", "20260918", "20260919"):
        t = datetime.strptime(day + "090000", "%Y%m%d%H%M%S")
        price = 1000.0
        for i in range(80):
            price *= 1.001 + (0.0005 if day == "20260918" else 0)
            out.append({
                "cntr_tm": (t + timedelta(minutes=5*i)).strftime("%Y%m%d%H%M%S"),
                "open_pric": str(price * .998),
                "high_pric": str(price * 1.002),
                "low_pric": str(price * .997),
                "cur_prc": str(price),
                "trde_qty": str(1000 + i * 20),
            })
    return list(reversed(out))


def _daily():
    out = []
    for d in ("20260914","20260915","20260916","20260917","20260918","20260919"):
        out.append({"dt":d,"open_pric":"900","high_pric":"1200","low_pric":"850","cur_prc":"1000","trde_qty":"100000"})
    return list(reversed(out))


def test_dates_and_historical_slice():
    rows = _rows()
    assert available_minute_dates(rows) == ["20260917","20260918","20260919"]
    result, series, day = analyze_danta_for_date(rows, _daily(), "20260918")
    assert day == "20260918"
    assert result.details["분석 기준일"] == "2026-09-18"
    # future day must not exist in historical context
    assert max(c["date"][:8] for c in series["candles"]) == "20260918"
    sliced = slice_series_for_date(series, day)
    assert sliced["candles"]
    assert {c["date"][:8] for c in sliced["candles"]} == {"20260918"}
