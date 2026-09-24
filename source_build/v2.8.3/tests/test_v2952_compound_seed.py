from pathlib import Path

from puma_trader.broker import SimBroker
from puma_trader.engine import TradeEngine
from puma_trader.models import Position, StrategySettings


def make_engine():
    return TradeEngine(SimBroker(), StrategySettings())


def test_profit_and_loss_roll_into_next_trade_seed():
    engine = make_engine()
    assert engine.current_trade_budget() == 500_000

    engine._record_realized_delta(50_000)
    assert engine.seed_capital == 550_000
    assert engine.current_trade_budget() == 550_000

    engine._record_realized_delta(-70_000)
    assert engine.seed_capital == 480_000
    assert engine.current_trade_budget() == 480_000


def test_daily_minus_four_percent_locks_new_buys_until_next_day():
    engine = make_engine()
    engine._record_realized_delta(-20_000)
    assert round(engine.daily_loss_pct(), 2) == -4.0
    assert engine.daily_loss_locked is True
    assert engine.can_open("005930") is False


def test_compound_phase_allows_only_one_open_position():
    engine = make_engine()
    engine.positions["005930"] = Position(
        code="005930",
        name="삼성전자",
        qty=1,
        entry_price=50_000,
        highest_price=50_000,
        opened_at="2026-10-01T09:05:00",
    )
    assert engine.can_open("000660") is False


def test_phase_one_target_stops_new_buys():
    engine = make_engine()
    engine.seed_capital = 3_000_000
    assert engine.phase1_complete() is True
    assert engine.can_open("005930") is False


def test_ui_locks_auto_paths_to_danta_and_ranks_candidates():
    src = Path("puma_trader/ui.py").read_text(encoding="utf-8")
    assert "단타 검색기 전체 → PUMA 최우선 1종목" in src
    assert "return self.start_danta_pool_auto()" in src
    assert "실전 자동매매는 단타 검색기 후보 종목만 허용합니다." in src
    assert '"puma_score": int(scores.get("danta", 0) or 0)' in src
    assert "현재 복리 시드(전액)" in src
    assert "하루 -4%" in src


def test_runtime_persists_compound_seed_fields():
    src = Path("puma_trader/storage.py").read_text(encoding="utf-8")
    for key in (
        '"seed_capital"',
        '"daily_start_seed"',
        '"daily_realized_pnl"',
        '"daily_loss_locked"',
        '"seed_pnl_delta"',
    ):
        assert key in src
