from pathlib import Path


def test_search_result_can_be_added_to_integrated_list():
    src = Path("puma_trader/ui.py").read_text(encoding="utf-8")
    assert 'self.focus_stock_add_btn = QPushButton("＋ 리스트 추가")' in src
    assert "def add_searched_stock_to_focus_list(self):" in src
    assert 'seq="MANUAL:SEARCH"' in src
    assert 'condition_name="검색 직접추가"' in src
    assert 'item["manual_search_only"] = True' in src
    assert 'return "검색추가"' in src


def test_search_only_entry_is_not_generic_auto_candidate():
    src = Path("puma_trader/ui.py").read_text(encoding="utf-8")
    targets = src[src.index("def _active_targets"):src.index("def start_danta_pool_auto")]
    assert 'if item.get("manual_search_only") and auto_count == 0:' in targets
    assert "continue" in targets


def test_whole_candidate_button_explains_monitor_then_trade():
    src = Path("puma_trader/ui.py").read_text(encoding="utf-8")
    assert "▶ 전체 후보 감시 · 조건충족만 매매" in src
    assert "전체 후보를 전부 매수하는 기능이 아닙니다." in src
