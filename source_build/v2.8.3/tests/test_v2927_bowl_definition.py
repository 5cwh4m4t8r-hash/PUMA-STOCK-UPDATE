from puma_trader.bowl import (
    BowlSettings,
    _find_bowl3_pullback,
    _is_bullish_body_224_breakout,
)


def _candle(op, hi, lo, close):
    return {
        "date": "20260101",
        "open": float(op),
        "high": float(hi),
        "low": float(lo),
        "close": float(close),
        "volume": 1000.0,
    }


def test_bowl3_breakout_requires_bullish_body_through_ema224():
    settings = BowlSettings()
    e224 = [100.0, 100.0]

    bullish = [
        _candle(98, 100, 97, 99),
        _candle(99, 106, 98.5, 105),
    ]
    assert _is_bullish_body_224_breakout(bullish, e224, 1, settings) is True

    bearish = [
        _candle(98, 100, 97, 99),
        _candle(105, 106, 98.5, 101),
    ]
    assert _is_bullish_body_224_breakout(bearish, e224, 1, settings) is False

    gap_above_without_body_cross = [
        _candle(98, 100, 97, 99),
        _candle(102, 106, 101, 105),
    ]
    assert _is_bullish_body_224_breakout(gap_above_without_body_cross, e224, 1, settings) is False


def test_bowl3_pullback_requires_bearish_candle_and_can_use_reference_open():
    settings = BowlSettings()
    candles = [
        _candle(98, 100, 97, 99),
        _candle(99, 106, 98.5, 105),   # 기준봉
        _candle(104, 105, 101, 103),   # 음봉이지만 기준봉 시가까지 안 내려옴
        _candle(103, 104, 98.8, 99.8), # 음봉, 기준봉 시가 99 근처까지 눌림
    ]
    e112 = [90.0] * len(candles)

    pullback = _find_bowl3_pullback(candles, e112, 1, settings, end_idx=len(candles))
    assert pullback is not None
    assert pullback["index"] == 3
    assert pullback["source"] == "기준봉시가"
    assert pullback["value"] == 99.0


def test_bowl3_pullback_can_use_ema112_when_reference_open_breaks():
    settings = BowlSettings()
    candles = [
        _candle(98, 100, 97, 99),
        _candle(99, 106, 98.5, 105),   # 기준봉
        _candle(103, 104, 89.5, 91.0), # 기준봉 시가는 이탈, EMA112=90은 지지
    ]
    e112 = [90.0] * len(candles)

    pullback = _find_bowl3_pullback(candles, e112, 1, settings, end_idx=len(candles))
    assert pullback is not None
    assert pullback["index"] == 2
    assert pullback["source"] == "112EMA"
    assert pullback["line"] == 112


def test_bowl3_pullback_ignores_bullish_retest_candle():
    settings = BowlSettings()
    candles = [
        _candle(98, 100, 97, 99),
        _candle(99, 106, 98.5, 105),
        _candle(98.5, 101, 98.0, 100.0),  # 양봉: 눌림 인정 금지
    ]
    e112 = [90.0] * len(candles)
    assert _find_bowl3_pullback(candles, e112, 1, settings, end_idx=len(candles)) is None
