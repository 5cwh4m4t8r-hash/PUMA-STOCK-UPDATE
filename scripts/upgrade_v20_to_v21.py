from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
pkg = ROOT / "work" / "PUMA_STOCK_PRO_v2.0"
ui_path = pkg / "puma_trader" / "ui.py"
swing_path = pkg / "puma_trader" / "swing.py"
entry_path = pkg / "puma_trader" / "entry_signal.py"
prob_path = pkg / "puma_trader" / "probability.py"
chart_path = pkg / "puma_trader" / "swing_chart.py"
updater_path = pkg / "puma_trader" / "updater.py"

ui = ui_path.read_text(encoding="utf-8")
swing = swing_path.read_text(encoding="utf-8")
entry = entry_path.read_text(encoding="utf-8")
prob = prob_path.read_text(encoding="utf-8")
chart = chart_path.read_text(encoding="utf-8")
updater = updater_path.read_text(encoding="utf-8")

def once(text, old, new, label):
    if old not in text:
        raise RuntimeError(f"target not found: {label}")
    return text.replace(old, new, 1)

# ---------- version ----------
ui = once(ui, 'self.setWindowTitle("PUMA STOCK PRO v2.0")', 'self.setWindowTitle("PUMA STOCK PRO v2.1")', "window version")
ui = once(ui, 'title = QLabel("🐆  PUMA STOCK PRO  v2.0")', 'title = QLabel("🐆  PUMA STOCK PRO  v2.1")', "header version")

# ---------- common market-path import ----------
ui = once(ui,
          "from .entry_signal import evaluate_core_entry\n",
          "from .entry_signal import evaluate_core_entry\nfrom .market_path import analyze_market_path\n",
          "ui market path import")
swing = once(swing,
             "from .watermelon_proxy import build_puma_watermelon\n",
             "from .watermelon_proxy import build_puma_watermelon\nfrom .market_path import analyze_market_path\n",
             "swing market path import")

# ---------- SwingSettings: user's requested 300% / 60~112 box defaults ----------
swing = once(swing, "    volume_ratio: float = 2.0\n", "    volume_ratio: float = 3.0\n", "300 percent accumulation")
swing = once(swing, "    accumulation_lookback: int = 90\n", "    accumulation_lookback: int = 112\n", "accumulation 112")
swing = once(swing, "    box_window: int = 18\n", "    box_window: int = 90  # legacy compatibility; dynamic box uses box_period_min/max\n", "legacy box window")
swing = once(swing,
"""    box_width_pct: float = 14.0
    breakout_buffer_pct: float = 0.2
""",
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
"dynamic box/path settings")

# ---------- swing analysis uses dynamic 60~112 box + common path ----------
swing = once(swing,
"""    required_acc = max(2, int(settings.accumulation_min_count or 2))
    box = _find_box(candles, settings)
    bval = blue[last] or 0.0
""",
"""    required_acc = max(2, int(settings.accumulation_min_count or 2))
    market_path = analyze_market_path(candles, settings)
    box = market_path.get('box')
    core_path = market_path.get('current', {})
    bval = blue[last] or 0.0
""",
"dynamic box call")

swing = once(swing,
"""    pullback = detect_breakout_pullback(candles)

    stage = '장기 역배열 확인'
""",
"""    pullback = detect_breakout_pullback(candles)

    stage = '장기 역배열 확인'
""",
"preserve secondary pullback")

# breakout/accepted should come from common path box/event.
swing = once(swing,
"""    breakout = bool(box and box.get('breakout_idx', -1) >= 0)
    if breakout:
        score += 15
    accepted = bool(box and box.get('accepted'))
""",
"""    breakout = bool(box and box.get('breakout_idx', -1) >= 0)
    if breakout:
        score += 15
    accepted = bool(box and box.get('accepted'))
""",
"breakout compatibility")

# Core path gets top priority in stage and score.
swing = once(swing,
"""    if pullback.get('confirmed'):
        score += 15
        if not accepted:
            stage = '기준봉 후 거래량 감소 눌림 · 진입구간 관찰'
    score = min(100, score)
""",
"""    if pullback.get('confirmed'):
        score += 10
        if not accepted:
            stage = '기준봉 후 거래량 감소 눌림 · 진입구간 관찰'
    if core_path.get('active'):
        score += 25
        stage = str(core_path.get('stage') or stage)
    elif core_path.get('stage') == '박스 상단 돌파 대기' and box:
        stage = '공구리 확인 · 거래량 300% 돌파 대기'
    score = min(100, score)
""",
"core path stage")

swing = once(swing,
"""    if pullback.get('confirmed'):
        reasons.append('기준봉 후 거래량 감소 눌림 확인')
""",
"""    if pullback.get('confirmed'):
        reasons.append('기준봉 후 거래량 감소 눌림 확인')
    if core_path.get('active'):
        reasons.insert(0, str(core_path.get('stage')))
""",
"core path reason")

# Richer box / path details.
swing = once(swing,
"""        '공구리(박스권)': '확인' if box else '미확인',
        '박스 상단 돌파': '확인' if breakout else '대기',
        '상단 박스 안착': '확인' if accepted else '대기',
""",
"""        '공구리(박스권)': (
            f"확인 · {box.get('period',0)}봉 · {box.get('low',0):,.0f}~{box.get('high',0):,.0f} · "
            f"폭 {box.get('width_pct',0):.1f}% · 상단터치 {box.get('top_touches',0)}회"
            if box else '미확인'
        ),
        '공통 수급·돌파 경로': (
            f"{'활성' if core_path.get('active') else '대기'} · {core_path.get('stage','-')} · "
            f"{core_path.get('reason','-')}"
        ),
        '박스 상단 돌파': (
            f"확인 · 거래량 {core_path.get('breakout_volume_ratio',0):.2f}배"
            if breakout else '대기 · 거래량 3.00배 이상 필요'
        ),
        '상단 박스 안착': '확인' if accepted else '대기',
        '재돌파': (
            f"확인 · 거래량 {core_path.get('rebreak_volume_ratio',0):.2f}배"
            if core_path.get('stage') == '거래량 동반 재돌파'
            else '대기 · 눌림 후 거래량 3.00배 재확대 필요'
        ),
""",
"market path details")

swing = once(swing,
"""        'box': box,
        'pullback': pullback,
""",
"""        'box': box,
        'pullback': pullback,
        'core_path': core_path,
        'path_breakout': market_path.get('path_breakout', []),
        'path_pullback': market_path.get('path_pullback', []),
        'path_rebreakout': market_path.get('path_rebreakout', []),
""",
"market path series")

# ---------- entry_signal: common essence before named-technique filters ----------
common_func = r'''

def _common_market_path_signal(series: dict) -> CoreEntrySignal | None:
    path = series.get("core_path")
    if not isinstance(path, dict):
        return None

    stage = str(path.get("stage") or "대기")
    reason = str(path.get("reason") or "")
    if bool(path.get("active")):
        matched = []
        if stage == "거래량 동반 상향돌파":
            matched = [
                "이전 전고점/박스상단 돌파",
                f"돌파 거래량 {float(path.get('breakout_volume_ratio',0)):.2f}배",
            ]
        elif stage == "돌파 후 거래량 감소 눌림":
            matched = [
                "이전 저항 상향돌파",
                "돌파가격 지지",
                f"눌림 거래량/돌파봉 {float(path.get('pullback_volume_ratio',1)):.2f}",
            ]
        elif stage == "거래량 동반 재돌파":
            matched = [
                "상향돌파 완료",
                "거래량 감소 눌림 완료",
                f"재돌파 거래량 {float(path.get('rebreak_volume_ratio',0)):.2f}배",
            ]
        else:
            matched = [stage]
        return CoreEntrySignal(True, f"공통 핵심경로 · {stage}", matched, [], reason)

    missing = []
    if stage == "박스 상단 돌파 대기":
        missing.append("전고점/박스상단 거래량 300%+ 돌파")
    elif stage == "돌파 상단 유지":
        missing.append("거래량 감소 눌림 또는 거래량 300%+ 재돌파")
    elif stage == "돌파 실패/박스 복귀":
        missing.append("돌파가격 재회복")
    else:
        missing.append("수급 유입→저항 돌파→거래량 감소 눌림/재돌파 구조")
    return CoreEntrySignal(False, f"공통 핵심경로 · {stage}", [], missing, reason)
'''
insert_at = entry.index("\ndef _day_signal")
entry = entry[:insert_at] + common_func + entry[insert_at:]

entry = once(entry,
"""def evaluate_core_entry(analysis: Any, series: dict, strategy: str) -> CoreEntrySignal:
    strategy = str(strategy or "").upper()
    if strategy == "DAY":
        return _day_signal(analysis, series)
    if strategy == "SWING":
        return _swing_signal(analysis, series)
    return _long_signal(analysis, series)
""",
"""def evaluate_core_entry(analysis: Any, series: dict, strategy: str) -> CoreEntrySignal:
    # All named techniques sit underneath the same supply/breakout/pullback path.
    common = _common_market_path_signal(series)
    if common is not None and common.active:
        return common

    # Keep technique-specific context, but the displayed entry decision is the
    # common path so users can see exactly what is still missing.
    strategy = str(strategy or "").upper()
    if common is not None:
        return common
    if strategy == "DAY":
        return _day_signal(analysis, series)
    if strategy == "SWING":
        return _swing_signal(analysis, series)
    return _long_signal(analysis, series)
""",
"common path priority")

# ---------- probability historical flags use the common path first ----------
prob = once(prob,
"""    wm_confirmed = series.get("watermelon_confirmed", [False]*n)

    out = [False] * n
""",
"""    wm_confirmed = series.get("watermelon_confirmed", [False]*n)
    path_breakout = series.get("path_breakout", [False]*n)
    path_pullback = series.get("path_pullback", [False]*n)
    path_rebreakout = series.get("path_rebreakout", [False]*n)

    out = [False] * n
""",
"path arrays probability")
prob = once(prob,
"""        wm = bool(i < len(wm_confirmed) and wm_confirmed[i])
        if strategy == "DAY":
            out[i] = any_arrow
        elif strategy == "SWING":
            out[i] = wm or (i < len(pink) and bool(pink[i])) or (i < len(red) and bool(red[i]))
        else:
            out[i] = wm
""",
"""        wm = bool(i < len(wm_confirmed) and wm_confirmed[i])
        common = any(
            i < len(arr) and bool(arr[i])
            for arr in (path_breakout, path_pullback, path_rebreakout)
            if isinstance(arr, list)
        )
        if strategy == "DAY":
            out[i] = common or any_arrow
        elif strategy == "SWING":
            out[i] = common or wm or (i < len(pink) and bool(pink[i])) or (i < len(red) and bool(red[i]))
        else:
            out[i] = common or wm
""",
"path probability logic")

# ---------- UI enrichment computes the same path for every timeframe ----------
ui = once(ui,
"""        try:
            # 수박은 내부 진행상태와 차트표시를 분리한다.
""",
"""        try:
            # 모든 기법의 최상위 공통경로: 거래량 유입 -> 저항 돌파 -> 거래량 감소 눌림 -> 재돌파.
            path_bundle = analyze_market_path(series["candles"], self.swing_settings)
            series["core_path"] = path_bundle.get("current", {})
            series["path_breakout"] = path_bundle.get("path_breakout", [])
            series["path_pullback"] = path_bundle.get("path_pullback", [])
            series["path_rebreakout"] = path_bundle.get("path_rebreakout", [])
            if path_bundle.get("box") and not series.get("box"):
                series["box"] = path_bundle.get("box")
            p = series["core_path"]
            analysis.details["공통 수급·돌파 경로"] = (
                f"{'활성' if p.get('active') else '대기'} · {p.get('stage','-')} · {p.get('reason','-')}"
            )

            # 수박은 내부 진행상태와 차트표시를 분리한다.
""",
"all-timeframe path enrichment")

# ---------- right analysis rows ----------
ui = ui.replace(
    'danta_names = ["패턴 점수", "핵심 진입 신호", "간단 이유",',
    'danta_names = ["패턴 점수", "핵심 진입 신호", "공통 수급·돌파 경로", "간단 이유",'
)
ui = ui.replace(
    'names = ["핵심 진입 신호", "간단 이유",',
    'names = ["핵심 진입 신호", "공통 수급·돌파 경로", "간단 이유",'
)
ui = ui.replace(
    '"상단 박스 안착", "파란점선", "화살표 신호"]',
    '"상단 박스 안착", "재돌파", "파란점선", "화살표 신호"]'
)
ui = ui.replace(
    'bowl_names = ["핵심 진입 신호", "간단 이유",',
    'bowl_names = ["핵심 진입 신호", "공통 수급·돌파 경로", "간단 이유",'
)

ui = once(ui,
'''                    "핵심 진입 신호": danta_analysis.details.get("핵심 진입 신호", "-"),
                    "간단 이유": dreason,
''',
'''                    "핵심 진입 신호": danta_analysis.details.get("핵심 진입 신호", "-"),
                    "공통 수급·돌파 경로": danta_analysis.details.get("공통 수급·돌파 경로", "-"),
                    "간단 이유": dreason,
''',
"danta common row map")

# ---------- reverse-swing settings UI ----------
ui = once(ui,
"""        self.sw_vol_ratio = self._dspin(1.0, 20.0, ss.volume_ratio, " 배")
""",
"""        self.sw_vol_ratio = self._dspin(1.0, 20.0, ss.volume_ratio, " 배")
""",
"volume widget retained")
ui = ui.replace('af.addRow("거래량 평균 대비", self.sw_vol_ratio)', 'af.addRow("거래량 평균 대비 (최소 300%)", self.sw_vol_ratio)')
ui = ui.replace('self.sw_acc_lookback = self._spin(20, 250, ss.accumulation_lookback)', 'self.sw_acc_lookback = self._spin(60, 112, ss.accumulation_lookback)')

box_start = ui.index('        box = QGroupBox("공구리(박스권)")')
box_end = ui.index('        blue = QGroupBox("파란점선")', box_start)
new_box_ui = r'''        box = QGroupBox("공구리(박스권) · 60~112봉 동적 탐지")
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
ui = ui[:box_start] + new_box_ui + ui[box_end:]

# ---------- settings persistence ----------
ui = once(ui,
"""        x.box_window = self.sw_box_window.value()
        x.box_width_pct = self.sw_box_width.value()
        x.breakout_buffer_pct = self.sw_breakout_buffer.value()
        x.acceptance_window = self.sw_accept_window.value()
        x.acceptance_min_closes = min(self.sw_accept_count.value(), x.acceptance_window)
        x.acceptance_tolerance_pct = self.sw_accept_tol.value()
""",
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
"persist dynamic box")

# ---------- preset ----------
preset_start = ui.index('        values = {\n', ui.index('    def apply_swing_preset'))
preset_end = ui.index('        }\n', preset_start) + len('        }\n')
new_values = r'''        values = {
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
ui = ui[:preset_start] + new_values + ui[preset_end:]
ui = ui.replace(
    '"PUMA 표준값 적용 · EMA112/224/448 · 매집 2회/20봉 · 공구리18/14% · 파란점선26/2.6/26"',
    '"PUMA 표준값 적용 · 거래량300% · 공구리60~112봉 · 눌림거래량≤55% · 재돌파300% · 파란점선26/2.6/26"'
)

# ---------- update note ----------
ui = ui.replace(
    "v2.0: 전략별 핵심 진입 신호를 명시하고 '현재 신호 아님' 대신 미충족 조건을 직접 표시. YTN형 기준봉 눌림은 독립 유효신호로 인정. 수박은 고확률 복합조건을 통과한 확정구간만 20봉당 1회 표시.",
    "v2.1: 모든 기법의 최상위 로직을 수급→전고점/박스상단 돌파→거래량감소 눌림→거래량동반 재돌파로 통합. 공구리는 60~112봉 동적 박스, 돌파/재돌파 거래량 300% 이상을 기본값으로 적용."
)

# ---------- chart ----------
chart = chart.replace(
    "'watermelon_stage','watermelon_score','watermelon_reason','watermelon_confirmed','watermelon_display'",
    "'watermelon_stage','watermelon_score','watermelon_reason','watermelon_confirmed','watermelon_display','path_breakout','path_pullback','path_rebreakout'"
)

# Make dynamic box label show actual range/period and extend top line through current bars.
old_box = """        # 공구리 박스
        box = self.series.get('box')
        if box and box.get('start',-1) < end and box.get('end',-1) >= start:
            bs = max(start, box['start']); be = min(end-1, box['end'])
            xs = x(bs-start)-4; xe = x(be-start)+4
            r = QRectF(xs, y(box['high']), xe-xs, y(box['low'])-y(box['high']))
            p.setPen(QPen(QColor('#f4ce48'),2,Qt.DashLine)); p.setBrush(QColor(244,206,72,28)); p.drawRect(r)
            p.setPen(QColor('#f4ce48')); p.drawText(int(xs+6), int(y(box['high'])-6), '공구리(박스권)')
"""
new_box = """        # 공구리 박스: 60~112봉 동적 탐지 결과.
        box = self.series.get('box')
        if box and box.get('start',-1) < end and box.get('end',-1) >= start:
            bs = max(start, box['start']); be = min(end-1, box['end'])
            xs = x(bs-start)-4; xe = x(be-start)+4
            r = QRectF(xs, y(box['high']), xe-xs, y(box['low'])-y(box['high']))
            p.setPen(QPen(QColor('#f4ce48'),2,Qt.DashLine)); p.setBrush(QColor(244,206,72,28)); p.drawRect(r)
            p.setPen(QColor('#f4ce48'))
            p.drawText(int(xs+6), int(y(box['high'])-6), f"공구리 {box.get('period','-')}봉")
            if box.get('breakout_idx', -1) >= 0:
                p.setPen(QPen(QColor('#f4ce48'), 1.6, Qt.DashLine))
                p.drawLine(QPointF(xe, y(box['high'])), QPointF(price_rect.right(), y(box['high'])))
                p.drawText(int(min(price_rect.right()-85, xe+6)), int(y(box['high'])-7), '돌파기준선')
"""
chart = once(chart, old_box, new_box, "dynamic box chart")

# Labels for the common path.
candle_loop_anchor = """            p.fillRect(
                QRectF(xx-cw/2,vol_rect.bottom()-vh,cw,vh),
                QColor(volume_col.red(),volume_col.green(),volume_col.blue(),185)
            )
"""
path_draw = candle_loop_anchor + r'''
            gi = start + i
            path_break = self.series.get('path_breakout', [])
            path_pull = self.series.get('path_pullback', [])
            path_rebreak = self.series.get('path_rebreakout', [])
            label = ''
            label_color = QColor('#ffffff')
            if isinstance(path_rebreak, list) and gi < len(path_rebreak) and path_rebreak[gi]:
                label = '재돌파'; label_color = QColor('#ffcf3d')
            elif isinstance(path_pull, list) and gi < len(path_pull) and path_pull[gi]:
                label = '눌림'; label_color = QColor('#62d98b')
            elif isinstance(path_break, list) and gi < len(path_break) and path_break[gi]:
                label = '돌파'; label_color = QColor('#ff6a6a')
            if label and n <= 180:
                p.setPen(label_color)
                p.setFont(QFont('Malgun Gothic', 8, QFont.Bold))
                p.drawText(int(xx-16), int(max(price_rect.top()+32, y(c['high'])-8)), label)
'''
chart = once(chart, candle_loop_anchor, path_draw, "path labels")

# ---------- updater ----------
updater = once(updater, 'CURRENT_VERSION = "2.0.0"', 'CURRENT_VERSION = "2.1.0"', "updater version")
updater = updater.replace("PUMA-STOCK-UPDATER/2.0", "PUMA-STOCK-UPDATER/2.1")

ui_path.write_text(ui, encoding="utf-8")
swing_path.write_text(swing, encoding="utf-8")
entry_path.write_text(entry, encoding="utf-8")
prob_path.write_text(prob, encoding="utf-8")
chart_path.write_text(chart, encoding="utf-8")
updater_path.write_text(updater, encoding="utf-8")
(pkg / "puma_trader" / "__init__.py").write_text('__version__ = "2.1.0"\n', encoding="utf-8")
print("PUMA v2.1 unified market-path patch applied")
