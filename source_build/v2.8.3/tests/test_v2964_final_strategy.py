from datetime import datetime, timedelta

from puma_trader.engine import _gaboja_stage3_exit_from_rows
from puma_trader.gaboja import evaluate_gaboja
from puma_trader.models import StrategySettings
from puma_trader.theme_strength import apply_theme_strength


def _d(date, o, h, l, c, v):
    return {"date": date, "open": o, "high": h, "low": l, "close": c, "volume": v}


def _daily():
    rows = []
    start = datetime(2025, 1, 1)
    for i in range(55):
        dt = (start + timedelta(days=i)).strftime("%Y%m%d")
        rows.append(_d(dt, 100, 101, 99, 100, 1000))
    rows[-6:-1] = [
        _d("20260924", 100, 104, 99, 100, 1000),
        _d("20260925", 100, 104, 99, 100, 1000),
        _d("20260928", 100, 104, 99, 100, 1000),
        _d("20260929", 100, 104, 99, 100, 1000),
        _d("20260930", 100, 104, 99, 100, 1000),
    ]
    return rows


def _opening_bearish_young2_rows():
    rows = []
    # 장초 동일시간대 거래량 기준을 만들기 위한 최근 5일 5분봉.
    for day in ("20260924", "20260925", "20260928", "20260929", "20260930"):
        rows += [
            _d(day + "090000", 100, 101, 99, 100, 100),
            _d(day + "090500", 100, 101, 99, 100, 100),
            _d(day + "091000", 100, 101, 99, 100, 100),
        ]
    rows += [
        _d("20261001090000", 100, 110, 95, 96, 1000),   # 첫 봉 음봉이어도 1영
        _d("20261001090500", 97, 100, 97, 98, 100),      # 65%+ 차, 거래량 둔화
        _d("20261001091000", 98, 113, 97.5, 112, 800),   # 2영 전환 · 몸통 종가가 1영 전고 돌파
    ]
    return rows


def test_opening_bearish_bar_can_be_young1_and_buy_waits_for_young2():
    sig = evaluate_gaboja(
        _opening_bearish_young2_rows(),
        _daily(),
        now=datetime(2026, 10, 1, 9, 10, 30),
    )
    assert sig.passed is True
    assert sig.entry_kind == "YOUNG2"
    assert sig.details["opening_bearish_young"] is True
    assert sig.details["pullback_index"] == 1
    assert sig.details["young2_index"] == 2


def test_old_25_percent_setting_migrates_to_50_percent():
    settings = StrategySettings.from_dict({"gabojago_partial_sell_ratio": 0.25})
    assert settings.gabojago_partial_sell_ratio == 0.50


def test_same_theme_strong_candidates_receive_bonus_only_as_tiebreak():
    rows = apply_theme_strength([
        {"code": "A", "live_puma_score": 4, "danta_score": 90,
         "themes": [{"code": "T1", "name": "철강", "change_pct": 6.0}]},
        {"code": "B", "live_puma_score": 3, "danta_score": 80,
         "themes": [{"code": "T1", "name": "철강", "change_pct": 6.0}]},
        {"code": "C", "live_puma_score": 4, "danta_score": 90,
         "themes": [{"code": "T2", "name": "바이오", "change_pct": 2.0}]},
    ])
    by_code = {x["code"]: x for x in rows}
    assert by_code["A"]["theme_peer_count"] == 2
    assert by_code["B"]["theme_bonus"] > 0
    assert by_code["C"]["theme_peer_count"] == 1
    assert by_code["C"]["theme_bonus"] == 0


def test_stage3_exit_requires_pullback_then_new_thrust():
    rows = [
        _d("20261001091000", 100, 107, 99, 106, 1000),  # 2영 진입
        _d("20261001091500", 106, 111, 105, 110, 900),
        _d("20261001092000", 110, 110, 107, 108, 400),   # 눌림
        _d("20261001092500", 108, 113, 108, 112, 1000),  # 3
    ]
    hit, high = _gaboja_stage3_exit_from_rows(
        rows,
        current_bar_key="202610010925",
        timeframe=5,
        entry_price=106,
        opened_at="2026-10-01T09:10:00",
    )
    assert hit is True
    assert high == 113


def test_stage3_does_not_fire_without_intermediate_pullback():
    rows = [
        _d("20261001091000", 100, 107, 99, 106, 1000),
        _d("20261001091500", 106, 111, 105, 110, 900),
        _d("20261001092000", 110, 114, 109, 113, 800),
        _d("20261001092500", 113, 116, 112, 115, 900),
    ]
    hit, _ = _gaboja_stage3_exit_from_rows(
        rows,
        current_bar_key="202610010925",
        timeframe=5,
        entry_price=106,
        opened_at="2026-10-01T09:10:00",
    )
    assert hit is False
