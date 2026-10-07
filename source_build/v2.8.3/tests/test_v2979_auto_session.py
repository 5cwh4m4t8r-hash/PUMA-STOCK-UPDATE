from pathlib import Path

from puma_trader.engine import TradeEngine
from puma_trader.models import StrategySettings


class _BrokerFirstBuyingPower:
    is_live = True
    name = "KIWOOM REST"

    def __init__(self):
        self.calls = []

    def get_buyable_qty(self, code, price=0):
        assert code == "372320"
        assert price == 27_000
        return 16

    def buy_market(self, code, qty):
        self.calls.append((code, qty))
        return {"ord_no": "B-1", "return_code": 0}

    def sell_market(self, code, qty):
        return {"ord_no": "S-1", "return_code": 0}


def test_defaults_use_final_session_times():
    settings = StrategySettings()
    assert settings.trade_start == "08:00"
    assert settings.regular_trade_start == "09:00"
    assert settings.scan_end == "15:00"
    assert settings.auto_trade_stop_time == "15:30"


def test_old_10am_scan_end_migrates_to_3pm():
    settings = StrategySettings.from_dict({"scan_end": "10:00"})
    assert settings.scan_end == "15:00"


def test_live_buy_uses_kiwoom_prequeried_quantity_before_order():
    broker = _BrokerFirstBuyingPower()
    engine = TradeEngine(broker, StrategySettings())
    engine.enabled = True
    engine._session_order_exchange = lambda: ""
    engine.seed_capital = 500_000

    result = engine._submit_buy(
        "372320", "큐로셀", 27_000,
        "가보자 차 매수", stop_price=26_000, entry_kind="PULLBACK",
        require_enabled=True,
    )
    assert result["status"] == "BUY_SENT"
    assert broker.calls == [("372320", 16)]
    assert engine.managed_qty["372320"] == 16
    assert "키움 실제 매수가능수량 우선" in result["signal"]


def test_daily_profit_and_loss_each_lock_new_entries():
    profit = TradeEngine(_BrokerFirstBuyingPower(), StrategySettings())
    profit.seed_capital = 500_000
    profit.daily_start_seed = 500_000
    profit._record_realized_delta(20_000)
    assert profit.daily_profit_locked is True
    assert profit.can_open("005930") is False

    loss = TradeEngine(_BrokerFirstBuyingPower(), StrategySettings())
    loss.seed_capital = 500_000
    loss.daily_start_seed = 500_000
    loss._record_realized_delta(-20_000)
    assert loss.daily_loss_locked is True
    assert loss.can_open("005930") is False


def test_ui_has_clock_start_close_stop_and_nonfatal_order_error():
    src = Path("puma_trader/ui.py").read_text(encoding="utf-8")
    assert "def _manage_auto_session_clock" in src
    assert 'auto_trade_stop_time", "15:30"' in src
    assert "self.start_danta_pool_auto(auto_clock=True)" in src
    assert "해당 종목 5분 격리 · 자동매매 계속" in src

    handler = src.split("def _on_auto_scan_error", 1)[1].split("def ", 1)[0]
    assert "주문 상태 재확인 · 자동매매 계속" in handler


def test_broker_uses_kiwoom_kt00011_before_buy():
    src = Path("puma_trader/broker.py").read_text(encoding="utf-8")
    assert '"/api/dostk/acnt", "kt00011"' in src
    assert '"min_ord_alowq"' in src
