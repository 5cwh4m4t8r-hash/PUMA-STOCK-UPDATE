from pathlib import Path

from puma_trader.market_path import _anchor_concrete_before_224_breakout


def b(i, o, h, l, c, v=1000):
    return {"date": str(i), "open": float(o), "high": float(h), "low": float(l), "close": float(c), "volume": float(v)}


def test_concrete_upper_line_falls_back_to_bullish_close_before_224_breakout():
    candles = [
        b(0, 84, 88, 82, 86),
        b(1, 86, 91, 85, 90),
        b(2, 88, 92, 86, 91),
        b(3, 89, 94, 88, 93),
        b(4, 90, 93, 87, 91),
        b(5, 91, 95, 90, 94),  # highest meaningful bullish close
        b(6, 92, 94, 89, 91),
        b(7, 91, 93, 88, 90),
        b(8, 90, 92, 87, 89),
        b(9, 89, 91, 86, 88),
        b(10, 92, 112, 91, 110, 5000),  # strong breakout candle
    ]
    box = {
        "start": 0, "end": 9, "low": 82.0, "high": 96.0,
        "width_pct": 15.0, "structure_type": "공구리",
        "score": 80.0, "breakout_idx": -1, "accepted": False,
    }
    e112 = [100.0] * len(candles)

    out = _anchor_concrete_before_224_breakout(candles, box, 10, e112)
    assert out is not None
    assert out["upper_source"] == "양봉종가"
    assert out["high"] == 94.0
    assert out["high"] < min(e112[out["start"]:out["end"] + 1])


def test_concrete_upper_line_must_remain_below_ema112():
    candles = [
        b(i, 90, 95, 85, 94 if i % 2 == 0 else 91)
        for i in range(10)
    ]
    candles.append(b(10, 92, 112, 91, 110, 5000))
    box = {
        "start": 0, "end": 9, "low": 85.0, "high": 96.0,
        "width_pct": 12.0, "structure_type": "공구리",
        "score": 80.0, "breakout_idx": -1, "accepted": False,
    }
    e112 = [93.0] * len(candles)
    out = _anchor_concrete_before_224_breakout(candles, box, 10, e112)
    assert out is None


def test_concrete_is_only_created_from_ema224_breakout_path():
    src = Path("puma_trader/market_path.py").read_text(encoding="utf-8")
    assert "if 224 in crossed:" in src
    assert "No strong EMA224 breakout -> no concrete box is drawn yet." in src
    assert 'str(x.get("upper_source") or "") in ("전고언덕", "양봉종가")' in src
