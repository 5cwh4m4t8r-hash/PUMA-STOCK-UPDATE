from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
pkg = ROOT / "work" / "PUMA_STOCK_PRO_v1.7"
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

# ---------- version / imports ----------
ui = once(ui, "    QLineEdit,\n", "    QLineEdit,\n    QPlainTextEdit,\n", "plain text edit import")
ui = once(ui, 'self.setWindowTitle("PUMA STOCK PRO v1.7")', 'self.setWindowTitle("PUMA STOCK PRO v1.8")', "window version")
ui = once(ui, 'title = QLabel("🐆  PUMA STOCK PRO  v1.7")', 'title = QLabel("🐆  PUMA STOCK PRO  v1.8")', "header version")

# ---------- scrollable strategy cards ----------
card_anchor = "\n\nclass NoWheelComboBox(QComboBox):\n"
card_class = r'''

class StrategySummaryBox(QPlainTextEdit):
    """Scrollable strategy summary; no ellipsis and no hover tooltip needed."""
    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setPlainText(text)
        self.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setMinimumHeight(118)
        self.setMaximumHeight(150)
        self.document().setDocumentMargin(7)

    def setText(self, text):
        self.setPlainText(str(text))

''' + card_anchor
ui = once(ui, card_anchor, card_class, "strategy summary class")

old_cards = '''        self.focus_danta_signal = QLabel("단타 DAY · 5분봉\\n분석 대기")
        self.focus_swing_signal = QLabel("역매공파 SWING\\n분석 대기")
        self.focus_bowl_signal = QLabel("밥그릇 3번 LONG\\n분석 대기")
        for lab in (self.focus_danta_signal, self.focus_swing_signal, self.focus_bowl_signal):
            lab.setAlignment(Qt.AlignCenter)
            lab.setWordWrap(True)
            lab.setMinimumHeight(112)
            lab.setStyleSheet("font-size:12px;font-weight:900;color:#f4c95d;background:#122238;border-radius:8px;padding:7px")
'''
new_cards = '''        self.focus_danta_signal = StrategySummaryBox("단타 DAY · 5분봉\\n분석 대기")
        self.focus_swing_signal = StrategySummaryBox("역매공파 SWING\\n분석 대기")
        self.focus_bowl_signal = StrategySummaryBox("밥그릇 3번 LONG\\n분석 대기")
        for lab in (self.focus_danta_signal, self.focus_swing_signal, self.focus_bowl_signal):
            lab.setStyleSheet("QPlainTextEdit{font-size:12px;font-weight:900;color:#f4c95d;background:#122238;border:0;border-radius:8px;padding:3px;} QScrollBar:vertical{width:9px;}")
'''
ui = once(ui, old_cards, new_cards, "scrollable cards")
ui = ui.replace("signals.setMinimumHeight(170)", "signals.setMinimumHeight(185)")

# Replace compact/ellipsis/tooltip summaries with full scrollable content.
old_d = '''            dprob_short = str(dprob).split(" (", 1)[0]
            djudge_short = str(djudge).split(" ·", 1)[0]
            dreason_short = dreason if len(dreason) <= 38 else dreason[:38] + "…"
            self.focus_danta_signal.setText(
                f"단타 DAY · 5분봉\\n{danta_analysis.stage} · {danta_analysis.score}/100 · 확률 {dprob_short}\\n판단: {djudge_short}\\n이유: {dreason_short}"
            )
            self.focus_danta_signal.setToolTip(f"확률: {dprob}\\n판단: {djudge}\\n이유: {dreason}")
'''
new_d = '''            self.focus_danta_signal.setText(
                f"단타 DAY · 5분봉\\n"
                f"단계: {danta_analysis.stage}\\n"
                f"점수: {danta_analysis.score}/100\\n"
                f"유사구간 확률: {dprob}\\n"
                f"판단: {djudge}\\n"
                f"이유: {dreason}"
            )
'''
ui = once(ui, old_d, new_d, "full danta summary")

old_s = '''            sprob_short = str(sprob).split(" (", 1)[0]
            sjudge_short = str(sjudge).split(" ·", 1)[0]
            sreason_short = sreason if len(sreason) <= 38 else sreason[:38] + "…"
            self.focus_swing_signal.setText(
                f"역매공파 SWING\\n{swing_analysis.stage} · {swing_analysis.score}/100 · 확률 {sprob_short}\\n판단: {sjudge_short}\\n이유: {sreason_short}"
            )
            self.focus_swing_signal.setToolTip(f"확률: {sprob}\\n판단: {sjudge}\\n이유: {sreason}")
'''
new_s = '''            self.focus_swing_signal.setText(
                f"역매공파 SWING\\n"
                f"단계: {swing_analysis.stage}\\n"
                f"점수: {swing_analysis.score}/100\\n"
                f"유사구간 확률: {sprob}\\n"
                f"판단: {sjudge}\\n"
                f"이유: {sreason}"
            )
'''
ui = once(ui, old_s, new_s, "full swing summary")

old_b = '''            bprob_short = str(bprob).split(" (", 1)[0]
            bjudge_short = str(bjudge).split(" ·", 1)[0]
            breason_short = breason if len(breason) <= 38 else breason[:38] + "…"
            self.focus_bowl_signal.setText(
                f"밥그릇 3번 LONG\\n{bowl_analysis.stage} · {bowl_analysis.score}/100 · 확률 {bprob_short}\\n판단: {bjudge_short}\\n이유: {breason_short}"
            )
            self.focus_bowl_signal.setToolTip(f"확률: {bprob}\\n판단: {bjudge}\\n이유: {breason}")
'''
new_b = '''            self.focus_bowl_signal.setText(
                f"밥그릇 3번 LONG\\n"
                f"단계: {bowl_analysis.stage}\\n"
                f"점수: {bowl_analysis.score}/100\\n"
                f"유사구간 확률: {bprob}\\n"
                f"판단: {bjudge}\\n"
                f"이유: {breason}"
            )
'''
ui = once(ui, old_b, new_b, "full bowl summary")

# QTextEdit styles instead of QLabel-specific style.
ui = ui.replace(
    'self.focus_danta_signal.setStyleSheet(f"font-size:12px;font-weight:900;color:{color};background:#122238;border-radius:8px;padding:7px")',
    'self.focus_danta_signal.setStyleSheet(f"QPlainTextEdit{{font-size:12px;font-weight:900;color:{color};background:#122238;border:0;border-radius:8px;padding:3px;}} QScrollBar:vertical{{width:9px;}}")'
)
ui = ui.replace(
    'self.focus_swing_signal.setStyleSheet("font-size:12px;font-weight:900;color:#62b8ff;background:#122238;border-radius:8px;padding:7px")',
    'self.focus_swing_signal.setStyleSheet("QPlainTextEdit{font-size:12px;font-weight:900;color:#62b8ff;background:#122238;border:0;border-radius:8px;padding:3px;} QScrollBar:vertical{width:9px;}")'
)
ui = ui.replace(
    'self.focus_bowl_signal.setStyleSheet("font-size:12px;font-weight:900;color:#d58cff;background:#122238;border-radius:8px;padding:7px")',
    'self.focus_bowl_signal.setStyleSheet("QPlainTextEdit{font-size:12px;font-weight:900;color:#d58cff;background:#122238;border:0;border-radius:8px;padding:3px;} QScrollBar:vertical{width:9px;}")'
)

# Update accumulation note in settings.
ui = ui.replace(
    "※ 매집봉 = 고거래량 + (긴 윗꼬리 OR 장대음봉). 여러 번 나오면 매집구간으로 누적.",
    "※ 단독 1회는 매집후보로만 기록. 고거래량 + (긴 윗꼬리 OR 장대음봉)이 20봉 안에 2회 이상 반복될 때만 '매집확정/매집구간'으로 판정."
)

ui = ui.replace(
    "v1.7: 전략3종 카드 잘림 전면 수정, 직접주문 가격 드롭다운을 현재가 주변 호가로 변경, 분봉 기준선26 가시성 강화, 일봉 EMA5 복구, 거래량 확대, 수박형 마커 숫자 제거·가시성 강화, 전역 휠 차단 안전망 추가.",
    "v1.8: 매집봉 오탐 감소를 위해 단독 신호를 후보로 강등하고 20봉 내 2회 이상 반복 시에만 매집확정. 하단 전략3종은 말줄임/툴팁을 제거하고 카드 내부 세로 스크롤로 전체 분석을 확인하도록 변경."
)

# ---------- stricter accumulation confirmation ----------
swing = swing.replace("    accumulation_min_count: int = 1", "    accumulation_min_count: int = 2")

start = swing.index("def accumulation_flags(candles: List[dict], settings: SwingSettings):")
end = swing.index("\n\ndef _find_box", start)
new_acc = r'''def accumulation_flags(candles: List[dict], settings: SwingSettings):
    """Conservative accumulation-candle confirmation.

    Raw candidate:
      high volume AND (dominant long upper wick OR large bearish body).
    Confirmed accumulation:
      at least two raw candidates occurring within 20 bars of each other.

    A lone candle is kept only as metadata '매집후보' and is NOT painted/scored
    as confirmed accumulation. This intentionally reduces false positives.
    """
    vols = [c['volume'] for c in candles]
    vma = rolling_mean(vols, settings.volume_period)
    raw = [False] * len(candles)
    meta = []

    for i, c in enumerate(candles):
        rng = max(c['high'] - c['low'], 1e-9)
        body = abs(c['close'] - c['open'])
        upper = max(0.0, c['high'] - max(c['open'], c['close']))
        lower = max(0.0, min(c['open'], c['close']) - c['low'])
        body_ratio = body / rng
        upper_ratio = upper / rng
        close_pos = (c['close'] - c['low']) / rng

        ratio = 0.0
        if i > 0 and vma[i - 1]:
            ratio = c['volume'] / vma[i - 1]

        high_volume = ratio >= settings.volume_ratio

        # 윗꼬리는 전체폭 비중 + 몸통 대비 우세 + 아래꼬리보다 명확히 길어야 한다.
        wick_body_req = max(float(settings.upper_wick_vs_body), 1.35)
        long_upper = (
            upper_ratio >= settings.upper_wick_ratio
            and upper >= body * wick_body_req
            and upper >= lower * 1.15
        )

        # 장대음봉은 몸통이 충분히 크고 종가가 봉 하단부에서 끝난 경우만 인정.
        big_bear = (
            c['close'] < c['open']
            and body_ratio >= settings.bearish_body_ratio
            and close_pos <= 0.42
        )

        candidate = bool(high_volume and (long_upper or big_bear))
        raw[i] = candidate
        meta.append({
            'volume_ratio': ratio,
            'upper_wick_ratio': upper_ratio,
            'body_ratio': body_ratio,
            'pattern': '긴 윗꼬리' if long_upper else ('장대음봉' if big_bear else '-'),
            'raw_candidate': candidate,
            'confirmed': False,
            'cluster_size': 0,
        })

    # 가까운 후보들을 그룹화. 20봉 안에 2개 이상일 때 그룹 전체를 확정한다.
    raw_idx = [i for i, flag in enumerate(raw) if flag]
    groups = []
    group = []
    for idx in raw_idx:
        if not group or idx - group[-1] <= 20:
            group.append(idx)
        else:
            groups.append(group)
            group = [idx]
    if group:
        groups.append(group)

    flags = [False] * len(candles)
    for group in groups:
        size = len(group)
        if size < 2:
            continue
        for idx in group:
            flags[idx] = True
            meta[idx]['confirmed'] = True
            meta[idx]['cluster_size'] = size

    return flags, meta
'''
swing = swing[:start] + new_acc + swing[end:]

# Analysis uses at least two confirmed candles and reports candidate vs confirmed counts.
swing = once(swing,
"""    look_start = max(0, len(candles) - settings.accumulation_lookback)
    acc_idx = [i for i in range(look_start, len(candles)) if acc_flags[i]]
    box = _find_box(candles, settings)
""",
"""    look_start = max(0, len(candles) - settings.accumulation_lookback)
    acc_idx = [i for i in range(look_start, len(candles)) if acc_flags[i]]
    raw_acc_idx = [
        i for i in range(look_start, len(candles))
        if i < len(acc_meta) and bool(acc_meta[i].get('raw_candidate'))
    ]
    required_acc = max(2, int(settings.accumulation_min_count or 2))
    box = _find_box(candles, settings)
""",
"accumulation counts")
swing = swing.replace(
    "    if len(acc_idx) >= settings.accumulation_min_count:\n",
    "    if len(acc_idx) >= required_acc:\n"
)
swing = swing.replace(
    "        f'매집 {len(acc_idx)}회',",
    "        (f'매집확정 {len(acc_idx)}봉' if len(acc_idx) >= required_acc else f'매집확정 없음 / 후보 {len(raw_acc_idx)}봉'),"
)
swing = swing.replace(
    "        '매집봉/구간': f'{len(acc_idx)}회 감지',",
    "        '매집봉/구간': (f'확정 {len(acc_idx)}봉 · 후보 {len(raw_acc_idx)}봉' if acc_idx else f'확정 없음 · 후보 {len(raw_acc_idx)}봉'),"
)

# Chart language: only confirmed flags reach here.
chart = chart.replace("p.drawText(int(xx-18), int(price_rect.top()+18), '매집')",
                      "p.drawText(int(xx-26), int(price_rect.top()+18), '매집확정')")

# ---------- updater ----------
updater = once(updater, 'CURRENT_VERSION = "1.7.0"', 'CURRENT_VERSION = "1.8.0"', "updater version")
updater = updater.replace("PUMA-STOCK-UPDATER/1.7", "PUMA-STOCK-UPDATER/1.8")

ui_path.write_text(ui, encoding="utf-8")
swing_path.write_text(swing, encoding="utf-8")
chart_path.write_text(chart, encoding="utf-8")
updater_path.write_text(updater, encoding="utf-8")
(pkg / "puma_trader" / "__init__.py").write_text('__version__ = "1.8.0"\n', encoding="utf-8")
print("PUMA v1.8 accumulation + scrollable strategy cards applied")
