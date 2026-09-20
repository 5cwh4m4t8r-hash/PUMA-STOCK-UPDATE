from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
pkg = ROOT / "work" / "PUMA_STOCK_PRO_v1.4.1"
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

# ---------- version ----------
ui = once(ui, 'self.setWindowTitle("PUMA STOCK PRO v1.4.1")', 'self.setWindowTitle("PUMA STOCK PRO v1.5")', "window version")
ui = once(ui, 'title = QLabel("🐆  PUMA STOCK PRO  v1.4.1")', 'title = QLabel("🐆  PUMA STOCK PRO  v1.5")', "header version")

# ---------- analysis labels ----------
ui = ui.replace(
    'danta_names = ["패턴 점수", "간단 이유", "검색 시간", "PUMA 기준선(26)", "EMA 5·20·60", "현재 5분봉 거래량", "최근 고점 돌파", "눌림 지지"]',
    'danta_names = ["패턴 점수", "간단 이유", "화살표 신호", "검색 시간", "PUMA 기준선(26)", "EMA 5·20·60", "현재 5분봉 거래량", "최근 고점 돌파", "눌림 지지"]'
)
ui = ui.replace('"수박/화살표"', '"화살표 신호"')

ui = once(
    ui,
    '''                    "간단 이유": dreason,
                    "검색 시간": danta_analysis.details.get("검색 시간", "-"),
''',
    '''                    "간단 이유": dreason,
                    "화살표 신호": danta_analysis.details.get("화살표 신호", "현재봉 화살표 없음"),
                    "검색 시간": danta_analysis.details.get("검색 시간", "-"),
''',
    "danta arrow detail map",
)

ui = ui.replace(
    "v1.4.1: 거래량 막대 색상을 직전 봉 대비 거래량 증감 기준으로 수정. 증가=빨강, 감소=파랑, 동일=회색.",
    "v1.5: 사용자 영웅문 화살표 3종을 수식 그대로 반영. 분홍/파랑/빨강 신호를 일봉·5분봉 차트에 색상별 매수 화살표로 표시."
)

# ---------- Danta series ----------
danta = once(danta, "from .indicators import ichimoku_cloud\n",
             "from .indicators import ichimoku_cloud\nfrom .signals import build_arrow_signals, latest_signal_reason\n",
             "danta signal import")
danta = once(
    danta,
    '''    details = {
        "간단 이유": " · ".join(reasons[:4]),
''',
    '''    arrow_series = build_arrow_signals(candles)
    arrow_reason = latest_signal_reason({"candles": candles, **arrow_series})

    details = {
        "간단 이유": " · ".join(reasons[:4]),
        "화살표 신호": arrow_reason,
''',
    "danta arrow reason",
)
danta = once(
    danta,
    '''    series.update(ichimoku_cloud(candles))
    return DantaAnalysis(
''',
    '''    series.update(ichimoku_cloud(candles))
    series.update(arrow_series)
    return DantaAnalysis(
''',
    "danta arrow series",
)

# ---------- Swing series ----------
swing = once(swing, "from .indicators import ichimoku_cloud\n",
             "from .indicators import ichimoku_cloud\nfrom .signals import build_arrow_signals, latest_signal_reason\n",
             "swing signal import")
swing = once(
    swing,
    '''    details = {
        '간단 이유': ' · '.join(reasons[:4]),
''',
    '''    arrow_series = build_arrow_signals(candles)
    arrow_reason = latest_signal_reason({'candles': candles, **arrow_series})

    details = {
        '간단 이유': ' · '.join(reasons[:4]),
''',
    "swing arrow setup",
)
swing = swing.replace("'수박/화살표': '사용자 수식 입력 대기',", "'화살표 신호': arrow_reason,")
swing = once(
    swing,
    """    series.update(ichimoku_cloud(candles))
    return analysis, series
""",
    """    series.update(ichimoku_cloud(candles))
    series.update(arrow_series)
    return analysis, series
""",
    "swing arrow series",
)

# ---------- Bowl series/details ----------
bowl = once(bowl, "from .swing import ema, normalize_candles\n",
            "from .swing import ema, normalize_candles\nfrom .signals import build_arrow_signals, latest_signal_reason\n",
            "bowl signal import")
bowl = once(
    bowl,
    '''    details = {
        '간단 이유': ' · '.join(reasons),
''',
    '''    arrow_series = build_arrow_signals(candles)
    arrow_reason = latest_signal_reason({'candles': candles, **arrow_series})

    details = {
        '간단 이유': ' · '.join(reasons),
''',
    "bowl arrow setup",
)
bowl = bowl.replace("'수박/화살표': '사용자 수식 입력 대기',", "'화살표 신호': arrow_reason,")
bowl = once(
    bowl,
    """    return result, {'candles': candles, 'ema224': e}
""",
    """    series = {'candles': candles, 'ema224': e}
    series.update(arrow_series)
    return result, series
""",
    "bowl arrow series",
)

# ---------- Chart rendering ----------
chart = once(
    chart,
    "        line_keys = [k for k in self.series.keys() if k not in ('candles','acc_flags','acc_meta','box','watermelon','cloud_a','cloud_b') and isinstance(self.series.get(k), list)]\n",
    "        line_keys = [k for k in self.series.keys() if k not in ('candles','acc_flags','acc_meta','box','watermelon','cloud_a','cloud_b','signal_pink','signal_blue','signal_red','signal_sar','signal_bb40_22') and isinstance(self.series.get(k), list)]\n",
    "exclude signal arrays from lines",
)

arrow_anchor = """        colors={
"""
arrow_block = r'''        # 사용자 영웅문 매수 화살표 3종.
        # 분홍: BBandsUp(40,2.2) 상향돌파 + EMA112/224/448 중 하나 상향돌파
        # 파랑: C>=SAR(0.066,0.016) + BBandsUp(40,2.2) 상향돌파 + EMA112 상향돌파
        # 빨강: C>=SAR(0.066,0.016) + EMA224 상향돌파
        sig_defs = [
            ('signal_pink', QColor('#ff33cc')),
            ('signal_blue', QColor('#1746ff')),
            ('signal_red', QColor('#ff2e2e')),
        ]
        for key, sig_color in sig_defs:
            arr = self.series.get(key, [])
            if not isinstance(arr, list):
                continue
            visible = arr[start:end]
            for i, active in enumerate(visible):
                if not active:
                    continue
                xx = x(i)
                # 같은 봉에 복수 신호가 겹칠 수 있어 색상별 높이를 조금 다르게 둔다.
                order = 0 if key == 'signal_pink' else 1 if key == 'signal_blue' else 2
                base = min(price_rect.bottom() - 3, y(cs[i]['low']) + 12 + order * 10)
                apex = base - 9
                p.setPen(QPen(sig_color, 2))
                p.drawLine(QPointF(xx, base + 6), QPointF(xx, apex + 4))
                p.setBrush(sig_color)
                tri = QPolygonF([
                    QPointF(xx, apex),
                    QPointF(xx - 5, apex + 7),
                    QPointF(xx + 5, apex + 7),
                ])
                p.drawPolygon(tri)
                p.setBrush(Qt.NoBrush)

''' + arrow_anchor
chart = once(chart, arrow_anchor, arrow_block, "arrow rendering")

# ---------- updater ----------
updater = once(updater, 'CURRENT_VERSION = "1.4.1"', 'CURRENT_VERSION = "1.5.0"', "updater version")
updater = updater.replace("PUMA-STOCK-UPDATER/1.4.1", "PUMA-STOCK-UPDATER/1.5")

ui_path.write_text(ui, encoding="utf-8")
chart_path.write_text(chart, encoding="utf-8")
swing_path.write_text(swing, encoding="utf-8")
danta_path.write_text(danta, encoding="utf-8")
bowl_path.write_text(bowl, encoding="utf-8")
updater_path.write_text(updater, encoding="utf-8")
(pkg / "puma_trader" / "__init__.py").write_text('__version__ = "1.5.0"\n', encoding="utf-8")
print("PUMA v1.5 exact arrow signals patch applied")
