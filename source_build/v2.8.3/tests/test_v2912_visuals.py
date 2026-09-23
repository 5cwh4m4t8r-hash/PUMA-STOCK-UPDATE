from puma_trader.classification import classify_scores
from puma_trader.market_path import _dedupe_display_boxes
from puma_trader.watermelon_proxy import build_puma_watermelon


def test_concrete_history_dedupes_same_zone_but_keeps_past_zone():
    same_a = {
        "start": 10, "end": 40, "low": 100.0, "high": 112.0,
        "period": 31, "score": 70.0, "structure_type": "공구리",
        "breakout_idx": 41, "accepted": True,
    }
    same_b = {
        "start": 14, "end": 44, "low": 101.5, "high": 113.0,
        "period": 31, "score": 82.0, "structure_type": "공구리",
        "breakout_idx": 45, "accepted": True,
    }
    old = {
        "start": 80, "end": 110, "low": 145.0, "high": 160.0,
        "period": 31, "score": 78.0, "structure_type": "공구리",
        "breakout_idx": 111, "accepted": True,
    }
    boxes = _dedupe_display_boxes([same_a, same_b, old])
    assert len(boxes) == 2
    assert boxes[0]["start"] == 10
    assert boxes[0]["end"] == 44
    assert boxes[1]["start"] == 80


def test_long_classification_explicitly_marks_bowl3():
    label, detail = classify_scores(20, 30, 75)
    assert "중장기" in label
    assert "밥3" in label
    assert "밥3 75" in detail


def test_arrow_overlap_alone_never_creates_watermelon_marker():
    candles = []
    price = 220.0
    for i in range(380):
        if i < 270:
            price *= 0.9985
        elif i < 340:
            price *= 1.0001
        else:
            price *= 1.003
        candles.append({
            "open": price * 0.997,
            "high": price * 1.008,
            "low": price * 0.990,
            "close": price,
            "volume": 1000.0,
            "date": str(i),
        })

    arrows = {
        "signal_pink": [True] * len(candles),
        "signal_blue": [False] * len(candles),
        "signal_red": [False] * len(candles),
        "signal_black": [False] * len(candles),
    }
    out = build_puma_watermelon(candles, arrows, acc_flags=[False] * len(candles))
    assert not any(out["watermelon_display"])
