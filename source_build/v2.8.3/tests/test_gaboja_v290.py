from datetime import datetime

from puma_trader.engine import AUTO_ORDER_BUDGET, TradeEngine
from puma_trader.gaboja import _candidate_filter
from puma_trader.models import StrategySettings


def _daily():
    return [
        {"date": "20260917", "open": 100, "high": 108, "low": 95, "close": 102, "volume": 1000},
        {"date": "20260918", "open": 102, "high": 109, "low": 99, "close": 104, "volume": 1000},
        {"date": "20260919", "open": 103, "high": 110, "low": 100, "close": 105, "volume": 1000},
        {"date": "20260920", "open": 104, "high": 111, "low": 101, "close": 106, "volume": 1000},
        {"date": "20260922", "open": 105, "high": 109, "low": 102, "close": 106, "volume": 1000},
    ]


def test_no_gap_can_pass_puma_secondary_filter():
    # 최근 5일 고가(111) 위 갭은 아니지만,
    # 시가위 + 거래속도 + 전일고/최근고점 공격으로 3/4를 충족한다.
    live = {"date": "20260923", "open": 100, "high": 110, "low": 99, "close": 108, "volume": 100}
    ok, d = _candidate_filter(_daily(), live, session_bars=2, morning_volume_ratio=3.5, min_score=3)
    assert d["gap_ok"] is False
    assert d["price_strength"] is True
    assert d["flow_ok"] is True
    assert d["high_attack"] is True
    assert d["puma_score"] >= 3
    assert ok is True


def test_weak_candidate_is_rejected():
    live = {"date": "20260923", "open": 100, "high": 101, "low": 96, "close": 98, "volume": 5}
    ok, d = _candidate_filter(_daily(), live, session_bars=4, morning_volume_ratio=1.0, min_score=3)
    assert d["gap_ok"] is False
    assert d["puma_score"] < 3
    assert ok is False


class CaptureBroker:
    is_live = False
    order_exchange = "KRX"

    def __init__(self):
        self.last_buy = None

    def buy_market(self, code, qty):
        self.last_buy = (code, qty)
        return {"ord_no": "TEST", "return_code": 0}


def test_auto_buy_budget_is_fixed_500k_even_if_setting_differs():
    broker = CaptureBroker()
    settings = StrategySettings(order_budget=9_999_999)
    engine = TradeEngine(broker, settings)
    assert engine.settings.order_budget == AUTO_ORDER_BUDGET == 500_000
    result = engine._submit_buy("000001", "TEST", 120_000, "test", stop_price=100_000)
    assert broker.last_buy == ("000001", 4)
    assert result["status"] == "BUY_SENT"
