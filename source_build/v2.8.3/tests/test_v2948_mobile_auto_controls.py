from pathlib import Path

from puma_trader.engine import TradeEngine


def test_mobile_auto_buttons_are_state_driven_and_one_tap():
    src = Path("puma_trader/mobile_bridge.py").read_text(encoding="utf-8")
    assert 'id="autoStopBtn"' in src
    assert "let autoCommandBusy=false, autoCommandWanted=null;" in src
    assert "startBtn.disabled=!unlocked || actuallyEnabled || autoCommandBusy;" in src
    assert "stopBtn.disabled=!actuallyEnabled || autoCommandBusy;" in src
    assert "if(autoCommandBusy)return;" in src
    assert "if(!confirm(what+' 자동매매를 시작할까요?'))return;" not in src
    assert "if(!confirm('자동매매를 중지할까요?'))return;" not in src
    assert "setInterval(check,150)" in src


def test_mobile_auto_commands_are_idempotent():
    src = Path("puma_trader/ui.py").read_text(encoding="utf-8")
    assert 'if command == "auto_stop":' in src
    assert "이미 자동매매 중지 상태입니다." in src
    assert 'if command == "auto_start":' in src
    assert "이미 자동매매 실행 중입니다. 설정 변경은 중지 후 다시 시작하세요." in src


def test_engine_submit_paths_recheck_enabled_immediately_before_order():
    src = Path("puma_trader/engine.py").read_text(encoding="utf-8")
    buy = src.index("def _submit_buy")
    sell = src.index("def _submit_sell")
    partial = src.index("def _submit_partial_sell")
    assert "if not self.enabled:" in src[buy:sell]
    assert "신규주문 차단" in src[buy:sell]
    assert "if not self.enabled:" in src[sell:partial]
    assert "자동주문 차단" in src[sell:partial]
    assert "if not self.enabled:" in src[partial:src.index("def process", partial)]


def test_mobile_stop_publishes_state_immediately():
    src = Path("puma_trader/ui.py").read_text(encoding="utf-8")
    block = src[src.index('if command == "auto_stop":'):src.index('if command == "auto_start":')]
    assert "self.stop_auto()" in block
    assert "self._publish_mobile_snapshot()" in block
