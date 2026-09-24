from pathlib import Path


def test_live_auto_uses_primary_live_arm_without_second_text_prompt():
    ui = Path("puma_trader/ui.py").read_text(encoding="utf-8")
    start = ui.index("def _confirm_live_auto_once")
    end = ui.index("def start_focus_auto", start)
    block = ui[start:end]

    assert "QInputDialog.getText" not in block
    assert "LIVE START" not in block
    assert "real_armed" in block
    assert "return False" in block
    assert "return True" in block


def test_manual_real_order_confirmation_remains():
    ui = Path("puma_trader/ui.py").read_text(encoding="utf-8")
    assert "LIVE ORDER" in ui
