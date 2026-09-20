from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
pkg = ROOT / "work" / "PUMA_STOCK_PRO_v2.2"
ui_path = pkg / "puma_trader" / "ui.py"
swing_path = pkg / "puma_trader" / "swing.py"
entry_path = pkg / "puma_trader" / "entry_signal.py"
chart_path = pkg / "puma_trader" / "swing_chart.py"
updater_path = pkg / "puma_trader" / "updater.py"

ui = ui_path.read_text(encoding="utf-8")
swing = swing_path.read_text(encoding="utf-8")
entry = entry_path.read_text(encoding="utf-8")
chart = chart_path.read_text(encoding="utf-8")
updater = updater_path.read_text(encoding="utf-8")

def once(text, old, new, label):
    if old not in text:
        raise RuntimeError(f"target not found: {label}")
    return text.replace(old, new, 1)

# ---------- version ----------
ui = once(ui, 'self.setWindowTitle("PUMA STOCK PRO v2.2")', 'self.setWindowTitle("PUMA STOCK PRO v2.3")', "window version")
ui = once(ui, 'title = QLabel("🐆  PUMA STOCK PRO  v2.2")', 'title = QLabel("🐆  PUMA STOCK PRO  v2.3")', "header version")

# ---------- settings defaults ----------
swing = swing.replace("    box_min_coverage: float = 0.72", "    box_min_coverage: float = 0.68")
swing = swing.replace("    box_min_touches: int = 3", "    box_min_touches: int = 2")
swing = swing.replace("    box_max_drift_pct: float = 6.0", "    box_max_drift_pct: float = 7.5")
swing = swing.replace("    pullback_volume_max_ratio: float = 0.45", "    pullback_volume_max_ratio: float = 0.60")
swing = swing.replace("    pullback_base_volume_max_ratio: float = 0.85", "    pullback_base_volume_max_ratio: float = 1.00")
swing = swing.replace("    pullback_support_tolerance_pct: float = 2.5", "    pullback_support_tolerance_pct: float = 3.0")
swing = swing.replace("    pullback_confirm_bars: int = 2", "    pullback_confirm_bars: int = 1")
swing = swing.replace("    breakout_buffer_pct: float = 0.3", "    breakout_buffer_pct: float = 0.15")
swing = once(
    swing,
    "    path_max_pullback_bars: int = 12\n",
    "    path_max_pullback_bars: int = 12\n    path_duplicate_suppress_bars: int = 8\n",
    "duplicate field",
)

# ---------- UI settings ----------
ui = ui.replace(
    'self.sw_pullback_bars = self._spin(2, 5, ss.pullback_confirm_bars)',
    'self.sw_pullback_bars = self._spin(1, 5, ss.pullback_confirm_bars)'
)
ui = ui.replace(
    'bf.addRow("확정 돌파 거래량 ≥", self.sw_breakout_vol)',
    'bf.addRow("돌파 거래량강도 ≥", self.sw_breakout_vol)'
)
ui = ui.replace(
    'bf.addRow("저거래량 확인 연속봉", self.sw_pullback_bars)',
    'bf.addRow("눌림 저거래량 최소봉", self.sw_pullback_bars)'
)

old_note = '''        note = QLabel(
            "박스 기간을 미리 정하지 않습니다. 탐색 범위 안에서 수평 지지·저항이 반복되고 "
            "가격이 실제로 왕복한 구간만 공구리로 채택합니다. 추세구간은 박스로 잡지 않습니다."
        )
'''
new_note = '''        note = QLabel(
            "공개 주식단테 강의의 핵심을 반영: 박스/매물대 돌파는 거래량이 확 붙어야 하고 "
            "(전봉 또는 최근20봉 평균 대비 300% 이상), 돌파 뒤 눌림에서는 거래량이 확 줄어야 합니다. "
            "박스 기간은 고정하지 않고 실제 수평 지지·저항 왕복구간을 자동 판정합니다."
        )
'''
ui = once(ui, old_note, new_note, "settings note")

# Preset values: less over-filtering while keeping 300% breakout/rebreak.
ui = ui.replace('"sw_box_coverage": 0.72,', '"sw_box_coverage": 0.68,')
ui = ui.replace('"sw_box_touches": 3,', '"sw_box_touches": 2,')
ui = ui.replace('"sw_box_drift": 6.0,', '"sw_box_drift": 7.5,')
ui = ui.replace('"sw_breakout_buffer": 0.3,', '"sw_breakout_buffer": 0.15,')
ui = ui.replace('"sw_pullback_vol": 0.45,', '"sw_pullback_vol": 0.60,')
ui = ui.replace('"sw_pullback_base_vol": 0.85,', '"sw_pullback_base_vol": 1.00,')
ui = ui.replace('"sw_pullback_tol": 2.5,', '"sw_pullback_tol": 3.0,')
ui = ui.replace('"sw_pullback_bars": 2,', '"sw_pullback_bars": 1,')
ui = ui.replace(
    "PUMA 표준값 적용 · 박스기간 자동 · 돌파300% · 눌림≤45%/평균≤85% · 재돌파300% · 파란점선26/2.6/26",
    "PUMA 표준값 적용 · 박스기간 자동 · 돌파강도300% · 눌림≤60%/평균≤100% · 재돌파300% · 파란점선26/2.6/26"
)

# ---------- probability uses common path quality rather than unrelated technique score ----------
old_est = '''            est = estimate_from_flags(
                series["candles"],
                flags,
                horizon_bars=horizon,
                tp_pct=tp,
                sl_pct=sl,
                current_score=int(getattr(analysis, "score", 0) or 0),
                current_active=core.active,
                core_signal_name=core.name,
                core_signal_reason=core.reason,
            )
'''
new_est = '''            path_quality = int((series.get("core_path") or {}).get("quality_score", 0) or 0)
            analysis.details["공통 경로 품질"] = f"{path_quality}/100"
            est = estimate_from_flags(
                series["candles"],
                flags,
                horizon_bars=horizon,
                tp_pct=tp,
                sl_pct=sl,
                current_score=(path_quality if path_quality > 0 else int(getattr(analysis, "score", 0) or 0)),
                current_active=core.active,
                core_signal_name=core.name,
                core_signal_reason=core.reason,
            )
'''
ui = once(ui, old_est, new_est, "probability quality")

# ---------- entry signal stage names ----------
start = entry.index("def _common_market_path_signal(series: dict)")
end = entry.index("\ndef _day_signal", start)
common = r'''def _common_market_path_signal(series: dict) -> CoreEntrySignal | None:
    path = series.get("core_path")
    if not isinstance(path, dict):
        return None

    stage = str(path.get("stage") or "대기")
    reason = str(path.get("reason") or "")
    quality = int(path.get("quality_score", 0) or 0)

    if bool(path.get("active")):
        matched = []
        if stage == "확정 돌파":
            matched = [
                "박스/전고점 저항 종가 돌파",
                f"거래량강도 {float(path.get('breakout_volume_ratio',0)):.2f}배",
                f"구조품질 {quality}/100",
            ]
        elif stage in ("확정 눌림", "눌림 확인 / 재상승 대기"):
            matched = [
                "선행 돌파 확인",
                "돌파가격 지지",
                f"눌림 거래량/돌파봉 {float(path.get('pullback_volume_ratio',1)):.2f}",
                f"구조품질 {quality}/100",
            ]
        elif stage == "확정 재돌파":
            matched = [
                "선행 돌파 확인",
                "저거래량 눌림 확인",
                f"재돌파 거래량강도 {float(path.get('rebreak_volume_ratio',0)):.2f}배",
                f"구조품질 {quality}/100",
            ]
        else:
            matched = [stage, f"구조품질 {quality}/100"]
        return CoreEntrySignal(True, f"공통 핵심경로 · {stage}", matched, [], reason)

    missing = []
    if stage == "공구리 형성 / 돌파 대기":
        missing.append("박스상단 종가돌파 + 거래량강도 300%")
    elif stage == "돌파 후 눌림 대기":
        missing.append("돌파선 지지 + 거래량이 확 죽는 눌림")
    elif stage == "돌파 실패 / 박스 복귀":
        missing.append("돌파기준선 재회복")
    else:
        missing.append("박스돌파→저거래량 눌림→재상승/재돌파 구조")
    return CoreEntrySignal(False, f"공통 핵심경로 · {stage}", [], missing, reason)

'''
entry = entry[:start] + common + entry[end:]

# ---------- chart labels: event flags are already sparse, so always show them ----------
chart = chart.replace("            if label and n <= 180:\n", "            if label:\n")

# ---------- update note ----------
ui = ui.replace(
    "v2.2: 박스 기간 고정을 제거하고 실제 수평 지지·저항 왕복구간만 공구리로 판정. 돌파/눌림/재돌파 라벨은 강화조건을 모두 통과한 최초 확정봉만 표시. 확률은 현재와 동일한 확정 단계만 따로 계산하고 표본수·95%구간·신뢰도를 함께 표시.",
    "v2.3: 공개 단테 강의의 박스돌파→저거래량 눌림 원칙을 재반영. 박스권 돌파는 전봉 또는 20봉평균 대비 거래량강도 300%로 확인하고, 눌림은 돌파선 지지와 뚜렷한 거래량 감소를 확인해 최초 1회 표시. 지나친 필터를 완화해 유효 돌파/눌림 누락을 줄이고 공통경로 품질점수를 확률판단에 사용."
)

# ---------- updater ----------
updater = once(updater, 'CURRENT_VERSION = "2.2.0"', 'CURRENT_VERSION = "2.3.0"', "updater version")
updater = updater.replace("PUMA-STOCK-UPDATER/2.2", "PUMA-STOCK-UPDATER/2.3")

ui_path.write_text(ui, encoding="utf-8")
swing_path.write_text(swing, encoding="utf-8")
entry_path.write_text(entry, encoding="utf-8")
chart_path.write_text(chart, encoding="utf-8")
updater_path.write_text(updater, encoding="utf-8")
(pkg / "puma_trader" / "__init__.py").write_text('__version__ = "2.3.0"\n', encoding="utf-8")
print("PUMA v2.3 balanced breakout/pullback patch applied")
