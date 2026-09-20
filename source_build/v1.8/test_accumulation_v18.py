from puma_trader.swing import SwingSettings, accumulation_flags


def _base_candle(i, volume=1000):
    p = 100 + i * 0.05
    return {"date": f"202601{i%28+1:02d}", "open": p, "high": p+1, "low": p-1, "close": p+0.2, "volume": volume}


def _upper_wick_candle(i):
    p = 102
    return {"date": f"202602{i%28+1:02d}", "open": p, "high": p+8, "low": p-1, "close": p+0.5, "volume": 2800}


def test_single_candidate_is_not_confirmed_accumulation():
    rows = [_base_candle(i) for i in range(30)] + [_upper_wick_candle(2)]
    flags, meta = accumulation_flags(rows, SwingSettings())
    assert meta[-1]["raw_candidate"] is True
    assert flags[-1] is False


def test_repeated_candidates_form_confirmed_accumulation_zone():
    rows = [_base_candle(i) for i in range(30)]
    rows.append(_upper_wick_candle(2))
    rows.extend(_base_candle(40+i) for i in range(6))
    rows.append(_upper_wick_candle(9))
    flags, meta = accumulation_flags(rows, SwingSettings())
    idx = [i for i, x in enumerate(flags) if x]
    assert len(idx) >= 2
    assert meta[idx[-1]]["confirmed"] is True
    assert meta[idx[-1]]["cluster_size"] >= 2
