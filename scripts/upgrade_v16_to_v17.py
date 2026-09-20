from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
pkg = ROOT / "work" / "PUMA_STOCK_PRO_v1.6"
ui_path = pkg / "puma_trader" / "ui.py"
chart_path = pkg / "puma_trader" / "swing_chart.py"
swing_path = pkg / "puma_trader" / "swing.py"
updater_path = pkg / "puma_trader" / "updater.py"

ui = ui_path.read_text(encoding="utf-8")
chart = chart_path.read_text(encoding="utf-8")
swing = swing_path.read_text(encoding="utf-8")
updater = updater_path.read_text(encoding="utf-8")

def once(text, old, new, label):
    if old not in text:
        raise RuntimeError(f"target not found: {label}")
    return text.replace(old, new, 1)

# ---------- imports / version ----------
ui = once(ui,
          "from PySide6.QtCore import QTime, QTimer, Qt, QDate, QSettings, QThread, Signal",
          "from PySide6.QtCore import QTime, QTimer, Qt, QDate, QSettings, QThread, Signal, QEvent",
          "QEvent import")
ui = once(ui,
          "    QAbstractItemView,\n",
          "    QAbstractItemView,\n    QAbstractSpinBox,\n",
          "QAbstractSpinBox import")
ui = once(ui, 'self.setWindowTitle("PUMA STOCK PRO v1.6")', 'self.setWindowTitle("PUMA STOCK PRO v1.7")', "window version")
ui = once(ui, 'title = QLabel("🐆  PUMA STOCK PRO  v1.6")', 'title = QLabel("🐆  PUMA STOCK PRO  v1.7")', "header version")

# ---------- price input: no giant zero list, current-price-centered tick list ----------
price_anchor = "\n\nclass TimeComboBox(NoWheelComboBox):\n"
price_class = r'''

class PriceComboBox(NoWheelComboBox):
    """Price editor with a compact nearby-price dropdown.

    - Blank until a reference/current price is available.
    - Dropdown shows nearby valid KRX-style tick prices instead of 0/100/1000...
    - Mouse wheel never changes the value.
    - Direct typing remains available.
    """
    def __init__(self, value: int = 0, parent=None):
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.NoInsert)
        self._reference = 0
        if self.lineEdit():
            self.lineEdit().setPlaceholderText("직접 입력")
            self.lineEdit().editingFinished.connect(self._normalize_text)
        if int(value or 0) > 0:
            self.set_reference_price(int(value), force=True)

    @staticmethod
    def tick_size(price: int) -> int:
        p = max(0, int(price or 0))
        if p < 2_000:
            return 1
        if p < 5_000:
            return 5
        if p < 20_000:
            return 10
        if p < 50_000:
            return 50
        if p < 200_000:
            return 100
        if p < 500_000:
            return 500
        return 1_000

    @classmethod
    def normalize_price(cls, price: int) -> int:
        p = max(0, int(round(float(price or 0))))
        if p <= 0:
            return 0
        tick = cls.tick_size(p)
        return max(tick, int(round(p / tick)) * tick)

    def value(self) -> int:
        text = self.currentText().replace(",", "").strip()
        if not text:
            return 0
        try:
            return self.normalize_price(int(float(text)))
        except Exception:
            return 0

    def setValue(self, value):
        p = self.normalize_price(value)
        if p <= 0:
            self.setEditText("")
            return
        text = f"{p:,}"
        idx = self.findText(text)
        if idx < 0:
            self.addItem(text, p)
            idx = self.findText(text)
        self.setCurrentIndex(idx)
        self.setEditText(text)

    def set_reference_price(self, price: int, force: bool = False):
        ref = self.normalize_price(price)
        if ref <= 0:
            return
        old = self.value()
        self._reference = ref
        tick = self.tick_size(ref)
        values = []
        for offset in range(-12, 13):
            p = ref + offset * tick
            if p > 0:
                values.append(self.normalize_price(p))
        values = sorted(set(values))

        self.blockSignals(True)
        self.clear()
        for p in values:
            self.addItem(f"{p:,}", p)
        keep = old > 0 and abs(old - ref) / ref <= 0.50 and not force
        self.setValue(old if keep else ref)
        self.blockSignals(False)

    def _normalize_text(self):
        p = self.value()
        if p > 0:
            self.setValue(p)

''' + price_anchor
ui = once(ui, price_anchor, price_class, "PriceComboBox class")

# ---------- app-wide wheel safety net ----------
ui = once(ui,
"""        self.setStyleSheet(DARK)

        self.settings = load_strategy()
""",
"""        self.setStyleSheet(DARK)

        # 최종 안전망: 앱 전체의 숫자/드롭다운 값은 휠로 변경되지 않는다.
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

        self.settings = load_strategy()
""",
"install global wheel filter")

helpers_anchor = """    # ---------- helpers ----------
    def _scroll_wrap(self, widget: QWidget) -> QScrollArea:
"""
helpers_new = """    # ---------- helpers ----------
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel:
            w = obj
            for _ in range(4):
                if isinstance(w, (QComboBox, QAbstractSpinBox)):
                    return True
                try:
                    w = w.parentWidget()
                except Exception:
                    w = None
                if w is None:
                    break
        return super().eventFilter(obj, event)

    def _scroll_wrap(self, widget: QWidget) -> QScrollArea:
"""
ui = once(ui, helpers_anchor, helpers_new, "global wheel event filter")

# ---------- strategy 3 cards: prevent clipped text ----------
ui = once(ui,
"""        self.focus_danta_signal = QLabel("단타 DAY · 5분봉\\n분석 대기")
        self.focus_danta_signal.setAlignment(Qt.AlignCenter)
        self.focus_danta_signal.setStyleSheet("font-size:14px;font-weight:900;color:#f4c95d;background:#122238;border-radius:8px;padding:8px")
        self.focus_swing_signal = QLabel("역매공파 SWING\\n분석 대기")
        self.focus_swing_signal.setAlignment(Qt.AlignCenter)
        self.focus_swing_signal.setStyleSheet("font-size:14px;font-weight:900;color:#f4c95d;background:#122238;border-radius:8px;padding:8px")
        self.focus_bowl_signal = QLabel("밥그릇 3번 LONG\\n분석 대기")
        self.focus_bowl_signal.setAlignment(Qt.AlignCenter)
        self.focus_bowl_signal.setStyleSheet("font-size:14px;font-weight:900;color:#f4c95d;background:#122238;border-radius:8px;padding:8px")
""",
"""        self.focus_danta_signal = QLabel("단타 DAY · 5분봉\\n분석 대기")
        self.focus_swing_signal = QLabel("역매공파 SWING\\n분석 대기")
        self.focus_bowl_signal = QLabel("밥그릇 3번 LONG\\n분석 대기")
        for lab in (self.focus_danta_signal, self.focus_swing_signal, self.focus_bowl_signal):
            lab.setAlignment(Qt.AlignCenter)
            lab.setWordWrap(True)
            lab.setMinimumHeight(112)
            lab.setStyleSheet("font-size:12px;font-weight:900;color:#f4c95d;background:#122238;border-radius:8px;padding:7px")
""",
"strategy cards")
ui = once(ui,
"""        self.focus_stage = QLabel("통합판정: 데이터 대기")
        self.focus_stage.setStyleSheet("font-size:14px;font-weight:900;color:#61ff8f;padding:4px")
        sg.addWidget(self.focus_stage, 1, 0, 1, 3)
        center.addWidget(signals, 1)
""",
"""        self.focus_stage = QLabel("통합판정: 데이터 대기")
        self.focus_stage.setWordWrap(True)
        self.focus_stage.setAlignment(Qt.AlignCenter)
        self.focus_stage.setMinimumHeight(34)
        self.focus_stage.setStyleSheet("font-size:12px;font-weight:900;color:#61ff8f;padding:4px")
        sg.addWidget(self.focus_stage, 1, 0, 1, 3)
        sg.setColumnStretch(0, 1); sg.setColumnStretch(1, 1); sg.setColumnStretch(2, 1)
        signals.setMinimumHeight(170)
        center.addWidget(signals, 2)
""",
"strategy group height")

# ---------- order price widgets ----------
ui = ui.replace("self.focus_order_price = self._spin(0, 2_000_000_000, 0, 100)", "self.focus_order_price = PriceComboBox()")
ui = ui.replace("self.focus_cond_price = self._spin(0, 2_000_000_000, 0, 100)", "self.focus_cond_price = PriceComboBox()")
ui = ui.replace("self.manual_price = self._spin(0, 2_000_000_000, 0, 100)", "self.manual_price = PriceComboBox()")
ui = ui.replace("self.manual_cond_price = self._spin(0, 2_000_000_000, 0, 100)", "self.manual_cond_price = PriceComboBox()")

# Current quote drives compact nearby-price dropdown in BOTH direct-order areas.
ui = once(ui,
"""            if price and hasattr(self, "manual_price") and self.manual_price.value() == 0:
                self.manual_price.setValue(int(price))
            if price and self.focus_order_price.value() == 0:
                self.focus_order_price.setValue(int(price))
""",
"""            if price:
                for widget_name in ("manual_price", "manual_cond_price", "focus_order_price", "focus_cond_price"):
                    widget = getattr(self, widget_name, None)
                    if isinstance(widget, PriceComboBox):
                        widget.set_reference_price(int(price), force=False)
""",
"focus price references")

ui = once(ui,
"""            self.manual_current.setText(f"{price:,.0f} 원")
            if price > 0 and self.manual_price.value() == 0:
                self.manual_price.setValue(int(price))
""",
"""            self.manual_current.setText(f"{price:,.0f} 원")
            if price > 0:
                for widget in (self.manual_price, self.manual_cond_price):
                    widget.set_reference_price(int(price), force=False)
""",
"manual price references")

# Stop-limit validation.
ui = once(ui,
"""        if not code:
            QMessageBox.warning(self, "주문", "종목코드를 입력하세요.")
            return
        if isinstance(self.broker, KiwoomRestBroker) and self.broker.real:
""",
"""        if not code:
            QMessageBox.warning(self, "주문", "종목코드를 입력하세요.")
            return
        if order_type == "stop_limit" and cond <= 0:
            QMessageBox.warning(self, "조건가격", "스톱지정가는 조건가격을 입력하세요.")
            return
        if isinstance(self.broker, KiwoomRestBroker) and self.broker.real:
""",
"manual stop price validation")

# Focus submit has a different prefix; insert validation before live lock.
ui = once(ui,
"""        price = self.focus_order_price.value()
        cond = self.focus_cond_price.value()
        if isinstance(self.broker, KiwoomRestBroker) and self.broker.real:
""",
"""        price = self.focus_order_price.value()
        cond = self.focus_cond_price.value()
        if order_type == "stop_limit" and cond <= 0:
            QMessageBox.warning(self, "조건가격", "스톱지정가는 조건가격을 입력하세요.")
            return
        if isinstance(self.broker, KiwoomRestBroker) and self.broker.real:
""",
"focus stop price validation")

# ---------- compact, non-clipping strategy card text ----------
old_cards = '''            self.focus_danta_signal.setText(
                f"단타 DAY · 5분봉\\n{danta_analysis.stage} · {danta_analysis.score}/100 · {dprob}\\n판단: {djudge}\\n이유: {dreason}"
            )
            self.focus_danta_signal.setStyleSheet(f"font-size:13px;font-weight:900;color:{color};background:#122238;border-radius:8px;padding:7px")
'''
new_cards = '''            dprob_short = str(dprob).split(" (", 1)[0]
            djudge_short = str(djudge).split(" ·", 1)[0]
            dreason_short = dreason if len(dreason) <= 38 else dreason[:38] + "…"
            self.focus_danta_signal.setText(
                f"단타 DAY · 5분봉\\n{danta_analysis.stage} · {danta_analysis.score}/100 · 확률 {dprob_short}\\n판단: {djudge_short}\\n이유: {dreason_short}"
            )
            self.focus_danta_signal.setToolTip(f"확률: {dprob}\\n판단: {djudge}\\n이유: {dreason}")
            self.focus_danta_signal.setStyleSheet(f"font-size:12px;font-weight:900;color:{color};background:#122238;border-radius:8px;padding:7px")
'''
ui = once(ui, old_cards, new_cards, "danta compact card")

old_swing_card = '''            self.focus_swing_signal.setText(
                f"역매공파 SWING\\n{swing_analysis.stage} · {swing_analysis.score}/100 · {sprob}\\n판단: {sjudge}\\n이유: {sreason}"
            )
            self.focus_swing_signal.setStyleSheet("font-size:13px;font-weight:900;color:#62b8ff;background:#122238;border-radius:8px;padding:7px")
'''
new_swing_card = '''            sprob_short = str(sprob).split(" (", 1)[0]
            sjudge_short = str(sjudge).split(" ·", 1)[0]
            sreason_short = sreason if len(sreason) <= 38 else sreason[:38] + "…"
            self.focus_swing_signal.setText(
                f"역매공파 SWING\\n{swing_analysis.stage} · {swing_analysis.score}/100 · 확률 {sprob_short}\\n판단: {sjudge_short}\\n이유: {sreason_short}"
            )
            self.focus_swing_signal.setToolTip(f"확률: {sprob}\\n판단: {sjudge}\\n이유: {sreason}")
            self.focus_swing_signal.setStyleSheet("font-size:12px;font-weight:900;color:#62b8ff;background:#122238;border-radius:8px;padding:7px")
'''
ui = once(ui, old_swing_card, new_swing_card, "swing compact card")

old_bowl_card = '''            self.focus_bowl_signal.setText(
                f"밥그릇 3번 LONG\\n{bowl_analysis.stage} · {bowl_analysis.score}/100 · {bprob}\\n판단: {bjudge}\\n이유: {breason}"
            )
            self.focus_bowl_signal.setStyleSheet("font-size:13px;font-weight:900;color:#d58cff;background:#122238;border-radius:8px;padding:7px")
'''
new_bowl_card = '''            bprob_short = str(bprob).split(" (", 1)[0]
            bjudge_short = str(bjudge).split(" ·", 1)[0]
            breason_short = breason if len(breason) <= 38 else breason[:38] + "…"
            self.focus_bowl_signal.setText(
                f"밥그릇 3번 LONG\\n{bowl_analysis.stage} · {bowl_analysis.score}/100 · 확률 {bprob_short}\\n판단: {bjudge_short}\\n이유: {breason_short}"
            )
            self.focus_bowl_signal.setToolTip(f"확률: {bprob}\\n판단: {bjudge}\\n이유: {breason}")
            self.focus_bowl_signal.setStyleSheet("font-size:12px;font-weight:900;color:#d58cff;background:#122238;border-radius:8px;padding:7px")
'''
ui = once(ui, old_bowl_card, new_bowl_card, "bowl compact card")

# ---------- update text ----------
ui = ui.replace(
    "v1.6: 공개 차트/강의 특징을 바탕으로 PUMA 수박근사 1~3단계 추가, 과거 유사신호 TP/SL 적중률과 PUMA 진입판단 표시, 모든 콤보박스 마우스휠 값변경 차단.",
    "v1.7: 전략3종 카드 잘림 전면 수정, 직접주문 가격 드롭다운을 현재가 주변 호가로 변경, 분봉 기준선26 가시성 강화, 일봉 EMA5 복구, 거래량 확대, 수박형 마커 숫자 제거·가시성 강화, 전역 휠 차단 안전망 추가."
)

# ---------- daily EMA5 ----------
swing = once(swing,
"""    e20 = ema(closes, settings.ema_short)
    e60 = ema(closes, settings.ema_mid)
""",
"""    e5 = ema(closes, 5)
    e20 = ema(closes, settings.ema_short)
    e60 = ema(closes, settings.ema_mid)
""",
"daily ema5 calculation")
swing = once(swing,
"""        'candles': candles,
        'ema20': e20, 'ema60': e60, 'ema112': e112, 'ema224': e224, 'ema448': e448,
""",
"""        'candles': candles,
        'ema5': e5, 'ema20': e20, 'ema60': e60, 'ema112': e112, 'ema224': e224, 'ema448': e448,
""",
"daily ema5 series")

# ---------- chart visual overhaul ----------
chart = once(chart,
"""        vol_h = 70
        watermelon_h = 22
        bottom = 42
""",
"""        vol_h = 86
        watermelon_h = 34
        bottom = 42
""",
"volume/watermelon height")

# More visible volume area labels.
chart = once(chart,
"""        maxvol = max(c['volume'] for c in cs) or 1
        acc_full = self.series.get('acc_flags', [False]*len(candles))
""",
"""        maxvol = max(c['volume'] for c in cs) or 1
        p.setPen(QColor('#91a8bd'))
        p.setFont(QFont('Malgun Gothic', 8, QFont.Bold))
        p.drawText(int(vol_rect.left()+4), int(vol_rect.top()+12), '거래량  ↑빨강 / ↓파랑')
        p.setPen(QPen(QColor('#263d58'), 1))
        p.drawLine(QPointF(vol_rect.left(), vol_rect.top()), QPointF(vol_rect.right(), vol_rect.top()))

        acc_full = self.series.get('acc_flags', [False]*len(candles))
""",
"volume label")

# Watermelon: no numbers; bigger and more recognizable.
wm_start = chart.index("        # PUMA 수박근사:")
wm_end = chart.index("        # 사용자 영웅문 매수 화살표 3종.", wm_start)
wm_block = r'''        # PUMA 수박근사: 숫자 대신 수박 자체의 크기/속/씨앗으로 단계를 구분.
        # 1단=작은 수박, 2단=붉은 속+씨앗, 3단=큰 수박+강조 링.
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
                if stage <= 0 or stage == prev:
                    prev = stage
                    continue
                prev = stage
                xx = x(i)
                cy = watermelon_rect.center().y()
                radius = 8.5 if stage == 1 else (10.5 if stage == 2 else 13.0)

                if stage >= 3:
                    p.setPen(QPen(QColor('#ffd44a'), 2.2))
                    p.setBrush(Qt.NoBrush)
                    p.drawEllipse(QPointF(xx, cy), radius+3.2, radius+3.2)

                p.setPen(QPen(QColor('#08753a'), 2.0))
                p.setBrush(QColor('#35b85c'))
                p.drawEllipse(QPointF(xx, cy), radius, radius)

                inner = radius - 3.0
                p.setPen(Qt.NoPen)
                p.setBrush(QColor('#ff9aa0' if stage == 1 else '#ef4c5b'))
                p.drawEllipse(QPointF(xx, cy), inner, inner)

                seeds = [(-3,-2),(3,-2),(0,3)] if stage == 2 else [(-4,-3),(0,-4),(4,-3),(-2,3),(3,3)]
                if stage >= 2:
                    p.setBrush(QColor('#1c1515'))
                    for dx, dy in seeds:
                        p.drawEllipse(QPointF(xx+dx, cy+dy), 1.0, 1.6)

                p.setBrush(Qt.NoBrush)

''' 
chart = chart[:wm_start] + wm_block + chart[wm_end:]

# 5-line and minute baseline visibility.
chart = once(chart,
"""        colors={
            'ema5':'#f5e145','ema20':'#f2d33c','ema60':'#27d36b','ema112':'#3d9cff',
            'ema224':'#c26cff','ema448':'#8f6b4b','blue':'#2e7cff','kijun':'#f2f2f2'
        }
        widths={'blue':3.0,'ema5':1.2,'kijun':2.0}
        styles={'blue':Qt.DotLine}
        for key in line_keys:
""",
"""        colors={
            'ema5':'#ffd400','ema20':'#f2a900','ema60':'#27d36b','ema112':'#3d9cff',
            'ema224':'#c26cff','ema448':'#8f6b4b','blue':'#2e7cff','kijun':'#ffffff'
        }
        widths={'blue':3.0,'ema5':2.8,'kijun':5.0}
        styles={'blue':Qt.DotLine}
        if 'ema5' in line_keys:
            line_keys = [k for k in line_keys if k != 'ema5'] + ['ema5']
        for key in line_keys:
""",
"ema5/kijun visibility")

chart = chart.replace("'ema5':'EMA5'", "'ema5':'EMA5(5선)'")
chart = chart.replace("'kijun':'PUMA기준선'", "'kijun':'기준선26'")

# ---------- updater ----------
updater = once(updater, 'CURRENT_VERSION = "1.6.0"', 'CURRENT_VERSION = "1.7.0"', "updater version")
updater = updater.replace("PUMA-STOCK-UPDATER/1.6", "PUMA-STOCK-UPDATER/1.7")

ui_path.write_text(ui, encoding="utf-8")
chart_path.write_text(chart, encoding="utf-8")
swing_path.write_text(swing, encoding="utf-8")
updater_path.write_text(updater, encoding="utf-8")
(pkg / "puma_trader" / "__init__.py").write_text('__version__ = "1.7.0"\n', encoding="utf-8")
print("PUMA v1.7 UI/chart/order overhaul applied")
