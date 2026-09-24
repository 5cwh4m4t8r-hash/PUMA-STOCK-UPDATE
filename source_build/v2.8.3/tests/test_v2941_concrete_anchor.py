from pathlib import Path

from puma_trader.market_path import _preview_concrete_before_bowl3


def b(i, o, h, l, c, v=1000):
    return {
        "date": str(i),
        "open": float(o),
        "high": float(h),
        "low": float(l),
        "close": float(c),
        "volume": float(v),
    }


def _pre_bowl_rows():
    rows = []
    for i in range(120):
        close = 90.0 + (i % 4) * 0.5
        rows.append(b(i, close - 0.5, 94.0, 80.0, close, 1000))
    # Current candle is still BELOW EMA224: this is before the 3/Bowl-3 breakout.
    rows[-1] = b(119, 94.0, 97.0, 90.0, 96.0, 1800)
    return rows


def test_concrete_preview_exists_before_ema224_breakout():
    candles = _pre_bowl_rows()
    box = {
        "start": 60,
        "end": 119,
        "low": 80.0,
        "high": 98.0,
        "width_pct": 20.0,
        "structure_type": "공구리",
        "score": 80.0,
        "breakout_idx": -1,
        "accepted": False,
    }
    e112 = [105.0] * len(candles)
    e224 = [100.0] * len(candles)

    out = _preview_concrete_before_bowl3(candles, box, 119, e112, e224)
    assert out is not None
    assert out["preview"] is True
    assert out["breakout_idx"] == -1
    assert out["upper_source"] in ("전고언덕", "양봉종가")
    assert out["high"] < 105.0
    assert candles[119]["close"] < e224[119]


def test_concrete_preview_upper_line_must_stay_below_ema112():
    candles = _pre_bowl_rows()
    for i in range(60, 120):
        candles[i] = b(i, 94.0, 98.0, 90.0, 96.0, 1000)
    box = {
        "start": 60,
        "end": 119,
        "low": 90.0,
        "high": 98.0,
        "width_pct": 9.0,
        "structure_type": "공구리",
        "score": 80.0,
        "breakout_idx": -1,
        "accepted": False,
    }
    e112 = [93.0] * len(candles)
    e224 = [100.0] * len(candles)

    out = _preview_concrete_before_bowl3(candles, box, 119, e112, e224)
    assert out is None


def test_breakout_uses_concrete_that_already_existed_on_previous_bar():
    src = Path("puma_trader/market_path.py").read_text(encoding="utf-8")
    assert "concrete must ALREADY EXIST before the EMA224 breakout" in src
    assert "_preview_concrete_before_bowl3(" in src
    assert "_anchor_concrete_before_224_breakout" not in src
    assert "raw_preview = find_box_before(candles, n - 1, settings)" in src
