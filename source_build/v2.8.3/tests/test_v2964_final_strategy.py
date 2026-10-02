from datetime import datetime, timedelta

from puma_trader.engine import TradeEngine, AutoOrderError, _gaboja_stage3_exit_from_rows, _gaboja_quick_profit_exit_from_rows
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


def test_opening_bearish_bar_can_be_young1_and_buy_at_cha():
    rows = _opening_bearish_young2_rows()[:-1]
    sig = evaluate_gaboja(
        rows,
        _daily(),
        now=datetime(2026, 10, 1, 9, 5, 30),
        apply_secondary_filter=False,
    )
    assert sig.passed is True
    assert sig.entry_kind == "PULLBACK"
    assert sig.details["opening_bearish_young"] is True
    assert sig.details["pullback_index"] == 1
    assert sig.details["early_cha"] is True


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
        _d("20261001091000", 100, 107, 99, 106, 1000),  # 차 진입 뒤 상승
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


def test_quick_profit_exit_locks_gain_on_first_rollover_after_run():
    rows = [
        _d("20261002080500", 32650, 32720, 32620, 32680, 500),
        _d("20261002081000", 32680, 32950, 32670, 32920, 700),
        _d("20261002081500", 32920, 33300, 32900, 33280, 800),
        _d("20261002082000", 33280, 33300, 33120, 33150, 500),
    ]
    hit, peak, gain = _gaboja_quick_profit_exit_from_rows(
        rows,
        current_bar_key="202610020820",
        timeframe=5,
        entry_price=32650,
        opened_at="2026-10-02T08:05:00",
        min_profit_pct=1.0,
        peak_retreat_pct=0.35,
    )
    assert hit is True
    assert peak == 33300
    assert gain > 1.9


def test_quick_profit_exit_does_not_sell_small_noise_before_min_gain():
    rows = [
        _d("20261002080500", 32900, 32940, 32880, 32920, 500),
        _d("20261002081000", 32920, 33050, 32900, 33020, 600),
        _d("20261002081500", 33020, 33060, 32900, 32920, 400),
    ]
    hit, _, gain = _gaboja_quick_profit_exit_from_rows(
        rows,
        current_bar_key="202610020815",
        timeframe=5,
        entry_price=32900,
        opened_at="2026-10-02T08:05:00",
        min_profit_pct=1.0,
        peak_retreat_pct=0.35,
    )
    assert hit is False
    assert gain < 1.0


def test_order_transport_failure_is_classified_as_auto_order_error():
    class BadOrderBroker:
        is_live = False
        def buy_market(self, code, qty):
            raise RuntimeError("order transport lost")
        def sell_market(self, code, qty):
            raise RuntimeError("order transport lost")

    engine = TradeEngine(BadOrderBroker(), StrategySettings())
    import pytest
    with pytest.raises(AutoOrderError):
        engine._buy_session_order("005930", 1)
    with pytest.raises(AutoOrderError):
        engine._sell_session_order("005930", 1)
