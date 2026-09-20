from PySide6.QtWidgets import QApplication
from puma_trader.swing_chart import SwingChart


def _app():
    return QApplication.instance() or QApplication([])


def test_render_cache_precomputes_line_and_day_keys():
    _app()
    w = SwingChart()
    candles = [
        {"date":"20260921090000","open":10,"high":12,"low":9,"close":11,"volume":100},
        {"date":"20260921090500","open":11,"high":13,"low":10,"close":12,"volume":120},
    ]
    w.set_basic_data(candles, {"ema5":[10.0,11.0], "path_breakout":[False,True]})
    assert "ema5" in w._line_keys
    assert "path_breakout" not in w._line_keys
    assert w._day_keys == ("20260921","20260921")
