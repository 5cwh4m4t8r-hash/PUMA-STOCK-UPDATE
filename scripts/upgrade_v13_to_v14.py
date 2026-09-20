from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
pkg = ROOT / "work" / "PUMA_STOCK_PRO_v1.3"
ui_path = pkg / "puma_trader" / "ui.py"
chart_path = pkg / "puma_trader" / "swing_chart.py"
swing_path = pkg / "puma_trader" / "swing.py"
bowl_path = pkg / "puma_trader" / "bowl.py"
danta_path = pkg / "puma_trader" / "danta.py"
updater_path = pkg / "puma_trader" / "updater.py"

ui = ui_path.read_text(encoding="utf-8")
chart = chart_path.read_text(encoding="utf-8")
swing = swing_path.read_text(encoding="utf-8")
bowl = bowl_path.read_text(encoding="utf-8")
danta = danta_path.read_text(encoding="utf-8")
updater = updater_path.read_text(encoding="utf-8")

def once(text, old, new, label):
    if old not in text:
        raise RuntimeError(f"target not found: {label}")
    return text.replace(old, new, 1)

def replace_func(text, start_name, next_name, new_block):
    start = text.index(f"    def {start_name}")
    end = text.index(f"    def {next_name}", start)
    return text[:start] + new_block.rstrip() + "\n\n" + text[end:]

# ---------- version / direct order naming ----------
ui = once(ui, 'self.setWindowTitle("PUMA STOCK PRO v1.3")', 'self.setWindowTitle("PUMA STOCK PRO v1.4")', "window version")
ui = once(ui, 'title = QLabel("🐆  PUMA STOCK PRO  v1.3")', 'title = QLabel("🐆  PUMA STOCK PRO  v1.4")', "header version")
ui = ui.replace('self.tabs.addTab(self.manual_widget, "고급 주문")', 'self.tabs.addTab(self.manual_widget, "직접 주문")')
ui = ui.replace('QGroupBox("영웅문 스타일 수동주문")', 'QGroupBox("직접 주문")')

# Current green/red strip is NOT the user's watermelon indicator: remove visible/use references until formula arrives.
ui = ui.replace('from .watermelon import build_watermelon\n', '')
ui = ui.replace('            series["watermelon"] = build_watermelon(series.get("candles", []))\n', '')
ui = ui.replace('                    danta_series["watermelon"] = build_watermelon(danta_series.get("candles", []))\n', '')
ui = ui.replace('                    swing_series["watermelon"] = build_watermelon(swing_series.get("candles", []))\n', '')
ui = ui.replace('            "watermelon": build_watermelon(candles),\n', '')

# Analysis panel now explicitly includes a brief reason line.
ui = ui.replace(
    'danta_names = ["패턴 점수", "검색 시간", "PUMA 기준선(26)", "EMA 5·20·60", "현재 5분봉 거래량", "최근 고점 돌파", "눌림 지지"]',
    'danta_names = ["패턴 점수", "간단 이유", "검색 시간", "PUMA 기준선(26)", "EMA 5·20·60", "현재 5분봉 거래량", "최근 고점 돌파", "눌림 지지"]'
)
ui = ui.replace(
    'names = ["장기 EMA 역배열", "매집봉/구간", "공구리(박스권)", "박스 상단 돌파", "상단 박스 안착", "파란점선", "수박/화살표"]',
    'names = ["간단 이유", "장기 EMA 역배열", "매집봉/구간", "공구리(박스권)", "박스 상단 돌파", "상단 박스 안착", "파란점선", "수박/화살표"]'
)
ui = ui.replace(
    'bowl_names = ["장기 224EMA 아래", "224EMA 돌파", "224EMA 위 안착", "눌림/지지", "224EMA 거리", "수박/화살표"]',
    'bowl_names = ["간단 이유", "장기 224EMA 아래", "224EMA 돌파", "224EMA 위 안착", "눌림/지지", "224EMA 거리", "수박/화살표"]'
)

# Summary cards include the concise "why".
old_apply = '''    def _apply_focus_analyses(self, danta_analysis, swing_analysis, bowl_analysis, label: str):
        if danta_analysis:
            color = "#61ff8f" if danta_analysis.candidate else ("#62b8ff" if danta_analysis.score >= 55 else "#f4c95d")
            self.focus_danta_signal.setText(f"단타 DAY · 5분봉\\n{danta_analysis.stage} · {danta_analysis.score}/100")
            self.focus_danta_signal.setStyleSheet(f"font-size:14px;font-weight:900;color:{color};background:#122238;border-radius:8px;padding:8px")
            if hasattr(self, "focus_danta_labels"):
                detail_map = {
                    "패턴 점수": f"{danta_analysis.score}/100 · {danta_analysis.stage}",
                    "검색 시간": danta_analysis.details.get("검색 시간", "-"),
                    "PUMA 기준선(26)": danta_analysis.details.get("PUMA 기준선(26)", danta_analysis.details.get("5분 기준선", "-")),
                    "EMA 5·20·60": danta_analysis.details.get("EMA 5·20·60", "-"),
                    "현재 5분봉 거래량": danta_analysis.details.get("현재 5분봉 거래량", "-"),
                    "최근 고점 돌파": danta_analysis.details.get("최근 고점 돌파", "-"),
                    "눌림 지지": danta_analysis.details.get("눌림 지지", "-"),
                }
                for key, lab in self.focus_danta_labels.items():
                    text = str(detail_map.get(key, "-"))
                    lab.setText(text)
                    good = any(word in text for word in ("확인", "진입허용", "상승/지지"))
                    lab.setStyleSheet(f"font-weight:800;color:{'#61ff8f' if good else '#f4c95d'}")

        if swing_analysis:
            self.focus_swing_signal.setText(f"역매공파 SWING\\n{swing_analysis.stage} · {swing_analysis.score}/100")
            self.focus_swing_signal.setStyleSheet("font-size:14px;font-weight:900;color:#62b8ff;background:#122238;border-radius:8px;padding:8px")
            for key, lab in self.focus_stage_labels.items():
                text = swing_analysis.details.get(key, "-")
                lab.setText(text)
                good = any(x in text for x in ("확인","감지")) and "미확인" not in text
                near = key == "파란점선" and getattr(swing_analysis, "blue_near", False)
                lab.setStyleSheet(f"font-weight:800;color:{'#61ff8f' if (good or near) else '#f4c95d'}")

        if bowl_analysis:
            self.focus_bowl_signal.setText(f"밥그릇 3번 LONG\\n{bowl_analysis.stage} · {bowl_analysis.score}/100")
            self.focus_bowl_signal.setStyleSheet("font-size:14px;font-weight:900;color:#d58cff;background:#122238;border-radius:8px;padding:8px")
            for key, lab in self.focus_bowl_labels.items():
                text = bowl_analysis.details.get(key, "-")
                lab.setText(text)
                good = "확인" in text and "미확인" not in text
                lab.setStyleSheet(f"font-weight:800;color:{'#61ff8f' if good else '#f4c95d'}")

        d = getattr(danta_analysis, "stage", "대기") if danta_analysis else "대기"
        s = getattr(swing_analysis, "stage", "대기") if swing_analysis else "대기"
        b = getattr(bowl_analysis, "stage", "대기") if bowl_analysis else "대기"
        self.focus_stage.setText(f"통합판정 · {label}  |  단타: {d}  |  역매공파: {s}  |  밥그릇3번: {b}")
'''
new_apply = '''    def _apply_focus_analyses(self, danta_analysis, swing_analysis, bowl_analysis, label: str):
        if danta_analysis:
            color = "#61ff8f" if danta_analysis.candidate else ("#62b8ff" if danta_analysis.score >= 55 else "#f4c95d")
            dreason = str(danta_analysis.details.get("간단 이유", "-"))
            self.focus_danta_signal.setText(
                f"단타 DAY · 5분봉\\n{danta_analysis.stage} · {danta_analysis.score}/100\\n이유: {dreason}"
            )
            self.focus_danta_signal.setStyleSheet(f"font-size:13px;font-weight:900;color:{color};background:#122238;border-radius:8px;padding:7px")
            if hasattr(self, "focus_danta_labels"):
                detail_map = {
                    "패턴 점수": f"{danta_analysis.score}/100 · {danta_analysis.stage}",
                    "간단 이유": dreason,
                    "검색 시간": danta_analysis.details.get("검색 시간", "-"),
                    "PUMA 기준선(26)": danta_analysis.details.get("PUMA 기준선(26)", danta_analysis.details.get("5분 기준선", "-")),
                    "EMA 5·20·60": danta_analysis.details.get("EMA 5·20·60", "-"),
                    "현재 5분봉 거래량": danta_analysis.details.get("현재 5분봉 거래량", "-"),
                    "최근 고점 돌파": danta_analysis.details.get("최근 고점 돌파", "-"),
                    "눌림 지지": danta_analysis.details.get("눌림 지지", "-"),
                }
                for key, lab in self.focus_danta_labels.items():
                    text = str(detail_map.get(key, "-"))
                    lab.setText(text)
                    good = any(word in text for word in ("확인", "진입허용", "상승/지지"))
                    lab.setStyleSheet(f"font-weight:800;color:{'#61ff8f' if good else '#f4c95d'}")

        if swing_analysis:
            sreason = str(swing_analysis.details.get("간단 이유", "-"))
            self.focus_swing_signal.setText(
                f"역매공파 SWING\\n{swing_analysis.stage} · {swing_analysis.score}/100\\n이유: {sreason}"
            )
            self.focus_swing_signal.setStyleSheet("font-size:13px;font-weight:900;color:#62b8ff;background:#122238;border-radius:8px;padding:7px")
            for key, lab in self.focus_stage_labels.items():
                text = swing_analysis.details.get(key, "-")
                lab.setText(text)
                good = any(x in text for x in ("확인","감지")) and "미확인" not in text
                near = key == "파란점선" and getattr(swing_analysis, "blue_near", False)
                lab.setStyleSheet(f"font-weight:800;color:{'#61ff8f' if (good or near) else '#f4c95d'}")

        if bowl_analysis:
            breason = str(bowl_analysis.details.get("간단 이유", "-"))
            self.focus_bowl_signal.setText(
                f"밥그릇 3번 LONG\\n{bowl_analysis.stage} · {bowl_analysis.score}/100\\n이유: {breason}"
            )
            self.focus_bowl_signal.setStyleSheet("font-size:13px;font-weight:900;color:#d58cff;background:#122238;border-radius:8px;padding:7px")
            for key, lab in self.focus_bowl_labels.items():
                text = bowl_analysis.details.get(key, "-")
                lab.setText(text)
                good = "확인" in text and "미확인" not in text
                lab.setStyleSheet(f"font-weight:800;color:{'#61ff8f' if good else '#f4c95d'}")

        d = getattr(danta_analysis, "stage", "대기") if danta_analysis else "대기"
        s = getattr(swing_analysis, "stage", "대기") if swing_analysis else "대기"
        b = getattr(bowl_analysis, "stage", "대기") if bowl_analysis else "대기"
        self.focus_stage.setText(f"통합판정 · {label}  |  단타: {d}  |  역매공파: {s}  |  밥그릇3번: {b}")
'''
ui = once(ui, old_apply, new_apply, "analysis reasons")

# Rename update text and explicitly state current watermelon is disabled pending user's formula.
ui = ui.replace(
    "v1.3: 일봉에는 날짜 경계선을 표시하지 않도록 정리하고, 조건검색 종목명 열 폭/글꼴/조회 우선순위를 개선해 종목명이 확실히 보이도록 수정.",
    "v1.4: 직접 주문 명칭 변경, 분석 카드에 간단 이유 표시, 기존 임시 수박바 제거, 일봉/5분봉에 일목균형표 선행스팬1·2 파란 구름대 반영."
)

# ---------- Danta: reason + Ichimoku ----------
danta = once(danta, "from .swing import ema, normalize_candles\n",
             "from .swing import ema, normalize_candles\nfrom .indicators import ichimoku_cloud\n",
             "danta ichimoku import")
danta = once(
    danta,
    '''    details = {
        "분석 기준일": latest_day,
''',
    '''    reasons = []
    reasons.append("기준선 위" if baseline_alive else "기준선 이탈")
    reasons.append("EMA 정배열" if ema_stack else "EMA 정배열 미확인")
    reasons.append(f"5분 거래량 {volume_ratio_5m:.2f}배")
    if breakout:
        reasons.append("최근 고점 돌파")
    elif pullback_hold:
        reasons.append("눌림 지지")
    else:
        reasons.append("돌파/눌림 미확인")

    details = {
        "간단 이유": " · ".join(reasons[:4]),
        "분석 기준일": latest_day,
''',
    "danta reason",
)
danta = once(
    danta,
    '''    series = {
        "candles": candles,
        "ema5": e5,
        "ema20": e20,
        "ema60": e60,
        "kijun": kijun,
    }
''',
    '''    series = {
        "candles": candles,
        "ema5": e5,
        "ema20": e20,
        "ema60": e60,
        "kijun": kijun,
    }
    series.update(ichimoku_cloud(candles))
''',
    "danta cloud",
)

# ---------- Swing: reason + Ichimoku + honest watermelon status ----------
swing = once(swing, "from typing import List, Dict, Optional\n",
             "from typing import List, Dict, Optional\n\nfrom .indicators import ichimoku_cloud\n",
             "swing ichimoku import")
swing = swing.replace("stage = '수박·화살표 최종 타점 대기'", "stage = '최종 신호(수박/화살표) 수식 대기'")
swing = once(
    swing,
    '''    details = {
        '장기 EMA 역배열': '확인' if reverse else '미확인',
''',
    '''    reasons = [
        ('장기 역배열 확인' if reverse else '장기 역배열 미확인'),
        f'매집 {len(acc_idx)}회',
        ('공구리 확인' if box else '공구리 미확인'),
        ('상단 안착 확인' if accepted else '상단 안착 대기'),
    ]
    if bnear:
        reasons.append(f'파란점선 근접 {bdist:+.2f}%')

    details = {
        '간단 이유': ' · '.join(reasons[:4]),
        '장기 EMA 역배열': '확인' if reverse else '미확인',
''',
    "swing reason",
)
swing = swing.replace("'수박/화살표': '외부 신호 대기',", "'수박/화살표': '사용자 수식 입력 대기',")
swing = once(
    swing,
    """        'box': box,
    }
    return analysis, series
""",
    """        'box': box,
    }
    series.update(ichimoku_cloud(candles))
    return analysis, series
""",
    "swing cloud",
)

# ---------- Bowl: reason + honest watermelon status ----------
bowl = bowl.replace("stage = '수박/화살표 최종 타점 대기'", "stage = '최종 신호(수박/화살표) 수식 대기'")
bowl = once(
    bowl,
    '''    details = {
        '장기 224EMA 아래': f'{below_count_at_break}봉 확인' if long_below else '미확인',
''',
    '''    reasons = [
        (f'224EMA 아래 {below_count_at_break}봉' if long_below else '장기 아래구간 미확인'),
        ('224EMA 돌파 확인' if breakout_idx >= 0 else '224EMA 돌파 대기'),
        ('위 안착 확인' if accepted else '위 안착 대기'),
        ('눌림 지지 확인' if retest else '눌림 지지 대기'),
    ]

    details = {
        '간단 이유': ' · '.join(reasons),
        '장기 224EMA 아래': f'{below_count_at_break}봉 확인' if long_below else '미확인',
''',
    "bowl reason",
)
bowl = bowl.replace("'수박/화살표': '외부 신호 대기',", "'수박/화살표': '사용자 수식 입력 대기',")

# ---------- Chart: remove fake watermelon strip, draw Ichimoku blue cloud with 26 future slots ----------
chart = once(chart, "from PySide6.QtGui import QColor, QPainter, QPen, QFont\n",
             "from PySide6.QtGui import QColor, QPainter, QPen, QFont, QPolygonF\n",
             "chart polygon import")
chart = chart.replace("v1.1:", "v1.4:", 1)

old_geom = '''        left, right, top = 60, 25, 28
        vol_h = 72
        watermelon_h = 13
        bottom = 54
        price_rect = QRectF(left, top, self.width()-left-right, self.height()-top-bottom-vol_h)
        vol_rect = QRectF(left, price_rect.bottom()+7, price_rect.width(), vol_h-12)
        watermelon_rect = QRectF(left, vol_rect.bottom()+4, price_rect.width(), watermelon_h)
'''
new_geom = '''        left, right, top = 60, 25, 28
        vol_h = 76
        bottom = 42
        price_rect = QRectF(left, top, self.width()-left-right, self.height()-top-bottom-vol_h)
        vol_rect = QRectF(left, price_rect.bottom()+7, price_rect.width(), vol_h-10)

        total_candles = len(candles)
        future_count = int(self.series.get('future_count', 0) or 0) if end >= total_candles else 0
        display_n = max(1, n + future_count)
'''
chart = once(chart, old_geom, new_geom, "chart geometry")

chart = once(
    chart,
    "        line_keys = [k for k in self.series.keys() if k not in ('candles','acc_flags','acc_meta','box','watermelon') and isinstance(self.series.get(k), list)]\n",
    "        line_keys = [k for k in self.series.keys() if k not in ('candles','acc_flags','acc_meta','box','watermelon','cloud_a','cloud_b') and isinstance(self.series.get(k), list)]\n",
    "line keys",
)

old_vals = '''        for key in line_keys:
            arr = self.series.get(key, [])
            vals += [v for v in arr[start:end] if isinstance(v, (int, float))]
        lo, hi = min(vals), max(vals)
'''
new_vals = '''        for key in line_keys:
            arr = self.series.get(key, [])
            vals += [v for v in arr[start:end] if isinstance(v, (int, float))]
        cloud_a = self.series.get('cloud_a', [])
        cloud_b = self.series.get('cloud_b', [])
        cloud_end = min(max(len(cloud_a), len(cloud_b)), end + future_count)
        if isinstance(cloud_a, list):
            vals += [v for v in cloud_a[start:cloud_end] if isinstance(v, (int, float))]
        if isinstance(cloud_b, list):
            vals += [v for v in cloud_b[start:cloud_end] if isinstance(v, (int, float))]
        lo, hi = min(vals), max(vals)
'''
chart = once(chart, old_vals, new_vals, "cloud y range")

chart = once(
    chart,
    "        def x(i): return price_rect.left() + (i + 0.5) * price_rect.width() / n\n",
    "        def x(i): return price_rect.left() + (i + 0.5) * price_rect.width() / display_n\n",
    "future x mapping",
)

chart = chart.replace("QPointF(xx, watermelon_rect.bottom())", "QPointF(xx, vol_rect.bottom())")
chart = chart.replace("int(watermelon_rect.bottom()+5)", "int(vol_rect.bottom()+7)")

# Remove entire old fake watermelon rendering block.
water_start = chart.index("        # PUMA 수박형 밴드:")
water_end = chart.index("        colors={", water_start)
chart = chart[:water_start] + chart[water_end:]

# Draw blue cloud before candles/lines.
cloud_anchor = "        # 공구리 박스\n"
cloud_block = '''        # 일목균형표 선행스팬 1·2: 사용자 영웅문 화면처럼 파란 구름대로 표시.
        # 최신 구간에서는 표준 +26 선행 구간까지 오른쪽에 예약해 구름이 앞쪽으로 이어진다.
        if isinstance(cloud_a, list) and isinstance(cloud_b, list):
            pts_a = []
            pts_b = []
            cloud_last = min(len(cloud_a), len(cloud_b), end + future_count)
            for gi in range(start, cloud_last):
                a = cloud_a[gi]
                b = cloud_b[gi]
                if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
                    continue
                xx = x(gi - start)
                pts_a.append(QPointF(xx, y(a)))
                pts_b.append(QPointF(xx, y(b)))
            if len(pts_a) >= 2 and len(pts_b) >= 2:
                poly = QPolygonF(pts_a + list(reversed(pts_b)))
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(40, 92, 255, 120))
                p.drawPolygon(poly)
                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(QColor('#1f55ff'), 1.2))
                for pts in (pts_a, pts_b):
                    for j in range(1, len(pts)):
                        p.drawLine(pts[j-1], pts[j])

''' + cloud_anchor
chart = once(chart, cloud_anchor, cloud_block, "cloud rendering")

# Date separator height after fake band removal.
chart = chart.replace("QPointF(xx, watermelon_rect.bottom())", "QPointF(xx, vol_rect.bottom())")

# Legend explicitly labels blue cloud.
legend_anchor = """        p.setPen(QColor('#7991aa')); p.setFont(QFont('Malgun Gothic',8))
        p.drawText(int(price_rect.right()-410), 19, 400, 18, Qt.AlignRight, '휠: 확대/축소 · 드래그: 과거/최신 이동 · 더블클릭: 최신')
"""
legend_new = """        p.setPen(QColor('#7991aa')); p.setFont(QFont('Malgun Gothic',8))
        p.drawText(int(price_rect.right()-410), 19, 400, 18, Qt.AlignRight, '휠: 확대/축소 · 드래그: 과거/최신 이동 · 더블클릭: 최신')
        if isinstance(cloud_a, list) and isinstance(cloud_b, list) and cloud_a and cloud_b:
            p.setPen(QColor('#3972ff'))
            p.setFont(QFont('Malgun Gothic', 8, QFont.Bold))
            p.drawText(int(price_rect.left()), int(price_rect.top()+27), '■ 일목 선행스팬1·2')
"""
chart = once(chart, legend_anchor, legend_new, "cloud legend")

# ---------- updater ----------
updater = once(updater, 'CURRENT_VERSION = "1.3.0"', 'CURRENT_VERSION = "1.4.0"', "updater version")
updater = updater.replace("PUMA-STOCK-UPDATER/1.3", "PUMA-STOCK-UPDATER/1.4")

ui_path.write_text(ui, encoding="utf-8")
chart_path.write_text(chart, encoding="utf-8")
swing_path.write_text(swing, encoding="utf-8")
bowl_path.write_text(bowl, encoding="utf-8")
danta_path.write_text(danta, encoding="utf-8")
updater_path.write_text(updater, encoding="utf-8")
(pkg / "puma_trader" / "__init__.py").write_text('__version__ = "1.4.0"\n', encoding="utf-8")
print("PUMA v1.4 chart/reference patch applied")
