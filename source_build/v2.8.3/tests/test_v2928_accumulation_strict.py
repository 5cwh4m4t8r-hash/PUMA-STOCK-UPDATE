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


def test_long_upper_wick_without_burst_volume_is_not_accumulation():
    candles = _base_candles()
    candles[-1] = {
        "date": "x",
        "open": 100.0,
        "high": 112.0,
        "low": 99.0,
        "close": 102.0,
        "volume": 1200.0,
    }
    raw, meta = accumulation_flags(candles, SwingSettings())
    assert raw[-1] is False
    assert meta[-1]["long_upper"] is True
    assert meta[-1]["burst_volume"] is False


def test_long_upper_wick_with_burst_volume_is_accumulation():
    candles = _base_candles()
    candles[-1] = {
        "date": "x",
        "open": 100.0,
        "high": 112.0,
        "low": 99.0,
        "close": 102.0,
        "volume": 2200.0,
    }
    raw, meta = accumulation_flags(candles, SwingSettings())
    assert raw[-1] is True
    assert meta[-1]["long_wick_burst"] is True
    assert meta[-1]["pattern"] == "폭발거래량 긴 윗꼬리"


def test_large_bearish_dump_with_stronger_burst_volume_is_accumulation():
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
    assert raw[-1] is True
    assert meta[-1]["big_bear_burst"] is True
    assert meta[-1]["pattern"] == "폭발거래량 장대음봉"


def test_tiny_doji_is_excluded_even_with_huge_volume():
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


def test_ambiguous_ordinary_bar_is_excluded_even_with_large_volume():
    candles = _base_candles()
    candles[-1] = {
        "date": "x",
        "open": 100.0,
        "high": 104.0,
        "low": 99.0,
        "close": 103.0,
        "volume": 5000.0,
    }
    raw, meta = accumulation_flags(candles, SwingSettings())
    assert raw[-1] is False
    assert meta[-1]["long_upper"] is False
    assert meta[-1]["big_bear"] is False
    assert meta[-1]["excluded_ambiguous_shape"] is True


def test_repeated_clear_accumulation_cluster_displays_only_strongest_bar():
    candles = _base_candles(45)
    for idx, vol in ((30, 2200.0), (38, 2600.0)):
        candles[idx] = {
            "date": str(idx),
            "open": 100.0,
            "high": 112.0,
            "low": 99.0,
            "close": 102.0,
            "volume": vol,
        }
    raw, meta = accumulation_flags(candles, SwingSettings())
    confirmed = confirm_accumulation_flags(raw, meta, cluster_window=20)
    assert raw[30] is True and raw[38] is True
    assert sum(1 for x in confirmed if x) == 1
    shown = [i for i, x in enumerate(confirmed) if x]
    assert shown == [38]
    assert meta[38]["cluster_representative"] is True


def test_declining_volume_is_never_accumulation():
    candles = _base_candles()
    candles[-2]["volume"] = 5000.0
    candles[-1] = {
        "date": "x",
        "open": 100.0,
        "high": 116.0,
        "low": 98.0,
        "close": 102.0,
        "volume": 4000.0,
    }
    raw, meta = accumulation_flags(candles, SwingSettings())
    assert raw[-1] is False
    assert meta[-1]["volume_up_vs_prev"] is False


def test_equal_volume_is_not_accumulation():
    candles = _base_candles()
    candles[-2]["volume"] = 4000.0
    candles[-1] = {
        "date": "x",
        "open": 100.0,
        "high": 116.0,
        "low": 98.0,
        "close": 102.0,
        "volume": 4000.0,
    }
    raw, meta = accumulation_flags(candles, SwingSettings())
    assert raw[-1] is False


def test_non_big_bearish_candle_is_never_accumulation():
    candles = _base_candles()
    candles[-1] = {
        "date": "x",
        "open": 103.0,
        "high": 114.0,
        "low": 99.0,
        "close": 101.0,
        "volume": 5000.0,
    }
    raw, meta = accumulation_flags(candles, SwingSettings())
    assert raw[-1] is False
    assert meta[-1]["is_bearish"] is True
    assert meta[-1]["big_bear"] is False


def test_short_upper_wick_is_rejected_even_with_three_times_average_volume():
    candles = _base_candles()
    candles[-1] = {
        "date": "x",
        "open": 100.0,
        "high": 104.0,
        "low": 99.0,
        "close": 103.0,
        "volume": 3000.0,
    }
    raw, meta = accumulation_flags(candles, SwingSettings())
    assert raw[-1] is False
    assert meta[-1]["long_upper"] is False


def test_single_clear_long_wick_burst_can_display():
    candles = _base_candles()
    candles[-1] = {
        "date": "x",
        "open": 100.0,
        "high": 112.0,
        "low": 99.0,
        "close": 102.0,
        "volume": 2200.0,
    }
    raw, meta = accumulation_flags(candles, SwingSettings())
    confirmed = confirm_accumulation_flags(raw, meta, cluster_window=20)
    assert raw[-1] is True
    assert meta[-1]["confidence_score"] >= 95
    assert confirmed[-1] is True
