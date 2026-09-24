from pathlib import Path


def test_candidate_short_history_is_not_cached_as_visual_arrow_result():
    ui = Path("puma_trader/ui.py").read_text(encoding="utf-8")
    start = ui.index("def _on_candidate_classified")
    end = ui.index("def _candidate_classifier_finished", start)
    block = ui[start:end]
    assert "_display_cache.put" not in block
    assert "short daily sample" in block


def test_day_focus_waits_for_complete_history_before_analysis():
    ui = Path("puma_trader/ui.py").read_text(encoding="utf-8")
    start = ui.index("def _focus_load_ready")
    end = ui.index("def _focus_load_failed", start)
    block = ui[start:end]
    assert 'not payload.get("complete") and self.focus_chart_mode == "DAY"' in block
    gate = block.index('not payload.get("complete") and self.focus_chart_mode == "DAY"')
    analyze = block.rindex("self._start_focus_analysis(payload)")
    assert gate < analyze


def test_kiwoom_daily_chart_requests_adjusted_prices():
    broker = Path("puma_trader/broker.py").read_text(encoding="utf-8")
    assert '"upd_stkpc_tp": "1"' in broker
    assert 'api_id = "ka10080" if is_minute else "ka10081"' in broker
