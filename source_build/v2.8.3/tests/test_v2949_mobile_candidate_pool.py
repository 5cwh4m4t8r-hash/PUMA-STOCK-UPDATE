from pathlib import Path


def test_mobile_all_scope_ignores_watchlist_and_uses_danta_pool():
    src = Path("puma_trader/ui.py").read_text(encoding="utf-8")
    block = src[src.index('if command == "auto_start":'):src.index('if command == "order":')]
    assert "self.focus_auto_danta_pool = True" in block
    assert "self.start_condition_stream()" in block
    assert 'raise ValueError("관심종목이 없습니다.")' not in block
    assert "단타 검색기 합집합" in block


def test_mobile_web_sends_hero_source_for_all_scope():
    src = Path("puma_trader/mobile_bridge.py").read_text(encoding="utf-8")
    assert "단타 검색기 전체 → PUMA 2차선별" in src
    assert "candidate_source:(scope==='ALL'?'HERO4'" in src


def test_mobile_all_scope_forces_hero_source_in_settings():
    src = Path("puma_trader/ui.py").read_text(encoding="utf-8")
    apply = src[src.index("def _apply_mobile_auto_settings"):src.index("@staticmethod", src.index("def _apply_mobile_auto_settings"))]
    assert 'if scope == "ALL":' in apply
    assert 'source = "HERO4"' in apply
