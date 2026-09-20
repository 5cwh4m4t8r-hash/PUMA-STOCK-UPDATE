from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
pkg = ROOT / "work" / "PUMA_STOCK_PRO_v1.0"
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

def replace_func(text, start_name, next_name, new_block):
    start = text.index(f"    def {start_name}")
    end = text.index(f"    def {next_name}", start)
    return text[:start] + new_block.rstrip() + "\n\n" + text[end:]

# ---------- imports / version ----------
ui = once(ui,
          "from PySide6.QtCore import QTime, QTimer, Qt, QDate, QSettings",
          "from PySide6.QtCore import QTime, QTimer, Qt, QDate, QSettings, QThread, Signal",
          "Qt thread imports")
ui = once(ui,
          "from .danta import analyze_danta\n",
          "from .danta import analyze_danta\nfrom .classification import classify_scores\nfrom .watermelon import build_watermelon\n",
          "v1.1 module imports")
ui = once(ui, 'self.setWindowTitle("PUMA STOCK PRO v1.0")', 'self.setWindowTitle("PUMA STOCK PRO v1.1")', "window version")
ui = once(ui, 'title = QLabel("🐆  PUMA STOCK PRO  v1.0")', 'title = QLabel("🐆  PUMA STOCK PRO  v1.1")', "header version")

# ---------- safer editable dropdown numeric controls ----------
classes_anchor = "\n\nclass MainWindow(QMainWindow):\n"
classes = r'''

class NumericComboBox(QComboBox):
    """Editable numeric dropdown.

    Mouse wheel is intentionally disabled to prevent accidental parameter
    changes. Users can type a value or open the arrow list.
    """
    def __init__(self, lo, hi, value, *, step=None, decimals=0, suffix="", parent=None):
        super().__init__(parent)
        self._lo = float(lo)
        self._hi = float(hi)
        self._decimals = int(decimals)
        self._suffix = str(suffix or "")
        if step is None:
            span = abs(self._hi - self._lo)
            if self._decimals:
                step = 0.05 if span <= 1 else 0.1 if span <= 5 else 0.5 if span <= 25 else 1.0
            else:
                step = 1
        self._step = float(step)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.NoInsert)
        self._populate(float(value))
        self.setValue(value)
        if self.lineEdit():
            self.lineEdit().editingFinished.connect(self._normalize_text)

    def wheelEvent(self, event):
        event.ignore()

    def _fmt(self, value):
        value = max(self._lo, min(self._hi, float(value)))
        if self._decimals <= 0:
            body = f"{int(round(value))}"
        else:
            body = f"{value:.{self._decimals}f}"
        return body + self._suffix

    def _populate(self, current):
        vals = {self._lo, self._hi, max(self._lo, min(self._hi, current))}
        span = self._hi - self._lo
        step = max(abs(self._step), 1e-9)
        count = int(abs(span) / step) if step else 0
        if 0 < count <= 50:
            for i in range(count + 1):
                vals.add(self._lo + i * step)
        else:
            for i in range(-8, 9):
                vals.add(current + i * step)
            # useful "nice" values across large numeric ranges
            for exp in range(-2, 10):
                base = 10 ** exp
                for m in (1, 2, 5):
                    for sign in (-1, 1):
                        vals.add(sign * m * base)
            for frac in (0.1, 0.25, 0.5, 0.75, 0.9):
                vals.add(self._lo + span * frac)
        clean = sorted({v for v in vals if self._lo <= v <= self._hi})
        for v in clean[:120]:
            self.addItem(self._fmt(v))

    def value(self):
        text = self.currentText().strip()
        if self._suffix and text.endswith(self._suffix):
            text = text[:-len(self._suffix)]
        text = text.replace(",", "").strip()
        try:
            value = float(text)
        except Exception:
            value = self._lo
        value = max(self._lo, min(self._hi, value))
        return int(round(value)) if self._decimals <= 0 else float(value)

    def setValue(self, value):
        text = self._fmt(value)
        idx = self.findText(text)
        if idx < 0:
            self.addItem(text)
            idx = self.findText(text)
        self.setCurrentIndex(idx)
        if self.isEditable():
            self.setEditText(text)

    def _normalize_text(self):
        self.setValue(self.value())


class TimeComboBox(QComboBox):
    def __init__(self, initial: QTime, step_minutes: int = 10, parent=None):
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.NoInsert)
        step_minutes = max(1, int(step_minutes))
        for minutes in range(0, 24 * 60, step_minutes):
            self.addItem(f"{minutes // 60:02d}:{minutes % 60:02d}")
        text = initial.toString("HH:mm") if initial and initial.isValid() else "09:00"
        if self.findText(text) < 0:
            self.addItem(text)
        self.setCurrentText(text)

    def wheelEvent(self, event):
        event.ignore()

    def time(self) -> QTime:
        t = QTime.fromString(self.currentText().strip(), "HH:mm")
        return t if t.isValid() else QTime(9, 0)


class NoWheelDateEdit(QDateEdit):
    def wheelEvent(self, event):
        event.ignore()


class CandidateClassifier(QThread):
    resultReady = Signal(str, object)

    def __init__(self, broker, code: str, scan_start: str, scan_end: str, swing_settings, bowl_settings, parent=None):
        super().__init__(parent)
        self.broker = broker
        self.code = code
        self.scan_start = scan_start
        self.scan_end = scan_end
        self.swing_settings = swing_settings
        self.bowl_settings = bowl_settings

    def run(self):
        payload = {"classification": "분석실패", "detail": "-", "danta": 0, "swing": 0, "bowl": 0}
        try:
            minute = self.broker.get_minute_candles(self.code, 5)
            getter = getattr(self.broker, "get_daily_candles", None)
            daily = getter(self.code, max_pages=2) if getter else []
            danta, _ = analyze_danta(minute, daily, scan_start=self.scan_start, scan_end=self.scan_end)
            swing, _ = analyze_swing(daily, self.swing_settings)
            bowl, _ = analyze_bowl(daily, self.bowl_settings)
            label, detail = classify_scores(danta.score, swing.score, bowl.score)
            payload = {
                "classification": label,
                "detail": detail,
                "danta": danta.score,
                "swing": swing.score,
                "bowl": bowl.score,
            }
        except Exception as exc:
            payload["detail"] = str(exc)
        self.resultReady.emit(self.code, payload)
'''
ui = once(ui, classes_anchor, classes + classes_anchor, "input/classifier classes")

# ---------- init state ----------
ui = once(ui,
"""        self.name_lookup_queue: list[str] = []
        self.selected_code: str = ""
""",
"""        self.name_lookup_queue: list[str] = []
        self.classification_queue: list[str] = []
        self.classification_thread: CandidateClassifier | None = None
        self.selected_code: str = ""
""",
"classification state")
ui = once(ui,
"""        self.focus_bowl_analysis = None
        self.focus_minute_raw: list[dict] = []
""",
"""        self.focus_bowl_analysis = None
        self.focus_danta_analysis = None
        self.focus_danta_series = None
        self.focus_minute_raw: list[dict] = []
""",
"danta focus state")

# ---------- main chart mode + condition table classification ----------
ui = once(ui,
"""        self.focus_chart_mode_combo = QComboBox()
        self.focus_chart_mode_combo.addItem("일봉 · 스윙/중장기", "DAY")
        self.focus_chart_mode_combo.currentIndexChanged.connect(self.focus_chart_mode_changed)
""",
"""        self.focus_chart_mode_combo = QComboBox()
        self.focus_chart_mode_combo.addItem("일봉 · 스윙/중장기", "DAY")
        self.focus_chart_mode_combo.addItem("5분봉 · 단타", "MIN")
        self.focus_chart_mode_combo.currentIndexChanged.connect(self.focus_chart_mode_changed)
""",
"main 5m chart mode")
ui = once(ui,
"""        self.focus_range_start = QDateEdit(QDate.currentDate().addYears(-1))
        self.focus_range_end = QDateEdit(QDate.currentDate())
""",
"""        self.focus_range_start = NoWheelDateEdit(QDate.currentDate().addYears(-1))
        self.focus_range_end = NoWheelDateEdit(QDate.currentDate())
""",
"no wheel dates")
ui = once(ui,
"""        self.focus_condition_table = QTableWidget(0, 3)
        self.focus_condition_table.setHorizontalHeaderLabels(["종목", "종목명", "상태"])
""",
"""        self.focus_condition_table = QTableWidget(0, 4)
        self.focus_condition_table.setHorizontalHeaderLabels(["종목", "종목명", "분류", "상태"])
""",
"focus classification column")
ui = once(ui,
"""        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
""",
"""        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)
""",
"focus header sizes")
ui = ui.replace("self.focus_condition_table.setMaximumWidth(340)", "self.focus_condition_table.setMaximumWidth(430)", 1)

# ---------- main 3-strategy summary ----------
old_signals = """        signals = QGroupBox("스윙 · 중장기 동시 분석")
        sg = QGridLayout(signals)
        self.focus_swing_signal = QLabel("역매공파 SWING\\n분석 대기")
        self.focus_swing_signal.setAlignment(Qt.AlignCenter)
        self.focus_swing_signal.setStyleSheet("font-size:14px;font-weight:900;color:#f4c95d;background:#122238;border-radius:8px;padding:8px")
        self.focus_bowl_signal = QLabel("밥그릇 3번 LONG\\n분석 대기")
        self.focus_bowl_signal.setAlignment(Qt.AlignCenter)
        self.focus_bowl_signal.setStyleSheet("font-size:14px;font-weight:900;color:#f4c95d;background:#122238;border-radius:8px;padding:8px")
        sg.addWidget(self.focus_swing_signal, 0, 0)
        sg.addWidget(self.focus_bowl_signal, 0, 1)
        self.focus_stage = QLabel("통합판정: 데이터 대기")
        self.focus_stage.setStyleSheet("font-size:14px;font-weight:900;color:#61ff8f;padding:4px")
        sg.addWidget(self.focus_stage, 1, 0, 1, 2)
        center.addWidget(signals, 1)
"""
new_signals = """        signals = QGroupBox("전략 3종 통합 분석")
        sg = QGridLayout(signals)
        self.focus_danta_signal = QLabel("단타 DAY · 5분봉\\n분석 대기")
        self.focus_danta_signal.setAlignment(Qt.AlignCenter)
        self.focus_danta_signal.setStyleSheet("font-size:14px;font-weight:900;color:#f4c95d;background:#122238;border-radius:8px;padding:8px")
        self.focus_swing_signal = QLabel("역매공파 SWING\\n분석 대기")
        self.focus_swing_signal.setAlignment(Qt.AlignCenter)
        self.focus_swing_signal.setStyleSheet("font-size:14px;font-weight:900;color:#f4c95d;background:#122238;border-radius:8px;padding:8px")
        self.focus_bowl_signal = QLabel("밥그릇 3번 LONG\\n분석 대기")
        self.focus_bowl_signal.setAlignment(Qt.AlignCenter)
        self.focus_bowl_signal.setStyleSheet("font-size:14px;font-weight:900;color:#f4c95d;background:#122238;border-radius:8px;padding:8px")
        sg.addWidget(self.focus_danta_signal, 0, 0)
        sg.addWidget(self.focus_swing_signal, 0, 1)
        sg.addWidget(self.focus_bowl_signal, 0, 2)
        self.focus_stage = QLabel("통합판정: 데이터 대기")
        self.focus_stage.setStyleSheet("font-size:14px;font-weight:900;color:#61ff8f;padding:4px")
        sg.addWidget(self.focus_stage, 1, 0, 1, 3)
        center.addWidget(signals, 1)
"""
ui = once(ui, old_signals, new_signals, "three strategy summary")

# ---------- main right analysis gets Danta summary ----------
analysis_anchor = """        stagebox = QGroupBox("역매공파 SWING 진행상태")
"""
danta_box = """        dantabox = QGroupBox("단타 DAY · 5분봉")
        dg = QGridLayout(dantabox)
        self.focus_danta_labels = {}
        danta_names = ["패턴 점수", "검색 시간", "PUMA 기준선(26)", "EMA 5·20·60", "현재 5분봉 거래량", "최근 고점 돌파", "눌림 지지"]
        for i, name in enumerate(danta_names):
            a = QLabel(name)
            b = QLabel("대기")
            b.setWordWrap(True)
            b.setStyleSheet("font-weight:800;color:#f4c95d")
            dg.addWidget(a, i, 0)
            dg.addWidget(b, i, 1)
            self.focus_danta_labels[name] = b
        open_danta = QPushButton("단타 상세 분석 열기")
        open_danta.clicked.connect(lambda: self.tabs.setCurrentWidget(self.strategy_widget))
        dg.addWidget(open_danta, len(danta_names), 0, 1, 2)
        av.addWidget(dantabox)

"""
ui = once(ui, analysis_anchor, danta_box + analysis_anchor, "danta main analysis")

# ---------- time controls become dropdowns ----------
ui = ui.replace('self.scan_start = QTimeEdit(QTime.fromString(self.settings.scan_start, "HH:mm"))',
                'self.scan_start = TimeComboBox(QTime.fromString(self.settings.scan_start, "HH:mm"), 10)')
ui = ui.replace('self.scan_end = QTimeEdit(QTime.fromString(self.settings.scan_end, "HH:mm"))',
                'self.scan_end = TimeComboBox(QTime.fromString(self.settings.scan_end, "HH:mm"), 10)')
ui = ui.replace('self.force_exit_time = QTimeEdit(QTime.fromString(self.settings.force_exit_time, "HH:mm"))',
                'self.force_exit_time = TimeComboBox(QTime.fromString(self.settings.force_exit_time, "HH:mm"), 10)')

# ---------- detailed Danta chart gets PUMA watermelon band ----------
ui = once(ui,
"""            self.danta_analysis = result
            self.danta_series = series
            lines = {k: v for k, v in series.items() if k != "candles"}
""",
"""            self.danta_analysis = result
            series["watermelon"] = build_watermelon(series["candles"])
            self.danta_series = series
            lines = {k: v for k, v in series.items() if k != "candles"}
""",
"danta watermelon detail")

# ---------- numeric controls ----------
old_numeric = """    def _dspin(self, lo, hi, val, suffix=""):
        x = QDoubleSpinBox()
        x.setRange(lo, hi)
        x.setDecimals(2)
        x.setValue(val)
        x.setSuffix(suffix)
        return x

    def _spin(self, lo, hi, val, step=1):
        x = QSpinBox()
        x.setRange(lo, hi)
        x.setSingleStep(step)
        x.setValue(val)
        return x
"""
new_numeric = """    def _dspin(self, lo, hi, val, suffix=""):
        return NumericComboBox(lo, hi, val, decimals=2, suffix=suffix)

    def _spin(self, lo, hi, val, step=1):
        return NumericComboBox(lo, hi, val, step=step, decimals=0)
"""
ui = once(ui, old_numeric, new_numeric, "numeric dropdown controls")

# ---------- condition table columns ----------
ui = once(ui,
"""        self.condition_table = QTableWidget(0, 5)
        self.condition_table.setHorizontalHeaderLabels(["종목코드", "종목명", "상태", "편입시각", "분석·매매"])
""",
"""        self.condition_table = QTableWidget(0, 6)
        self.condition_table.setHorizontalHeaderLabels(["종목코드", "종목명", "분류", "상태", "편입시각", "분석·매매"])
""",
"full condition classification")

# Clear all related views/queues on condition restart.
ui = once(ui,
"""        self.condition_candidates.clear()
        self.condition_table.setRowCount(0)
        self.save_settings_silent()
""",
"""        self.condition_candidates.clear()
        self.condition_table.setRowCount(0)
        if hasattr(self, "focus_condition_table"):
            self.focus_condition_table.setRowCount(0)
        self.classification_queue.clear()
        self.save_settings_silent()
""",
"clear condition views")

# Initialize/queue classification on snapshot and new entry.
ui = once(ui,
"""            self.condition_candidates[code] = {"name": name or code, "active": True, "entered_at": now, "entry_event": False}
            self._upsert_condition_row(code)
            self._ensure_market_row(code, name or code, "영웅문4")
""",
"""            self.condition_candidates[code] = {"name": name or code, "active": True, "entered_at": now, "entry_event": False, "classification": "분석중", "class_detail": "-"}
            self._upsert_condition_row(code)
            self._ensure_market_row(code, name or code, "영웅문4")
            self._queue_candidate_classification(code)
""",
"snapshot classification")
ui = once(ui,
"""        self.condition_candidates[code] = {"name": name or old_name or code, "active": True, "entered_at": now, "entry_event": True}
        self._upsert_condition_row(code)
        self._ensure_market_row(code, name or old_name or code, "영웅문4")
""",
"""        self.condition_candidates[code] = {"name": name or old_name or code, "active": True, "entered_at": now, "entry_event": True, "classification": "분석중", "class_detail": "-"}
        self._upsert_condition_row(code)
        self._ensure_market_row(code, name or old_name or code, "영웅문4")
        self._queue_candidate_classification(code)
""",
"entry classification")

# ---------- replace upsert + add classification methods ----------
new_upsert = r'''    def _classification_color(self, label: str) -> QColor:
        label = str(label or "")
        if "단타" in label and "스윙" in label:
            return QColor("#d58cff")
        if label.startswith("단타"):
            return QColor("#61d4ff")
        if label.startswith("스윙"):
            return QColor("#61ff8f")
        if "중장기" in label:
            return QColor("#d58cff")
        if label == "분석중":
            return QColor("#8fa5bc")
        return QColor("#f4c95d")

    def _set_candidate_classification(self, code: str, classification: str, detail: str = "-", scores: dict | None = None):
        item = self.condition_candidates.get(code)
        if item is None:
            return
        item["classification"] = classification
        item["class_detail"] = detail
        if scores:
            item["scores"] = dict(scores)
        self._upsert_condition_row(code)

    def _queue_candidate_classification(self, code: str):
        code = str(code).strip()
        if not code or code in self.classification_queue:
            return
        if not isinstance(self.broker, KiwoomRestBroker) or not self.broker.token:
            return
        if self.classification_thread is not None and self.classification_thread.isRunning():
            if getattr(self.classification_thread, "code", "") == code:
                return
        self.classification_queue.append(code)
        self._start_next_candidate_classification()

    def _start_next_candidate_classification(self):
        if self.classification_thread is not None and self.classification_thread.isRunning():
            return
        while self.classification_queue:
            code = self.classification_queue.pop(0)
            item = self.condition_candidates.get(code)
            if not item or not item.get("active"):
                continue
            worker = CandidateClassifier(
                self.broker,
                code,
                self.scan_start.time().toString("HH:mm"),
                self.scan_end.time().toString("HH:mm"),
                self.swing_settings,
                self.bowl_settings,
                self,
            )
            worker.resultReady.connect(self._on_candidate_classified)
            worker.finished.connect(self._candidate_classifier_finished)
            self.classification_thread = worker
            worker.start()
            return

    def _on_candidate_classified(self, code: str, payload: object):
        data = payload if isinstance(payload, dict) else {}
        self._set_candidate_classification(
            code,
            str(data.get("classification") or "분석실패"),
            str(data.get("detail") or "-"),
            {"danta": data.get("danta", 0), "swing": data.get("swing", 0), "bowl": data.get("bowl", 0)},
        )

    def _candidate_classifier_finished(self):
        self.classification_thread = None
        QTimer.singleShot(80, self._start_next_candidate_classification)

    def _upsert_condition_row(self, code: str):
        item = self.condition_candidates.get(code, {})
        classification = str(item.get("classification") or "분석중")
        detail = str(item.get("class_detail") or "-")

        row = None
        for r in range(self.condition_table.rowCount()):
            if self.condition_table.item(r, 0).text() == code:
                row = r
                break
        if row is None:
            row = self.condition_table.rowCount()
            self.condition_table.insertRow(row)
            for c in range(6):
                self.condition_table.setItem(row, c, QTableWidgetItem(""))

        display_name = item.get("name", "")
        self.condition_table.item(row, 0).setText(code)
        self.condition_table.item(row, 1).setText(display_name if display_name and display_name != code else "조회중...")
        self.condition_table.item(row, 2).setText(classification)
        self.condition_table.item(row, 2).setToolTip(detail)
        self.condition_table.item(row, 2).setForeground(self._classification_color(classification))
        self.condition_table.item(row, 3).setText("편입" if item.get("active") else "이탈")
        self.condition_table.item(row, 4).setText(item.get("entered_at", "-"))
        self.condition_table.item(row, 5).setText("▶ 클릭해서 열기")
        self.condition_table.item(row, 5).setForeground(QColor("#62b8ff"))

        if hasattr(self, "focus_condition_table"):
            frow = None
            for rr in range(self.focus_condition_table.rowCount()):
                if self.focus_condition_table.item(rr, 0).text() == code:
                    frow = rr
                    break
            if frow is None:
                frow = self.focus_condition_table.rowCount()
                self.focus_condition_table.insertRow(frow)
                for cc in range(4):
                    self.focus_condition_table.setItem(frow, cc, QTableWidgetItem(""))
            self.focus_condition_table.item(frow, 0).setText(code)
            self.focus_condition_table.item(frow, 1).setText(display_name if display_name and display_name != code else "조회중...")
            self.focus_condition_table.item(frow, 2).setText(classification)
            self.focus_condition_table.item(frow, 2).setToolTip(detail)
            self.focus_condition_table.item(frow, 2).setForeground(self._classification_color(classification))
            self.focus_condition_table.item(frow, 3).setText("편입" if item.get("active") else "이탈")
'''
ui = replace_func(ui, "_upsert_condition_row(self, code: str):", "_focus_condition_row_clicked(self, row: int, column: int):", new_upsert)

# ---------- full focus refresh: Danta + swing + bowl all integrated ----------
new_focus_refresh = r'''    def focus_refresh(self):
        code = self.selected_code
        if not code:
            return
        try:
            self.focus_origin.setText("시세·5분봉·과거 일봉·3전략을 불러오는 중...")
            QApplication.processEvents()
            name = self.selected_name or code
            price = 0.0
            if isinstance(self.broker, KiwoomRestBroker):
                info = self.broker.get_stock_info(code)
                name = str(info.get("stk_nm") or self.name_cache.get(code) or name).strip()
                price = abs(float(str(info.get("cur_prc", 0)).replace(",", "") or 0))
                if name and name != code:
                    self.name_cache[code] = name
                    self.selected_name = name
                    if code in self.condition_candidates:
                        self.condition_candidates[code]["name"] = name
                        self._upsert_condition_row(code)
                    self._ensure_market_row(code, name, self._source_for_code(code))

            self.selected_name = name or self.selected_name or code
            self.focus_title.setText(f"{self.selected_name}  {code}")
            self.focus_price.setText(f"{price:,.0f} 원" if price else "-")
            self._sync_selected_stock_everywhere()
            if hasattr(self, "manual_current"):
                self.manual_current.setText(f"{price:,.0f} 원" if price else "-")
            if price and hasattr(self, "manual_price") and self.manual_price.value() == 0:
                self.manual_price.setValue(int(price))
            if price and self.focus_order_price.value() == 0:
                self.focus_order_price.setValue(int(price))

            # 5분봉 단타 데이터
            try:
                minute = self.broker.get_minute_candles(code, 5)
                self.focus_minute_raw = minute or []
            except Exception:
                self.focus_minute_raw = []

            # 일봉 스윙/중장기 데이터
            daily_rows = []
            swing_analysis = None
            bowl_analysis = None
            getter = getattr(self.broker, "get_daily_candles", None)
            if getter:
                daily_rows = getter(code, max_pages=self.focus_history_pages) or []
                if daily_rows:
                    self.focus_daily_raw = daily_rows
                    swing_analysis, swing_series = analyze_swing(daily_rows, self._swing_settings_from_ui())
                    bowl_analysis, _ = analyze_bowl(daily_rows, self.bowl_settings)
                    swing_series = dict(swing_series)
                    swing_series["watermelon"] = build_watermelon(swing_series.get("candles", []))
                    self.focus_daily_analysis = swing_analysis
                    self.focus_daily_series = swing_series
                    self.focus_bowl_analysis = bowl_analysis
                    self._set_focus_date_bounds()

            # 단타 분석은 메인에도 요약, 상세 탭에도 그대로 유지
            danta_analysis = None
            if self.focus_minute_raw:
                try:
                    danta_analysis, danta_series = analyze_danta(
                        self.focus_minute_raw,
                        daily_rows,
                        scan_start=self.scan_start.time().toString("HH:mm"),
                        scan_end=self.scan_end.time().toString("HH:mm"),
                    )
                    danta_series = dict(danta_series)
                    danta_series["watermelon"] = build_watermelon(danta_series.get("candles", []))
                    self.focus_danta_analysis = danta_analysis
                    self.focus_danta_series = danta_series
                except Exception:
                    self.focus_danta_analysis = None
                    self.focus_danta_series = None

            self._apply_focus_analyses(danta_analysis, swing_analysis, bowl_analysis, "전체")

            # 조건검색 표의 단타/스윙/중장기 분류도 선택 종목 분석 결과로 즉시 갱신
            if code in self.condition_candidates and (danta_analysis or swing_analysis or bowl_analysis):
                ds = getattr(danta_analysis, "score", 0) if danta_analysis else 0
                ss = getattr(swing_analysis, "score", 0) if swing_analysis else 0
                bs = getattr(bowl_analysis, "score", 0) if bowl_analysis else 0
                label, detail = classify_scores(ds, ss, bs)
                self._set_candidate_classification(code, label, detail, {"danta": ds, "swing": ss, "bowl": bs})

            self._update_focus_chart(False)
            day_count = len(self.focus_daily_series.get("candles", [])) if self.focus_daily_series else 0
            self.focus_origin.setText(
                f"유입: {self._source_for_code(code)} · 일봉 {day_count}봉 · 단타/스윙/중장기 연동 · "
                f"마지막 갱신 {datetime.now().strftime('%H:%M:%S')}"
            )
        except Exception as exc:
            self.focus_origin.setText("불러오기 실패")
            QMessageBox.critical(self, "종목 분석 실패", str(exc))
'''
ui = replace_func(ui, "focus_refresh(self):", "_set_focus_date_bounds(self):", new_focus_refresh)

# ---------- minute chart series uses Danta lines/watermelon ----------
new_minute_series = r'''    def _minute_chart_series(self):
        if self.focus_danta_series and self.focus_danta_series.get("candles"):
            candles = self.focus_danta_series["candles"]
            return candles, {k: v for k, v in self.focus_danta_series.items() if k != "candles"}
        candles = normalize_candles(self.focus_minute_raw or [])
        closes = [c["close"] for c in candles]
        return candles, {
            "ema5": ema(closes, 5),
            "ema20": ema(closes, 20),
            "ema60": ema(closes, 60),
            "watermelon": build_watermelon(candles),
        }
'''
ui = replace_func(ui, "_minute_chart_series(self):", "_update_focus_chart(self, preserve_view: bool = True):", new_minute_series)

# ---------- range analysis keeps Danta summary visible ----------
ui = ui.replace("self._apply_focus_analyses(sa, ba, label)", "self._apply_focus_analyses(self.focus_danta_analysis, sa, ba, label)")
ui = ui.replace("self._apply_focus_analyses(self.focus_daily_analysis, self.focus_bowl_analysis, \"전체\")",
                "self._apply_focus_analyses(self.focus_danta_analysis, self.focus_daily_analysis, self.focus_bowl_analysis, \"전체\")")

# ---------- unified three-analysis renderer ----------
new_apply = r'''    def _apply_focus_analyses(self, danta_analysis, swing_analysis, bowl_analysis, label: str):
        if danta_analysis:
            color = "#61ff8f" if danta_analysis.candidate else ("#62b8ff" if danta_analysis.score >= 55 else "#f4c95d")
            self.focus_danta_signal.setText(f"단타 DAY · 5분봉\n{danta_analysis.stage} · {danta_analysis.score}/100")
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
            self.focus_swing_signal.setText(f"역매공파 SWING\n{swing_analysis.stage} · {swing_analysis.score}/100")
            self.focus_swing_signal.setStyleSheet("font-size:14px;font-weight:900;color:#62b8ff;background:#122238;border-radius:8px;padding:8px")
            for key, lab in self.focus_stage_labels.items():
                text = swing_analysis.details.get(key, "-")
                lab.setText(text)
                good = any(x in text for x in ("확인","감지")) and "미확인" not in text
                near = key == "파란점선" and getattr(swing_analysis, "blue_near", False)
                lab.setStyleSheet(f"font-weight:800;color:{'#61ff8f' if (good or near) else '#f4c95d'}")

        if bowl_analysis:
            self.focus_bowl_signal.setText(f"밥그릇 3번 LONG\n{bowl_analysis.stage} · {bowl_analysis.score}/100")
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
ui = replace_func(ui, "_apply_focus_analyses(self, swing_analysis, bowl_analysis, label: str):", "focus_submit(self, side: str):", new_apply)

# save_swing_and_reanalyze signature update call
ui = ui.replace("self._apply_focus_analyses(sa, self.focus_bowl_analysis, \"전체\")",
                "self._apply_focus_analyses(self.focus_danta_analysis, sa, self.focus_bowl_analysis, \"전체\")")

# ---------- update note ----------
ui = ui.replace(
    "v1.0: 전 화면 레이아웃 재구성, 메인 우측 기능탭, 단타 설정 탭화, 해상도 자동배치/분할비율 저장, 역매공파 설정 영구저장.",
    "v1.1: 조건검색 단타/스윙/중장기 자동분류, 메인에 단타 분석 재통합, 차트 하단 PUMA 수박형 밴드, 숫자 입력을 휠 없는 직접입력+드롭다운 방식으로 변경."
)

# ---------- close classifier cleanly ----------
ui = once(ui,
"""    def closeEvent(self, event):
        self._save_ui_layout()
        self.stop_auto()
        self.stop_condition_stream()
        event.accept()
""",
"""    def closeEvent(self, event):
        self._save_ui_layout()
        self.stop_auto()
        self.stop_condition_stream()
        self.classification_queue.clear()
        worker = self.classification_thread
        if worker is not None and worker.isRunning():
            worker.wait(1200)
        event.accept()
""",
"classifier close")

# ---------- chart: PUMA watermelon bottom band ----------
chart = chart.replace("v0.6: 마우스 휠 확대/축소, 좌우 드래그 과거 탐색, 선택 분석구간 강조,",
                      "v1.1: 마우스 휠 확대/축소, 좌우 드래그 과거 탐색, 선택 분석구간 강조,")
chart = once(chart,
"""        left, right, top = 60, 25, 28
        vol_h = 82
        bottom = 42
        price_rect = QRectF(left, top, self.width()-left-right, self.height()-top-bottom-vol_h)
        vol_rect = QRectF(left, price_rect.bottom()+8, price_rect.width(), vol_h-8)
""",
"""        left, right, top = 60, 25, 28
        vol_h = 72
        watermelon_h = 13
        bottom = 54
        price_rect = QRectF(left, top, self.width()-left-right, self.height()-top-bottom-vol_h)
        vol_rect = QRectF(left, price_rect.bottom()+7, price_rect.width(), vol_h-12)
        watermelon_rect = QRectF(left, vol_rect.bottom()+4, price_rect.width(), watermelon_h)
""",
"chart geometry")
chart = once(chart,
"""        line_keys = [k for k in self.series.keys() if k not in ('candles','acc_flags','acc_meta','box') and isinstance(self.series.get(k), list)]
""",
"""        line_keys = [k for k in self.series.keys() if k not in ('candles','acc_flags','acc_meta','box','watermelon') and isinstance(self.series.get(k), list)]
""",
"exclude watermelon line")
chart = once(chart,
"""            vh=vol_rect.height()*c['volume']/maxvol; p.fillRect(QRectF(xx-cw/2,vol_rect.bottom()-vh,cw,vh),QColor(col.red(),col.green(),col.blue(),170))

        colors={
""",
"""            vh=vol_rect.height()*c['volume']/maxvol; p.fillRect(QRectF(xx-cw/2,vol_rect.bottom()-vh,cw,vh),QColor(col.red(),col.green(),col.blue(),170))

        # PUMA 수박형 밴드: 화면 전체를 칠하지 않고 신호 주변의 짧은 구간만 표시.
        water_full = self.series.get('watermelon', [])
        if isinstance(water_full, list) and water_full:
            water = water_full[start:end]
            step_w = price_rect.width() / max(1, n)
            p.setFont(QFont('Malgun Gothic', 7, QFont.Bold))
            p.setPen(QColor('#8aa0b8'))
            p.drawText(5, int(watermelon_rect.bottom()), '수박')
            for i, state in enumerate(water):
                if state not in (-1, 1):
                    continue
                xx = x(i)
                col = QColor('#38d878') if state > 0 else QColor('#ef5965')
                p.fillRect(QRectF(xx-step_w/2, watermelon_rect.top(), step_w+1, watermelon_rect.height()), col)

        colors={
""",
"paint watermelon")
chart = once(chart,
"""            p.drawText(int(x(j)-35), int(vol_rect.bottom()+22), 75, 18, Qt.AlignCenter, txt)
""",
"""            p.drawText(int(x(j)-35), int(watermelon_rect.bottom()+5), 75, 18, Qt.AlignCenter, txt)
""",
"x label below watermelon")

# ---------- version ----------
updater = once(updater, 'CURRENT_VERSION = "1.0.0"', 'CURRENT_VERSION = "1.1.0"', "updater version")
updater = updater.replace("PUMA-STOCK-UPDATER/1.0", "PUMA-STOCK-UPDATER/1.1")

ui_path.write_text(ui, encoding="utf-8")
chart_path.write_text(chart, encoding="utf-8")
updater_path.write_text(updater, encoding="utf-8")
(pkg / "puma_trader" / "__init__.py").write_text('__version__ = "1.1.0"\n', encoding="utf-8")
print("PUMA v1.1 integration patch applied")
