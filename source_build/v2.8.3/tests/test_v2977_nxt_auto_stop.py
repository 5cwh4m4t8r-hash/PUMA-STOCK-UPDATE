from puma_trader.broker import BrokerError, OrderStateUnknown
from puma_trader.engine import AutoOrderError, TradeEngine
from puma_trader.models import StrategySettings


class _DefiniteRejectBroker:
    is_live = True

    def get_best_quote(self, code, exchange="NXT"):
        return {"best_ask": 1000, "best_bid": 990}

    def buy_limit_on(self, code, qty, price, exchange):
        raise BrokerError("주문 거절")


class _UnknownStateBroker(_DefiniteRejectBroker):
    def buy_limit_on(self, code, qty, price, exchange):
        raise OrderStateUnknown("timeout")


def _nxt_settings():
    s = StrategySettings()
    s.trade_start = "00:00"
    s.nxt_premarket_end = "23:59"
    return s


def test_definitive_nxt_buy_rejection_does_not_become_auto_stop_error():
    engine = TradeEngine(_DefiniteRejectBroker(), _nxt_settings())
    try:
        engine._buy_session_order("005930", 1)
    except Exception as exc:
        assert isinstance(exc, BrokerError)
        assert not isinstance(exc, AutoOrderError)
    else:
        raise AssertionError("expected rejection")
    assert "005930" in engine.cooldowns


def test_unknown_nxt_order_state_still_uses_safety_stop_error():
    engine = TradeEngine(_UnknownStateBroker(), _nxt_settings())
    try:
        engine._buy_session_order("005930", 1)
    except Exception as exc:
        assert isinstance(exc, AutoOrderError)
    else:
        raise AssertionError("expected unknown-state error")
