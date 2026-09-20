from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
pkg = ROOT / "work" / "PUMA_STOCK_PRO_v1.5"
ui_path = pkg / "puma_trader" / "ui.py"
chart_path = pkg / "puma_trader" / "swing_chart.py"
swing_path = pkg / "puma_trader" / "swing.py"
danta_path = pkg / "puma_trader" / "danta.py"
bowl_path = pkg / "puma_trader" / "bowl.py"
updater_path = pkg / "puma_trader" / "updater.py"

ui = ui_path.read_text(encoding="utf-8")
chart = chart_path.read_text(encoding="utf-8")
swing = swing_path.read_text(encoding="utf-8")
danta = danta_path.read_text(encoding="utf-8")
bowl = bowl_path.read_text(encoding="utf-8")
updater = updater_path.read_text(encoding="utf-8")

def once(text, old, new, label):
    if old not in text:
        raise RuntimeError(f"target not found: {label}")
    return text.replace(old, new, 1)

# ---------- imports / version ----------
ui = once(ui, "from .classification import classify_scores\n",
          "from .classification import classify_scores\nfrom .watermelon_proxy import build_puma_watermelon\nfrom .probability import estimate_from_flags, strategy_flags\n",
          "ui analytics imports")
ui = once(ui, 'self.setWindowTitle("PUMA STOCK PRO v1.5")', 'self.setWindowTitle("PUMA STOCK PRO v1.6")', "window version")
ui = once(ui, 'title = QLabel("🐆  PUMA STOCK PRO  v1.5")', 'title = QLabel("🐆  PUMA STOCK PRO  v1.6")', "header version")

# ---------- eliminate ALL wheel-driven combo value changes ----------
insert_anchor = "\n\nclass NumericComboBox(QComboBox):\n"
no_wheel_class = r'''

class NoWheelComboBox(QComboBox):
    """Dropdown-only combo: mouse wheel never changes the current value."""
    def wheelEvent(self, event):
        event.ignore()

''' + insert_anchor
ui = once(ui, insert_anchor, no_wheel_class, "NoWheelComboBox")
ui = ui.replace("class NumericComboBox(QComboBox):", "class NumericComboBox(NoWheelComboBox):")
ui = ui.replace("class TimeComboBox(QComboBox):", "class TimeComboBox(NoWheelComboBox):")
ui = ui.replace("QComboBox()", "NoWheelComboBox()")

# ---------- analysis fields ----------
ui = ui.replace(
    'danta_names = ["패턴 점수", "간단 이유", "화살표 신호", "검색 시간", "PUMA 기준선(26)", "EMA 5·20·60", "현재 5분봉 거래량", "최근 고점 돌파", "눌림 지지"]',
    'danta_names = ["패턴 점수", "간단 이유", "PUMA 수박근사", "유사구간 확률", "PUMA 판단", "화살표 신호", "검색 시간", "PUMA 기준선(26)", "EMA 5·20·60", "현재 5분봉 거래량", "최근 고점 돌파", "눌림 지지"]'
)
ui = ui.replace(
    'names = ["간단 이유", "장기 EMA 역배열", "매집봉/구간", "공구리(박스권)", "박스 상단 돌파", "상단 박스 안착", "파란점선", "화살표 신호"]',
    'names = ["간단 이유", "PUMA 수박근사", "유사구간 확률", "PUMA 판단", "장기 EMA 역배열", "매집봉/구간", "공구리(박스권)", "박스 상단 돌파", "상단 박스 안착", "파란점선", "화살표 신호"]'
)
ui = ui.replace(
    'bowl_names = ["간단 이유", "장기 224EMA 아래", "224EMA 돌파", "224EMA 위 안착", "눌림/지지", "224EMA 거리", "화살표 신호"]',
    'bowl_names = ["간단 이유", "PUMA 수박근사", "유사구간 확률", "PUMA 판단", "장기 224EMA 아래", "224EMA 돌파", "224EMA 위 안착", "눌림/지지", "224EMA 거리", "화살표 신호"]'
)

# ---------- helper: enrich series with proxy + empirical probability ----------
helper_anchor = """    def _sync_selected_stock_everywhere(self):
"""
helper = r'''    def _enrich_setup_stats(self, analysis, series: dict, strategy: str):
        if not analysis or not series or not series.get("candles"):
            return analysis, series
        try:
            wm = build_puma_watermelon(series["candles"], series)
            series.update(wm)
            stages = wm.get("watermelon_stage", [])
            scores = wm.get("watermelon_score", [])
            reasons = wm.get("watermelon_reason", [])
            stage = int(stages[-1]) if stages else 0
            wscore = int(scores[-1]) if scores else 0
            wreason = str(reasons[-1]) if reasons else "조건 미충족"
            analysis.details["PUMA 수박근사"] = f"{stage}단계 · {wscore}/100 · {wreason}"

            flags = strategy_flags(series, strategy)
            if strategy == "DAY":
                horizon = 12   # 5분봉 1시간
            elif strategy == "SWING":
                horizon = 20   # 20 거래일
            else:
                horizon = 60   # 60 거래일

            tp = float(self.focus_tp.value()) if hasattr(self, "focus_tp") else float(self.settings.take_profit_pct)
            sl = abs(float(self.focus_sl.value())) if hasattr(self, "focus_sl") else abs(float(self.settings.stop_loss_pct))
            current_active = bool(flags[-1]) if flags else False
            if strategy == "DAY":
                current_active = current_active and bool(getattr(analysis, "in_time", False))

            est = estimate_from_flags(
                series["candles"],
                flags,
                horizon_bars=horizon,
                tp_pct=tp,
                sl_pct=sl,
                current_score=int(getattr(analysis, "score", 0) or 0),
                current_active=current_active,
            )
            analysis.details["유사구간 확률"] = est.summary()
            analysis.details["PUMA 판단"] = f"{est.verdict} · {est.reason}"
            analysis.details["확률 기준"] = f"과거 동일계열 신호 · TP {tp:.1f}% / SL {sl:.1f}% · {horizon}봉"
        except Exception as exc:
            analysis.details["PUMA 수박근사"] = f"계산 실패: {exc}"
            analysis.details["유사구간 확률"] = "계산 불가"
            analysis.details["PUMA 판단"] = "판단 유보"
        return analysis, series

''' + helper_anchor
ui = once(ui, helper_anchor, helper, "setup stats helper")

# ---------- detailed Danta cache enrichment ----------
ui = once(
    ui,
    """            series = dict(series)
            self.danta_analysis = result
            self.danta_series = series
""",
    """            series = dict(series)
            result, series = self._enrich_setup_stats(result, series, "DAY")
            self.danta_analysis = result
            self.danta_series = series
""",
    "detail danta enrichment",
)

# ---------- main refresh enrichment ----------
ui = once(
    ui,
    """                    swing_analysis, swing_series = analyze_swing(daily_rows, self._swing_settings_from_ui())
                    bowl_analysis, _ = analyze_bowl(daily_rows, self.bowl_settings)
                    swing_series = dict(swing_series)
                    self.focus_daily_analysis = swing_analysis
                    self.focus_daily_series = swing_series
                    self.focus_bowl_analysis = bowl_analysis
""",
    """                    swing_analysis, swing_series = analyze_swing(daily_rows, self._swing_settings_from_ui())
                    bowl_analysis, bowl_series = analyze_bowl(daily_rows, self.bowl_settings)
                    swing_series = dict(swing_series)
                    bowl_series = dict(bowl_series)
                    swing_analysis, swing_series = self._enrich_setup_stats(swing_analysis, swing_series, "SWING")
                    bowl_analysis, bowl_series = self._enrich_setup_stats(bowl_analysis, bowl_series, "LONG")
                    self.focus_daily_analysis = swing_analysis
                    self.focus_daily_series = swing_series
                    self.focus_bowl_analysis = bowl_analysis
""",
    "daily enrichment",
)
ui = once(
    ui,
    """                    danta_series = dict(danta_series)
                    self.focus_danta_analysis = danta_analysis
                    self.focus_danta_series = danta_series
""",
    """                    danta_series = dict(danta_series)
                    danta_analysis, danta_series = self._enrich_setup_stats(danta_analysis, danta_series, "DAY")
                    self.focus_danta_analysis = danta_analysis
                    self.focus_danta_series = danta_series
""",
    "main danta enrichment",
)

# ---------- date refresh enrichment ----------
ui = once(
    ui,
    """            series = dict(series)
            self.focus_danta_analysis = result
            self.focus_danta_series = series
""",
    """            series = dict(series)
            result, series = self._enrich_setup_stats(result, series, "DAY")
            self.focus_danta_analysis = result
            self.focus_danta_series = series
""",
    "date danta enrichment",
)

# ---------- analysis renderer maps + judgment in summary cards ----------
ui = once(
    ui,
    '''                    "간단 이유": dreason,
                    "화살표 신호": danta_analysis.details.get("화살표 신호", "현재봉 화살표 없음"),
''',
    '''                    "간단 이유": dreason,
                    "PUMA 수박근사": danta_analysis.details.get("PUMA 수박근사", "-"),
                    "유사구간 확률": danta_analysis.details.get("유사구간 확률", "-"),
                    "PUMA 판단": danta_analysis.details.get("PUMA 판단", "-"),
                    "화살표 신호": danta_analysis.details.get("화살표 신호", "현재봉 화살표 없음"),
''',
    "danta stat map",
)

ui = once(
    ui,
    '''            self.focus_danta_signal.setText(
                f"단타 DAY · 5분봉\\n{danta_analysis.stage} · {danta_analysis.score}/100\\n이유: {dreason}"
            )
''',
    '''            djudge = danta_analysis.details.get("PUMA 판단", "판단 유보")
            dprob = danta_analysis.details.get("유사구간 확률", "-")
            self.focus_danta_signal.setText(
                f"단타 DAY · 5분봉\\n{danta_analysis.stage} · {danta_analysis.score}/100 · {dprob}\\n판단: {djudge}\\n이유: {dreason}"
            )
''',
    "danta card judgment",
)
ui = once(
    ui,
    '''            self.focus_swing_signal.setText(
                f"역매공파 SWING\\n{swing_analysis.stage} · {swing_analysis.score}/100\\n이유: {sreason}"
            )
''',
    '''            sjudge = swing_analysis.details.get("PUMA 판단", "판단 유보")
            sprob = swing_analysis.details.get("유사구간 확률", "-")
            self.focus_swing_signal.setText(
                f"역매공파 SWING\\n{swing_analysis.stage} · {swing_analysis.score}/100 · {sprob}\\n판단: {sjudge}\\n이유: {sreason}"
            )
''',
    "swing card judgment",
)
ui = once(
    ui,
    '''            self.focus_bowl_signal.setText(
                f"밥그릇 3번 LONG\\n{bowl_analysis.stage} · {bowl_analysis.score}/100\\n이유: {breason}"
            )
''',
    '''            bjudge = bowl_analysis.details.get("PUMA 판단", "판단 유보")
            bprob = bowl_analysis.details.get("유사구간 확률", "-")
            self.focus_bowl_signal.setText(
                f"밥그릇 3번 LONG\\n{bowl_analysis.stage} · {bowl_analysis.score}/100 · {bprob}\\n판단: {bjudge}\\n이유: {breason}"
            )
''',
    "bowl card judgment",
)

# ---------- update note ----------
ui = ui.replace(
    "v1.5: 사용자 영웅문 화살표 3종을 수식 그대로 반영. 분홍/파랑/빨강 신호를 일봉·5분봉 차트에 색상별 매수 화살표로 표시.",
    "v1.6: 공개 차트/강의 특징을 바탕으로 PUMA 수박근사 1~3단계 추가, 과거 유사신호 TP/SL 적중률과 PUMA 진입판단 표시, 모든 콤보박스 마우스휠 값변경 차단."
)

# ---------- analyzer modules: add proxy series/details ----------
for name, text in (("danta", danta), ("swing", swing), ("bowl", bowl)):
    if name == "danta":
        text = once(text, "from .signals import build_arrow_signals, latest_signal_reason\n",
                    "from .signals import build_arrow_signals, latest_signal_reason\nfrom .watermelon_proxy import build_puma_watermelon\n",
                    "danta proxy import")
        text = once(text,
                    "    series.update(arrow_series)\n    return DantaAnalysis(\n",
                    "    series.update(arrow_series)\n    series.update(build_puma_watermelon(candles, arrow_series))\n    return DantaAnalysis(\n",
                    "danta proxy series")
        danta = text
    elif name == "swing":
        text = once(text, "from .signals import build_arrow_signals, latest_signal_reason\n",
                    "from .signals import build_arrow_signals, latest_signal_reason\nfrom .watermelon_proxy import build_puma_watermelon\n",
                    "swing proxy import")
        text = once(text,
                    "    series.update(arrow_series)\n    return analysis, series\n",
                    "    series.update(arrow_series)\n    series.update(build_puma_watermelon(candles, arrow_series))\n    wm_stage = series.get('watermelon_stage', [0])[-1] if series.get('watermelon_stage') else 0\n    wm_score = series.get('watermelon_score', [0])[-1] if series.get('watermelon_score') else 0\n    wm_reason = series.get('watermelon_reason', ['-'])[-1] if series.get('watermelon_reason') else '-'\n    analysis.details['PUMA 수박근사'] = f'{wm_stage}단계 · {wm_score}/100 · {wm_reason}'\n    return analysis, series\n",
                    "swing proxy series")
        swing = text
    else:
        text = once(text, "from .signals import build_arrow_signals, latest_signal_reason\n",
                    "from .signals import build_arrow_signals, latest_signal_reason\nfrom .watermelon_proxy import build_puma_watermelon\n",
                    "bowl proxy import")
        text = once(text,
                    "    series.update(arrow_series)\n    return result, series\n",
                    "    series.update(arrow_series)\n    series.update(build_puma_watermelon(candles, arrow_series))\n    wm_stage = series.get('watermelon_stage', [0])[-1] if series.get('watermelon_stage') else 0\n    wm_score = series.get('watermelon_score', [0])[-1] if series.get('watermelon_score') else 0\n    wm_reason = series.get('watermelon_reason', ['-'])[-1] if series.get('watermelon_reason') else '-'\n    result.details['PUMA 수박근사'] = f'{wm_stage}단계 · {wm_score}/100 · {wm_reason}'\n    return result, series\n",
                    "bowl proxy series")
        bowl = text

# ---------- chart: PUMA watermelon approximation as actual watermelon markers ----------
chart = once(
    chart,
    "        vol_h = 76\n        bottom = 42\n        price_rect = QRectF(left, top, self.width()-left-right, self.height()-top-bottom-vol_h)\n        vol_rect = QRectF(left, price_rect.bottom()+7, price_rect.width(), vol_h-10)\n",
    "        vol_h = 70\n        watermelon_h = 22\n        bottom = 42\n        price_rect = QRectF(left, top, self.width()-left-right, self.height()-top-bottom-vol_h-watermelon_h)\n        watermelon_rect = QRectF(left, price_rect.bottom()+3, price_rect.width(), watermelon_h)\n        vol_rect = QRectF(left, watermelon_rect.bottom()+3, price_rect.width(), vol_h-10)\n",
    "watermelon chart geometry",
)
chart = once(
    chart,
    "        line_keys = [k for k in self.series.keys() if k not in ('candles','acc_flags','acc_meta','box','watermelon','cloud_a','cloud_b','signal_pink','signal_blue','signal_red','signal_sar','signal_bb40_22') and isinstance(self.series.get(k), list)]\n",
    "        line_keys = [k for k in self.series.keys() if k not in ('candles','acc_flags','acc_meta','box','watermelon','watermelon_stage','watermelon_score','watermelon_reason','cloud_a','cloud_b','signal_pink','signal_blue','signal_red','signal_sar','signal_bb40_22') and isinstance(self.series.get(k), list)]\n",
    "exclude proxy arrays",
)
chart = chart.replace("price_rect.height()+vol_h)", "price_rect.height()+vol_h+watermelon_h)")
chart = chart.replace("QPointF(xx, vol_rect.bottom()))", "QPointF(xx, vol_rect.bottom()))")  # keep explicit

arrow_anchor = """        # 사용자 영웅문 매수 화살표 3종.
"""
wm_draw = r'''        # PUMA 수박근사: 단순 초록/빨강 막대가 아니라 1~3단계 수박 마커로 표시.
        # 원본 비공개 수식 복제가 아니라 공개 차트/강의에서 관찰되는
        # 장기이평 수렴 -> 224 돌파/안착 -> 눌림/거래량/화살표 강화 흐름을 시각화한다.
        wm = self.series.get('watermelon_stage', [])
        if isinstance(wm, list) and wm:
            p.setFont(QFont('Malgun Gothic', 7, QFont.Bold))
            p.setPen(QColor('#83a1ba'))
            p.drawText(5, int(watermelon_rect.center().y()+3), 'PUMA수박')
            prev = 0
            for i, stage in enumerate(wm[start:end]):
                try:
                    stage = int(stage)
                except Exception:
                    stage = 0
                # 연속된 동일 단계는 첫 봉만 표시해 차트가 지저분해지지 않게 한다.
                if stage <= 0 or stage == prev:
                    prev = stage
                    continue
                prev = stage
                xx = x(i)
                cy = watermelon_rect.center().y()
                radius = 6.0 + min(stage, 3) * 0.7
                p.setPen(QPen(QColor('#0b7d3c'), 1.6))
                p.setBrush(QColor('#39b85f'))
                p.drawEllipse(QPointF(xx, cy), radius, radius)
                if stage >= 2:
                    inner = radius - 2.2
                    p.setPen(Qt.NoPen)
                    p.setBrush(QColor('#f06069' if stage == 2 else '#ef3e52'))
                    p.drawEllipse(QPointF(xx, cy), inner, inner)
                if stage >= 3:
                    p.setBrush(QColor('#1a1a1a'))
                    for dx, dy in ((-2,-1),(2,-1),(0,2)):
                        p.drawEllipse(QPointF(xx+dx, cy+dy), 0.9, 1.4)
                p.setBrush(Qt.NoBrush)
                p.setPen(QColor('#ffffff'))
                p.drawText(int(xx-3), int(cy+3), str(stage))

''' + arrow_anchor
chart = once(chart, arrow_anchor, wm_draw, "watermelon draw")

legend_anchor = """        if isinstance(cloud_a, list) and isinstance(cloud_b, list) and cloud_a and cloud_b:
            p.setPen(QColor('#3972ff'))
            p.setFont(QFont('Malgun Gothic', 8, QFont.Bold))
            p.drawText(int(price_rect.left()), int(price_rect.top()+27), '■ 일목 선행스팬1·2')
"""
legend_new = legend_anchor + """        if isinstance(self.series.get('watermelon_stage'), list) and self.series.get('watermelon_stage'):
            p.setPen(QColor('#39b85f'))
            p.drawText(int(price_rect.left()+150), int(price_rect.top()+27), '● PUMA 수박근사(1~3단)')
"""
chart = once(chart, legend_anchor, legend_new, "watermelon legend")

# ---------- updater ----------
updater = once(updater, 'CURRENT_VERSION = "1.5.0"', 'CURRENT_VERSION = "1.6.0"', "updater version")
updater = updater.replace("PUMA-STOCK-UPDATER/1.5", "PUMA-STOCK-UPDATER/1.6")

ui_path.write_text(ui, encoding="utf-8")
chart_path.write_text(chart, encoding="utf-8")
swing_path.write_text(swing, encoding="utf-8")
danta_path.write_text(danta, encoding="utf-8")
bowl_path.write_text(bowl, encoding="utf-8")
updater_path.write_text(updater, encoding="utf-8")
(pkg / "puma_trader" / "__init__.py").write_text('__version__ = "1.6.0"\n', encoding="utf-8")
print("PUMA v1.6 patch applied")
