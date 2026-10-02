from datetime import datetime, timedelta

from puma_trader.gaboja import evaluate_gaboja


def _d(date, o, h, l, c, v):
    return {"date": date, "open": o, "high": h, "low": l, "close": c, "volume": v}


def _daily():
    rows = []
    # enough history for BB40 and EAVG context
    p = 100.0
    start = datetime(2025, 1, 1)
    for i in range(55):
        dt = (start + timedelta(days=i)).strftime("%Y%m%d")
        rows.append(_d(dt, p, p + 1, p - 1, p, 1000))
    # previous five stay below 105
    rows[-6:-1] = [
        _d("20260916", 100, 104, 99, 100, 1000),
        _d("20260917", 100, 104, 99, 100, 1000),
        _d("20260918", 100, 104, 99, 100, 1000),
        _d("20260921", 100, 104, 99, 100, 1000),
        _d("20260922", 100, 104, 99, 100, 1000),
    ]
    # gap above previous 5 highs, >3x volume, closes through long EAVG/BB area
    rows[-1] = _d("20260923", 106, 125, 106, 124, 3500)
    return rows


def _minute(body_break=True):
    rows = []
    for day in ("20260916", "20260917", "20260918", "20260921", "20260922"):
        rows += [
            _d(day+"090000", 100, 101, 99, 100, 100),
            _d(day+"090500", 100, 101, 99, 100, 100),
            _d(day+"091000", 100, 101, 99, 100, 100),
            _d(day+"091500", 100, 101, 99, 100, 100),
            _d(day+"092000", 100, 101, 99, 100, 100),
        ]
    rows += [
        _d("20260923090000", 106, 107, 105.8, 106.5, 600),
        _d("20260923090500", 106.5, 109, 106.4, 108.8, 700),
        _d("20260923091000", 108.8, 113, 108.7, 112.5, 1400),  # 영1
        _d("20260923091500", 110.5, 110.7, 107.8, 108.3, 100), # 65% 이상 되돌림 + 진행봉 거래량속도 둔화
    ]
    if body_break:
        rows.append(_d("20260923092000", 112.2, 114.5, 112.0, 114.0, 800))
    return rows


def test_gaboja_cha_is_entry():
    sig = evaluate_gaboja(_minute(False), _daily(), now=datetime(2026,9,23,9,15,30))
    assert sig.passed is True
    assert sig.entry_kind == "PULLBACK"
    assert sig.basis_open == 106


def test_gaboja_body_rebreak_requires_body_cross():
    sig = evaluate_gaboja(_minute(True), _daily(), now=datetime(2026,9,23,9,20))
    assert sig.passed is True
    assert sig.entry_kind == "YOUNG2"
    assert sig.young1_high == 113


def test_tail_only_break_is_rejected():
    rows = _minute(False)
    rows.append(_d("20260923092000", 112.0, 114.5, 111.8, 112.8, 800))
    sig = evaluate_gaboja(rows, _daily(), now=datetime(2026,9,23,9,20))
    assert sig.passed is False




def test_pullback_shallower_than_65pct_is_not_cha():
    rows = _minute(False)
    rows[-1] = _d("20260923091500", 112.0, 112.2, 110.0, 111.0, 400)
    sig = evaluate_gaboja(rows, _daily(), now=datetime(2026,9,23,9,15))
    assert sig.passed is False
    assert "65%" in sig.reason


def test_65pct_retracement_boundary_is_used():
    rows = _minute(False)
    # B=106, H=113 -> 65% 되돌림선 = 113 - 7*0.65 = 108.45
    rows[-1] = _d("20260923091500", 110.5, 110.7, 108.4, 108.5, 100)
    sig = evaluate_gaboja(rows, _daily(), now=datetime(2026,9,23,9,15,30))
    assert sig.passed is False

    rows[-1] = _d("20260923091500", 110.5, 110.7, 107.8, 108.4, 100)
    sig = evaluate_gaboja(rows, _daily(), now=datetime(2026,9,23,9,15,30))
    assert sig.passed is True
    assert sig.entry_kind == "PULLBACK"
    assert round(sig.details["cha_ceiling"], 2) == 108.45


def test_deep_cha_enters_immediately():
    sig = evaluate_gaboja(_minute(False), _daily(), now=datetime(2026,9,23,9,15,30))
    assert sig.passed is True
    assert sig.entry_kind == "PULLBACK"
    assert sig.details["early_cha"] is True
    assert sig.details["cha_ready"] is True
    assert round(sig.details["cha_ceiling"], 2) == 108.45
    assert sig.current_price == 108.3


def test_live_cha_rejects_raw_low_volume_when_per_second_pace_is_fast():
    rows = _minute(False)
    # 영1은 1400/300 = 4.67주/s. 현재봉은 총량 500으로 더 작아 보여도
    # 시작 30초 시점에는 16.67주/s라서 '거래량 둔화 차'가 아니다.
    rows[-1] = _d("20260923091500", 110.5, 110.7, 107.8, 108.3, 500)
    sig = evaluate_gaboja(
        rows, _daily(), now=datetime(2026,9,23,9,15,30),
        cha_min_live_seconds=20,
    )
    assert sig.passed is False


def test_live_cha_enters_without_waiting_for_next_bar():
    rows = _minute(False)
    rows[-1] = _d("20260923091500", 110.5, 110.7, 107.8, 108.3, 100)
    sig = evaluate_gaboja(
        rows, _daily(), now=datetime(2026,9,23,9,15,30),
        cha_min_live_seconds=20,
    )
    assert sig.passed is True
    assert sig.entry_kind == "PULLBACK"
    assert sig.details["cha_ready"] is True
    assert sig.details["pullback_elapsed_sec"] == 30.0
    assert sig.details["pullback_volume_pace"] < sig.details["young_volume_pace"]


def test_live_cha_waits_for_minimum_observation_seconds():
    rows = _minute(False)
    rows[-1] = _d("20260923091500", 110.5, 110.7, 107.8, 108.3, 5)
    sig = evaluate_gaboja(
        rows, _daily(), now=datetime(2026,9,23,9,15,10),
        cha_min_live_seconds=20,
    )
    assert sig.passed is False

def test_pullback_cannot_touch_basis_open():
    rows = _minute(False)
    rows[-1] = _d("20260923091500", 112.0, 112.2, 106.0, 110.0, 400)
    sig = evaluate_gaboja(rows, _daily(), now=datetime(2026,9,23,9,15))
    assert sig.passed is False


def test_high_volume_deep_drop_is_not_bought_at_cha_but_enters_on_body_recovery_breakout():
    rows = _minute(False)
    # 영1 1400/300=4.67주/s보다 눌림 거래량속도가 더 강하다.
    # 따라서 09:15에는 차 매수 금지, 이후 전고(113) 양봉 몸통돌파 때만 진입한다.
    rows[-1] = _d("20260923091500", 110.5, 110.7, 107.8, 108.3, 1800)

    hot_drop = evaluate_gaboja(
        rows, _daily(), now=datetime(2026, 9, 23, 9, 15, 30),
        cha_min_live_seconds=20,
    )
    assert hot_drop.passed is False
    assert hot_drop.entry_kind == ""

    rows.append(_d("20260923092000", 112.2, 114.5, 112.0, 114.0, 900))
    recovered = evaluate_gaboja(
        rows, _daily(), now=datetime(2026, 9, 23, 9, 20, 30),
        cha_min_live_seconds=20,
    )
    assert recovered.passed is True
    assert recovered.entry_kind == "YOUNG2"
    assert recovered.young1_high == 113
    assert recovered.pullback_low == 107.8
    assert recovered.details["second_young"] is True
    assert recovered.details["pullback_index"] == 3
    assert recovered.details["volume_required_for_structure"] is False


def test_high_volume_recovery_requires_bullish_body_not_wick_only():
    rows = _minute(False)
    rows[-1] = _d("20260923091500", 110.5, 110.7, 107.8, 108.3, 1800)
    # 고가는 전고 113을 넘지만 몸통 종가는 전고 아래 -> 진입 금지.
    rows.append(_d("20260923092000", 112.0, 114.5, 111.8, 112.8, 900))
    sig = evaluate_gaboja(
        rows, _daily(), now=datetime(2026, 9, 23, 9, 20, 30),
        cha_min_live_seconds=20,
    )
    assert sig.passed is False
    assert sig.entry_kind == ""


def test_low_volume_drift_then_gradual_recovery_is_kept_as_youngcha_and_bought_at_young2():
    rows = _minute(False)
    # 거래량 없이 깊게 눌린 뒤, 여러 봉에 걸쳐 천천히 회복한다.
    rows[-1] = _d("20260923091500", 110.5, 110.7, 107.8, 108.3, 80)
    rows += [
        _d("20260923092000", 108.3, 109.8, 108.1, 109.5, 70),
        _d("20260923092500", 109.5, 111.5, 109.2, 111.0, 75),
        _d("20260923093000", 112.0, 114.2, 111.8, 114.0, 85),
    ]

    sig = evaluate_gaboja(
        rows, _daily(), now=datetime(2026, 9, 23, 9, 30, 30),
        cha_min_live_seconds=20,
    )
    assert sig.passed is True
    assert sig.entry_kind == "YOUNG2"
    assert sig.young1_high == 113
    assert sig.pullback_low == 107.8
    assert sig.details["second_young"] is True
    assert sig.details["volume_required_for_structure"] is False


def test_young2_structure_survives_even_when_pullback_volume_does_not_slow():
    rows = _minute(False)
    rows[-1] = _d("20260923091500", 110.5, 110.7, 107.8, 108.3, 1800)

    watching = evaluate_gaboja(
        rows, _daily(), now=datetime(2026, 9, 23, 9, 15, 30),
        cha_min_live_seconds=20,
    )
    assert watching.passed is False
    assert watching.details["structural_pullback"] is True
    assert watching.details["volume_required_for_structure"] is False

    rows.append(_d("20260923092000", 112.2, 114.5, 112.0, 114.0, 900))
    sig = evaluate_gaboja(
        rows, _daily(), now=datetime(2026, 9, 23, 9, 20, 30),
        cha_min_live_seconds=20,
    )
    assert sig.passed is True
    assert sig.entry_kind == "YOUNG2"


def test_single_bar_young_does_not_require_local_volume_expansion():
    rows = []
    for day in ("20260916", "20260917", "20260918", "20260921", "20260922"):
        rows += [
            _d(day+"090000", 100, 101, 99, 100, 100),
            _d(day+"090500", 100, 101, 99, 100, 100),
            _d(day+"091000", 100, 101, 99, 100, 100),
            _d(day+"091500", 100, 101, 99, 100, 100),
        ]
    rows += [
        _d("20260923090000", 106, 107, 105.8, 106.5, 1200),
        _d("20260923090500", 106.5, 109, 106.4, 108.8, 1200),
        # 직전 평균 거래량보다 적어도 가격이 상승하며 직전 고점을 넘으면 1영 구조 후보.
        _d("20260923091000", 108.8, 113, 108.7, 112.5, 200),
        _d("20260923091500", 110.5, 110.7, 107.8, 108.3, 50),
        _d("20260923092000", 112.2, 114.5, 112.0, 114.0, 60),
    ]
    sig = evaluate_gaboja(
        rows, _daily(), now=datetime(2026, 9, 23, 9, 20, 30),
        apply_secondary_filter=False,
        cha_min_live_seconds=20,
    )
    assert sig.passed is True
    assert sig.entry_kind == "YOUNG2"
    assert sig.young1_high == 113


def test_rfhic_like_opening_wick_spike_is_not_young_or_cha_entry():
    rows = []
    for day in ("20260925", "20260928", "20260929", "20260930", "20261001"):
        rows += [
            _d(day+"080000", 60000, 60200, 59800, 60050, 100),
            _d(day+"080500", 60050, 60200, 59950, 60100, 100),
        ]
    # RFHIC-like: first bar spikes hard to a high but leaves a dominant upper wick.
    rows += [
        _d("20261002080000", 61700, 64500, 61500, 62600, 1200),
        _d("20261002080500", 62600, 62800, 62050, 62200, 250),
    ]
    sig = evaluate_gaboja(
        rows, _daily(), now=datetime(2026, 10, 2, 8, 5, 30),
        apply_secondary_filter=False,
        cha_max_ratio=0.65,
        cha_min_live_seconds=20,
    )
    assert sig.passed is False
    assert sig.entry_kind == ""


def test_ls_like_first_pullback_is_cha_entry_with_35pct_retrace():
    rows = []
    for day in ("20260925", "20260928", "20260929", "20260930", "20261001"):
        rows += [
            _d(day+"080000", 32400, 32500, 32350, 32450, 100),
            _d(day+"080500", 32450, 32520, 32400, 32480, 100),
        ]
    rows += [
        _d("20261002080000", 32400, 32900, 32380, 32850, 1200),  # 1영
        _d("20261002080500", 32850, 32880, 32620, 32650, 250),   # 약 50% 눌림 = 차
    ]
    sig = evaluate_gaboja(
        rows, _daily(), now=datetime(2026, 10, 2, 8, 5, 30),
        apply_secondary_filter=False,
        cha_max_ratio=0.65,
        cha_min_live_seconds=20,
    )
    assert sig.passed is True
    assert sig.entry_kind == "PULLBACK"
    assert sig.young1_high == 32900


def test_ls_like_missed_cha_enters_on_first_body_break_not_late_rebased_breakout():
    rows = []
    for day in ("20260925", "20260928", "20260929", "20260930", "20261001"):
        rows += [
            _d(day+"080000", 32400, 32500, 32350, 32450, 100),
            _d(day+"080500", 32450, 32520, 32400, 32480, 100),
        ]
    rows += [
        _d("20261002080000", 32400, 32900, 32380, 32850, 1200),  # 1영
        _d("20261002080500", 32850, 32880, 32620, 32650, 250),   # 차
        _d("20261002081000", 32840, 33000, 32820, 32950, 350),   # 첫 전고 몸통돌파 = 2영
    ]
    sig = evaluate_gaboja(
        rows, _daily(), now=datetime(2026, 10, 2, 8, 10, 30),
        apply_secondary_filter=False,
        cha_max_ratio=0.65,
        cha_min_live_seconds=20,
    )
    assert sig.passed is True
    assert sig.entry_kind == "YOUNG2"
    assert sig.young1_high == 32900
    assert sig.details["pullback_index"] == 1
