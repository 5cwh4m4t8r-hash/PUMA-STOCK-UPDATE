from puma_trader.bowl import analyze_bowl
from puma_trader.swing import demo_candles


def test_bowl_series_exposes_chart_marker_metadata():
    analysis, series = analyze_bowl(demo_candles(620))
    assert "bowl3_markers" in series
    assert isinstance(series["bowl3_markers"], list)
    for marker in series["bowl3_markers"]:
        assert marker["kind"] in {"prebreak", "breakout", "accepted", "core"}
        assert 0 <= int(marker["index"]) < len(series["candles"])
        label = str(marker["label"])
        if marker["kind"] == "core":
            assert label.startswith("밥3")
        else:
            assert label in {"224 직전", "224 돌파", "돌파 유지"}
