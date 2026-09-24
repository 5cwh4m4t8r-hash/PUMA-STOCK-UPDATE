from puma_trader.swing import SwingSettings, accumulation_flags, confirm_accumulation_flags


def _base_candles(n=30):
    return [
        {
            "date": str(i),
            "open": 100.0,
            "high": 102.0,
            "low": 98.0,
            "close": 101.0,
            "volume": 1000.0,
        }
        for i in range(n)
    ]


def test_low_volume_long_upper_wick_is_not_accumulation():
    candles = _base_candles()
    candles[-1] = {
        "date": "x",
        "open": 100.0,
        "high": 112.0,
        "low": 99.0,
        "close": 102.0,
        "volume": 2500.0,  # < 3x prior 20-bar average
    }
    raw, meta = accumulation_flags(candles, SwingSettings())
    assert raw[-1] is False
    assert meta[-1]["volume_ratio"] < 3.0


def test_large_bearish_dump_is_not_accumulation_even_with_volume():
    candles = _base_candles()
    candles[-1] = {
        "date": "x",
        "open": 112.0,
        "high": 114.0,
        "low": 98.0,
        "close": 100.0,
        "volume": 5000.0,
    }
    raw, meta = accumulation_flags(candles, SwingSettings())
    assert raw[-1] is False


def test_small_cross_doji_is_not_accumulation_even_with_long_wick_and_volume():
    candles = _base_candles()
    candles[-1] = {
        "date": "x",
        "open": 100.0,
        "high": 112.0,
        "low": 99.0,
        "close": 100.4,
        "volume": 5000.0,
    }
    raw, meta = accumulation_flags(candles, SwingSettings())
    assert raw[-1] is False
    assert meta[-1]["excluded_small_cross"] is True


def test_high_volume_long_upper_wick_is_accumulation_candidate():
    candles = _base_candles()
    candles[-1] = {
        "date": "x",
        "open": 100.0,
        "high": 112.0,
        "low": 99.0,
        "close": 102.0,
        "volume": 5000.0,
    }
    raw, meta = accumulation_flags(candles, SwingSettings())
    assert raw[-1] is True
    assert meta[-1]["pattern"] == "고거래량 긴 윗꼬리"
    assert meta[-1]["volume_ratio"] >= 3.0
    assert meta[-1]["upper_wick_ratio"] >= 0.45
    assert meta[-1]["body_ratio"] >= 0.10


def test_chart_confirmation_still_requires_repeated_strict_candidates():
    candles = _base_candles(45)
    for idx in (30, 38):
        candles[idx] = {
            "date": str(idx),
            "open": 100.0,
            "high": 112.0,
            "low": 99.0,
            "close": 102.0,
            "volume": 5000.0,
        }
    raw, meta = accumulation_flags(candles, SwingSettings())
    confirmed = confirm_accumulation_flags(raw, meta, cluster_window=20)
    assert raw[30] is True and raw[38] is True
    assert confirmed[30] is True and confirmed[38] is True
