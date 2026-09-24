from pathlib import Path

from puma_trader.market_path import analyze_market_path, clear_market_path_cache
from puma_trader.swing import SwingSettings


def b(i, o, h, l, c, v=1000):
    return {"date": str(i), "open": o, "high": h, "low": l, "close": c, "volume": v}


def test_bowl_chart_uses_simple_bowl3_label_only():
    src = Path("puma_trader/bowl.py").read_text(encoding="utf-8")
    assert "'label': '밥3'" in src
    assert "'label': f'밥3 " not in src
    assert '"label": f"밥3 ' not in src


def test_current_concrete_is_not_exposed_above_ema224():
    rows = []
    for i in range(240):
        rows.append(b(i, 120, 121, 119, 120, 1000))
    for k in range(30):
        c = 90 + ((k % 4) - 1.5) * 0.4
        h = 97 if k in (1, 9, 17, 25) else c + 1.0
        l = 84 if k in (5, 13, 21, 29) else c - 1.0
        rows.append(b(240 + k, c - 0.2, h, l, c, 1000))

    # Strong breakout carries current price above EMA224.
    rows.append(b(270, 90, 117, 89, 115, 4000))
    clear_market_path_cache()
    out = analyze_market_path(rows, SwingSettings())

    assert out["current"]["breakout_idx"] >= 0
    assert out["box"] is None or out["box"].get("structure_type") != "공구리"
    # Past valid concrete may remain visible; only CURRENT concrete is forbidden above EMA224.


def test_concrete_filter_requires_box_top_below_ema112():
    src = Path("puma_trader/market_path.py").read_text(encoding="utf-8")
    assert "def concrete_allowed_below_long_mas" in src
    assert "box_high < min(valid_112)" in src
    assert "e112[j] is not None" in src
    assert "box_for_ui = None if event.get(\"structure_type\") == \"공구리\" else event" in src
