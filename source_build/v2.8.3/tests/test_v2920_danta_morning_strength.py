from puma_trader.danta import market_open_volume_ratio
from puma_trader.gaboja import _candidate_filter
from puma_trader.bowl import BowlSettings, is_bowl3_overextended


def _bar(day, hhmm, volume, close=100.0):
    return {
        "date": f"{day}{hhmm}00",
        "open": close,
        "high": close * 1.01,
        "low": close * 0.99,
        "close": close,
        "volume": float(volume),
    }


def test_morning_volume_ratio_uses_same_elapsed_5min_bars():
    rows = []
    for day in ("20260916", "20260917", "20260918", "20260921", "20260922"):
        rows += [
            _bar(day, "0900", 100),
            _bar(day, "0905", 100),
            _bar(day, "0910", 100),
            _bar(day, "0915", 100),
        ]
    rows += [
        _bar("20260923", "0900", 350, 100),
        _bar("20260923", "0905", 350, 101),
        _bar("20260923", "0910", 350, 102),
        _bar("20260923", "0915", 350, 103),
    ]
    out = market_open_volume_ratio(rows, 5)
    assert out["days"] == 5
    assert out["bars"] == 4
    assert round(out["ratio"], 2) == 3.50
    assert out["price_from_open_pct"] > 0


def test_gaboja_secondary_filter_requires_300pct_morning_volume():
    daily = [
        {"date": "20260917", "open": 100, "high": 104, "low": 98, "close": 101, "volume": 1000},
        {"date": "20260918", "open": 101, "high": 105, "low": 99, "close": 102, "volume": 1000},
        {"date": "20260919", "open": 102, "high": 106, "low": 100, "close": 103, "volume": 1000},
        {"date": "20260920", "open": 103, "high": 107, "low": 101, "close": 104, "volume": 1000},
        {"date": "20260922", "open": 104, "high": 108, "low": 102, "close": 105, "volume": 1000},
    ]
    live = {"date": "20260923", "open": 105, "high": 110, "low": 104, "close": 109, "volume": 500}
    weak, wd = _candidate_filter(daily, live, session_bars=4, morning_volume_ratio=2.99, min_score=2)
    strong, sd = _candidate_filter(daily, live, session_bars=4, morning_volume_ratio=3.01, min_score=2)
    assert wd["morning_volume_300_ok"] is False
    assert weak is False
    assert sd["morning_volume_300_ok"] is True
    assert strong is True


def test_bowl3_current_candidate_is_invalid_when_too_far_above_224():
    settings = BowlSettings(max_entry_distance_pct=8.0)
    assert is_bowl3_overextended(8.01, settings) is True
    assert is_bowl3_overextended(8.0, settings) is False
