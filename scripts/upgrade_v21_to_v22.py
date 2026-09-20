from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
pkg = ROOT / "work" / "PUMA_STOCK_PRO_v2.1"
ui_path = pkg / "puma_trader" / "ui.py"
swing_path = pkg / "puma_trader" / "swing.py"
chart_path = pkg / "puma_trader" / "swing_chart.py"
updater_path = pkg / "puma_trader" / "updater.py"

ui = ui_path.read_text(encoding="utf-8")
swing = swing_path.read_text(encoding="utf-8")
chart = chart_path.read_text(encoding="utf-8")
updater = updater_path.read_text(encoding="utf-8")

def once(text, old, new, label):
    if old not in text:
        raise RuntimeError(f"target not found: {label}")
    return text.replace(old, new, 1)

# ---------- version ----------
ui = once(ui, 'self.setWindowTitle("PUMA STOCK PRO v2.1")', 'self.setWindowTitle("PUMA STOCK PRO v2.2")', "window version")
ui = once(ui, 'title = QLabel("🐆  PUMA STOCK PRO  v2.1")', 'title = QLabel("🐆  PUMA STOCK PRO  v2.2")', "header version")

# ---------- Swing settings: duration is no longer fixed ----------
swing = once(swing,
"""    box_period_min: int = 60
    box_period_max: int = 112
    box_width_pct: float = 25.0
    box_min_coverage: float = 0.70
    box_min_touches: int = 3
    box_touch_tolerance_pct: float = 2.5
    breakout_volume_ratio: float = 3.0
    pullback_volume_max_ratio: float = 0.55
    pullback_support_tolerance_pct: float = 3.0
    rebreak_volume_ratio: float = 3.0
    path_max_pullback_bars: int = 12
    breakout_buffer_pct: float = 0.2
""",
"""    # legacy fields kept for old config compatibility; v2.2 does not force box duration.
    box_period_min: int = 60
    box_period_max: int = 112
    box_search_lookback: int = 160
    box_width_pct: float = 30.0
    box_min_coverage: float = 0.72
    box_min_touches: int = 3
    box_min_alternations: int = 2
    box_touch_tolerance_pct: float = 2.5
    box_max_drift_pct: float = 6.0
    breakout_volume_ratio: float = 3.0
    pullback_volume_max_ratio: float = 0.45
    pullback_base_volume_max_ratio: float = 0.85
    pullback_support_tolerance_pct: float = 2.5
    pullback_confirm_bars: int = 2
    rebreak_volume_ratio: float = 3.0
    path_max_pullback_bars: int = 12
    breakout_buffer_pct: float = 0.3
""",
"v2.2 swing settings")

# ---------- analysis: distinguish true box from prior-high hill ----------
swing = once(swing,
"""    if box:
        score += 20
        stage = '박스 상단 돌파 대기' if box.get('breakout_idx', -1) < 0 else '상단 안착 확인'
""",
"""    if box:
        if box.get('structure_type') == '공구리':
            score += 20
            stage = '공구리 확인 · 돌파 대기' if box.get('breakout_idx', -1) < 0 else '공구리 상단 돌파 확인'
        else:
            score += 10
            stage = '전고점언덕 저항 확인'
""",
"box stage distinction")

swing = once(swing,
"""        ('공구리 확인' if box else '공구리 미확인'),
""",
"""        (
            '공구리 확인'
            if box and box.get('structure_type') == '공구리'
            else ('전고점언덕 확인' if box else '공구리 미확인')
        ),
""",
"reason structure distinction")

swing = once(swing,
"""        '공구리(박스권)': (
            f"확인 · {box.get('period',0)}봉 · {box.get('low',0):,.0f}~{box.get('high',0):,.0f} · "
            f"폭 {box.get('width_pct',0):.1f}% · 상단터치 {box.get('top_touches',0)}회"
            if box else '미확인'
        ),
""",
"""        '공구리(박스권)': (
            (
                f"확인 · 기간 자동 {box.get('period',0)}봉 · "
                f"지지 {box.get('low',0):,.0f} / 저항 {box.get('high',0):,.0f} · "
                f"상단 {box.get('top_touches',0)}회 / 하단 {box.get('bottom_touches',0)}회 · "
                f"왕복 {box.get('alternations',0)}회 · 기울기 {box.get('drift_pct',0):.1f}%"
            )
            if box and box.get('structure_type') == '공구리'
            else (
                f"공구리 미확인 · 전고점언덕 저항 {box.get('high',0):,.0f} 확인"
                if box else '미확인'
            )
        ),
""",
"box detail distinction")

swing = swing.replace(
    "if core_path.get('stage') == '거래량 동반 재돌파'",
    "if core_path.get('stage') == '확정 재돌파'"
)

# ---------- UI: dynamic box settings ----------
old_box = '''        box = QGroupBox("공구리(박스권) · 60~112봉 동적 탐지")
        bf = QFormLayout(box)
        self.sw_box_min = self._spin(20, 112, ss.box_period_min)
        self.sw_box_max = self._spin(60, 160, ss.box_period_max)
        self.sw_box_width = self._dspin(5, 50, ss.box_width_pct, " %")
        self.sw_box_coverage = self._dspin(0.50, 0.95, ss.box_min_coverage)
        self.sw_box_touches = self._spin(2, 10, ss.box_min_touches)
        self.sw_box_touch_tol = self._dspin(0.5, 8.0, ss.box_touch_tolerance_pct, " %")
        self.sw_breakout_buffer = self._dspin(0.0, 5.0, ss.breakout_buffer_pct, " %")
        self.sw_breakout_vol = self._dspin(1.0, 10.0, ss.breakout_volume_ratio, " 배")
        self.sw_pullback_vol = self._dspin(0.10, 1.20, ss.pullback_volume_max_ratio)
        self.sw_pullback_tol = self._dspin(0.5, 8.0, ss.pullback_support_tolerance_pct, " %")
        self.sw_rebreak_vol = self._dspin(1.0, 10.0, ss.rebreak_volume_ratio, " 배")
        self.sw_path_bars = self._spin(3, 30, ss.path_max_pullback_bars)
        bf.addRow("박스 최소 기간", self.sw_box_min)
        bf.addRow("박스 최대 기간", self.sw_box_max)
        bf.addRow("박스 최대 폭", self.sw_box_width)
        bf.addRow("박스 내 종가 비율 ≥", self.sw_box_coverage)
        bf.addRow("상·하단 최소 접촉", self.sw_box_touches)
        bf.addRow("접촉 허용오차", self.sw_box_touch_tol)
        bf.addRow("상단 돌파 버퍼", self.sw_breakout_buffer)
        bf.addRow("돌파 거래량 ≥", self.sw_breakout_vol)
        bf.addRow("눌림 거래량/돌파봉 ≤", self.sw_pullback_vol)
        bf.addRow("박스상단 지지 허용", self.sw_pullback_tol)
        bf.addRow("재돌파 거래량 ≥", self.sw_rebreak_vol)
        bf.addRow("눌림 추적 최대봉", self.sw_path_bars)
        note = QLabel(
            "공구리: 60~112봉에서 종가가 같은 가격대에 70% 이상 머물고, "
            "상단·하단을 각각 3회 이상 확인한 박스를 우선 채택합니다."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#9eb4c9")
        bf.addRow(note)
        sv.addWidget(box)
'''
new_box = '''        box = QGroupBox("공구리(박스권) · 기간 자동")
        bf = QFormLayout(box)
        auto_period = QLabel("자동 판정 · 지지/저항 반복이 실제로 이어진 구간만 사용")
        auto_period.setStyleSheet("color:#61ff8f;font-weight:800")
        self.sw_box_lookback = self._spin(40, 400, ss.box_search_lookback)
        self.sw_box_width = self._dspin(5, 50, ss.box_width_pct, " %")
        self.sw_box_coverage = self._dspin(0.50, 0.95, ss.box_min_coverage)
        self.sw_box_touches = self._spin(2, 10, ss.box_min_touches)
        self.sw_box_alternations = self._spin(1, 10, ss.box_min_alternations)
        self.sw_box_touch_tol = self._dspin(0.5, 8.0, ss.box_touch_tolerance_pct, " %")
        self.sw_box_drift = self._dspin(1.0, 20.0, ss.box_max_drift_pct, " %")
        self.sw_breakout_buffer = self._dspin(0.0, 5.0, ss.breakout_buffer_pct, " %")
        self.sw_breakout_vol = self._dspin(1.0, 10.0, ss.breakout_volume_ratio, " 배")
        self.sw_pullback_vol = self._dspin(0.10, 1.00, ss.pullback_volume_max_ratio)
        self.sw_pullback_base_vol = self._dspin(0.10, 1.20, ss.pullback_base_volume_max_ratio)
        self.sw_pullback_tol = self._dspin(0.5, 8.0, ss.pullback_support_tolerance_pct, " %")
        self.sw_pullback_bars = self._spin(2, 5, ss.pullback_confirm_bars)
        self.sw_rebreak_vol = self._dspin(1.0, 10.0, ss.rebreak_volume_ratio, " 배")
        self.sw_path_bars = self._spin(3, 30, ss.path_max_pullback_bars)
        bf.addRow("박스 기간", auto_period)
        bf.addRow("과거 탐색 범위", self.sw_box_lookback)
        bf.addRow("박스 최대 폭", self.sw_box_width)
        bf.addRow("박스 내 종가 비율 ≥", self.sw_box_coverage)
        bf.addRow("상·하단 최소 독립접촉", self.sw_box_touches)
        bf.addRow("상↔하 최소 왕복", self.sw_box_alternations)
        bf.addRow("접촉 허용오차", self.sw_box_touch_tol)
        bf.addRow("박스 기울기 최대", self.sw_box_drift)
        bf.addRow("상단 돌파 버퍼", self.sw_breakout_buffer)
        bf.addRow("확정 돌파 거래량 ≥", self.sw_breakout_vol)
        bf.addRow("눌림 거래량/돌파봉 ≤", self.sw_pullback_vol)
        bf.addRow("눌림 거래량/20봉평균 ≤", self.sw_pullback_base_vol)
        bf.addRow("돌파선 지지 허용", self.sw_pullback_tol)
        bf.addRow("저거래량 확인 연속봉", self.sw_pullback_bars)
        bf.addRow("확정 재돌파 거래량 ≥", self.sw_rebreak_vol)
        bf.addRow("눌림 추적 최대봉", self.sw_path_bars)
        note = QLabel(
            "박스 기간을 미리 정하지 않습니다. 탐색 범위 안에서 수평 지지·저항이 반복되고 "
            "가격이 실제로 왕복한 구간만 공구리로 채택합니다. 추세구간은 박스로 잡지 않습니다."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#9eb4c9")
        bf.addRow(note)
        sv.addWidget(box)
'''
ui = once(ui, old_box, new_box, "dynamic box UI")

# ---------- settings persistence ----------
ui = once(ui,
"""        x.box_period_min = self.sw_box_min.value()
        x.box_period_max = max(x.box_period_min, self.sw_box_max.value())
        x.box_width_pct = self.sw_box_width.value()
        x.box_min_coverage = self.sw_box_coverage.value()
        x.box_min_touches = self.sw_box_touches.value()
        x.box_touch_tolerance_pct = self.sw_box_touch_tol.value()
        x.breakout_buffer_pct = self.sw_breakout_buffer.value()
        x.breakout_volume_ratio = self.sw_breakout_vol.value()
        x.pullback_volume_max_ratio = self.sw_pullback_vol.value()
        x.pullback_support_tolerance_pct = self.sw_pullback_tol.value()
        x.rebreak_volume_ratio = self.sw_rebreak_vol.value()
        x.path_max_pullback_bars = self.sw_path_bars.value()
""",
"""        x.box_search_lookback = self.sw_box_lookback.value()
        x.box_width_pct = self.sw_box_width.value()
        x.box_min_coverage = self.sw_box_coverage.value()
        x.box_min_touches = self.sw_box_touches.value()
        x.box_min_alternations = self.sw_box_alternations.value()
        x.box_touch_tolerance_pct = self.sw_box_touch_tol.value()
        x.box_max_drift_pct = self.sw_box_drift.value()
        x.breakout_buffer_pct = self.sw_breakout_buffer.value()
        x.breakout_volume_ratio = self.sw_breakout_vol.value()
        x.pullback_volume_max_ratio = self.sw_pullback_vol.value()
        x.pullback_base_volume_max_ratio = self.sw_pullback_base_vol.value()
        x.pullback_support_tolerance_pct = self.sw_pullback_tol.value()
        x.pullback_confirm_bars = self.sw_pullback_bars.value()
        x.rebreak_volume_ratio = self.sw_rebreak_vol.value()
        x.path_max_pullback_bars = self.sw_path_bars.value()
""",
"save v2.2 box settings")

# ---------- preset ----------
old_values = '''        values = {
            "sw_vol_period": 20,
            "sw_vol_ratio": 3.0,
            "sw_wick_ratio": 0.42,
            "sw_wick_body": 1.35,
            "sw_bear_body": 0.58,
            "sw_acc_lookback": 112,
            "sw_acc_min": 2,
            "sw_acc_cluster": 20,
            "sw_box_min": 60,
            "sw_box_max": 112,
            "sw_box_width": 25.0,
            "sw_box_coverage": 0.70,
            "sw_box_touches": 3,
            "sw_box_touch_tol": 2.5,
            "sw_breakout_buffer": 0.2,
            "sw_breakout_vol": 3.0,
            "sw_pullback_vol": 0.55,
            "sw_pullback_tol": 3.0,
            "sw_rebreak_vol": 3.0,
            "sw_path_bars": 12,
            "sw_blue_period": 26,
            "sw_blue_dev": 2.6,
            "sw_blue_shift": 26,
            "sw_blue_near": 3.0,
        }
'''
new_values = '''        values = {
            "sw_vol_period": 20,
            "sw_vol_ratio": 3.0,
            "sw_wick_ratio": 0.42,
            "sw_wick_body": 1.35,
            "sw_bear_body": 0.58,
            "sw_acc_lookback": 112,
            "sw_acc_min": 2,
            "sw_acc_cluster": 20,
            "sw_box_lookback": 160,
            "sw_box_width": 30.0,
            "sw_box_coverage": 0.72,
            "sw_box_touches": 3,
            "sw_box_alternations": 2,
            "sw_box_touch_tol": 2.5,
            "sw_box_drift": 6.0,
            "sw_breakout_buffer": 0.3,
            "sw_breakout_vol": 3.0,
            "sw_pullback_vol": 0.45,
            "sw_pullback_base_vol": 0.85,
            "sw_pullback_tol": 2.5,
            "sw_pullback_bars": 2,
            "sw_rebreak_vol": 3.0,
            "sw_path_bars": 12,
            "sw_blue_period": 26,
            "sw_blue_dev": 2.6,
            "sw_blue_shift": 26,
            "sw_blue_near": 3.0,
        }
'''
ui = once(ui, old_values, new_values, "v2.2 preset")
ui = ui.replace(
    "PUMA 표준값 적용 · 거래량300% · 공구리60~112봉 · 눌림거래량≤55% · 재돌파300% · 파란점선26/2.6/26",
    "PUMA 표준값 적용 · 박스기간 자동 · 돌파300% · 눌림≤45%/평균≤85% · 재돌파300% · 파란점선26/2.6/26"
)

# ---------- probability wording ----------
ui = ui.replace(
    'f"과거 유사 신호의 TP-before-SL 통계 · TP {tp:.1f}% / SL {sl:.1f}% · {horizon}봉"',
    'f"현재와 동일한 확정 단계의 TP-before-SL 통계 · TP {tp:.1f}% / SL {sl:.1f}% · {horizon}봉"'
)

# ---------- update note ----------
ui = ui.replace(
    "v2.1: 모든 기법의 최상위 로직을 수급→전고점/박스상단 돌파→거래량감소 눌림→거래량동반 재돌파로 통합. 공구리는 60~112봉 동적 박스, 돌파/재돌파 거래량 300% 이상을 기본값으로 적용.",
    "v2.2: 박스 기간 고정을 제거하고 실제 수평 지지·저항 왕복구간만 공구리로 판정. 돌파/눌림/재돌파 라벨은 강화조건을 모두 통과한 최초 확정봉만 표시. 확률은 현재와 동일한 확정 단계만 따로 계산하고 표본수·95%구간·신뢰도를 함께 표시."
)

# ---------- chart: true box vs prior-high hill; sparse labels ----------
box_start = chart.index("        # 공구리 박스:")
box_end = chart.index("        maxvol = max(c['volume'] for c in cs) or 1", box_start)
new_chart_box = r'''        # 공구리/전고점언덕: 구조 종류를 구분해서 표시.
        box = self.series.get('box')
        if box and box.get('start',-1) < end and box.get('end',-1) >= start:
            bs = max(start, box['start']); be = min(end-1, box['end'])
            xs = x(bs-start)-4; xe = x(be-start)+4
            structure_type = str(box.get('structure_type') or '공구리')

            if structure_type == '공구리':
                r = QRectF(xs, y(box['high']), xe-xs, y(box['low'])-y(box['high']))
                p.setPen(QPen(QColor('#f4ce48'),2,Qt.DashLine))
                p.setBrush(QColor(244,206,72,24))
                p.drawRect(r)
                p.setPen(QColor('#f4ce48'))
                p.drawText(
                    int(xs+6), int(y(box['high'])-6),
                    f"공구리 · 지지/저항 {box.get('period','-')}봉"
                )
            else:
                p.setPen(QPen(QColor('#f4ce48'),2,Qt.DashLine))
                p.drawLine(QPointF(xs, y(box['high'])), QPointF(xe, y(box['high'])))
                p.drawText(int(xs+6), int(y(box['high'])-6), '전고점언덕 저항')

            if box.get('breakout_idx', -1) >= 0:
                p.setPen(QPen(QColor('#f4ce48'), 1.6, Qt.DashLine))
                p.drawLine(QPointF(xe, y(box['high'])), QPointF(price_rect.right(), y(box['high'])))
                p.drawText(int(min(price_rect.right()-85, xe+6)), int(y(box['high'])-7), '돌파기준선')

'''
chart = chart[:box_start] + new_chart_box + chart[box_end:]

# More explicit sparse confirmation labels.
chart = chart.replace("label = '재돌파'; label_color = QColor('#ffcf3d')", "label = '✓재돌파'; label_color = QColor('#ffcf3d')")
chart = chart.replace("label = '눌림'; label_color = QColor('#62d98b')", "label = '✓눌림'; label_color = QColor('#62d98b')")
chart = chart.replace("label = '돌파'; label_color = QColor('#ff6a6a')", "label = '✓돌파'; label_color = QColor('#ff6a6a')")

# ---------- updater ----------
updater = once(updater, 'CURRENT_VERSION = "2.1.0"', 'CURRENT_VERSION = "2.2.0"', "updater version")
updater = updater.replace("PUMA-STOCK-UPDATER/2.1", "PUMA-STOCK-UPDATER/2.2")

ui_path.write_text(ui, encoding="utf-8")
swing_path.write_text(swing, encoding="utf-8")
chart_path.write_text(chart, encoding="utf-8")
updater_path.write_text(updater, encoding="utf-8")
(pkg / "puma_trader" / "__init__.py").write_text('__version__ = "2.2.0"\n', encoding="utf-8")
print("PUMA v2.2 adaptive box + sparse confirmed path patch applied")
