from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
pkg = ROOT / "work" / "PUMA_STOCK_PRO_v0.9"
ui_path = pkg / "puma_trader" / "ui.py"
storage_path = pkg / "puma_trader" / "storage.py"
chart_path = pkg / "puma_trader" / "swing_chart.py"
updater_path = pkg / "puma_trader" / "updater.py"
init_path = pkg / "puma_trader" / "__init__.py"

ui = ui_path.read_text(encoding="utf-8")
storage = storage_path.read_text(encoding="utf-8")
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

# ---------- imports / global styling ----------
ui = once(ui, "from PySide6.QtCore import QTime, QTimer, Qt, QDate",
          "from PySide6.QtCore import QTime, QTimer, Qt, QDate, QSettings", "QSettings")
ui = once(ui,
          "from .storage import load_strategy, load_watchlist, save_strategy, save_watchlist",
          "from .storage import load_strategy, load_watchlist, save_strategy, save_watchlist, load_swing_settings, save_swing_settings",
          "swing storage imports")
ui = once(ui, 'self.setWindowTitle("PUMA STOCK PRO v0.9")', 'self.setWindowTitle("PUMA STOCK PRO v1.0")', "window version")
ui = once(ui, 'title = QLabel("🐆  PUMA STOCK PRO  v0.9")', 'title = QLabel("🐆  PUMA STOCK PRO  v1.0")', "title version")
ui = ui.replace("QGroupBox { border: 1px solid #29415f; border-radius: 8px; margin-top: 12px; padding: 10px; font-weight: 700; }",
                "QGroupBox { border: 1px solid #29415f; border-radius: 8px; margin-top: 10px; padding: 8px; font-weight: 700; }")
ui = ui.replace("QPushButton { background: #183457; border: 1px solid #315b89; border-radius: 7px; padding: 8px 12px; font-weight: 700; }",
                "QPushButton { background: #183457; border: 1px solid #315b89; border-radius: 7px; padding: 6px 9px; font-weight: 700; }")
ui = ui.replace("QTabBar::tab { background:#13253b; padding:7px 11px; margin-right:2px; }",
                "QTabBar::tab { background:#13253b; padding:6px 10px; margin-right:2px; }")
ui = once(ui, 'QTabBar::tab:selected { background:#1d4776; }\n',
          'QTabBar::tab:selected { background:#1d4776; }\nQScrollArea { border:0; background:transparent; }\n',
          "scroll style")

# ---------- persistent swing settings ----------
ui = once(ui, "        self.swing_settings = SwingSettings()",
          "        self.swing_settings = load_swing_settings()\n        self.ui_state = QSettings(\"PUMA\", \"PUMA_STOCK_PRO\")",
          "load swing/ui settings")

# Remove invisible duplicate Swing screen construction.
ui = once(ui,
"""        # 역매공파 설정 컨트롤은 분석 로직 호환을 위해 내부에 유지하지만,
        # 별도 중복 화면은 보여주지 않고 통합 트레이딩에서 분석 결과를 표시한다.
        self.swing_settings_widget = self._swing_tab()

""", "", "remove hidden swing widget")

# Restore sizes after widgets exist.
ui = once(ui,
"""        self._load_saved_connection()
        if getattr(self, "auto_connect_box", None) is not None and self.auto_connect_box.isChecked():
            QTimer.singleShot(900, self.auto_connect_saved)
""",
"""        self._load_saved_connection()
        self._apply_display_profile()
        QTimer.singleShot(0, self._restore_ui_layout)
        if getattr(self, "auto_connect_box", None) is not None and self.auto_connect_box.isChecked():
            QTimer.singleShot(900, self.auto_connect_saved)
""",
"display profile hook")

# ---------- dashboard: resizable vertical split ----------
new_dashboard = r'''    def _dashboard_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("자동매매 대상"))
        self.source_combo = QComboBox()
        self.source_combo.addItem("관심종목만", "WATCHLIST")
        self.source_combo.addItem("영웅문4 조건식", "HERO4")
        self.source_combo.addItem("관심종목 + 영웅문4", "BOTH")
        idx = self.source_combo.findData(self.settings.candidate_source)
        self.source_combo.setCurrentIndex(max(0, idx))
        controls.addWidget(self.source_combo)

        self.start_btn = QPushButton("▶ 자동매매 시작")
        self.start_btn.setObjectName("startBtn")
        self.stop_btn = QPushButton("■ 자동매매 중지")
        self.stop_btn.setObjectName("stopBtn")
        self.start_btn.clicked.connect(self.start_auto)
        self.stop_btn.clicked.connect(self.stop_auto)
        controls.addWidget(self.start_btn)
        controls.addWidget(self.stop_btn)
        controls.addStretch()

        add = QPushButton("＋ 관심종목 추가")
        add.clicked.connect(self.add_symbol)
        delete = QPushButton("－ 관심종목에서 삭제")
        delete.clicked.connect(self.delete_symbol)
        controls.addWidget(add)
        controls.addWidget(delete)
        lay.addLayout(controls)

        self.dashboard_splitter = QSplitter(Qt.Vertical)

        market_wrap = QWidget()
        market_lay = QVBoxLayout(market_wrap)
        market_lay.setContentsMargins(0, 0, 0, 0)
        self.market_table = QTableWidget(0, 8)
        self.market_table.setHorizontalHeaderLabels([
            "종목코드", "종목명", "유입경로", "현재가", "상태", "신호/사유", "보유수량", "수익률"
        ])
        self.market_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.market_table.setAlternatingRowColors(True)
        self.market_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        market_lay.addWidget(self.market_table)
        self.dashboard_splitter.addWidget(market_wrap)

        logbox = QGroupBox("실시간 주문/신호 로그")
        loglay = QVBoxLayout(logbox)
        self.log_table = QTableWidget(0, 5)
        self.log_table.setHorizontalHeaderLabels(["시간", "종목", "구분", "현재가", "내용"])
        self.log_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        loglay.addWidget(self.log_table)
        self.dashboard_splitter.addWidget(logbox)
        self.dashboard_splitter.setStretchFactor(0, 3)
        self.dashboard_splitter.setStretchFactor(1, 1)
        self.dashboard_splitter.setSizes([580, 220])
        lay.addWidget(self.dashboard_splitter, 1)
        return w
'''
ui = replace_func(ui, "_dashboard_tab(self):", "_focus_tab(self):", new_dashboard)

# ---------- main integrated trading ----------
new_focus = r'''    def _focus_tab(self):
        """조건검색 -> 일봉 차트 -> 역매공파/밥그릇 -> 주문을 한 화면에서 처리."""
        w = QWidget()
        root = QVBoxLayout(w)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(5)

        head = QHBoxLayout()
        self.focus_title = QLabel("종목을 선택하세요")
        self.focus_title.setStyleSheet("font-size:20px;font-weight:900;color:#ffffff")
        self.focus_price = QLabel("-")
        self.focus_price.setStyleSheet("font-size:22px;font-weight:900;color:#ff626b")
        self.focus_origin = QLabel("조건검색 목록에서 종목을 클릭하면 자동으로 열립니다.")
        self.focus_origin.setStyleSheet("color:#8fb6d9")
        refresh = QPushButton("↻ 전체 새로고침")
        refresh.clicked.connect(self.focus_refresh)
        head.addWidget(self.focus_title)
        head.addWidget(self.focus_price)
        head.addWidget(self.focus_origin, 1)
        head.addWidget(refresh)
        root.addLayout(head)

        tools = QHBoxLayout()
        self.focus_chart_mode_combo = QComboBox()
        self.focus_chart_mode_combo.addItem("일봉 · 스윙/중장기", "DAY")
        self.focus_chart_mode_combo.currentIndexChanged.connect(self.focus_chart_mode_changed)
        tools.addWidget(self.focus_chart_mode_combo)
        for text, fn in [
            ("◀ 과거", lambda: self.focus_chart.pan_bars(-60)),
            ("최신 ▶", lambda: self.focus_chart.show_latest()),
            ("＋ 확대", lambda: self.focus_chart.zoom_by(0.78)),
            ("－ 축소", lambda: self.focus_chart.zoom_by(1.28)),
            ("전체보기", lambda: self.focus_chart.show_all()),
        ]:
            b = QPushButton(text)
            b.clicked.connect(fn)
            tools.addWidget(b)
        more = QPushButton("과거 +5페이지")
        more.clicked.connect(self.focus_load_more_history)
        tools.addWidget(more)
        self.focus_view_label = QLabel("차트 구간: -")
        self.focus_view_label.setStyleSheet("color:#8fb6d9;font-weight:700")
        tools.addWidget(self.focus_view_label, 1)
        root.addLayout(tools)

        range_row = QHBoxLayout()
        range_row.addWidget(QLabel("분석구간"))
        self.focus_range_start = QDateEdit(QDate.currentDate().addYears(-1))
        self.focus_range_end = QDateEdit(QDate.currentDate())
        for d in (self.focus_range_start, self.focus_range_end):
            d.setCalendarPopup(True)
            d.setDisplayFormat("yyyy-MM-dd")
        range_row.addWidget(self.focus_range_start)
        range_row.addWidget(QLabel("~"))
        range_row.addWidget(self.focus_range_end)
        range_btn = QPushButton("선택 날짜 분석")
        range_btn.clicked.connect(self.focus_analyze_date_range)
        visible_btn = QPushButton("보이는 구간 분석")
        visible_btn.clicked.connect(self.focus_analyze_visible)
        all_btn = QPushButton("전체 분석 복귀")
        all_btn.clicked.connect(self.focus_analyze_all)
        range_row.addWidget(range_btn)
        range_row.addWidget(visible_btn)
        range_row.addWidget(all_btn)
        self.focus_range_status = QLabel("분석: 전체")
        self.focus_range_status.setStyleSheet("color:#61ff8f;font-weight:800")
        range_row.addWidget(self.focus_range_status, 1)
        root.addLayout(range_row)

        self.focus_splitter = QSplitter(Qt.Horizontal)

        candidates = QGroupBox("조건검색 결과")
        cand_lay = QVBoxLayout(candidates)
        self.focus_condition_table = QTableWidget(0, 3)
        self.focus_condition_table.setHorizontalHeaderLabels(["종목", "종목명", "상태"])
        hdr = self.focus_condition_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.focus_condition_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.focus_condition_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.focus_condition_table.cellClicked.connect(self._focus_condition_row_clicked)
        self.focus_condition_table.setMinimumWidth(200)
        self.focus_condition_table.setMaximumWidth(340)
        cand_lay.addWidget(self.focus_condition_table)
        cand_help = QLabel("종목 클릭 → 차트·스윙분석·주문·단타분석이 같은 종목으로 연동")
        cand_help.setWordWrap(True)
        cand_help.setStyleSheet("color:#8fb6d9")
        cand_lay.addWidget(cand_help)
        self.focus_splitter.addWidget(candidates)

        center_panel = QWidget()
        center = QVBoxLayout(center_panel)
        center.setContentsMargins(0, 0, 0, 0)
        center.setSpacing(5)
        self.focus_chart = SwingChart()
        self.focus_chart.viewportChanged.connect(lambda t: self.focus_view_label.setText("차트 구간: " + t))
        center.addWidget(self.focus_chart, 7)

        signals = QGroupBox("스윙 · 중장기 동시 분석")
        sg = QGridLayout(signals)
        self.focus_swing_signal = QLabel("역매공파 SWING\n분석 대기")
        self.focus_swing_signal.setAlignment(Qt.AlignCenter)
        self.focus_swing_signal.setStyleSheet("font-size:14px;font-weight:900;color:#f4c95d;background:#122238;border-radius:8px;padding:8px")
        self.focus_bowl_signal = QLabel("밥그릇 3번 LONG\n분석 대기")
        self.focus_bowl_signal.setAlignment(Qt.AlignCenter)
        self.focus_bowl_signal.setStyleSheet("font-size:14px;font-weight:900;color:#f4c95d;background:#122238;border-radius:8px;padding:8px")
        sg.addWidget(self.focus_swing_signal, 0, 0)
        sg.addWidget(self.focus_bowl_signal, 0, 1)
        self.focus_stage = QLabel("통합판정: 데이터 대기")
        self.focus_stage.setStyleSheet("font-size:14px;font-weight:900;color:#61ff8f;padding:4px")
        sg.addWidget(self.focus_stage, 1, 0, 1, 2)
        center.addWidget(signals, 1)
        self.focus_splitter.addWidget(center_panel)

        # 오른쪽은 세로로 억지로 쌓지 않고 기능별 소형 탭으로 분리.
        # 어느 해상도에서도 버튼/입력창 높이가 눌리지 않는다.
        self.focus_side_tabs = QTabWidget()

        analysis_page = QWidget()
        av = QVBoxLayout(analysis_page)
        av.setContentsMargins(5, 5, 5, 5)
        stagebox = QGroupBox("역매공파 SWING 진행상태")
        st = QGridLayout(stagebox)
        self.focus_stage_labels = {}
        names = ["장기 EMA 역배열", "매집봉/구간", "공구리(박스권)", "박스 상단 돌파", "상단 박스 안착", "파란점선", "수박/화살표"]
        for i, name in enumerate(names):
            a = QLabel(name)
            b = QLabel("대기")
            b.setWordWrap(True)
            b.setStyleSheet("font-weight:800;color:#f4c95d")
            st.addWidget(a, i, 0)
            st.addWidget(b, i, 1)
            self.focus_stage_labels[name] = b
        av.addWidget(stagebox)

        bowlbox = QGroupBox("밥그릇 3번 · SWING~LONG")
        bg = QGridLayout(bowlbox)
        self.focus_bowl_labels = {}
        bowl_names = ["장기 224EMA 아래", "224EMA 돌파", "224EMA 위 안착", "눌림/지지", "224EMA 거리", "수박/화살표"]
        for i, name in enumerate(bowl_names):
            a = QLabel(name)
            b = QLabel("대기")
            b.setWordWrap(True)
            b.setStyleSheet("font-weight:800;color:#f4c95d")
            bg.addWidget(a, i, 0)
            bg.addWidget(b, i, 1)
            self.focus_bowl_labels[name] = b
        av.addWidget(bowlbox)
        av.addStretch()
        self.focus_side_tabs.addTab(self._scroll_wrap(analysis_page), "분석")

        swing_settings_page = QWidget()
        sv = QVBoxLayout(swing_settings_page)
        sv.setContentsMargins(5, 5, 5, 5)
        ss = self.swing_settings

        acc = QGroupBox("매집봉 기준")
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

        box = QGroupBox("공구리(박스권)")
        bf = QFormLayout(box)
        self.sw_box_window = self._spin(5, 60, ss.box_window)
        self.sw_box_width = self._dspin(2, 30, ss.box_width_pct, " %")
        self.sw_accept_window = self._spin(3, 20, ss.acceptance_window)
        self.sw_accept_count = self._spin(2, 15, ss.acceptance_min_closes)
        bf.addRow("박스 판정 기간", self.sw_box_window)
        bf.addRow("박스 최대 폭", self.sw_box_width)
        bf.addRow("돌파 후 확인봉", self.sw_accept_window)
        bf.addRow("상단 위 종가 최소", self.sw_accept_count)
        sv.addWidget(box)

        blue = QGroupBox("파란점선")
        bl = QFormLayout(blue)
        self.sw_blue_period = self._spin(2, 100, ss.blue_period)
        self.sw_blue_dev = self._dspin(0.1, 5.0, ss.blue_dev)
        self.sw_blue_shift = self._spin(0, 100, ss.blue_shift)
        self.sw_blue_near = self._dspin(0.1, 15, ss.blue_near_pct, " %")
        bl.addRow("BBands Period", self.sw_blue_period)
        bl.addRow("편차 D1", self.sw_blue_dev)
        bl.addRow("Shift Period2", self.sw_blue_shift)
        bl.addRow("근접 판정", self.sw_blue_near)
        formula = QLabel("shift(BBandsUp(26, 2.6), 26)")
        formula.setStyleSheet("color:#4f9dff;font-weight:800")
        bl.addRow("수식", formula)
        sv.addWidget(blue)

        apply_swing = QPushButton("💾 저장 + 현재 종목 다시 분석")
        apply_swing.setObjectName("conditionBtn")
        apply_swing.clicked.connect(self.save_swing_and_reanalyze)
        self.focus_swing_settings_status = QLabel("설정은 config에 자동 보존됩니다.")
        self.focus_swing_settings_status.setStyleSheet("color:#8fb6d9")
        sv.addWidget(apply_swing)
        sv.addWidget(self.focus_swing_settings_status)
        sv.addStretch()
        self.focus_side_tabs.addTab(self._scroll_wrap(swing_settings_page), "역매공파 설정")

        order_page = QWidget()
        ov = QVBoxLayout(order_page)
        ov.setContentsMargins(5, 5, 5, 5)
        order = QGroupBox("바로 주문")
        of = QFormLayout(order)
        self.focus_order_type = QComboBox()
        self.focus_order_type.addItem("시장가", "market")
        self.focus_order_type.addItem("지정가", "limit")
        self.focus_order_type.addItem("스톱지정가", "stop_limit")
        self.focus_qty = self._spin(1, 10_000_000, 1)
        self.focus_order_price = self._spin(0, 2_000_000_000, 0, 100)
        self.focus_cond_price = self._spin(0, 2_000_000_000, 0, 100)
        of.addRow("주문방식", self.focus_order_type)
        of.addRow("수량", self.focus_qty)
        of.addRow("가격", self.focus_order_price)
        of.addRow("조건가격", self.focus_cond_price)
        qr = QHBoxLayout()
        for text, n in [("1주",1),("10주",10),("50주",50),("100주",100)]:
            b = QPushButton(text)
            b.clicked.connect(lambda _, x=n: self.focus_qty.setValue(x))
            qr.addWidget(b)
        of.addRow("빠른수량", qr)
        br = QHBoxLayout()
        bb = QPushButton("▲ 매수")
        bb.setStyleSheet("background:#b82f43;border:1px solid #ef5b6d;padding:12px;font-size:15px;font-weight:900")
        sb = QPushButton("▼ 매도")
        sb.setStyleSheet("background:#1e5fc5;border:1px solid #4f8fee;padding:12px;font-size:15px;font-weight:900")
        bb.clicked.connect(lambda: self.focus_submit("BUY"))
        sb.clicked.connect(lambda: self.focus_submit("SELL"))
        br.addWidget(bb)
        br.addWidget(sb)
        of.addRow(br)
        ov.addWidget(order)
        order_note = QLabel("실전 주문은 LIVE 잠금 + 주문 직전 LIVE ORDER 확인을 그대로 사용합니다.")
        order_note.setWordWrap(True)
        order_note.setStyleSheet("color:#9eb4c9")
        ov.addWidget(order_note)
        ov.addStretch()
        self.focus_side_tabs.addTab(self._scroll_wrap(order_page), "주문")

        auto_page = QWidget()
        auv = QVBoxLayout(auto_page)
        auv.setContentsMargins(5, 5, 5, 5)
        auto = QGroupBox("이 종목만 자동매매")
        afm = QFormLayout(auto)
        self.focus_budget = self._spin(10_000, 100_000_000, self.settings.order_budget, 10_000)
        self.focus_tp = self._dspin(0.1, 100, self.settings.take_profit_pct, " %")
        self.focus_sl = self._dspin(-50, -0.1, self.settings.stop_loss_pct, " %")
        self.focus_trail = QCheckBox("트레일링 스탑")
        self.focus_trail.setChecked(self.settings.trailing_enabled)
        self.focus_trail_start = self._dspin(0.1, 100, self.settings.trailing_start_pct, " %")
        self.focus_trail_gap = self._dspin(0.1, 30, self.settings.trailing_gap_pct, " %")
        afm.addRow("종목당 투입금", self.focus_budget)
        afm.addRow("익절", self.focus_tp)
        afm.addRow("손절", self.focus_sl)
        afm.addRow(self.focus_trail)
        afm.addRow("트레일링 시작", self.focus_trail_start)
        afm.addRow("고점대비 하락", self.focus_trail_gap)
        ar = QHBoxLayout()
        start = QPushButton("▶ 선택 종목 자동매매 시작")
        start.setObjectName("startBtn")
        stop = QPushButton("■ 중지")
        stop.setObjectName("stopBtn")
        start.clicked.connect(self.start_focus_auto)
        stop.clicked.connect(self.stop_auto)
        ar.addWidget(start)
        ar.addWidget(stop)
        afm.addRow(ar)
        auv.addWidget(auto)
        note = QLabel("단타는 '단타 분석' 탭에서 별도 판정합니다. 메인 자동매매는 기존 엔진 안전잠금/리스크 제한을 그대로 사용합니다.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#9eb4c9")
        auv.addWidget(note)
        auv.addStretch()
        self.focus_side_tabs.addTab(self._scroll_wrap(auto_page), "자동매매")

        self.focus_side_tabs.setMinimumWidth(330)
        self.focus_splitter.addWidget(self.focus_side_tabs)
        self.focus_splitter.setCollapsible(0, False)
        self.focus_splitter.setCollapsible(1, False)
        self.focus_splitter.setCollapsible(2, False)
        self.focus_splitter.setStretchFactor(0, 1)
        self.focus_splitter.setStretchFactor(1, 5)
        self.focus_splitter.setStretchFactor(2, 2)
        self.focus_splitter.setSizes([230, 850, 400])
        root.addWidget(self.focus_splitter, 1)
        return w
'''
ui = replace_func(ui, "_focus_tab(self):", "_strategy_tab(self):", new_focus)

# ---------- short-term analysis: resizable top + tabbed settings ----------
new_strategy = r'''    def _strategy_tab(self):
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(5)

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

        info = QLabel("5분봉 고정 · PUMA 기준선(26) · 장초반 거래량 · EMA 5/20/60 · 돌파/눌림을 함께 판정합니다. 공개 개념을 PUMA 방식으로 수치화한 분석판이며 비공개/유료 검색식을 복제한 것은 아닙니다.")
        info.setWordWrap(True)
        info.setStyleSheet("color:#9eb4c9;padding:3px")
        outer.addWidget(info)

        self.danta_vertical_splitter = QSplitter(Qt.Vertical)

        self.danta_analysis_splitter = QSplitter(Qt.Horizontal)
        self.danta_chart = SwingChart()
        self.danta_chart.setMinimumHeight(260)
        self.danta_analysis_splitter.addWidget(self.danta_chart)

        result_box = QGroupBox("단타 판정")
        rv = QVBoxLayout(result_box)
        self.danta_score_label = QLabel("패턴 -- / 100")
        self.danta_score_label.setAlignment(Qt.AlignCenter)
        self.danta_score_label.setStyleSheet("font-size:26px;font-weight:900;color:#62b8ff;padding:5px")
        self.danta_stage_label = QLabel("종목을 선택하세요")
        self.danta_stage_label.setAlignment(Qt.AlignCenter)
        self.danta_stage_label.setStyleSheet("font-size:16px;font-weight:900;color:#f4c95d;padding:4px")
        self.danta_details = QTableWidget(0, 2)
        self.danta_details.setHorizontalHeaderLabels(["판정 항목", "현재 상태"])
        dh = self.danta_details.horizontalHeader()
        dh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        dh.setSectionResizeMode(1, QHeaderView.Stretch)
        self.danta_details.verticalHeader().setVisible(False)
        self.danta_details.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.danta_details.setSelectionMode(QAbstractItemView.NoSelection)
        rv.addWidget(self.danta_score_label)
        rv.addWidget(self.danta_stage_label)
        rv.addWidget(self.danta_details, 1)
        self.danta_analysis_splitter.addWidget(result_box)
        self.danta_analysis_splitter.setStretchFactor(0, 5)
        self.danta_analysis_splitter.setStretchFactor(1, 2)
        self.danta_analysis_splitter.setSizes([960, 430])
        self.danta_vertical_splitter.addWidget(self.danta_analysis_splitter)

        self.danta_settings_tabs = QTabWidget()

        criteria = QWidget()
        cg = QGridLayout(criteria)
        cg.setContentsMargins(10, 10, 10, 10)
        self.timeframe = QComboBox()
        self.timeframe.addItem("5")
        self.timeframe.setCurrentText("5")
        self.timeframe.setEnabled(False)
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
        pairs = [
            ("기준 분봉", self.timeframe), ("검색 시작", self.scan_start),
            ("검색 종료", self.scan_end), ("최소 등락률", self.min_change),
            ("최대 등락률", self.max_change), ("거래량 급증", self.vol_ratio),
            ("단기 EMA", self.ma_fast), ("중기 EMA", self.ma_mid),
            ("장기 EMA", self.ma_slow), ("돌파 Lookback", self.breakout),
            ("RSI 최소", self.rsi_min), ("RSI 최대", self.rsi_max),
        ]
        for i, (label, widget) in enumerate(pairs):
            col = 0 if i < 6 else 2
            row = i if i < 6 else i - 6
            cg.addWidget(QLabel(label), row, col)
            cg.addWidget(widget, row, col + 1)
        cg.addWidget(self.use_ma, 6, 0, 1, 2)
        cg.addWidget(self.use_breakout, 6, 2, 1, 2)
        cg.addWidget(self.use_rsi, 7, 0, 1, 2)
        crit_note = QLabel("단타 분석 자체는 5분봉으로 고정합니다. 시간 조건은 실시간 진입 가능 여부에만 사용하고, 패턴 점수는 장 마감 후 복기에서도 유지됩니다.")
        crit_note.setWordWrap(True)
        crit_note.setStyleSheet("color:#9eb4c9")
        cg.addWidget(crit_note, 8, 0, 1, 4)
        self.danta_settings_tabs.addTab(self._scroll_wrap(criteria), "분석 기준")

        risk = QWidget()
        rf = QFormLayout(risk)
        self.order_budget = self._spin(10_000, 100_000_000, self.settings.order_budget, 10_000)
        self.max_positions = self._spin(1, 20, self.settings.max_positions)
        self.cooldown = self._spin(0, 240, self.settings.cooldown_min)
        self.max_daily_orders = self._spin(1, 100, self.settings.max_daily_orders)
        self.account_sync_sec = self._spin(2, 60, self.settings.account_sync_sec)
        self.exchange_combo = QComboBox()
        self.exchange_combo.addItems(["KRX", "NXT", "SOR"])
        self.exchange_combo.setCurrentText(self.settings.order_exchange)
        rf.addRow("종목당 투입금", self.order_budget)
        rf.addRow("최대 보유종목", self.max_positions)
        rf.addRow("재진입 대기(분)", self.cooldown)
        rf.addRow("PUMA 일일 주문 상한", self.max_daily_orders)
        rf.addRow("실계좌 동기화(초)", self.account_sync_sec)
        rf.addRow("주문 거래소", self.exchange_combo)
        risk_note = QLabel("실전 자동주문은 LIVE START 안전잠금과 실제 잔고 동기화를 그대로 사용합니다.")
        risk_note.setWordWrap(True)
        risk_note.setStyleSheet("color:#9eb4c9")
        rf.addRow(risk_note)
        self.danta_settings_tabs.addTab(self._scroll_wrap(risk), "주문 · 리스크")

        sell = QWidget()
        sf = QFormLayout(sell)
        self.take_profit = self._dspin(0.1, 100, self.settings.take_profit_pct, " %")
        self.stop_loss = self._dspin(-50, -0.1, self.settings.stop_loss_pct, " %")
        self.trailing = QCheckBox("트레일링 스탑 사용")
        self.trailing.setChecked(self.settings.trailing_enabled)
        self.trailing_start = self._dspin(0.1, 100, self.settings.trailing_start_pct, " %")
        self.trailing_gap = self._dspin(0.1, 30, self.settings.trailing_gap_pct, " %")
        self.force_exit = QCheckBox("장 종료 전 전량청산")
        self.force_exit.setChecked(self.settings.force_exit_enabled)
        self.force_exit_time = QTimeEdit(QTime.fromString(self.settings.force_exit_time, "HH:mm"))
        sf.addRow("익절", self.take_profit)
        sf.addRow("손절", self.stop_loss)
        sf.addRow(self.trailing)
        sf.addRow("트레일링 시작", self.trailing_start)
        sf.addRow("고점 대비 하락", self.trailing_gap)
        sf.addRow(self.force_exit)
        sf.addRow("청산 시각", self.force_exit_time)
        save = QPushButton("💾 단타/리스크 설정 저장")
        save.clicked.connect(self.save_settings)
        sf.addRow(save)
        self.danta_settings_tabs.addTab(self._scroll_wrap(sell), "매도 조건")

        self.danta_settings_tabs.setMinimumHeight(210)
        self.danta_vertical_splitter.addWidget(self.danta_settings_tabs)
        self.danta_vertical_splitter.setStretchFactor(0, 4)
        self.danta_vertical_splitter.setStretchFactor(1, 2)
        self.danta_vertical_splitter.setSizes([520, 260])
        outer.addWidget(self.danta_vertical_splitter, 1)
        return w
'''
ui = replace_func(ui, "_strategy_tab(self):", "_manual_order_tab(self):", new_strategy)

# ---------- manual order: resizable instead of fixed three-column squeeze ----------
new_manual = r'''    def _manual_order_tab(self):
        w = QWidget()
        root = QVBoxLayout(w)
        root.setContentsMargins(6, 6, 6, 6)

        self.manual_splitter = QSplitter(Qt.Horizontal)

        order = QGroupBox("영웅문 스타일 수동주문")
        f = QFormLayout(order)
        self.manual_code = QLineEdit("005930")
        self.manual_name = QLabel("-")
        self.manual_current = QLabel("-")
        self.manual_current.setStyleSheet("font-size:24px;font-weight:900;color:#ff5a5f")
        quote_btn = QPushButton("현재가 조회")
        quote_btn.clicked.connect(self.manual_quote)
        qrow = QHBoxLayout()
        qrow.addWidget(self.manual_code)
        qrow.addWidget(quote_btn)
        f.addRow("종목코드", qrow)
        f.addRow("종목명", self.manual_name)
        f.addRow("현재가", self.manual_current)

        self.manual_type = QComboBox()
        self.manual_type.addItem("시장가", "market")
        self.manual_type.addItem("지정가", "limit")
        self.manual_type.addItem("스톱지정가", "stop_limit")
        self.manual_qty = self._spin(1, 10_000_000, 1)
        self.manual_price = self._spin(0, 2_000_000_000, 0, 100)
        self.manual_cond_price = self._spin(0, 2_000_000_000, 0, 100)
        f.addRow("주문방식", self.manual_type)
        f.addRow("수량", self.manual_qty)
        f.addRow("주문가격", self.manual_price)
        f.addRow("조건가격(스톱)", self.manual_cond_price)

        quick = QHBoxLayout()
        for text, n in [("1주",1),("10주",10),("50주",50),("100주",100)]:
            b = QPushButton(text)
            b.clicked.connect(lambda _, x=n: self.manual_qty.setValue(x))
            quick.addWidget(b)
        f.addRow("빠른수량", quick)

        buy = QPushButton("▲ 매수 주문")
        buy.setStyleSheet("background:#b82f43;border:1px solid #ef5b6d;padding:14px;font-size:16px;font-weight:900")
        sell = QPushButton("▼ 매도 주문")
        sell.setStyleSheet("background:#1e5fc5;border:1px solid #4f8fee;padding:14px;font-size:16px;font-weight:900")
        buy.clicked.connect(lambda: self.manual_submit("BUY"))
        sell.clicked.connect(lambda: self.manual_submit("SELL"))
        brow = QHBoxLayout()
        brow.addWidget(buy)
        brow.addWidget(sell)
        f.addRow(brow)
        warning = QLabel("실전 수동주문은 LIVE 1차 잠금 + 주문 직전 LIVE ORDER 확인이 필요합니다.")
        warning.setWordWrap(True)
        f.addRow(warning)
        self.manual_splitter.addWidget(self._scroll_wrap(order))

        ema = QGroupBox("EMA 기준 주문 · 준비")
        ef = QFormLayout(ema)
        self.manual_ema_period = QComboBox()
        self.manual_ema_period.addItems(["5","20","60","112","224","448"])
        self.manual_ema_offset = self._dspin(-10,10,0.0," %")
        self.manual_ema_action = QComboBox()
        self.manual_ema_action.addItems(["도달 시 매수","종가 이탈 시 매도","터치 시 매도"])
        ef.addRow("기준 EMA", self.manual_ema_period)
        ef.addRow("EMA 대비 가격", self.manual_ema_offset)
        ef.addRow("동작", self.manual_ema_action)
        info = QLabel("EMA 예약주문은 실시간 시세 스트림 연결 전 단계입니다. 현재 직접 주문은 시장가/지정가/스톱지정가까지 REST 주문에 연결되어 있습니다.")
        info.setWordWrap(True)
        info.setStyleSheet("color:#9eb4c9")
        ef.addRow(info)
        self.manual_splitter.addWidget(self._scroll_wrap(ema))

        helpbox = QGroupBox("주문 방식")
        hv = QVBoxLayout(helpbox)
        help_text = QLabel("시장가: 현재 시장에서 즉시 체결을 시도\n\n지정가: 원하는 가격을 직접 입력\n\n스톱지정가: 조건가격 도달 시 지정가 주문으로 전환\n\nPUMA 자동매매와 수동주문은 서로 분리 기록합니다.")
        help_text.setWordWrap(True)
        hv.addWidget(help_text)
        hv.addStretch()
        self.manual_splitter.addWidget(self._scroll_wrap(helpbox))

        self.manual_splitter.setStretchFactor(0, 2)
        self.manual_splitter.setStretchFactor(1, 1)
        self.manual_splitter.setStretchFactor(2, 1)
        self.manual_splitter.setSizes([650, 420, 360])
        root.addWidget(self.manual_splitter, 1)
        return w
'''
ui = replace_func(ui, "_manual_order_tab(self):", "_swing_tab(self):", new_manual)

# ---------- connection tab: scroll-safe ----------
new_connection = r'''    def _connection_tab(self):
        outer = QWidget()
        root = QVBoxLayout(outer)
        root.setContentsMargins(6, 6, 6, 6)

        content = QWidget()
        lay = QGridLayout(content)

        api = QGroupBox("키움 REST API · 한 번 저장 후 자동 연결")
        al = QFormLayout(api)
        self.appkey = QLineEdit()
        self.appkey.setPlaceholderText("처음 한 번만 입력")
        self.secret = QLineEdit()
        self.secret.setEchoMode(QLineEdit.Password)
        self.secret.setPlaceholderText("처음 한 번만 입력")
        self.api_env = QComboBox()
        self.api_env.addItems(["모의투자", "실전투자"])
        self.remember_kiwoom = QCheckBox("이 PC에 안전하게 기억")
        self.remember_kiwoom.setChecked(True)
        self.auto_connect_box = QCheckBox("PUMA 실행 시 자동 연결")
        self.auto_connect_box.setChecked(True)

        row = QHBoxLayout()
        connect = QPushButton("⚡ 저장하고 바로 연결")
        connect.clicked.connect(self.save_and_connect_kiwoom)
        forget = QPushButton("저장정보 삭제")
        forget.clicked.connect(self.forget_kiwoom_credentials)
        row.addWidget(connect)
        row.addWidget(forget)

        self.live_btn = QPushButton("🔒 실전주문 잠금 해제")
        self.live_btn.setObjectName("liveBtn")
        self.live_btn.clicked.connect(self.arm_live)
        self.saved_cred_label = QLabel("저장된 연결정보 없음")
        self.saved_cred_label.setStyleSheet("color:#8fb6d9")

        al.addRow("App Key", self.appkey)
        al.addRow("App Secret", self.secret)
        al.addRow("환경", self.api_env)
        al.addRow(self.remember_kiwoom)
        al.addRow(self.auto_connect_box)
        al.addRow(row)
        al.addRow("상태", self.saved_cred_label)
        al.addRow(self.live_btn)
        note = QLabel("App Key/Secret은 평문 JSON으로 저장하지 않고 Windows DPAPI로 암호화합니다. 자동 연결은 인증만 수행하며 실전주문 잠금은 자동으로 풀지 않습니다.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#9eb4c9")
        al.addRow(note)

        sim = QGroupBox("오프라인 테스트")
        sl = QVBoxLayout(sim)
        sim_note = QLabel("키움 연결 없이 UI와 전략 로직을 시험합니다. 실제 주문은 전송되지 않습니다.")
        sim_note.setWordWrap(True)
        sl.addWidget(sim_note)
        btn = QPushButton("SIMULATION 모드로 전환")
        btn.clicked.connect(self.use_sim)
        sl.addWidget(btn)

        safety = QGroupBox("실전 안전장치")
        sf = QVBoxLayout(safety)
        safety_note = QLabel(
            "· 프로그램 시작 시 실전 서버 자동 인증 가능\n"
            "· 실제 주문은 별도 실전주문 잠금 해제 필요\n"
            "· 자동매매 시작 시 LIVE START 재확인\n"
            "· 실제 잔고 동기화 / 일일 주문 상한 / 중복주문 차단 유지"
        )
        safety_note.setWordWrap(True)
        sf.addWidget(safety_note)

        lay.addWidget(api, 0, 0, 1, 2)
        lay.addWidget(sim, 1, 0)
        lay.addWidget(safety, 1, 1)
        lay.setRowStretch(2, 1)

        root.addWidget(self._scroll_wrap(content), 1)
        return outer
'''
ui = replace_func(ui, "_connection_tab(self):", "_update_tab(self):", new_connection)

# ---------- helpers for scroll / screen / saved splitter layout ----------
helper_anchor = """    # ---------- helpers ----------
    def _dspin(self, lo, hi, val, suffix=""):
"""
helper_block = r'''    # ---------- helpers ----------
    def _scroll_wrap(self, widget: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(widget)
        return scroll

    def _apply_display_profile(self):
        screen = QApplication.primaryScreen()
        if not screen:
            return
        geo = screen.availableGeometry()
        width, height = geo.width(), geo.height()

        if hasattr(self, "focus_splitter"):
            left = max(195, min(300, int(width * 0.15)))
            right = max(340, min(480, int(width * 0.25)))
            center = max(520, width - left - right - 90)
            self.focus_splitter.setSizes([left, center, right])
        if hasattr(self, "focus_chart"):
            self.focus_chart.setMinimumHeight(300 if height < 850 else 380)

        if hasattr(self, "danta_analysis_splitter"):
            chart_w = max(620, int(width * 0.68))
            result_w = max(330, int(width * 0.27))
            self.danta_analysis_splitter.setSizes([chart_w, result_w])
        if hasattr(self, "danta_vertical_splitter"):
            upper = max(340, int(height * 0.56))
            lower = max(210, int(height * 0.26))
            self.danta_vertical_splitter.setSizes([upper, lower])
        if hasattr(self, "danta_chart"):
            self.danta_chart.setMinimumHeight(245 if height < 850 else 300)
        if hasattr(self, "manual_splitter"):
            self.manual_splitter.setSizes([
                max(430, int(width * 0.43)),
                max(300, int(width * 0.28)),
                max(260, int(width * 0.24)),
            ])

    def _restore_ui_layout(self):
        for key, widget in [
            ("focus_splitter", getattr(self, "focus_splitter", None)),
            ("dashboard_splitter", getattr(self, "dashboard_splitter", None)),
            ("danta_vertical_splitter", getattr(self, "danta_vertical_splitter", None)),
            ("danta_analysis_splitter", getattr(self, "danta_analysis_splitter", None)),
            ("manual_splitter", getattr(self, "manual_splitter", None)),
        ]:
            if widget is None:
                continue
            state = self.ui_state.value(key)
            if state:
                try:
                    widget.restoreState(state)
                except Exception:
                    pass

    def _save_ui_layout(self):
        for key, widget in [
            ("focus_splitter", getattr(self, "focus_splitter", None)),
            ("dashboard_splitter", getattr(self, "dashboard_splitter", None)),
            ("danta_vertical_splitter", getattr(self, "danta_vertical_splitter", None)),
            ("danta_analysis_splitter", getattr(self, "danta_analysis_splitter", None)),
            ("manual_splitter", getattr(self, "manual_splitter", None)),
        ]:
            if widget is not None:
                self.ui_state.setValue(key, widget.saveState())

    def _dspin(self, lo, hi, val, suffix=""):
'''
ui = once(ui, helper_anchor, helper_block, "UI helper block")

# ---------- Swing settings use integrated controls and persist ----------
old_swing_settings = r'''    def _swing_settings_from_ui(self):
        x = SwingSettings()
        x.volume_ratio = self.sw_vol_ratio.value()
        x.upper_wick_ratio = self.sw_wick_ratio.value()
        x.bearish_body_ratio = self.sw_bear_body.value()
        x.accumulation_lookback = self.sw_acc_lookback.value()
        x.box_window = self.sw_box_window.value()
        x.box_width_pct = self.sw_box_width.value()
        x.acceptance_window = self.sw_accept_window.value()
        x.acceptance_min_closes = min(self.sw_accept_count.value(), x.acceptance_window)
        x.blue_period = self.sw_blue_period.value()
        x.blue_dev = self.sw_blue_dev.value()
        x.blue_shift = self.sw_blue_shift.value()
        x.blue_near_pct = self.sw_blue_near.value()
        self.swing_settings = x
        return x
'''
new_swing_settings = r'''    def _swing_settings_from_ui(self):
        x = SwingSettings()
        x.volume_ratio = self.sw_vol_ratio.value()
        x.upper_wick_ratio = self.sw_wick_ratio.value()
        x.bearish_body_ratio = self.sw_bear_body.value()
        x.accumulation_lookback = self.sw_acc_lookback.value()
        x.box_window = self.sw_box_window.value()
        x.box_width_pct = self.sw_box_width.value()
        x.acceptance_window = self.sw_accept_window.value()
        x.acceptance_min_closes = min(self.sw_accept_count.value(), x.acceptance_window)
        x.blue_period = self.sw_blue_period.value()
        x.blue_dev = self.sw_blue_dev.value()
        x.blue_shift = self.sw_blue_shift.value()
        x.blue_near_pct = self.sw_blue_near.value()
        self.swing_settings = x
        save_swing_settings(x)
        return x

    def save_swing_and_reanalyze(self):
        try:
            settings = self._swing_settings_from_ui()
            self.focus_swing_settings_status.setText("설정 저장 완료")
            if self.focus_daily_raw:
                sa, series = analyze_swing(self.focus_daily_raw, settings)
                self.focus_daily_analysis = sa
                self.focus_daily_series = series
                self._apply_focus_analyses(sa, self.focus_bowl_analysis, "전체")
                self._update_focus_chart(True)
                self.focus_swing_settings_status.setText(f"저장 + 재분석 완료 · {sa.stage} · {sa.score}/100")
        except Exception as exc:
            self.focus_swing_settings_status.setText(f"저장/재분석 실패: {exc}")
'''
ui = once(ui, old_swing_settings, new_swing_settings, "swing persistence")

# ---------- Danta UI result language ----------
ui = ui.replace('self.danta_score_label.setText(f"{result.score} / 100")',
                'self.danta_score_label.setText(f"패턴 {result.score} / 100")')
ui = ui.replace('self.strategy_signal_label.setText(f"5분봉 · {result.stage} · {result.score}/100")',
                'self.strategy_signal_label.setText(f"5분봉 · {result.stage} · 패턴 {result.score}/100")')

# Update current notes.
ui = ui.replace(
    "v0.9: 메인 오른쪽 영역 스크롤/폭 개선, 역매공파 별도 중복 탭 제거 후 메인 통합 유지, 단타 분석 전용 화면 추가.",
    "v1.0: 전 화면 레이아웃 재구성, 메인 우측 기능탭, 단타 설정 탭화, 해상도 자동배치/분할비율 저장, 역매공파 설정 영구저장."
)

# Save splitter layout on exit.
ui = once(ui,
"""    def closeEvent(self, event):
        self.stop_auto()
        self.stop_condition_stream()
        event.accept()
""",
"""    def closeEvent(self, event):
        self._save_ui_layout()
        self.stop_auto()
        self.stop_condition_stream()
        event.accept()
""",
"close state")

# ---------- storage.py: swing settings persistence ----------
storage = once(storage, "from .models import StrategySettings\n",
               "from .models import StrategySettings\nfrom .swing import SwingSettings\n",
               "storage swing import")
storage = once(storage, 'RUNTIME_PATH = CONFIG_DIR / "runtime.json"\n',
               'RUNTIME_PATH = CONFIG_DIR / "runtime.json"\nSWING_PATH = CONFIG_DIR / "swing.json"\n',
               "swing path")
storage += r'''

def load_swing_settings() -> SwingSettings:
    CONFIG_DIR.mkdir(exist_ok=True)
    if not SWING_PATH.exists():
        return SwingSettings()
    try:
        raw = json.loads(SWING_PATH.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return SwingSettings()
        allowed = SwingSettings().__dict__.keys()
        clean = {k: raw[k] for k in allowed if k in raw}
        return SwingSettings(**clean)
    except Exception:
        return SwingSettings()


def save_swing_settings(settings: SwingSettings):
    CONFIG_DIR.mkdir(exist_ok=True)
    SWING_PATH.write_text(
        json.dumps(settings.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
'''

# ---------- chart: a compact colored line legend ----------
needle = """        p.setPen(QColor('#7991aa')); p.setFont(QFont('Malgun Gothic',8))
        p.drawText(int(price_rect.right()-410), 19, 400, 18, Qt.AlignRight, '휠: 확대/축소 · 드래그: 과거/최신 이동 · 더블클릭: 최신')
"""
legend = """        p.setPen(QColor('#7991aa')); p.setFont(QFont('Malgun Gothic',8))
        p.drawText(int(price_rect.right()-410), 19, 400, 18, Qt.AlignRight, '휠: 확대/축소 · 드래그: 과거/최신 이동 · 더블클릭: 최신')

        # 현재 차트에 실제 존재하는 선만 간단한 색상 범례로 표시.
        label_map = {
            'ema5':'EMA5', 'ema20':'EMA20', 'ema60':'EMA60', 'ema112':'EMA112',
            'ema224':'EMA224', 'ema448':'EMA448', 'blue':'파란점선', 'kijun':'PUMA기준선'
        }
        lx = price_rect.left()
        ly = price_rect.top() + 13
        p.setFont(QFont('Malgun Gothic', 7, QFont.Bold))
        for key in line_keys:
            name = label_map.get(key)
            if not name:
                continue
            p.setPen(QColor(colors.get(key, '#9bb8d1')))
            p.drawText(int(lx), int(ly), name)
            lx += 12 + max(35, len(name) * 8)
            if lx > price_rect.right() - 80:
                break
"""
chart = once(chart, needle, legend, "chart line legend")

# ---------- versions ----------
updater = once(updater, 'CURRENT_VERSION = "0.9.0"', 'CURRENT_VERSION = "1.0.0"', "updater version")
updater = updater.replace("PUMA-STOCK-UPDATER/0.9", "PUMA-STOCK-UPDATER/1.0")

ui_path.write_text(ui, encoding="utf-8")
storage_path.write_text(storage, encoding="utf-8")
chart_path.write_text(chart, encoding="utf-8")
updater_path.write_text(updater, encoding="utf-8")
init_path.write_text('__version__ = "1.0.0"\n', encoding="utf-8")

print("PUMA v1.0 UI overhaul applied")
