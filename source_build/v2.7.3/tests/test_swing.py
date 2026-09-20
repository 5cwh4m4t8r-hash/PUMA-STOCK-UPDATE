from puma_trader.swing import SwingSettings, analyze, demo_candles, normalize_candles, accumulation_flags, shifted_bbands_upper


def test_demo_analyzes():
    a, s = analyze(demo_candles())
    assert len(s['candles']) >= 500
    assert a.accumulation_count >= 0
    assert isinstance(a.box_found, bool)


def test_blue_formula_shape():
    candles = normalize_candles(demo_candles())
    closes = [x['close'] for x in candles]
    line = shifted_bbands_upper(closes, 26, 2.6, 26)
    assert len(line) == len(closes)
    assert line[-1] is not None


def test_accumulation_is_volume_plus_pattern():
    candles = normalize_candles(demo_candles())
    flags, meta = accumulation_flags(candles, SwingSettings())
    idx = [i for i,v in enumerate(flags) if v]
    assert idx
    assert all(meta[i]['volume_ratio'] >= 2.0 for i in idx)
