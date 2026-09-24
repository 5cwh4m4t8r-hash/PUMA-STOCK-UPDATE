from puma_trader.bowl import BowlSettings, _historical_bowl3_markers, analyze_bowl
from puma_trader.swing import demo_candles


def test_bowl_series_exposes_chart_marker_metadata():
    analysis, series = analyze_bowl(demo_candles(620))
    assert "bowl3_markers" in series
    assert isinstance(series["bowl3_markers"], list)
    for marker in series["bowl3_markers"]:
        assert marker["kind"] in {"prebreak", "breakout", "accepted", "historical_core", "core"}
        assert 0 <= int(marker["index"]) < len(series["candles"])
        label = str(marker["label"])
        if marker["kind"] in {"historical_core", "core"}:
            assert label.startswith("밥3")
        else:
            assert label in {"224 직전", "224 양봉돌파", "돌파 유지"}


def test_historical_bowl3_marker_survives_newer_bars():
    settings = BowlSettings()
    candles = []
    for i in range(340):
        close = 90.0
        if i == 300:
            close = 105.0
        elif i > 300:
            close = 104.0 if i < 304 else 101.0 if i == 304 else 102.0
        low = close - 1.0
        if i == 304:
            low = 99.5
        open_price = close - 0.5
        if i == 300:
            open_price = 99.0
        elif i == 304:
            open_price = 103.0
        candles.append({
            "date": f"2025{i // 28 + 1:02d}{i % 28 + 1:02d}",
            "open": open_price,
            "high": close + 1.0,
            "low": low,
            "close": close,
            "volume": 1000.0,
        })

    e224 = [None] * 223 + [100.0] * (340 - 223)
    e112 = [None] * 111 + [95.0] * (340 - 111)

    markers = _historical_bowl3_markers(candles, e112, e224, settings)
    assert any(
        marker["kind"] == "historical_core"
        and int(marker["index"]) == 304
        and str(marker["label"]).startswith("밥3 ")
        and str(marker.get("retest_source") or "") in ("기준봉시가", "112EMA", "공구리중간")
        for marker in markers
    )

    # Newer bars appended later must not remove the already found historical spot.
    candles.extend([
        {
            "date": f"202612{day:02d}",
            "open": 102.0,
            "high": 103.0,
            "low": 101.0,
            "close": 102.0,
            "volume": 1000.0,
        }
        for day in range(1, 11)
    ])
    e224.extend([100.0] * 10)
    e112.extend([95.0] * 10)
    markers2 = _historical_bowl3_markers(candles, e112, e224, settings)
    assert any(int(marker["index"]) == 304 for marker in markers2)
