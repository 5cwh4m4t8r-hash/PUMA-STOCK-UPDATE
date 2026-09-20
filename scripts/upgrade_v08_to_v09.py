from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
pkg = ROOT / "work" / "PUMA_STOCK_PRO_v0.8"
ui_path = pkg / "puma_trader" / "ui.py"
chart_path = pkg / "puma_trader" / "swing_chart.py"
updater_path = pkg / "puma_trader" / "updater.py"
init_path = pkg / "puma_trader" / "__init__.py"

ui = ui_path.read_text(encoding="utf-8")
chart = chart_path.read_text(encoding="utf-8")
updater = updater_path.read_text(encoding="utf-8")
init = init_path.read_text(encoding="utf-8")

def once(text, old, new, label):
    if old not in text:
        raise RuntimeError(f"target not found: {label}")
    return text.replace(old, new, 1)

def replace_func(text, start_name, next_name, new_block):
    start = text.index(f"    def {start_name}")
    end = text.index(f"    def {next_name}", start)
    return text[:start] + new_block.rstrip() + "\n\n" + text[end:]

# version / imports
ui = once(ui, 'self.setWindowTitle("PUMA STOCK PRO v0.8")', 'self.setWindowTitle("PUMA STOCK PRO v0.9")', "window version")
ui = once(ui, 'title = QLabel("🐆  PUMA STOCK PRO  v0.8")', 'title = QLabel("🐆  PUMA STOCK PRO  v0.9")', "header version")
ui = once(ui, "    QSpinBox,\n    QSplitter,", "    QSpinBox,\n    QScrollArea,\n    QSplitter,", "QScrollArea import")
ui = once(ui, "from .bowl import BowlSettings, analyze_bowl\n", "from .bowl import BowlSettings, analyze_bowl\nfrom .danta import analyze_danta\n", "danta import")

# tab structure: remove visible duplicate swing tab, make short-term analysis a dedicated tab
old_tabs = """        self.tabs = QTabWidget()
        self.tabs.setUsesScrollButtons(True)
        self.focus_widget = self._focus_tab()
        self.hero_widget = self._hero_tab()
        self.dashboard_widget = self._dashboard_tab()
        self.strategy_widget = self._strategy_tab()
        self.manual_widget = self._manual_order_tab()
        self.swing_widget = self._swing_tab()
        self.connection_widget = self._connection_tab()
        self.update_widget = self._update_tab()
        self.tabs.addTab(self.focus_widget, "통합 트레이딩")
        self.tabs.addTab(self.hero_widget, "조건검색")
        self.tabs.addTab(self.dashboard_widget, "잔고 · 로그")
        self.tabs.addTab(self.strategy_widget, "전략 상세설정")
        self.tabs.addTab(self.manual_widget, "고급 주문")
        self.tabs.addTab(self.swing_widget, "역매공파 상세")
        self.tabs.addTab(self.connection_widget, "설정 · 키움연결")
        self.tabs.addTab(self.update_widget, "업데이트")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        outer.addWidget(self.tabs)
"""
new_tabs = """        self.tabs = QTabWidget()
        self.tabs.setUsesScrollButtons(True)
        self.focus_widget = self._focus_tab()
        self.hero_widget = self._hero_tab()
        self.dashboard_widget = self._dashboard_tab()
        self.strategy_widget = self._strategy_tab()
        self.manual_widget = self._manual_order_tab()

        # 역매공파 설정 컨트롤은 분석 로직 호환을 위해 내부에 유지하지만,
        # 별도 중복 화면은 보여주지 않고 통합 트레이딩에서 분석 결과를 표시한다.
        self.swing_settings_widget = self._swing_tab()

        self.connection_widget = self._connection_tab()
        self.update_widget = self._update_tab()
        self.tabs.addTab(self.focus_widget, "통합 트레이딩")
        self.tabs.addTab(self.hero_widget, "조건검색")
        self.tabs.addTab(self.dashboard_widget, "잔고 · 로그")
        self.tabs.addTab(self.strategy_widget, "단타 분석")
        self.tabs.addTab(self.manual_widget, "고급 주문")
        self.tabs.addTab(self.connection_widget, "설정 · 키움연결")
        self.tabs.addTab(self.update_widget, "업데이트")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        outer.addWidget(self.tabs)
"""
ui = once(ui, old_tabs, new_tabs, "tabs")

# Main chart is now swing/long only.
ui = once(ui,
"""        self.focus_chart_mode_combo = QComboBox()
        self.focus_chart_mode_combo.addItem("일봉 · 스윙/중장기", "DAY")
        self.focus_chart_mode_combo.addItem("5분봉 · 아침단타", "MIN")
        self.focus_chart_mode_combo.currentIndexChanged.connect(self.focus_chart_mode_changed)
""",
"""        self.focus_chart_mode_combo = QComboBox()
        self.focus_chart_mode_combo.addItem("일봉 · 스윙/중장기", "DAY")
        self.focus_chart_mode_combo.currentIndexChanged.connect(self.focus_chart_mode_changed)
""",
"main chart mode")

# Replace three-strategy strip with swing + long only.
old_signals = """        signals = QGroupBox("전략 3종 동시 분석 · 한 화면")
        sg = QGridLayout(signals)
        self.focus_day_signal = QLabel("오돌이 DAY\\n5분봉 분석 대기")
        self.focus_day_signal.setAlignment(Qt.AlignCenter)
        self.focus_day_signal.setStyleSheet("font-size:15px;font-weight:900;color:#f4c95d;background:#122238;border-radius:8px;padding:10px")
        self.focus_swing_signal = QLabel("역매공파 SWING\\n분석 대기")
        self.focus_swing_signal.setAlignment(Qt.AlignCenter)
        self.focus_swing_signal.setStyleSheet("font-size:15px;font-weight:900;color:#f4c95d;background:#122238;border-radius:8px;padding:10px")
        self.focus_bowl_signal = QLabel("밥그릇 3번 LONG\\n분석 대기")
        self.focus_bowl_signal.setAlignment(Qt.AlignCenter)
        self.focus_bowl_signal.setStyleSheet("font-size:15px;font-weight:900;color:#f4c95d;background:#122238;border-radius:8px;padding:10px")
        sg.addWidget(self.focus_day_signal, 0, 0)
        sg.addWidget(self.focus_swing_signal, 0, 1)
        sg.addWidget(self.focus_bowl_signal, 0, 2)
        self.focus_stage = QLabel("통합판정: 데이터 대기")
        self.focus_stage.setStyleSheet("font-size:16px;font-weight:900;color:#61ff8f;padding:6px")
        sg.addWidget(self.focus_stage, 1, 0, 1, 3)
        left.addWidget(signals, 1)
"""
new_signals = """        signals = QGroupBox("스윙 · 중장기 동시 분석")
        sg = QGridLayout(signals)
        self.focus_swing_signal = QLabel("역매공파 SWING\\n분석 대기")
        self.focus_swing_signal.setAlignment(Qt.AlignCenter)
        self.focus_swing_signal.setStyleSheet("font-size:15px;font-weight:900;color:#f4c95d;background:#122238;border-radius:8px;padding:10px")
        self.focus_bowl_signal = QLabel("밥그릇 3번 LONG\\n분석 대기")
        self.focus_bowl_signal.setAlignment(Qt.AlignCenter)
        self.focus_bowl_signal.setStyleSheet("font-size:15px;font-weight:900;color:#f4c95d;background:#122238;border-radius:8px;padding:10px")
        sg.addWidget(self.focus_swing_signal, 0, 0)
        sg.addWidget(self.focus_bowl_signal, 0, 1)
        self.focus_stage = QLabel("통합판정: 데이터 대기")
        self.focus_stage.setStyleSheet("font-size:16px;font-weight:900;color:#61ff8f;padding:6px")
        sg.addWidget(self.focus_stage, 1, 0, 1, 2)
        left.addWidget(signals, 1)
"""
ui = once(ui, old_signals, new_signals, "main signal strip")

# Right red-box area gets a scroll container so nothing is crushed/hidden at smaller resolutions.
ui = once(ui,
"""        right_panel = QWidget()
        right = QVBoxLayout(right_panel)
        right.setContentsMargins(0, 0, 0, 0)
""",
"""        right_panel = QWidget()
        right = QVBoxLayout(right_panel)
        right.setContentsMargins(4, 0, 4, 0)
        right.setSpacing(6)
""",
"right layout")
ui = once(ui,
"""        right.addStretch()
        self.focus_splitter.addWidget(right_panel)
        self.focus_splitter.setCollapsible(0, False)
""",
"""        right.addStretch()

        self.focus_right_scroll = QScrollArea()
        self.focus_right_scroll.setWidgetResizable(True)
        self.focus_right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.focus_right_scroll.setWidget(right_panel)
        self.focus_right_scroll.setMinimumWidth(330)
        self.focus_splitter.addWidget(self.focus_right_scroll)
        self.focus_splitter.setCollapsible(0, False)
""",
"right scroll")
ui = ui.replace("self.focus_splitter.setSizes([240, 820, 360])", "self.focus_splitter.setSizes([235, 855, 390])", 1)

# Dedicated short-term analysis tab.
new_strategy = r'''    def _strategy_tab(self):
        w = QWidget()
        outer = QVBoxLayout(w)

        head = QHBoxLayout()
        self.strategy_selected_label = QLabel("선택종목: 없음")
        self.strategy_selected_label.setStyleSheet("font-size:18px;font-weight:900;color:#8dc7ff")
        self.strategy_signal_label = QLabel("PUMA 단타 분석 대기")
        self.strategy_signal_label.setStyleSheet("font-size:16px;font-weight:900;color:#f4c95d")
        refresh = QPushButton("↻ 단타 즉시 분석")
        refresh.setObjectName("conditionBtn")
        refresh.clicked.connect(self.strategy_refresh_selected)
        head.addWidget(self.strategy_selected_label)
        head.addWidget(self.strategy_signal_label)
        head.addStretch()
        head.addWidget(refresh)
        outer.addLayout(head)

        info = QLabel("5분봉 · 기준선 · 장초반 거래량 · EMA 정배열 · 돌파/눌림을 함께 판정합니다. 공개적으로 설명된 주식단테 단타 개념을 PUMA 방식으로 수치화한 분석판이며, 비공개/유료 검색식을 복제한 것은 아닙니다.")
        info.setWordWrap(True)
        info.setStyleSheet("color:#9eb4c9;padding:4px")
        outer.addWidget(info)

        analysis_split = QSplitter(Qt.Horizontal)
        self.danta_chart = SwingChart()
        self.danta_chart.setMinimumHeight(330)
        analysis_split.addWidget(self.danta_chart)

        result_box = QGroupBox("단타 판정")
        rv = QVBoxLayout(result_box)
        self.danta_score_label = QLabel("점수 -- / 100")
        self.danta_score_label.setAlignment(Qt.AlignCenter)
        self.danta_score_label.setStyleSheet("font-size:28px;font-weight:900;color:#62b8ff;padding:8px")
        self.danta_stage_label = QLabel("종목을 선택하세요")
        self.danta_stage_label.setAlignment(Qt.AlignCenter)
        self.danta_stage_label.setStyleSheet("font-size:17px;font-weight:900;color:#f4c95d;padding:6px")
        self.danta_details = QTableWidget(0, 2)
        self.danta_details.setHorizontalHeaderLabels(["판정 항목", "현재 상태"])
        self.danta_details.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.danta_details.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.danta_details.setSelectionMode(QAbstractItemView.NoSelection)
        rv.addWidget(self.danta_score_label)
        rv.addWidget(self.danta_stage_label)
        rv.addWidget(self.danta_details, 1)
        analysis_split.addWidget(result_box)
        analysis_split.setStretchFactor(0, 5)
        analysis_split.setStretchFactor(1, 2)
        analysis_split.setSizes([950, 420])
        outer.addWidget(analysis_split, 3)

        settings = QSplitter(Qt.Horizontal)

        buy = QGroupBox("단타 분석 기준")
        b = QFormLayout(buy)
        self.timeframe = QComboBox()
        self.timeframe.addItems(["1", "3", "5", "10", "15", "30", "60"])
        self.timeframe.setCurrentText(str(self.settings.timeframe_min))
        self.scan_start = QTimeEdit(QTime.fromString(self.settings.scan_start, "HH:mm"))
        self.scan_end = QTimeEdit(QTime.fromString(self.settings.scan_end, "HH:mm"))
        self.min_change = self._dspin(-30, 30, self.settings.min_change_pct, " %")
        self.max_change = self._dspin(-30, 30, self.settings.max_change_pct, " %")
        self.vol_ratio = self._dspin(0, 20, self.settings.volume_ratio_min, " 배")
        self.use_ma = QCheckBox("EMA 정배열 사용")
        self.use_ma.setChecked(self.settings.use_ma_stack)
        self.ma_fast = self._spin(1, 200, self.settings.ma_fast)
        self.ma_mid = self._spin(2, 300, self.settings.ma_mid)
        self.ma_slow = self._spin(3, 500, self.settings.ma_slow)
        self.use_breakout = QCheckBox("직전 고점 돌파 사용")
        self.use_breakout.setChecked(self.settings.use_breakout)
        self.breakout = self._spin(2, 120, self.settings.breakout_lookback)
        self.use_rsi = QCheckBox("RSI 범위 사용")
        self.use_rsi.setChecked(self.settings.use_rsi)
        self.rsi_min = self._dspin(0, 100, self.settings.rsi_min)
        self.rsi_max = self._dspin(0, 100, self.settings.rsi_max)
        for label, widget in [
            ("기준 분봉", self.timeframe), ("검색 시작", self.scan_start), ("검색 종료", self.scan_end),
            ("최소 등락률", self.min_change), ("최대 등락률", self.max_change), ("거래량 급증", self.vol_ratio),
            ("", self.use_ma), ("단기 EMA", self.ma_fast), ("중기 EMA", self.ma_mid), ("장기 EMA", self.ma_slow),
            ("", self.use_breakout), ("돌파 Lookback", self.breakout), ("", self.use_rsi),
            ("RSI 최소", self.rsi_min), ("RSI 최대", self.rsi_max),
        ]:
            b.addRow(label, widget)
        settings.addWidget(buy)

        risk = QGroupBox("주문 · 리스크")
        r = QFormLayout(risk)
        self.order_budget = self._spin(10_000, 100_000_000, self.settings.order_budget, 10_000)
        self.max_positions = self._spin(1, 20, self.settings.max_positions)
        self.cooldown = self._spin(0, 240, self.settings.cooldown_min)
        self.max_daily_orders = self._spin(1, 100, self.settings.max_daily_orders)
        self.account_sync_sec = self._spin(2, 60, self.settings.account_sync_sec)
        self.exchange_combo = QComboBox()
        self.exchange_combo.addItems(["KRX", "NXT", "SOR"])
        self.exchange_combo.setCurrentText(self.settings.order_exchange)
        r.addRow("종목당 투입금", self.order_budget)
        r.addRow("최대 보유종목", self.max_positions)
        r.addRow("재진입 대기(분)", self.cooldown)
        r.addRow("PUMA 일일 주문 상한", self.max_daily_orders)
        r.addRow("실계좌 동기화(초)", self.account_sync_sec)
        r.addRow("주문 거래소", self.exchange_combo)
        r.addRow(QLabel("실전 자동주문은 기존 LIVE START 안전잠금을 그대로 사용합니다."))
        settings.addWidget(risk)

        sell = QGroupBox("매도 조건")
        s = QFormLayout(sell)
        self.take_profit = self._dspin(0.1, 100, self.settings.take_profit_pct, " %")
        self.stop_loss = self._dspin(-50, -0.1, self.settings.stop_loss_pct, " %")
        self.trailing = QCheckBox("트레일링 스탑 사용")
        self.trailing.setChecked(self.settings.trailing_enabled)
        self.trailing_start = self._dspin(0.1, 100, self.settings.trailing_start_pct, " %")
        self.trailing_gap = self._dspin(0.1, 30, self.settings.trailing_gap_pct, " %")
        self.force_exit = QCheckBox("장 종료 전 전량청산")
        self.force_exit.setChecked(self.settings.force_exit_enabled)
        self.force_exit_time = QTimeEdit(QTime.fromString(self.settings.force_exit_time, "HH:mm"))
        for label, widget in [
            ("익절", self.take_profit), ("손절", self.stop_loss), ("", self.trailing),
            ("트레일링 시작", self.trailing_start), ("고점 대비 하락", self.trailing_gap),
            ("", self.force_exit), ("청산 시각", self.force_exit_time),
        ]:
            s.addRow(label, widget)
        save = QPushButton("💾 단타/리스크 설정 저장")
        save.clicked.connect(self.save_settings)
        s.addRow(save)
        settings.addWidget(sell)

        settings.setStretchFactor(0, 2)
        settings.setStretchFactor(1, 1)
        settings.setStretchFactor(2, 1)
        settings.setSizes([620, 360, 360])
        outer.addWidget(settings, 2)
        return w
'''
ui = replace_func(ui, "_strategy_tab(self):", "_manual_order_tab(self):", new_strategy)

# Remove visible swing-tab reaction and replace short-term refresh logic.
old_tab_change = """        if widget is getattr(self, "strategy_widget", None):
            QTimer.singleShot(0, self.strategy_refresh_selected)
        elif widget is getattr(self, "manual_widget", None):
            QTimer.singleShot(0, self.manual_quote)
        elif widget is getattr(self, "swing_widget", None):
            if isinstance(self.broker, KiwoomRestBroker) and self.broker.token:
                QTimer.singleShot(0, lambda: self.swing_load_kiwoom(silent=True))
"""
new_tab_change = """        if widget is getattr(self, "strategy_widget", None):
            QTimer.singleShot(0, self.strategy_refresh_selected)
        elif widget is getattr(self, "manual_widget", None):
            QTimer.singleShot(0, self.manual_quote)
"""
ui = once(ui, old_tab_change, new_tab_change, "tab linkage")

old_strategy_refresh_start = ui.index("    def strategy_refresh_selected(self):")
old_strategy_refresh_end = ui.index("    def open_focus_stock", old_strategy_refresh_start)
new_strategy_refresh = r'''    def strategy_refresh_selected(self):
        code = (self.selected_code or "").strip()
        if not code:
            if hasattr(self, "strategy_signal_label"):
                self.strategy_signal_label.setText("PUMA 단타 분석: 종목을 선택하세요")
            return
        name = self.selected_name or code
        self._sync_selected_stock_everywhere()
        try:
            self.strategy_signal_label.setText("5분봉·일봉 거래량 불러오는 중...")
            QApplication.processEvents()
            minute = self.broker.get_minute_candles(code, 5)
            getter = getattr(self.broker, "get_daily_candles", None)
            daily = getter(code, max_pages=1) if getter else []
            result, series = analyze_danta(
                minute,
                daily,
                scan_start=self.scan_start.time().toString("HH:mm"),
                scan_end=self.scan_end.time().toString("HH:mm"),
            )
            self.danta_analysis = result
            self.danta_series = series
            lines = {k: v for k, v in series.items() if k != "candles"}
            self.danta_chart.set_basic_data(
                series["candles"], lines,
                title=f"{name} {code} · 5분봉 · PUMA 단타 분석",
                preserve_view=False,
            )
            self.danta_score_label.setText(f"{result.score} / 100")
            self.danta_stage_label.setText(result.stage)
            color = "#61ff8f" if result.candidate else ("#62b8ff" if result.score >= 55 else "#f4c95d")
            self.danta_score_label.setStyleSheet(f"font-size:28px;font-weight:900;color:{color};padding:8px")
            self.danta_stage_label.setStyleSheet(f"font-size:17px;font-weight:900;color:{color};padding:6px")
            self.strategy_signal_label.setText(f"5분봉 · {result.stage} · {result.score}/100")
            self.strategy_signal_label.setStyleSheet(f"font-size:16px;font-weight:900;color:{color}")
            self.danta_details.setRowCount(0)
            for key, value in result.details.items():
                row = self.danta_details.rowCount()
                self.danta_details.insertRow(row)
                self.danta_details.setItem(row, 0, QTableWidgetItem(str(key)))
                self.danta_details.setItem(row, 1, QTableWidgetItem(str(value)))
        except Exception as exc:
            self.strategy_signal_label.setText(f"{name} · 단타 분석 실패: {exc}")
            self.strategy_signal_label.setStyleSheet("font-size:16px;font-weight:900;color:#ff7b83")

'''
ui = ui[:old_strategy_refresh_start] + new_strategy_refresh + ui[old_strategy_refresh_end:]

# Main refresh still preloads 5m data, but short-term judgement is no longer drawn on main screen.
old_minute = """            # 1) 오돌이/아침단타: 5분봉 엔진
            try:
                minute = self.broker.get_minute_candles(code, self.settings.timeframe_min)
                self.focus_minute_raw = minute or []
                sig = evaluate_buy(minute, self.settings) if minute else None
                if sig:
                    self.focus_day_signal.setText(f"오돌이 DAY · 5분봉\\n{'매수조건 충족' if sig.passed else sig.reason}")
                    self.focus_day_signal.setStyleSheet(f"font-size:15px;font-weight:900;color:{'#61ff8f' if sig.passed else '#f4c95d'};background:#122238;border-radius:8px;padding:10px")
            except Exception as exc:
                self.focus_day_signal.setText(f"오돌이 DAY · 5분봉\\n조회 실패: {exc}")

            # 2) 일봉: 역매공파 + 밥그릇3번을 같은 데이터로 동시에 판정
"""
new_minute = """            # 단타는 별도 '단타 분석' 화면에서 판정한다. 메인에서는 데이터만 미리 적재한다.
            try:
                minute = self.broker.get_minute_candles(code, 5)
                self.focus_minute_raw = minute or []
            except Exception:
                self.focus_minute_raw = []

            # 일봉: 역매공파 + 밥그릇3번을 같은 데이터로 동시에 판정
"""
ui = once(ui, old_minute, new_minute, "main minute block")

# Main chart helper remains compatible but no longer presents short-term option.
ui = ui.replace('title=f"{self.selected_name or self.selected_code} · {self.settings.timeframe_min}분봉 · 오돌이 DAY"',
                'title=f"{self.selected_name or self.selected_code} · 5분봉 · PUMA 단타"')

# Update text.
ui = ui.replace(
    "v0.8: 해상도 최적화 + 통합/전략상세/역매공파/고급주문 선택종목 실시간 연동 + 종목 클릭 버그 수정.",
    "v0.9: 메인 오른쪽 영역 스크롤/폭 개선, 역매공파 별도 중복 탭 제거 후 메인 통합 유지, 단타 분석 전용 화면 추가."
)

# Chart line style for public '기준선'.
chart = once(chart,
"""            'ema224':'#c26cff','ema448':'#8f6b4b','blue':'#2e7cff'
""",
"""            'ema224':'#c26cff','ema448':'#8f6b4b','blue':'#2e7cff','kijun':'#f2f2f2'
""",
"kijun color")
chart = once(chart,
"""        widths={'blue':3.0,'ema5':1.2}
""",
"""        widths={'blue':3.0,'ema5':1.2,'kijun':2.0}
""",
"kijun width")

updater = once(updater, 'CURRENT_VERSION = "0.8.0"', 'CURRENT_VERSION = "0.9.0"', "updater version")
updater = updater.replace("PUMA-STOCK-UPDATER/0.8", "PUMA-STOCK-UPDATER/0.9")
init = '__version__ = "0.9.0"\n'

ui_path.write_text(ui, encoding="utf-8")
chart_path.write_text(chart, encoding="utf-8")
updater_path.write_text(updater, encoding="utf-8")
init_path.write_text(init, encoding="utf-8")
print("v0.9 patch applied")
