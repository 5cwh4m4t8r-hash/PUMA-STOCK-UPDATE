from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
pkg = ROOT / "work" / "PUMA_STOCK_PRO_v1.8"
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
ui = once(ui, 'self.setWindowTitle("PUMA STOCK PRO v1.8")', 'self.setWindowTitle("PUMA STOCK PRO v1.9")', "window version")
ui = once(ui, 'title = QLabel("🐆  PUMA STOCK PRO  v1.8")', 'title = QLabel("🐆  PUMA STOCK PRO  v1.9")', "header version")

# ---------- SwingSettings: expose a fixed operational preset ----------
swing = once(
    swing,
    "    accumulation_min_count: int = 2\n",
    "    accumulation_min_count: int = 2\n    accumulation_cluster_window: int = 20\n",
    "cluster window field",
)

# Use configured cluster window, and actually score/paint only confirmed accumulation.
swing = once(
    swing,
    "    acc_flags, acc_meta = accumulation_flags(candles, settings)\n",
    "    raw_acc_flags, acc_meta = accumulation_flags(candles, settings)\n    acc_flags = confirm_accumulation_flags(raw_acc_flags, acc_meta, settings.accumulation_cluster_window)\n",
    "confirmed accumulation in analyze",
)

# ---------- general breakout-pullback detector (captures YTN-like setup without hard-coding a ticker) ----------
analyze_anchor = "\n\ndef analyze(candles_raw: List[dict], settings: SwingSettings | None = None)"
pullback_func = r'''

def detect_breakout_pullback(candles: List[dict]) -> dict:
    """Detect a strong 기준봉 -> high-volume shakeout -> contracting pullback.

    This is ticker-agnostic. It is designed to recognize patterns like:
    quiet base -> +18% or stronger breakout close -> 2~6 bars of pullback ->
    price still above the breakout candle open/base while volume contracts.
    """
    n = len(candles)
    default = {
        'confirmed': False, 'quality': 0, 'impulse_index': -1,
        'impulse_change_pct': 0.0, 'bars_after': 0, 'volume_contraction': 1.0,
        'current_above_impulse_open': False, 'retrace_pct': 0.0, 'reason': '미확인',
    }
    if n < 25:
        return default

    vols = [float(c['volume']) for c in candles]
    candidates = []
    start = max(20, n - 12)
    for i in range(start, n - 1):
        prev_close = float(candles[i-1]['close'])
        c = candles[i]
        if prev_close <= 0:
            continue
        chg = (float(c['close']) / prev_close - 1.0) * 100.0
        base_vol = mean(vols[max(0, i-20):i]) if i > 0 else 0.0
        vol_ratio = (float(c['volume']) / base_vol) if base_vol else 0.0
        strong_close = float(c['close']) >= float(c['high']) * 0.90
        if chg >= 18.0 and vol_ratio >= 3.0 and strong_close:
            candidates.append((i, chg, vol_ratio))

    if not candidates:
        return default

    i, chg, vol_ratio = candidates[-1]
    bars_after = n - 1 - i
    if not (2 <= bars_after <= 6):
        return default

    impulse = candles[i]
    after = candles[i+1:]
    current = candles[-1]
    peak_high = max(float(c['high']) for c in after) if after else float(impulse['high'])
    peak_vol = max(float(c['volume']) for c in ([impulse] + after))
    current_vol = float(current['volume'])
    contraction = current_vol / peak_vol if peak_vol else 1.0

    impulse_open = float(impulse['open'])
    current_close = float(current['close'])
    above_open = current_close >= impulse_open * 1.03
    retrace = ((peak_high - current_close) / peak_high * 100.0) if peak_high else 0.0
    controlled_pullback = 5.0 <= retrace <= 35.0
    volume_calm = contraction <= 0.45

    quality = 0
    quality += 30
    if vol_ratio >= 8.0:
        quality += 15
    elif vol_ratio >= 5.0:
        quality += 10
    if above_open:
        quality += 25
    if controlled_pullback:
        quality += 15
    if volume_calm:
        quality += 20
    quality = min(100, quality)

    confirmed = bool(above_open and controlled_pullback and volume_calm and quality >= 65)
    reason = (
        f"기준봉 {chg:+.1f}% · {bars_after}봉 눌림 · "
        f"거래량 {contraction*100:.0f}%로 감소 · "
        f"기준봉 시가 {'상회' if above_open else '이탈'}"
    )
    return {
        'confirmed': confirmed,
        'quality': quality,
        'impulse_index': i,
        'impulse_change_pct': chg,
        'bars_after': bars_after,
        'volume_contraction': contraction,
        'current_above_impulse_open': above_open,
        'retrace_pct': retrace,
        'reason': reason,
    }

''' + analyze_anchor
swing = once(swing, analyze_anchor, pullback_func, "pullback detector")

# Detect and include in score/details. This is a separate setup factor, not a fake accumulation candle.
swing = once(
    swing,
    "    bnear = bool(bval and abs(bdist) <= settings.blue_near_pct)\n\n    stage = '장기 역배열 확인'\n",
    "    bnear = bool(bval and abs(bdist) <= settings.blue_near_pct)\n    pullback = detect_breakout_pullback(candles)\n\n    stage = '장기 역배열 확인'\n",
    "pullback call",
)
swing = once(
    swing,
    "    if bnear:\n        score += 10\n        if accepted:\n            stage = '최종 신호(수박/화살표) 수식 대기'\n",
    "    if bnear:\n        score += 10\n        if accepted:\n            stage = '최종 신호(수박/화살표) 수식 대기'\n    if pullback.get('confirmed'):\n        score += 15\n        if not accepted:\n            stage = '기준봉 후 거래량 감소 눌림 · 진입구간 관찰'\n    score = min(100, score)\n",
    "pullback score",
)
swing = once(
    swing,
    "    if bnear:\n        reasons.append(f'파란점선 근접 {bdist:+.2f}%')\n",
    "    if bnear:\n        reasons.append(f'파란점선 근접 {bdist:+.2f}%')\n    if pullback.get('confirmed'):\n        reasons.append('기준봉 후 거래량 감소 눌림 확인')\n",
    "pullback reason",
)
swing = once(
    swing,
    "        '화살표 신호': arrow_reason,\n",
    "        '화살표 신호': arrow_reason,\n        '기준봉 눌림': (f\"확인 · {pullback['reason']} · 품질 {pullback['quality']}/100\" if pullback.get('confirmed') else f\"미확인 · {pullback.get('reason','-')}\"),\n",
    "pullback detail",
)
swing = once(
    swing,
    "        'box': box,\n",
    "        'box': box,\n        'pullback': pullback,\n",
    "pullback series",
)

# ---------- reverse-swing settings UI: show all operative values ----------
ui = once(
    ui,
    'names = ["간단 이유", "PUMA 수박근사", "유사구간 확률", "PUMA 판단", "장기 EMA 역배열", "매집봉/구간", "공구리(박스권)", "박스 상단 돌파", "상단 박스 안착", "파란점선", "화살표 신호"]',
    'names = ["간단 이유", "PUMA 수박근사", "유사구간 확률", "PUMA 판단", "기준봉 눌림", "장기 EMA 역배열", "매집봉/구간", "공구리(박스권)", "박스 상단 돌파", "상단 박스 안착", "파란점선", "화살표 신호"]',
    "analysis pullback row",
)

acc_old = '''        acc = QGroupBox("매집봉 기준")
        af = QFormLayout(acc)
        self.sw_vol_ratio = self._dspin(1.0, 20.0, ss.volume_ratio, " 배")
        self.sw_wick_ratio = self._dspin(0.1, 0.9, ss.upper_wick_ratio)
        self.sw_bear_body = self._dspin(0.2, 0.95, ss.bearish_body_ratio)
        self.sw_acc_lookback = self._spin(20, 250, ss.accumulation_lookback)
        af.addRow("거래량 평균 대비", self.sw_vol_ratio)
        af.addRow("긴 윗꼬리 / 전체폭 ≥", self.sw_wick_ratio)
        af.addRow("장대음봉 몸통 / 전체폭 ≥", self.sw_bear_body)
        af.addRow("매집 Lookback", self.sw_acc_lookback)
        sv.addWidget(acc)
'''
acc_new = '''        ema_box = QGroupBox("장기 EMA · 고정 기준")
        ef = QFormLayout(ema_box)
        ef.addRow("중장기 기준", QLabel("EMA 112 / 224 / 448"))
        ef.addRow("역배열", QLabel("112 < 224 < 448"))
        sv.addWidget(ema_box)

        acc = QGroupBox("매집봉/매집구간 · PUMA 표준값")
        af = QFormLayout(acc)
        self.sw_vol_period = self._spin(5, 60, ss.volume_period)
        self.sw_vol_ratio = self._dspin(1.0, 20.0, ss.volume_ratio, " 배")
        self.sw_wick_ratio = self._dspin(0.1, 0.9, ss.upper_wick_ratio)
        self.sw_wick_body = self._dspin(0.5, 5.0, max(ss.upper_wick_vs_body, 1.35))
        self.sw_bear_body = self._dspin(0.2, 0.95, ss.bearish_body_ratio)
        self.sw_acc_lookback = self._spin(20, 250, ss.accumulation_lookback)
        self.sw_acc_min = self._spin(2, 6, max(2, ss.accumulation_min_count))
        self.sw_acc_cluster = self._spin(5, 60, ss.accumulation_cluster_window)
        af.addRow("거래량 평균 기간", self.sw_vol_period)
        af.addRow("거래량 평균 대비", self.sw_vol_ratio)
        af.addRow("긴 윗꼬리 / 전체폭 ≥", self.sw_wick_ratio)
        af.addRow("윗꼬리 / 몸통 ≥", self.sw_wick_body)
        af.addRow("장대음봉 몸통 / 전체폭 ≥", self.sw_bear_body)
        af.addRow("매집 Lookback", self.sw_acc_lookback)
        af.addRow("확정 최소 후보 수", self.sw_acc_min)
        af.addRow("후보 반복 간격(봉)", self.sw_acc_cluster)
        sv.addWidget(acc)
'''
ui = once(ui, acc_old, acc_new, "expanded accumulation controls")

box_old = '''        self.sw_box_window = self._spin(5, 60, ss.box_window)
        self.sw_box_width = self._dspin(2, 30, ss.box_width_pct, " %")
        self.sw_accept_window = self._spin(3, 20, ss.acceptance_window)
        self.sw_accept_count = self._spin(2, 15, ss.acceptance_min_closes)
        bf.addRow("박스 판정 기간", self.sw_box_window)
        bf.addRow("박스 최대 폭", self.sw_box_width)
        bf.addRow("돌파 후 확인봉", self.sw_accept_window)
        bf.addRow("상단 위 종가 최소", self.sw_accept_count)
'''
box_new = '''        self.sw_box_window = self._spin(5, 60, ss.box_window)
        self.sw_box_width = self._dspin(2, 30, ss.box_width_pct, " %")
        self.sw_breakout_buffer = self._dspin(0.0, 5.0, ss.breakout_buffer_pct, " %")
        self.sw_accept_window = self._spin(3, 20, ss.acceptance_window)
        self.sw_accept_count = self._spin(2, 15, ss.acceptance_min_closes)
        self.sw_accept_tol = self._dspin(0.0, 5.0, ss.acceptance_tolerance_pct, " %")
        bf.addRow("박스 판정 기간", self.sw_box_window)
        bf.addRow("박스 최대 폭", self.sw_box_width)
        bf.addRow("상단 돌파 버퍼", self.sw_breakout_buffer)
        bf.addRow("돌파 후 확인봉", self.sw_accept_window)
        bf.addRow("상단 위 종가 최소", self.sw_accept_count)
        bf.addRow("안착 허용오차", self.sw_accept_tol)
'''
ui = once(ui, box_old, box_new, "expanded box controls")

# Add one-click exact preset.
preset_anchor = '''        apply_swing = QPushButton("💾 저장 + 현재 종목 다시 분석")
'''
preset_block = '''        preset = QPushButton("↺ PUMA 표준값 적용")
        preset.clicked.connect(self.apply_swing_preset)
        sv.addWidget(preset)

''' + preset_anchor
ui = once(ui, preset_anchor, preset_block, "preset button")

# Persist all fields.
ui = once(
    ui,
    '''        x.volume_ratio = self.sw_vol_ratio.value()
        x.upper_wick_ratio = self.sw_wick_ratio.value()
        x.bearish_body_ratio = self.sw_bear_body.value()
        x.accumulation_lookback = self.sw_acc_lookback.value()
        x.box_window = self.sw_box_window.value()
        x.box_width_pct = self.sw_box_width.value()
        x.acceptance_window = self.sw_accept_window.value()
        x.acceptance_min_closes = min(self.sw_accept_count.value(), x.acceptance_window)
''',
    '''        x.volume_period = self.sw_vol_period.value()
        x.volume_ratio = self.sw_vol_ratio.value()
        x.upper_wick_ratio = self.sw_wick_ratio.value()
        x.upper_wick_vs_body = self.sw_wick_body.value()
        x.bearish_body_ratio = self.sw_bear_body.value()
        x.accumulation_lookback = self.sw_acc_lookback.value()
        x.accumulation_min_count = max(2, self.sw_acc_min.value())
        x.accumulation_cluster_window = self.sw_acc_cluster.value()
        x.box_window = self.sw_box_window.value()
        x.box_width_pct = self.sw_box_width.value()
        x.breakout_buffer_pct = self.sw_breakout_buffer.value()
        x.acceptance_window = self.sw_accept_window.value()
        x.acceptance_min_closes = min(self.sw_accept_count.value(), x.acceptance_window)
        x.acceptance_tolerance_pct = self.sw_accept_tol.value()
''',
    "save all swing settings",
)

# Preset method inserted before save_swing_and_reanalyze.
method_anchor = "    def save_swing_and_reanalyze(self):\n"
preset_method = r'''    def apply_swing_preset(self):
        """PUMA operational defaults, not a claimed proprietary formula."""
        values = {
            "sw_vol_period": 20,
            "sw_vol_ratio": 2.0,
            "sw_wick_ratio": 0.42,
            "sw_wick_body": 1.35,
            "sw_bear_body": 0.58,
            "sw_acc_lookback": 90,
            "sw_acc_min": 2,
            "sw_acc_cluster": 20,
            "sw_box_window": 18,
            "sw_box_width": 14.0,
            "sw_breakout_buffer": 0.2,
            "sw_accept_window": 8,
            "sw_accept_count": 4,
            "sw_accept_tol": 1.0,
            "sw_blue_period": 26,
            "sw_blue_dev": 2.6,
            "sw_blue_shift": 26,
            "sw_blue_near": 3.0,
        }
        for name, value in values.items():
            widget = getattr(self, name, None)
            if widget is not None:
                widget.setValue(value)
        self.focus_swing_settings_status.setText(
            "PUMA 표준값 적용 · EMA112/224/448 · 매집 2회/20봉 · 공구리18/14% · 파란점선26/2.6/26"
        )

''' + method_anchor
ui = once(ui, method_anchor, preset_method, "preset method")

ui = ui.replace(
    "v1.8: 매집봉 오탐 감소를 위해 단독 신호를 후보로 강등하고 20봉 내 2회 이상 반복 시에만 매집확정. 하단 전략3종은 말줄임/툴팁을 제거하고 카드 내부 세로 스크롤로 전체 분석을 확인하도록 변경.",
    "v1.9: YTN형 급등 기준봉-거래량 감소 눌림을 일반 패턴으로 추가. 영웅문 화면에 맞춰 EMA5/20/60/112/224/448 색·굵기 재정리, 224 검정선/검정화살표는 흰 외곽선으로 대비 강화. 역매공파 설정값을 전부 노출하고 PUMA 표준값 버튼 추가."
)

# ---------- chart: MA colors / widths based on user's HTS visual ----------
chart = once(
    chart,
    "('candles','acc_flags','acc_meta','box','watermelon','watermelon_stage','watermelon_score','watermelon_reason','cloud_a','cloud_b','signal_pink','signal_blue','signal_red','signal_sar','signal_bb40_22')",
    "('candles','acc_flags','acc_meta','box','watermelon','watermelon_stage','watermelon_score','watermelon_reason','cloud_a','cloud_b','signal_pink','signal_blue','signal_red','signal_black','signal_sar','signal_bb40_22')",
    "exclude black signal",
)

sig_old = '''        sig_defs = [
            ('signal_pink', QColor('#ff33cc')),
            ('signal_blue', QColor('#1746ff')),
            ('signal_red', QColor('#ff2e2e')),
        ]
'''
sig_new = '''        sig_defs = [
            ('signal_pink', QColor('#ff33cc')),
            ('signal_blue', QColor('#1746ff')),
            ('signal_red', QColor('#ff2e2e')),
            # 검정 화살표는 별도 수식이 연결될 경우 사용.
            # 어두운 PUMA 배경에서는 흰 외곽선을 먼저 그려 영웅문 회색배경 수준의 대비를 확보한다.
            ('signal_black', QColor('#050505')),
        ]
'''
chart = once(chart, sig_old, sig_new, "black signal style")

arrow_draw_old = '''                p.setPen(QPen(sig_color, 2))
                p.drawLine(QPointF(xx, base + 6), QPointF(xx, apex + 4))
                p.setBrush(sig_color)
                tri = QPolygonF([
                    QPointF(xx, apex),
                    QPointF(xx - 5, apex + 7),
                    QPointF(xx + 5, apex + 7),
                ])
                p.drawPolygon(tri)
                p.setBrush(Qt.NoBrush)
'''
arrow_draw_new = '''                tri_outer = QPolygonF([
                    QPointF(xx, apex-2),
                    QPointF(xx - 7, apex + 9),
                    QPointF(xx + 7, apex + 9),
                ])
                p.setPen(QPen(QColor('#f4f7fb'), 2.2))
                p.setBrush(QColor('#f4f7fb'))
                p.drawPolygon(tri_outer)
                p.drawLine(QPointF(xx, base + 7), QPointF(xx, apex + 4))

                tri = QPolygonF([
                    QPointF(xx, apex),
                    QPointF(xx - 5, apex + 7),
                    QPointF(xx + 5, apex + 7),
                ])
                p.setPen(QPen(sig_color, 1.6))
                p.setBrush(sig_color)
                p.drawPolygon(tri)
                p.drawLine(QPointF(xx, base + 6), QPointF(xx, apex + 4))
                p.setBrush(Qt.NoBrush)
'''
chart = once(chart, arrow_draw_old, arrow_draw_new, "arrow halo")

colors_old = '''        colors={
            'ema5':'#ffd400','ema20':'#f2a900','ema60':'#27d36b','ema112':'#3d9cff',
            'ema224':'#c26cff','ema448':'#8f6b4b','blue':'#2e7cff','kijun':'#ffffff'
        }
        widths={'blue':3.0,'ema5':2.8,'kijun':5.0}
        styles={'blue':Qt.DotLine}
        if 'ema5' in line_keys:
            line_keys = [k for k in line_keys if k != 'ema5'] + ['ema5']
        for key in line_keys:
            col = QColor(colors.get(key, '#9bb8d1'))
            self._draw_series(p, self.series[key], start, end, x, y, col, widths.get(key,1.5), styles.get(key,Qt.SolidLine))
'''
colors_new = '''        # 사용자 영웅문 화면의 시각 체계를 PUMA 어두운 배경에 맞게 재현.
        # 5=노랑, 20=빨강, 60=초록, 112=갈색/주황, 224=검정 굵게, 448=회색 점선.
        colors={
            'ema5':'#ffd21f',
            'ema20':'#ff3434',
            'ema60':'#00b85a',
            'ema112':'#b85a18',
            'ema224':'#050505',
            'ema448':'#9aa0a6',
            'blue':'#1f49ff',
            'kijun':'#f2e7a3'
        }
        widths={
            'ema5':2.3,'ema20':2.1,'ema60':2.1,'ema112':2.5,
            'ema224':3.2,'ema448':1.8,'blue':3.2,'kijun':5.0
        }
        styles={'blue':Qt.DotLine,'ema448':Qt.DashLine}
        priority = ['ema448','ema224','ema112','ema60','ema20','ema5','blue','kijun']
        ordered = [k for k in priority if k in line_keys] + [k for k in line_keys if k not in priority]
        for key in ordered:
            col = QColor(colors.get(key, '#9bb8d1'))
            if key == 'ema224':
                # 영웅문에서는 회색 배경이라 검정 224선이 잘 보인다.
                # PUMA 검정 배경에서는 밝은 외곽선을 먼저 깔고 검정 코어를 그린다.
                self._draw_series(p, self.series[key], start, end, x, y, QColor('#d9dde3'), 5.0, Qt.SolidLine)
            if key == 'kijun':
                self._draw_series(p, self.series[key], start, end, x, y, QColor('#b71c1c'), 1.0, Qt.SolidLine)
            self._draw_series(p, self.series[key], start, end, x, y, col, widths.get(key,1.5), styles.get(key,Qt.SolidLine))
'''
chart = once(chart, colors_old, colors_new, "MA visual system")

# Watermelon legend explains shapes in-place.
chart = once(
    chart,
    "p.drawText(int(price_rect.left()+150), int(price_rect.top()+27), '● PUMA 수박근사(1~3단)')",
    "p.drawText(int(price_rect.left()+150), int(price_rect.top()+27), '● 수박: 작은껍질=접근 · 붉은속=안착 · 금테=강화')",
    "watermelon shape legend",
)

# ---------- updater ----------
updater = once(updater, 'CURRENT_VERSION = "1.8.0"', 'CURRENT_VERSION = "1.9.0"', "updater version")
updater = updater.replace("PUMA-STOCK-UPDATER/1.8", "PUMA-STOCK-UPDATER/1.9")

ui_path.write_text(ui, encoding="utf-8")
swing_path.write_text(swing, encoding="utf-8")
chart_path.write_text(chart, encoding="utf-8")
updater_path.write_text(updater, encoding="utf-8")
(pkg / "puma_trader" / "__init__.py").write_text('__version__ = "1.9.0"\n', encoding="utf-8")
print("PUMA v1.9 visual/swing/pullback patch applied")
