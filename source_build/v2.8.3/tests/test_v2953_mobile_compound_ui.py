from pathlib import Path


def test_mobile_compound_ui_removes_legacy_sizing_inputs():
    src = Path("puma_trader/mobile_bridge.py").read_text(encoding="utf-8")
    assert 'id="autoBudget"' not in src
    assert 'id="autoMaxPositions"' not in src
    assert 'id="autoSeed"' in src
    assert 'id="autoDailyLoss"' in src
    assert 'id="autoRiskState"' in src
    assert "1종목 고정" in src
    assert "1차 목표 3,000,000원" in src


def test_mobile_start_does_not_send_legacy_sizing_values():
    src = Path("puma_trader/mobile_bridge.py").read_text(encoding="utf-8")
    block = src[src.index("async function startAuto()"):src.index("async function stopAuto()")]
    assert "order_budget:" not in block
    assert "max_positions:" not in block
    assert "max_daily_orders:" not in block
    assert "candidate_source:(scope==='ALL'?'HERO4'" in block


def test_mobile_handler_forces_current_seed_and_one_position():
    src = Path("puma_trader/ui.py").read_text(encoding="utf-8")
    start = src.index("def _apply_mobile_auto_settings")
    end = src.index("@staticmethod", start)
    block = src[start:end]
    assert "self.engine.current_trade_budget()" in block
    assert "max_pos = 1" in block
    assert "data.get(\"max_positions\")" not in block
    assert "self.order_budget.setValue(budget)" in block
    assert "self.focus_budget.setValue(budget)" in block
