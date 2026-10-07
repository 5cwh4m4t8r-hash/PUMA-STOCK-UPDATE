from pathlib import Path

from puma_trader.broker import BrokerError
from puma_trader.engine import TradeEngine, _max_buyable_qty_from_error
from puma_trader.models import StrategySettings


class _BuyingPowerBroker:
    is_live = True

    def __init__(self):
        self.calls = []

    def buy_market(self, code, qty):
        self.calls.append((code, qty))
        if len(self.calls) == 1:
            raise BrokerError("[2000](855056:매수증거금이 부족합니다. 16주 매수가능)")
        return {"ord_no": "OK-1", "return_code": 0, "return_msg": "정상"}

    def sell_market(self, code, qty):
        return {"ord_no": "S-1", "return_code": 0}


def test_parse_kiwoom_buyable_qty():
    assert _max_buyable_qty_from_error(
        "[2000](855056:매수증거금이 부족합니다. 16주 매수가능)"
    ) == 16
    assert _max_buyable_qty_from_error("1주 매수가능") == 1
    assert _max_buyable_qty_from_error("일시 통신 오류") == 0


def test_buy_retries_once_with_kiwoom_reported_affordable_qty():
    broker = _BuyingPowerBroker()
    engine = TradeEngine(broker, StrategySettings())
    engine._session_order_exchange = lambda: ""
    resp = engine._buy_session_order("372320", 18)
    assert broker.calls == [("372320", 18), ("372320", 16)]
    assert resp["_puma_order_qty"] == 16
    assert resp["_puma_qty_adjusted_from"] == 18


def test_submit_buy_records_actual_adjusted_qty_not_requested_qty():
    broker = _BuyingPowerBroker()
    engine = TradeEngine(broker, StrategySettings())
    engine.enabled = True
    engine._session_order_exchange = lambda: ""
    engine.seed_capital = 500_000
    res = engine._submit_buy(
        "372320", "큐로셀", 27_000,
        "가보자 차 매수", stop_price=26_000, entry_kind="PULLBACK",
        require_enabled=True,
    )
    assert res["status"] == "BUY_SENT"
    assert engine.managed_qty["372320"] == 16
    assert engine.pending_orders["372320"]["qty"] == 16
    assert "자동조정" in res["signal"]


def test_ui_keeps_auto_on_for_deterministic_buying_power_rejection():
    src = Path("puma_trader/ui.py").read_text(encoding="utf-8")
    assert '"ORDER REJECT"' in src
    assert '"매수증거금" in text' in src
    assert '"주문거절 · 자동매매 계속"' in src
