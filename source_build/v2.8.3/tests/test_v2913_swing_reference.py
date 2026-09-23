from puma_trader.bowl import analyze_bowl
from puma_trader.swing import analyze, demo_candles, normalize_candles
from puma_trader.swing_reference import evaluate_swing_reference_profiles


def test_reference_profiles_are_exposed_and_scored():
    candles = normalize_candles(demo_candles(620))
    out = evaluate_swing_reference_profiles(candles)
    assert set(("A", "B", "C")).issubset(out)
    assert 0 <= out["best_score"] <= 100
    for key in ("A", "B", "C"):
        assert 0 <= out[key]["score"] <= 100
        assert isinstance(out[key]["summary"], str)
        assert isinstance(out[key]["features"], dict)


def test_swing_analysis_contains_three_photo_searchers():
    analysis, series = analyze(demo_candles(620))
    assert "스윙검색기 A · 224근접" in analysis.details
    assert "스윙검색기 B · 급등후눌림" in analysis.details
    assert "스윙검색기 C · 장기돌파" in analysis.details
    assert "스윙검색기 종합" in analysis.details
    assert isinstance(series.get("swing_reference"), dict)


def test_bowl3_has_prebreak_stage_context():
    analysis, series = analyze_bowl(demo_candles(620))
    assert "밥그릇 단계" in analysis.details
    assert "밥3 직전조건" in analysis.details
    assert "역배열 60<112<224" in analysis.details
    assert "112봉 신고거래량" in analysis.details
    assert "2번구간 횡보" in analysis.details
    assert 0 <= analysis.score <= 100
    assert "bowl_stage2_ready" in series
