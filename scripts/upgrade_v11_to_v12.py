from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
pkg = ROOT / "work" / "PUMA_STOCK_PRO_v1.1"
ui_path = pkg / "puma_trader" / "ui.py"
chart_path = pkg / "puma_trader" / "swing_chart.py"
broker_path = pkg / "puma_trader" / "broker.py"
updater_path = pkg / "puma_trader" / "updater.py"

ui = ui_path.read_text(encoding="utf-8")
chart = chart_path.read_text(encoding="utf-8")
broker = broker_path.read_text(encoding="utf-8")
updater = updater_path.read_text(encoding="utf-8")

def once(text, old, new, label):
    if old not in text:
        raise RuntimeError(f"target not found: {label}")
    return text.replace(old, new, 1)

def replace_func(text, start_name, next_name, new_block):
    start = text.index(f"    def {start_name}")
    end = text.index(f"    def {next_name}", start)
    return text[:start] + new_block.rstrip() + "\n\n" + text[end:]

# ---------- version / imports ----------
ui = once(
    ui,
    "from .danta import analyze_danta\n",
    "from .danta import analyze_danta, analyze_danta_for_date, available_minute_dates, slice_series_for_date\n",
    "date-aware danta imports",
)
ui = once(ui, 'self.setWindowTitle("PUMA STOCK PRO v1.1")', 'self.setWindowTitle("PUMA STOCK PRO v1.2")', "window version")
ui = once(ui, 'title = QLabel("🐆  PUMA STOCK PRO  v1.1")', 'title = QLabel("🐆  PUMA STOCK PRO  v1.2")', "header version")

# ---------- state ----------
ui = once(
    ui,
    """        self.focus_danta_series = None
        self.focus_minute_raw: list[dict] = []
        self.focus_chart_mode = "DAY"
""",
    """        self.focus_danta_series = None
        self.focus_minute_raw: list[dict] = []
        self.intraday_days: list[str] = []
        self.intraday_selected_day: str = ""
        self.danta_raw_minute: list[dict] = []
        self.danta_raw_daily: list[dict] = []
        self.danta_cache_code: str = ""
        self.focus_chart_mode = "DAY"
""",
    "intraday date state",
)

# ---------- main chart date selector ----------
old_mode = """        self.focus_chart_mode_combo = QComboBox()
        self.focus_chart_mode_combo.addItem("일봉 · 스윙/중장기", "DAY")
        self.focus_chart_mode_combo.addItem("5분봉 · 단타", "MIN")
        self.focus_chart_mode_combo.currentIndexChanged.connect(self.focus_chart_mode_changed)
        tools.addWidget(self.focus_chart_mode_combo)
"""
new_mode = """        self.focus_chart_mode_combo = QComboBox()
        self.focus_chart_mode_combo.addItem("일봉 · 스윙/중장기", "DAY")
        self.focus_chart_mode_combo.addItem("5분봉 · 단타", "MIN")
        self.focus_chart_mode_combo.currentIndexChanged.connect(self.focus_chart_mode_changed)
        tools.addWidget(self.focus_chart_mode_combo)

        tools.addWidget(QLabel("단타 날짜"))
        self.focus_intraday_date_combo = QComboBox()
        self.focus_intraday_date_combo.addItem("전체 · 날짜 구분", "")
        self.focus_intraday_date_combo.setMinimumWidth(145)
        self.focus_intraday_date_combo.setEnabled(False)
        self.focus_intraday_date_combo.currentIndexChanged.connect(self.focus_intraday_date_changed)
        tools.addWidget(self.focus_intraday_date_combo)

        prev_day = QPushButton("◀ 전일")
        next_day = QPushButton("다음일 ▶")
        prev_day.clicked.connect(lambda: self._step_intraday_day(-1))
        next_day.clicked.connect(lambda: self._step_intraday_day(1))
        self.focus_intraday_prev_btn = prev_day
        self.focus_intraday_next_btn = next_day
        prev_day.setEnabled(False)
        next_day.setEnabled(False)
        tools.addWidget(prev_day)
        tools.addWidget(next_day)
"""
ui = once(ui, old_mode, new_mode, "main date selector")

# ---------- detailed Danta date selector ----------
old_head = """        refresh = QPushButton("↻ 단타 즉시 분석")
        refresh.setObjectName("conditionBtn")
        refresh.clicked.connect(self.strategy_refresh_selected)
        head.addWidget(self.strategy_selected_label)
        head.addWidget(self.strategy_signal_label)
        head.addStretch()
        head.addWidget(refresh)
        outer.addLayout(head)
"""
new_head = """        refresh = QPushButton("↻ 단타 즉시 분석")
        refresh.setObjectName("conditionBtn")
        refresh.clicked.connect(self.strategy_refresh_selected)
        self.danta_date_combo = QComboBox()
        self.danta_date_combo.addItem("전체 · 날짜 구분", "")
        self.danta_date_combo.setMinimumWidth(145)
        self.danta_date_combo.currentIndexChanged.connect(self.danta_intraday_date_changed)
        dprev = QPushButton("◀ 전일")
        dnext = QPushButton("다음일 ▶")
        dprev.clicked.connect(lambda: self._step_intraday_day(-1))
        dnext.clicked.connect(lambda: self._step_intraday_day(1))
        head.addWidget(self.strategy_selected_label)
        head.addWidget(self.strategy_signal_label)
        head.addStretch()
        head.addWidget(QLabel("날짜"))
        head.addWidget(self.danta_date_combo)
        head.addWidget(dprev)
        head.addWidget(dnext)
        head.addWidget(refresh)
        outer.addLayout(head)
"""
ui = once(ui, old_head, new_head, "danta date selector")

ui = ui.replace(
    "5분봉 고정 · PUMA 기준선(26) · 장초반 거래량 · EMA 5/20/60 · 돌파/눌림을 함께 판정합니다.",
    "5분봉 고정 · 거래일별 선택/복기 · PUMA 기준선(26) · 장초반 거래량 · EMA 5/20/60 · 돌파/눌림을 함께 판정합니다.",
    1,
)

# ---------- date helper methods before selected-stock sync ----------
anchor = """    def _sync_selected_stock_everywhere(self):
"""
helpers = r'''    @staticmethod
    def _pretty_intraday_day(day: str) -> str:
        s = "".join(ch for ch in str(day or "") if ch.isdigit())[:8]
        if len(s) == 8:
            return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
        return str(day or "")

    def _populate_intraday_dates(self, rows):
        days = available_minute_dates(rows or [])
        self.intraday_days = days
        current = self.intraday_selected_day if self.intraday_selected_day in days else ""

        for combo_name in ("focus_intraday_date_combo", "danta_date_combo"):
            combo = getattr(self, combo_name, None)
            if combo is None:
                continue
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("전체 · 날짜 구분", "")
            for day in reversed(days):
                combo.addItem(self._pretty_intraday_day(day), day)
            idx = combo.findData(current)
            combo.setCurrentIndex(idx if idx >= 0 else 0)
            combo.blockSignals(False)

        self.intraday_selected_day = current
        enabled = bool(days)
        if hasattr(self, "focus_intraday_prev_btn"):
            self.focus_intraday_prev_btn.setEnabled(enabled and self.focus_chart_mode == "MIN")
        if hasattr(self, "focus_intraday_next_btn"):
            self.focus_intraday_next_btn.setEnabled(enabled and self.focus_chart_mode == "MIN")

    def _sync_intraday_date_combos(self, day: str):
        day = day if day in self.intraday_days else ""
        self.intraday_selected_day = day
        for combo_name in ("focus_intraday_date_combo", "danta_date_combo"):
            combo = getattr(self, combo_name, None)
            if combo is None:
                continue
            combo.blockSignals(True)
            idx = combo.findData(day)
            combo.setCurrentIndex(idx if idx >= 0 else 0)
            combo.blockSignals(False)

    def _step_intraday_day(self, delta: int):
        if not self.intraday_days:
            return
        day = self.intraday_selected_day
        if day not in self.intraday_days:
            # 전체 보기에서 전일은 직전 거래일, 다음일은 최신 거래일로 진입.
            idx = len(self.intraday_days) - 1
            if delta < 0 and len(self.intraday_days) >= 2:
                idx -= 1
        else:
            idx = self.intraday_days.index(day)
            idx = max(0, min(len(self.intraday_days) - 1, idx + int(delta)))
        self._sync_intraday_date_combos(self.intraday_days[idx])
        self._refresh_focus_danta_date()
        if self.tabs.currentWidget() is getattr(self, "strategy_widget", None):
            self._render_danta_detail_from_cache()

    def focus_intraday_date_changed(self):
        combo = getattr(self, "focus_intraday_date_combo", None)
        if combo is None:
            return
        day = str(combo.currentData() or "")
        self._sync_intraday_date_combos(day)
        self._refresh_focus_danta_date()
        self._update_focus_chart(False)

    def danta_intraday_date_changed(self):
        combo = getattr(self, "danta_date_combo", None)
        if combo is None:
            return
        day = str(combo.currentData() or "")
        self._sync_intraday_date_combos(day)
        self._refresh_focus_danta_date()
        if self.danta_cache_code == self.selected_code and self.danta_raw_minute:
            self._render_danta_detail_from_cache()
        elif self.selected_code:
            self.strategy_refresh_selected()

    def _refresh_focus_danta_date(self):
        if not self.focus_minute_raw:
            return
        try:
            result, series, day = analyze_danta_for_date(
                self.focus_minute_raw,
                self.focus_daily_raw,
                self.intraday_selected_day or None,
                scan_start=self.scan_start.time().toString("HH:mm"),
                scan_end=self.scan_end.time().toString("HH:mm"),
            )
            series = dict(series)
            series["watermelon"] = build_watermelon(series.get("candles", []))
            self.focus_danta_analysis = result
            self.focus_danta_series = series
            label = self._pretty_intraday_day(day)
            if not self.intraday_selected_day:
                label = f"최신 {label}"
            self._apply_focus_analyses(result, self.focus_daily_analysis, self.focus_bowl_analysis, label)
        except Exception as exc:
            self.focus_danta_signal.setText(f"단타 DAY · 5분봉\n날짜 분석 실패: {exc}")

    def _render_danta_detail_from_cache(self):
        if not self.danta_raw_minute:
            return
        name = self.selected_name or self.selected_code
        try:
            result, series, day = analyze_danta_for_date(
                self.danta_raw_minute,
                self.danta_raw_daily,
                self.intraday_selected_day or None,
                scan_start=self.scan_start.time().toString("HH:mm"),
                scan_end=self.scan_end.time().toString("HH:mm"),
            )
            series = dict(series)
            series["watermelon"] = build_watermelon(series.get("candles", []))
            self.danta_analysis = result
            self.danta_series = series

            chart_series = series
            if self.intraday_selected_day:
                chart_series = slice_series_for_date(series, day)
            candles = chart_series.get("candles", [])
            lines = {k: v for k, v in chart_series.items() if k != "candles"}
            day_label = self._pretty_intraday_day(day)
            title_suffix = day_label if self.intraday_selected_day else f"전체 · 최신분석 {day_label}"
            self.danta_chart.set_basic_data(
                candles,
                lines,
                title=f"{name} {self.selected_code} · 5분봉 · {title_suffix}",
                preserve_view=False,
            )

            self.danta_score_label.setText(f"패턴 {result.score} / 100")
            self.danta_stage_label.setText(f"{day_label} · {result.stage}")
            color = "#61ff8f" if result.candidate else ("#62b8ff" if result.score >= 55 else "#f4c95d")
            self.danta_score_label.setStyleSheet(f"font-size:28px;font-weight:900;color:{color};padding:8px")
            self.danta_stage_label.setStyleSheet(f"font-size:17px;font-weight:900;color:{color};padding:6px")
            self.strategy_signal_label.setText(f"{day_label} · 5분봉 · {result.stage} · 패턴 {result.score}/100")
            self.strategy_signal_label.setStyleSheet(f"font-size:16px;font-weight:900;color:{color}")

            self.danta_details.setRowCount(0)
            for key, value in result.details.items():
                row = self.danta_details.rowCount()
                self.danta_details.insertRow(row)
                self.danta_details.setItem(row, 0, QTableWidgetItem(str(key)))
                self.danta_details.setItem(row, 1, QTableWidgetItem(str(value)))
        except Exception as exc:
            self.strategy_signal_label.setText(f"{name} · 날짜별 단타 분석 실패: {exc}")
            self.strategy_signal_label.setStyleSheet("font-size:16px;font-weight:900;color:#ff7b83")

''' + anchor
ui = once(ui, anchor, helpers, "intraday date helpers")

# ---------- detailed strategy refresh uses multi-page minute data + date renderer ----------
new_strategy_refresh = r'''    def strategy_refresh_selected(self):
        code = (self.selected_code or "").strip()
        if not code:
            if hasattr(self, "strategy_signal_label"):
                self.strategy_signal_label.setText("PUMA 단타 분석: 종목을 선택하세요")
            return
        name = self.selected_name or code
        self._sync_selected_stock_everywhere()
        try:
            self.strategy_signal_label.setText("5분봉 날짜별 데이터·일봉 거래량 불러오는 중...")
            QApplication.processEvents()
            minute = self.broker.get_minute_candles(code, 5, max_pages=4)
            getter = getattr(self.broker, "get_daily_candles", None)
            daily = getter(code, max_pages=2) if getter else []
            self.danta_raw_minute = minute or []
            self.danta_raw_daily = daily or []
            self.danta_cache_code = code
            self._populate_intraday_dates(self.danta_raw_minute)
            self._render_danta_detail_from_cache()
        except Exception as exc:
            self.strategy_signal_label.setText(f"{name} · 단타 분석 실패: {exc}")
            self.strategy_signal_label.setStyleSheet("font-size:16px;font-weight:900;color:#ff7b83")
'''
ui = replace_func(ui, "strategy_refresh_selected(self):", "open_focus_stock(self, code: str, name: str = \"\"):", new_strategy_refresh)

# Reset date when selecting a new stock.
ui = once(
    ui,
    """        self.selected_code = code
        self.selected_name = self.name_cache.get(code) or (name if name and name != code else code)
""",
    """        changed_stock = code != self.selected_code
        self.selected_code = code
        self.selected_name = self.name_cache.get(code) or (name if name and name != code else code)
        if changed_stock:
            self.intraday_selected_day = ""
            self.danta_cache_code = ""
            self.danta_raw_minute = []
            self.danta_raw_daily = []
""",
    "reset date on stock change",
)

# ---------- focus refresh fetches multiple minute pages and analyzes selected day ----------
ui = once(
    ui,
    """                minute = self.broker.get_minute_candles(code, 5)
                self.focus_minute_raw = minute or []
""",
    """                minute = self.broker.get_minute_candles(code, 5, max_pages=4)
                self.focus_minute_raw = minute or []
                self._populate_intraday_dates(self.focus_minute_raw)
""",
    "multi-page minute focus",
)

old_danta_block = """            # 단타 분석은 메인에도 요약, 상세 탭에도 그대로 유지
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
"""
new_danta_block = """            # 단타 분석은 5분봉 고정. 화면에서는 거래일별로 분리/복기할 수 있다.
            danta_analysis = None
            latest_danta_for_classification = None
            if self.focus_minute_raw:
                try:
                    danta_analysis, danta_series, analyzed_day = analyze_danta_for_date(
                        self.focus_minute_raw,
                        daily_rows,
                        self.intraday_selected_day or None,
                        scan_start=self.scan_start.time().toString("HH:mm"),
                        scan_end=self.scan_end.time().toString("HH:mm"),
                    )
                    danta_series = dict(danta_series)
                    danta_series["watermelon"] = build_watermelon(danta_series.get("candles", []))
                    self.focus_danta_analysis = danta_analysis
                    self.focus_danta_series = danta_series

                    # 조건검색 분류는 사용자가 과거 날짜를 보고 있어도 항상 최신 데이터 기준.
                    latest_danta_for_classification, _, _ = analyze_danta_for_date(
                        self.focus_minute_raw,
                        daily_rows,
                        None,
                        scan_start=self.scan_start.time().toString("HH:mm"),
                        scan_end=self.scan_end.time().toString("HH:mm"),
                    )
                except Exception:
                    self.focus_danta_analysis = None
                    self.focus_danta_series = None

            danta_label = self._pretty_intraday_day(self.intraday_selected_day) if self.intraday_selected_day else "최신"
            self._apply_focus_analyses(danta_analysis, swing_analysis, bowl_analysis, danta_label)

            # 조건검색 표의 단타/스윙/중장기 분류도 최신 분석 결과로 즉시 갱신
            if code in self.condition_candidates and (latest_danta_for_classification or swing_analysis or bowl_analysis):
                ds = getattr(latest_danta_for_classification, "score", 0) if latest_danta_for_classification else 0
"""
ui = once(ui, old_danta_block, new_danta_block, "date aware focus danta")

# ---------- minute chart slices by selected date ----------
new_minute_series = r'''    def _minute_chart_series(self):
        if self.focus_danta_series and self.focus_danta_series.get("candles"):
            series = dict(self.focus_danta_series)
            if self.intraday_selected_day:
                series = slice_series_for_date(series, self.intraday_selected_day)
            candles = series.get("candles", [])
            return candles, {k: v for k, v in series.items() if k != "candles"}
        candles = normalize_candles(self.focus_minute_raw or [])
        closes = [c["close"] for c in candles]
        series = {
            "candles": candles,
            "ema5": ema(closes, 5),
            "ema20": ema(closes, 20),
            "ema60": ema(closes, 60),
            "watermelon": build_watermelon(candles),
        }
        if self.intraday_selected_day:
            series = slice_series_for_date(series, self.intraday_selected_day)
        return series.get("candles", []), {k: v for k, v in series.items() if k != "candles"}
'''
ui = replace_func(ui, "_minute_chart_series(self):", "_update_focus_chart(self, preserve_view: bool = True):", new_minute_series)

# ---------- chart title + selector enabling ----------
old_update = """        if mode == 'MIN':
            candles, lines = self._minute_chart_series()
            self.focus_chart.set_basic_data(candles, lines, title=f"{self.selected_name or self.selected_code} · 5분봉 · PUMA 단타", preserve_view=preserve_view)
        elif self.focus_daily_series:
"""
new_update = """        is_min = mode == 'MIN'
        if hasattr(self, "focus_intraday_date_combo"):
            self.focus_intraday_date_combo.setEnabled(is_min)
        if hasattr(self, "focus_intraday_prev_btn"):
            self.focus_intraday_prev_btn.setEnabled(is_min and bool(self.intraday_days))
        if hasattr(self, "focus_intraday_next_btn"):
            self.focus_intraday_next_btn.setEnabled(is_min and bool(self.intraday_days))

        if mode == 'MIN':
            candles, lines = self._minute_chart_series()
            day_text = self._pretty_intraday_day(self.intraday_selected_day) if self.intraday_selected_day else "전체 · 날짜구분"
            self.focus_chart.set_basic_data(
                candles,
                lines,
                title=f"{self.selected_name or self.selected_code} · 5분봉 · {day_text} · PUMA 단타",
                preserve_view=preserve_view,
            )
        elif self.focus_daily_series:
"""
ui = once(ui, old_update, new_update, "date title and enable")

ui = once(
    ui,
    """    def focus_chart_mode_changed(self):
        self.focus_chart.clear_analysis_range()
        self._update_focus_chart(False)
""",
    """    def focus_chart_mode_changed(self):
        self.focus_chart.clear_analysis_range()
        self._update_focus_chart(False)
        if self.focus_chart_mode == "MIN":
            self.focus_range_status.setText(
                "단타: 전체 날짜 구분" if not self.intraday_selected_day
                else f"단타 날짜: {self._pretty_intraday_day(self.intraday_selected_day)}"
            )
        else:
            self.focus_range_status.setText("분석: 전체")
""",
    "mode status",
)

# ---------- update text ----------
ui = ui.replace(
    "v1.1: 조건검색 단타/스윙/중장기 자동분류, 메인에 단타 분석 재통합, 차트 하단 PUMA 수박형 밴드, 숫자 입력을 휠 없는 직접입력+드롭다운 방식으로 변경.",
    "v1.2: 단타 5분봉은 유지하면서 거래일별 선택/복기, 전일·다음일 이동, 전체보기 날짜 구분선, 과거 날짜 분석 시 미래 데이터 차단을 추가.",
)

# ---------- broker: multi-page minute candles ----------
broker = once(
    broker,
    """    def get_minute_candles(self, code: str, timeframe: int) -> List[dict]:
        raise NotImplementedError
""",
    """    def get_minute_candles(self, code: str, timeframe: int, max_pages: int = 1, base_dt: str | None = None) -> List[dict]:
        raise NotImplementedError
""",
    "base minute signature",
)
broker = once(
    broker,
    """    def get_minute_candles(self, code: str, timeframe: int):
        self._ensure(code)
""",
    """    def get_minute_candles(self, code: str, timeframe: int, max_pages: int = 1, base_dt: str | None = None):
        self._ensure(code)
""",
    "sim minute signature",
)

old_kiwoom_minute = """    def get_minute_candles(self, code: str, timeframe: int):
        body = {
            "stk_cd": code,
            "tic_scope": str(timeframe),
            "upd_stkpc_tp": "1",
            "base_dt": datetime.now().strftime("%Y%m%d"),
        }
        data = self._post("/api/dostk/chart", "ka10080", body)
        return data.get("stk_min_pole_chart_qry", [])
"""
new_kiwoom_minute = """    def get_minute_candles(self, code: str, timeframe: int, max_pages: int = 1, base_dt: str | None = None):
        body = {
            "stk_cd": code,
            "tic_scope": str(timeframe),
            "upd_stkpc_tp": "1",
            "base_dt": (base_dt or datetime.now().strftime("%Y%m%d")),
        }
        rows: list[dict] = []
        cont_yn = ""
        next_key = ""
        pages = max(1, min(10, int(max_pages or 1)))
        for _ in range(pages):
            data, cont_yn, next_key = self._post_page(
                "/api/dostk/chart", "ka10080", body, cont_yn, next_key
            )
            part = data.get("stk_min_pole_chart_qry", [])
            if isinstance(part, list):
                rows.extend(x for x in part if isinstance(x, dict))
            if cont_yn != "Y":
                break
            time.sleep(0.16)

        # continuation 응답에 중복 경계봉이 섞일 경우 시간키 기준 제거.
        out = []
        seen = set()
        for row in rows:
            key = str(row.get("cntr_tm") or row.get("dt") or row.get("date") or "")
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            out.append(row)
        return out
"""
broker = once(broker, old_kiwoom_minute, new_kiwoom_minute, "kiwoom minute pagination")

# ---------- chart date separators ----------
chart = once(
    chart,
    """        # grid / y labels
        p.setPen(QPen(QColor('#17304a'), 1))
""",
    """        # 5분봉처럼 여러 거래일이 한 화면에 있을 때 날짜 경계를 명확히 분리.
        def day_key(raw):
            return ''.join(ch for ch in str(raw or '') if ch.isdigit())[:8]

        visible_days = [day_key(c.get('date', '')) for c in cs]
        unique_days = [d for i, d in enumerate(visible_days) if d and (i == 0 or d != visible_days[i-1])]
        if len(unique_days) > 1:
            step_w = price_rect.width() / max(1, n)
            previous = visible_days[0] if visible_days else ''
            p.setFont(QFont('Malgun Gothic', 8, QFont.Bold))
            for i in range(1, n):
                current = visible_days[i]
                if current and current != previous:
                    xx = x(i) - step_w / 2
                    p.setPen(QPen(QColor('#5b7898'), 1, Qt.DashLine))
                    p.drawLine(QPointF(xx, price_rect.top()), QPointF(xx, watermelon_rect.bottom()))
                    label = f"{current[4:6]}/{current[6:8]}" if len(current) == 8 else current
                    p.setPen(QColor('#9bb8d1'))
                    p.drawText(int(xx + 4), int(price_rect.top() + 14), label)
                    previous = current

        # grid / y labels
        p.setPen(QPen(QColor('#17304a'), 1))
""",
    "chart date separators",
)

# ---------- versions ----------
updater = once(updater, 'CURRENT_VERSION = "1.1.0"', 'CURRENT_VERSION = "1.2.0"', "updater version")
updater = updater.replace("PUMA-STOCK-UPDATER/1.1", "PUMA-STOCK-UPDATER/1.2")

ui_path.write_text(ui, encoding="utf-8")
chart_path.write_text(chart, encoding="utf-8")
broker_path.write_text(broker, encoding="utf-8")
updater_path.write_text(updater, encoding="utf-8")
(pkg / "puma_trader" / "__init__.py").write_text('__version__ = "1.2.0"\n', encoding="utf-8")
print("PUMA v1.2 date-separated 5-minute patch applied")
