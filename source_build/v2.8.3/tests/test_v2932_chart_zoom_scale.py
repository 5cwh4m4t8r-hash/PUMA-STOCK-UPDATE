from pathlib import Path


def test_chart_price_axis_does_not_auto_include_diagnostic_lists():
    src = Path("puma_trader/swing_chart.py").read_text(encoding="utf-8")
    start = src.index("def _prepare_render_cache")
    end = src.index("def _emit_paint_timing", start)
    block = src[start:end]
    assert "price_line_order" in block
    assert "signal_vema40" not in block
    assert "signal_disparity224" not in block
    assert "for k, value in series.items()" not in block


def test_chart_zoom_can_reach_fifteen_bars_and_uses_visible_price_scale():
    src = Path("puma_trader/swing_chart.py").read_text(encoding="utf-8")
    assert "max(15, min(total, new_n))" in src
    assert "candle_lo = min(float(c['low']) for c in cs)" in src
    assert "candle_hi = max(float(c['high']) for c in cs)" in src
    assert "include_near_price" in src
    assert "pad_ratio = 0.035 if n <= 30" in src
