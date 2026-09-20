from puma_trader.classification import classify_scores
from puma_trader.watermelon import build_watermelon


def test_candidate_classification():
    label, detail = classify_scores(70, 20, 10)
    assert label == "단타"
    assert "단 70" in detail
    label, _ = classify_scores(70, 65, 20)
    assert label == "단타+스윙"
    label, _ = classify_scores(10, 20, 35)
    assert label == "중장기관찰"


def test_watermelon_shape():
    rows = []
    price = 1000.0
    for i in range(100):
        price *= 1.003 if i > 60 else 1.0002
        rows.append({
            "date": f"202609{i%28+1:02d}090000",
            "open": price * 0.997,
            "high": price * 1.004,
            "low": price * 0.995,
            "close": price,
            "volume": 1000 if i < 60 else 2500,
        })
    out = build_watermelon(rows)
    assert len(out) == len(rows)
    assert set(out).issubset({-1, 0, 1})
