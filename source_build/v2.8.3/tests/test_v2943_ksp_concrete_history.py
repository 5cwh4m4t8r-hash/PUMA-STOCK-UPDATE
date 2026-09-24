from puma_trader.market_path import (
    _preview_concrete_before_bowl3,
    _scan_historical_concrete_previews,
)
from puma_trader.swing import SwingSettings


def b(date, o, h, l, c, v=1000):
    return {
        "date": str(date),
        "open": float(o),
        "high": float(h),
        "low": float(l),
        "close": float(c),
        "volume": float(v),
    }


def test_ksp_reference_base_can_show_concrete_before_breakout():
    # KSP(073010) public daily tail, 2026-08-21 ~ 2026-09-09.
    # Prepend 60 older below-224 bars only to satisfy long-context history.
    candles = [
        b(f"p{i}", 2800, 2860, 2740, 2800 + (i % 3) * 10, 80000)
        for i in range(60)
    ]
    candles += [
        b("2026-08-21", 2970, 2970, 2780, 2785, 127672),
        b("2026-08-24", 2785, 2860, 2750, 2795, 69144),
        b("2026-08-25", 2790, 2885, 2690, 2855, 62597),
        b("2026-08-26", 2870, 3040, 2855, 3000, 165925),
        b("2026-08-27", 3005, 3045, 2965, 3030, 62760),
        b("2026-08-28", 3070, 3070, 2970, 3010, 56791),
        b("2026-08-31", 3000, 3000, 2855, 2915, 134105),
        b("2026-09-01", 2915, 2965, 2810, 2865, 91440),
        b("2026-09-02", 2805, 2860, 2700, 2710, 115166),
        b("2026-09-03", 2790, 2790, 2670, 2745, 81482),
        b("2026-09-04", 2745, 2800, 2725, 2760, 38475),
        b("2026-09-07", 2825, 2835, 2730, 2795, 34899),
        b("2026-09-08", 2800, 2845, 2730, 2745, 91944),
        b("2026-09-09", 2825, 2850, 2745, 2790, 60336),
    ]

    start = 60
    end = len(candles) - 1
    raw_box = {
        "start": start,
        "end": end,
        "low": 2670.0,
        "high": 3070.0,
        "width_pct": 13.9,
        "coverage": 0.8,
        "top_touches": 4,
        "bottom_touches": 5,
        "alternations": 4,
        "drift_pct": 2.0,
        "directionality": 0.2,
        "period": end - start + 1,
        "score": 85.0,
        "structure_type": "공구리",
        "breakout_idx": -1,
        "accepted": False,
    }

    # Reference long-MA geometry: box is under EMA112 and current price remains
    # below but near EMA224, i.e. before the later 3/Bowl-3 breakout area.
    e112 = [3200.0] * len(candles)
    e224 = [2950.0] * len(candles)

    out = _preview_concrete_before_bowl3(
        candles, raw_box, end, e112, e224, SwingSettings()
    )
    assert out is not None
    assert out["preview"] is True
    assert out["breakout_idx"] == -1
    assert out["upper_source"] in ("전고언덕", "양봉종가")
    assert out["high"] < 3200.0
    assert candles[end]["close"] < e224[end]


def _box_wave(start_date, center, low, high, count, volume=1000):
    rows = []
    for i in range(count):
        top = (i % 6) in (0, 1)
        bottom = (i % 6) in (3, 4)
        close = high * 0.985 if top else low * 1.015 if bottom else center
        rows.append(
            b(
                f"{start_date}-{i}",
                close * 0.995,
                high if top else close * 1.015,
                low if bottom else close * 0.985,
                close,
                volume,
            )
        )
    return rows


def test_full_history_scan_keeps_multiple_distinct_concrete_boxes():
    candles = []
    candles += _box_wave("a", 90, 80, 100, 90, 1000)
    # Above-224 separation; should split historical structures.
    candles += [b(f"gap-{i}", 120, 124, 118, 122, 1300) for i in range(25)]
    candles += _box_wave("b", 72, 64, 82, 95, 900)

    n = len(candles)
    e112 = []
    e224 = []
    for i in range(n):
        if i < 100:
            e112.append(110.0)
            e224.append(102.0)
        elif i < 115:
            e112.append(115.0)
            e224.append(110.0)
        else:
            e112.append(92.0)
            e224.append(86.0)

    boxes = _scan_historical_concrete_previews(
        candles, e112, e224, SwingSettings()
    )

    assert len(boxes) >= 2
    assert all(x["structure_type"] == "공구리" for x in boxes)
    assert all(x["high"] < min(e112[x["start"]:x["end"] + 1]) for x in boxes)
    assert boxes[0]["end"] < boxes[-1]["start"]


def test_historical_scan_is_used_in_both_event_and_no_event_paths():
    from pathlib import Path

    src = Path("puma_trader/market_path.py").read_text(encoding="utf-8")
    assert src.count("_scan_historical_concrete_previews(") >= 3
    assert "historical_previews + ([preview_box] if preview_box else [])" in src
    assert "confirmed_concrete + historical_previews" in src
