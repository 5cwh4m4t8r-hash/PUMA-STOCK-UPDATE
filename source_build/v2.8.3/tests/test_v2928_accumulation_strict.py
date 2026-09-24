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


def test_ordinary_volume_long_upper_wick_is_not_accumulation():
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
    assert meta[-1]["volume_ratio"] < 1.35


def test_visible_volume_spike_under_three_times_can_be_accumulation():
    candles = _base_candles()
    candles[-1] = {
        "date": "x",
        "open": 100.0,
        "high": 112.0,
        "low": 99.0,
        "close": 102.0,
        "volume": 2200.0,  # clearly visible, but below 3x
    }
    raw, meta = accumulation_flags(candles, SwingSettings())
    assert raw[-1] is True
    assert meta[-1]["volume_ratio"] < 3.0
    assert meta[-1]["pattern"] == "고거래량 긴 윗꼬리"


def test_large_bearish_dump_with_burst_volume_is_accumulation_candidate():
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
    assert meta[-1]["big_bear"] is True
    assert meta[-1]["pattern"] == "고거래량 장대음봉"


def test_small_cross_doji_stays_excluded_even_with_large_volume():
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


def test_muted_price_response_without_long_wick_or_overwhelming_volume_is_excluded():
    candles = _base_candles()
    candles[-2]["close"] = 100.0
    candles[-1] = {
        "date": "x",
        "open": 100.0,
        "high": 103.0,
        "low": 98.5,
        "close": 101.5,
        "volume": 1900.0,
    }
    raw, meta = accumulation_flags(candles, SwingSettings())
    assert raw[-1] is False
    assert meta[-1]["muted_price_response"] is True
    assert meta[-1]["overwhelming_volume"] is False


def test_chart_confirmation_still_requires_repeated_candidates():
    candles = _base_candles(45)
    for idx in (30, 38):
        candles[idx] = {
            "date": str(idx),
            "open": 100.0,
            "high": 112.0,
            "low": 99.0,
            "close": 102.0,
            "volume": 2300.0,
        }
    raw, meta = accumulation_flags(candles, SwingSettings())
    confirmed = confirm_accumulation_flags(raw, meta, cluster_window=20)
    assert raw[30] is True and raw[38] is True
    assert confirmed[30] is True and confirmed[38] is True


def test_declining_volume_bar_is_never_accumulation_even_if_absolute_volume_is_huge():
    candles = _base_candles()
    candles[-2]["volume"] = 5000.0
    candles[-1] = {
        "date": "x",
        "open": 100.0,
        "high": 116.0,
        "low": 98.0,
        "close": 102.0,
        "volume": 4000.0,  # huge, but lower than previous bar => blue volume
    }
    raw, meta = accumulation_flags(candles, SwingSettings())
    assert raw[-1] is False
    assert meta[-1]["volume_up_vs_prev"] is False
    assert meta[-1]["excluded_volume_not_up"] is True


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
    assert meta[-1]["volume_up_vs_prev"] is False


def test_non_big_bearish_candle_is_never_accumulation():
    candles = _base_candles()
    candles[-1] = {
        "date": "x",
        "open": 103.0,
        "high": 114.0,
        "low": 99.0,
        "close": 101.0,  # bearish, but not a large bearish dump
        "volume": 5000.0,
    }
    raw, meta = accumulation_flags(candles, SwingSettings())
    assert raw[-1] is False
    assert meta[-1]["is_bearish"] is True
    assert meta[-1]["big_bear"] is False
    assert meta[-1]["excluded_non_big_bear"] is True


def test_short_upper_wick_requires_overwhelming_volume():
    candles = _base_candles()
    candles[-1] = {
        "date": "x",
        "open": 100.0,
        "high": 104.0,
        "low": 99.0,
        "close": 103.0,
        "volume": 1900.0,  # elevated, but not overwhelming
    }
    raw, meta = accumulation_flags(candles, SwingSettings())
    assert raw[-1] is False
    assert meta[-1]["overwhelming_volume"] is False
    assert meta[-1]["excluded_short_wick_without_overwhelming_volume"] is True


def test_short_upper_wick_with_overwhelming_volume_can_be_accumulation():
    candles = _base_candles()
    candles[-1] = {
        "date": "x",
        "open": 100.0,
        "high": 104.0,
        "low": 99.0,
        "close": 103.0,
        "volume": 3000.0,  # 3x prior average
    }
    raw, meta = accumulation_flags(candles, SwingSettings())
    assert raw[-1] is True
    assert meta[-1]["overwhelming_volume"] is True
    assert meta[-1]["pattern"] == "압도적 거래량"
