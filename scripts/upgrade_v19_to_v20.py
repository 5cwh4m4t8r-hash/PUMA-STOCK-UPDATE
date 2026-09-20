from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
pkg = ROOT / "work" / "PUMA_STOCK_PRO_v1.9"
ui_path = pkg / "puma_trader" / "ui.py"
chart_path = pkg / "puma_trader" / "swing_chart.py"
updater_path = pkg / "puma_trader" / "updater.py"

ui = ui_path.read_text(encoding="utf-8")
chart = chart_path.read_text(encoding="utf-8")
updater = updater_path.read_text(encoding="utf-8")

def once(text, old, new, label):
    if old not in text:
        raise RuntimeError(f"target not found: {label}")
    return text.replace(old, new, 1)

# ---------- version / imports ----------
ui = once(ui,
          "from .probability import estimate_from_flags, strategy_flags\n",
          "from .probability import estimate_from_flags, strategy_flags\nfrom .entry_signal import evaluate_core_entry\n",
          "entry signal import")
ui = once(ui, 'self.setWindowTitle("PUMA STOCK PRO v1.9")', 'self.setWindowTitle("PUMA STOCK PRO v2.0")', "window version")
ui = once(ui, 'title = QLabel("🐆  PUMA STOCK PRO  v1.9")', 'title = QLabel("🐆  PUMA STOCK PRO  v2.0")', "header version")

# ---------- explicit core signal rows ----------
ui = ui.replace(
    'danta_names = ["패턴 점수", "간단 이유", "PUMA 수박근사", "유사구간 확률", "PUMA 판단", "화살표 신호", "검색 시간", "PUMA 기준선(26)", "EMA 5·20·60", "현재 5분봉 거래량", "최근 고점 돌파", "눌림 지지"]',
    'danta_names = ["패턴 점수", "핵심 진입 신호", "간단 이유", "PUMA 수박근사", "유사구간 확률", "PUMA 판단", "화살표 신호", "검색 시간", "PUMA 기준선(26)", "EMA 5·20·60", "현재 5분봉 거래량", "최근 고점 돌파", "눌림 지지"]'
)
ui = ui.replace(
    'names = ["간단 이유", "PUMA 수박근사", "유사구간 확률", "PUMA 판단", "기준봉 눌림", "장기 EMA 역배열", "매집봉/구간", "공구리(박스권)", "박스 상단 돌파", "상단 박스 안착", "파란점선", "화살표 신호"]',
    'names = ["핵심 진입 신호", "간단 이유", "PUMA 수박근사", "유사구간 확률", "PUMA 판단", "기준봉 눌림", "장기 EMA 역배열", "매집봉/구간", "공구리(박스권)", "박스 상단 돌파", "상단 박스 안착", "파란점선", "화살표 신호"]'
)
ui = ui.replace(
    'bowl_names = ["간단 이유", "PUMA 수박근사", "유사구간 확률", "PUMA 판단", "장기 224EMA 아래", "224EMA 돌파", "224EMA 위 안착", "눌림/지지", "224EMA 거리", "화살표 신호"]',
    'bowl_names = ["핵심 진입 신호", "간단 이유", "PUMA 수박근사", "유사구간 확률", "PUMA 판단", "장기 224EMA 아래", "224EMA 돌파", "224EMA 위 안착", "눌림/지지", "224EMA 거리", "화살표 신호"]'
)

# ---------- replace enrichment logic ----------
start = ui.index("    def _enrich_setup_stats(self, analysis, series: dict, strategy: str):")
end = ui.index("\n    def _sync_selected_stock_everywhere", start)
new_enrich = r'''    def _enrich_setup_stats(self, analysis, series: dict, strategy: str):
        if not analysis or not series or not series.get("candles"):
            return analysis, series
        try:
            # 수박은 내부 진행상태와 차트표시를 분리한다.
            # 차트에는 strict-confirmed + cooldown을 통과한 확정구간만 표시.
            wm = build_puma_watermelon(series["candles"], series)
            series.update(wm)
            scores = wm.get("watermelon_score", [])
            reasons = wm.get("watermelon_reason", [])
            confirmed = wm.get("watermelon_confirmed", [])
            display = wm.get("watermelon_display", [])
            wscore = int(scores[-1]) if scores else 0
            wreason = str(reasons[-1]) if reasons else "조건 미충족"
            wconfirmed = bool(confirmed[-1]) if confirmed else False
            recent_display = False
            if display:
                recent_display = any(bool(x) for x in display[max(0, len(display)-20):])
            if wconfirmed:
                analysis.details["PUMA 수박근사"] = f"확정구간 · {wscore}/100 · {wreason}"
            elif recent_display:
                analysis.details["PUMA 수박근사"] = f"최근 확정수박 존재 · 현재는 해제 · {wscore}/100"
            else:
                analysis.details["PUMA 수박근사"] = f"표시 없음 · 확정조건 미충족 · {wscore}/100"

            # '핵심 진입 신호'를 전략별로 명시적으로 계산한다.
            core = evaluate_core_entry(analysis, series, strategy)
            analysis.details["핵심 진입 신호"] = core.status_text

            flags = strategy_flags(series, strategy)
            if strategy == "DAY":
                horizon = 12
            elif strategy == "SWING":
                horizon = 20
            else:
                horizon = 60

            tp = float(self.focus_tp.value()) if hasattr(self, "focus_tp") else float(self.settings.take_profit_pct)
            sl = abs(float(self.focus_sl.value())) if hasattr(self, "focus_sl") else abs(float(self.settings.stop_loss_pct))

            est = estimate_from_flags(
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
            analysis.details["유사구간 확률"] = est.summary()
            analysis.details["PUMA 판단"] = f"{est.verdict} · {est.reason}"
            analysis.details["확률 기준"] = (
                f"과거 유사 신호의 TP-before-SL 통계 · TP {tp:.1f}% / SL {sl:.1f}% · {horizon}봉"
            )
        except Exception as exc:
            analysis.details["PUMA 수박근사"] = f"계산 실패: {exc}"
            analysis.details["핵심 진입 신호"] = "계산 실패"
            analysis.details["유사구간 확률"] = "계산 불가"
            analysis.details["PUMA 판단"] = "판단 유보"
        return analysis, series
'''
ui = ui[:start] + new_enrich + ui[end:]

# ---------- detail maps ----------
ui = once(ui,
'''                    "패턴 점수": f"{danta_analysis.score}/100 · {danta_analysis.stage}",
                    "간단 이유": dreason,
''',
'''                    "패턴 점수": f"{danta_analysis.score}/100 · {danta_analysis.stage}",
                    "핵심 진입 신호": danta_analysis.details.get("핵심 진입 신호", "-"),
                    "간단 이유": dreason,
''',
"danta core detail")

# ---------- summary cards explicitly show core signal ----------
ui = once(
    ui,
    '            dprob = danta_analysis.details.get("유사구간 확률", "-")\n            self.focus_danta_signal.setText(\n',
    '            dprob = danta_analysis.details.get("유사구간 확률", "-")\n            dcore = danta_analysis.details.get("핵심 진입 신호", "-")\n            self.focus_danta_signal.setText(\n',
    "danta core variable",
)
ui = once(
    ui,
    '                f"단타 DAY · 5분봉\\n"\n                f"단계: {danta_analysis.stage}\\n"',
    '                f"단타 DAY · 5분봉\\n"\n                f"핵심: {dcore}\\n"\n                f"단계: {danta_analysis.stage}\\n"',
    "danta core line",
)

ui = once(
    ui,
    '            sprob = swing_analysis.details.get("유사구간 확률", "-")\n            self.focus_swing_signal.setText(\n',
    '            sprob = swing_analysis.details.get("유사구간 확률", "-")\n            score_core = swing_analysis.details.get("핵심 진입 신호", "-")\n            self.focus_swing_signal.setText(\n',
    "swing core variable",
)
ui = once(
    ui,
    '                f"역매공파 SWING\\n"\n                f"단계: {swing_analysis.stage}\\n"',
    '                f"역매공파 SWING\\n"\n                f"핵심: {score_core}\\n"\n                f"단계: {swing_analysis.stage}\\n"',
    "swing core line",
)

ui = once(
    ui,
    '            bprob = bowl_analysis.details.get("유사구간 확률", "-")\n            self.focus_bowl_signal.setText(\n',
    '            bprob = bowl_analysis.details.get("유사구간 확률", "-")\n            bcore = bowl_analysis.details.get("핵심 진입 신호", "-")\n            self.focus_bowl_signal.setText(\n',
    "bowl core variable",
)
ui = once(
    ui,
    '                f"밥그릇 3번 LONG\\n"\n                f"단계: {bowl_analysis.stage}\\n"',
    '                f"밥그릇 3번 LONG\\n"\n                f"핵심: {bcore}\\n"\n                f"단계: {bowl_analysis.stage}\\n"',
    "bowl core line",
)

# Make core signal visually meaningful in swing/bowl loops automatically (keys read details).
# Increase card height slightly because the explicit core line is now visible.
ui = ui.replace("self.setMinimumHeight(118)", "self.setMinimumHeight(132)")
ui = ui.replace("self.setMaximumHeight(150)", "self.setMaximumHeight(178)")
ui = ui.replace("signals.setMinimumHeight(185)", "signals.setMinimumHeight(205)")

# ---------- update note ----------
ui = ui.replace(
    "v1.9: YTN형 급등 기준봉-거래량 감소 눌림을 일반 패턴으로 추가. 영웅문 화면에 맞춰 EMA5/20/60/112/224/448 색·굵기 재정리, 224 검정선/검정화살표는 흰 외곽선으로 대비 강화. 역매공파 설정값을 전부 노출하고 PUMA 표준값 버튼 추가.",
    "v2.0: 전략별 핵심 진입 신호를 명시하고 '현재 신호 아님' 대신 미충족 조건을 직접 표시. YTN형 기준봉 눌림은 독립 유효신호로 인정. 수박은 고확률 복합조건을 통과한 확정구간만 20봉당 1회 표시."
)

# ---------- chart: show only strict confirmed watermelon events ----------
old_wm_start = chart.index("        # PUMA 수박근사:")
old_wm_end = chart.index("        # 사용자 영웅문 매수 화살표 3종.", old_wm_start)
new_wm = r'''        # PUMA 수박근사: 확정구간만 표시.
        # stage 1/2 후보는 화면에 그리지 않고, strict 조건을 모두 통과한 이벤트만
        # 20봉 cooldown을 거쳐 큰 수박 한 개로 표시한다.
        wm = self.series.get('watermelon_display', [])
        if isinstance(wm, list) and wm:
            p.setFont(QFont('Malgun Gothic', 7, QFont.Bold))
            p.setPen(QColor('#83a1ba'))
            p.drawText(5, int(watermelon_rect.center().y()+3), 'PUMA수박확정')
            for i, stage in enumerate(wm[start:end]):
                if not stage:
                    continue
                xx = x(i)
                cy = watermelon_rect.center().y()
                radius = 13.0

                p.setPen(QPen(QColor('#ffd44a'), 2.5))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(QPointF(xx, cy), radius+3.5, radius+3.5)

                p.setPen(QPen(QColor('#08753a'), 2.2))
                p.setBrush(QColor('#35b85c'))
                p.drawEllipse(QPointF(xx, cy), radius, radius)

                p.setPen(Qt.NoPen)
                p.setBrush(QColor('#ef4c5b'))
                p.drawEllipse(QPointF(xx, cy), radius-3.2, radius-3.2)

                p.setBrush(QColor('#1c1515'))
                for dx, dy in ((-4,-3),(0,-4),(4,-3),(-2,3),(3,3)):
                    p.drawEllipse(QPointF(xx+dx, cy+dy), 1.0, 1.6)
                p.setBrush(Qt.NoBrush)

'''
chart = chart[:old_wm_start] + new_wm + chart[old_wm_end:]

# Exclude new arrays from line renderer.
chart = chart.replace(
    "'watermelon_stage','watermelon_score','watermelon_reason'",
    "'watermelon_stage','watermelon_score','watermelon_reason','watermelon_confirmed','watermelon_display'"
)
chart = chart.replace(
    "● 수박: 작은껍질=접근 · 붉은속=안착 · 금테=강화",
    "● PUMA 수박확정: 복합조건 충족 구간만 표시"
)

# ---------- updater ----------
updater = once(updater, 'CURRENT_VERSION = "1.9.0"', 'CURRENT_VERSION = "2.0.0"', "updater version")
updater = updater.replace("PUMA-STOCK-UPDATER/1.9", "PUMA-STOCK-UPDATER/2.0")

ui_path.write_text(ui, encoding="utf-8")
chart_path.write_text(chart, encoding="utf-8")
updater_path.write_text(updater, encoding="utf-8")
(pkg / "puma_trader" / "__init__.py").write_text('__version__ = "2.0.0"\n', encoding="utf-8")
print("PUMA v2.0 core signal + sparse watermelon patch applied")
