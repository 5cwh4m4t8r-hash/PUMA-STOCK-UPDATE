from pathlib import Path


def test_raw_accumulation_candidates_are_not_drawn():
    src = Path("puma_trader/swing_chart.py").read_text(encoding="utf-8")
    assert "Raw accumulation candidates are intentionally not drawn." in src
    assert "is_candidate = i < len(raw_acc)" not in src
    assert "매집확정" in src


def test_concrete_boxes_are_hidden_when_current_price_is_above_ema224():
    src = Path("puma_trader/swing_chart.py").read_text(encoding="utf-8")
    assert "current_above_224 = bool(" in src
    assert "float(candles[-1]['close']) > float(ema224_full[len(candles)-1])" in src
    assert "not (current_above_224 and b.get('structure_type') == '공구리')" in src


def test_accumulation_display_and_internal_evidence_are_separate():
    src = Path("puma_trader/swing.py").read_text(encoding="utf-8")
    assert "acc_evidence_flags" in src
    assert "cluster_confirmed" in src
    assert "build_puma_watermelon(candles, arrow_series, acc_flags=acc_evidence_flags)" in src
