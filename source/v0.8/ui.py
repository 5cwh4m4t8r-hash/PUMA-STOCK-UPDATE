from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QTime, QTimer, Qt, QDate
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QDateEdit,
    QFormLayout,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from .broker import BrokerError, KiwoomRestBroker, SimBroker
from .conditions import ConditionStreamThread, fetch_condition_list
from .engine import TradeEngine
from .models import StrategySettings
from .storage import load_strategy, load_watchlist, save_strategy, save_watchlist
from .swing import SwingSettings, analyze as analyze_swing, demo_candles, normalize_candles, ema
from .strategy import evaluate_buy
from .bowl import BowlSettings, analyze_bowl
from .swing_chart import SwingChart
from .updater import CURRENT_VERSION, download_package, fetch_manifest, load_update_config, save_update_config, stage_and_apply
from .secure_credentials import load_credentials, save_credentials, clear_credentials, CredentialError

DARK = """
QMainWindow, QWidget { background: #0b1626; color: #e8eef7; font-family: 'Malgun Gothic'; }
QGroupBox { border: 1px solid #29415f; border-radius: 8px; margin-top: 12px; padding: 10px; font-weight: 700; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 6px; }
QPushButton { background: #183457; border: 1px solid #315b89; border-radius: 7px; padding: 8px 12px; font-weight: 700; }
QPushButton:hover { background: #21456f; }
QPushButton#startBtn { background:#078a50; border-color:#19b36f; }
QPushButton#stopBtn { background:#9e2e39; border-color:#d14b58; }
QPushButton#liveBtn { background:#7a5313; border-color:#b37c1e; }
QPushButton#conditionBtn { background:#164b7a; border-color:#2d79b8; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTimeEdit, QDateEdit { background:#101f33; border:1px solid #35506d; border-radius:5px; padding:5px; }
QTableWidget { background:#0f1d2f; gridline-color:#263d58; alternate-background-color:#12253b; }
QHeaderView::section { background:#162b45; color:#e8eef7; padding:7px; border:0; font-weight:700; }
QTabWidget::pane { border:1px solid #29415f; }
QTabBar::tab { background:#13253b; padding:7px 11px; margin-right:2px; }
QTabBar::tab:selected { background:#1d4776; }
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PUMA STOCK PRO v0.8")
        self.setMinimumSize(1024, 680)
        self.resize(1280, 800)
        self.setStyleSheet(DARK)

        self.settings = load_strategy()
        self.watchlist = load_watchlist()
        self.condition_candidates: dict[str, dict] = {}
        self.condition_thread: ConditionStreamThread | None = None
        self.condition_list: list[tuple[str, str]] = []
        self.row_by_code: dict[str, int] = {}
        self.name_cache: dict[str, str] = {}
        self.name_lookup_queue: list[str] = []
        self.selected_code: str = ""
        self.selected_name: str = ""
        self.focus_only_code: str | None = None

        self.broker = SimBroker()
        self.engine = TradeEngine(self.broker, self.settings)
        self.real_armed = False
        self.scan_index = 0
        self.swing_settings = SwingSettings()
        self.swing_raw = []
        self.swing_analysis = None
        self.bowl_settings = BowlSettings()
        self.focus_daily_raw: list[dict] = []
        self.focus_daily_series = None
        self.focus_daily_analysis = None
        self.focus_bowl_analysis = None
        self.focus_minute_raw: list[dict] = []
        self.focus_chart_mode = "DAY"
        self.focus_history_pages = 8
        self.focus_range_label = "전체"

        self.timer = QTimer(self)
        self.timer.setInterval(1800)
        self.timer.timeout.connect(self.scan_one)

        # 조건검색 WebSocket은 종목명 없이 코드만 주는 경우가 있어 REST 종목정보로 천천히 보완한다.
        self.name_lookup_timer = QTimer(self)
        self.name_lookup_timer.setInterval(420)
        self.name_lookup_timer.timeout.connect(self._resolve_next_name)

        self._build_ui()
        self._load_watchlist_rows()
        self._set_status("SIMULATION", "모의 엔진 준비 완료")

    # ---------- UI ----------
    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)

        header = QHBoxLayout()
        title = QLabel("🐆  PUMA STOCK PRO  v0.8")
        title.setFont(QFont("Malgun Gothic", 22, QFont.Bold))
        header.addWidget(title)
        header.addStretch()
        self.mode_label = QLabel("SIMULATION")
        self.mode_label.setStyleSheet("background:#0d6942;padding:8px 14px;border-radius:12px;font-weight:700")
        self.conn_label = QLabel("● 준비")
        self.quick_connect_btn = QPushButton("⚡ 키움 빠른연결")
        self.quick_connect_btn.clicked.connect(self.quick_connect)
        header.addWidget(self.mode_label)
        header.addWidget(self.conn_label)
        header.addWidget(self.quick_connect_btn)
        outer.addLayout(header)

        self.tabs = QTabWidget()
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

        self._load_saved_connection()
        if getattr(self, "auto_connect_box", None) is not None and self.auto_connect_box.isChecked():
            QTimer.singleShot(900, self.auto_connect_saved)

    def _dashboard_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)

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

        self.market_table = QTableWidget(0, 8)
        self.market_table.setHorizontalHeaderLabels([
            "종목코드", "종목명", "유입경로", "현재가", "상태", "신호/사유", "보유수량", "수익률"
        ])
        self.market_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.market_table.setAlternatingRowColors(True)
        self.market_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        lay.addWidget(self.market_table, 3)

        logbox = QGroupBox("실시간 주문/신호 로그")
        loglay = QVBoxLayout(logbox)
        self.log_table = QTableWidget(0, 5)
        self.log_table.setHorizontalHeaderLabels(["시간", "종목", "구분", "현재가", "내용"])
        self.log_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.log_table.setMaximumHeight(270)
        loglay.addWidget(self.log_table)
        lay.addWidget(logbox)
        return w

    def _focus_tab(self):
        """조건검색 종목 클릭 -> 과거차트/전략3종/주문/자동매매를 한 화면에서 처리."""
        w = QWidget()
        root = QVBoxLayout(w)

        head = QHBoxLayout()
        self.focus_title = QLabel("종목을 선택하세요")
        self.focus_title.setStyleSheet("font-size:22px;font-weight:900;color:#ffffff")
        self.focus_price = QLabel("-")
        self.focus_price.setStyleSheet("font-size:24px;font-weight:900;color:#ff626b")
        self.focus_origin = QLabel("조건검색 목록에서 종목을 클릭하면 자동으로 열립니다.")
        self.focus_origin.setStyleSheet("color:#8fb6d9")
        refresh = QPushButton("↻ 전체 새로고침")
        refresh.clicked.connect(self.focus_refresh)
        head.addWidget(self.focus_title)
        head.addWidget(self.focus_price)
        head.addWidget(self.focus_origin)
        head.addStretch()
        head.addWidget(refresh)
        root.addLayout(head)

        # 영웅문처럼 차트 자체에서 과거 탐색/확대/구간분석을 바로 수행한다.
        tools = QHBoxLayout()
        self.focus_chart_mode_combo = QComboBox()
        self.focus_chart_mode_combo.addItem("일봉 · 스윙/중장기", "DAY")
        self.focus_chart_mode_combo.addItem("5분봉 · 아침단타", "MIN")
        self.focus_chart_mode_combo.currentIndexChanged.connect(self.focus_chart_mode_changed)
        tools.addWidget(self.focus_chart_mode_combo)
        for text, fn in [
            ("◀ 과거", lambda: self.focus_chart.pan_bars(-60)),
            ("최신 ▶", lambda: self.focus_chart.show_latest()),
            ("＋ 확대", lambda: self.focus_chart.zoom_by(0.78)),
            ("－ 축소", lambda: self.focus_chart.zoom_by(1.28)),
            ("전체보기", lambda: self.focus_chart.show_all()),
        ]:
            b = QPushButton(text); b.clicked.connect(fn); tools.addWidget(b)
        more = QPushButton("과거 데이터 +5페이지")
        more.clicked.connect(self.focus_load_more_history)
        tools.addWidget(more)
        self.focus_view_label = QLabel("차트 구간: -")
        self.focus_view_label.setStyleSheet("color:#8fb6d9;font-weight:700")
        tools.addWidget(self.focus_view_label)
        tools.addStretch()
        root.addLayout(tools)

        range_row = QHBoxLayout()
        range_row.addWidget(QLabel("분석구간"))
        self.focus_range_start = QDateEdit(QDate.currentDate().addYears(-1))
        self.focus_range_end = QDateEdit(QDate.currentDate())
        for d in (self.focus_range_start, self.focus_range_end):
            d.setCalendarPopup(True); d.setDisplayFormat("yyyy-MM-dd")
        range_row.addWidget(self.focus_range_start)
        range_row.addWidget(QLabel("~"))
        range_row.addWidget(self.focus_range_end)
        range_btn = QPushButton("선택 날짜 분석")
        range_btn.clicked.connect(self.focus_analyze_date_range)
        visible_btn = QPushButton("현재 보이는 구간 분석")
        visible_btn.clicked.connect(self.focus_analyze_visible)
        all_btn = QPushButton("전체 데이터 분석 복귀")
        all_btn.clicked.connect(self.focus_analyze_all)
        range_row.addWidget(range_btn); range_row.addWidget(visible_btn); range_row.addWidget(all_btn)
        self.focus_range_status = QLabel("분석: 전체")
        self.focus_range_status.setStyleSheet("color:#61ff8f;font-weight:800")
        range_row.addWidget(self.focus_range_status)
        range_row.addStretch()
        root.addLayout(range_row)

        body = QHBoxLayout()
        self.focus_splitter = QSplitter(Qt.Horizontal)

        candidates = QGroupBox("조건검색 결과")
        cand_lay = QVBoxLayout(candidates)
        self.focus_condition_table = QTableWidget(0, 3)
        self.focus_condition_table.setHorizontalHeaderLabels(["종목", "종목명", "상태"])
        self.focus_condition_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.focus_condition_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.focus_condition_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.focus_condition_table.cellClicked.connect(self._focus_condition_row_clicked)
        self.focus_condition_table.setMinimumWidth(210)
        self.focus_condition_table.setMaximumWidth(340)
        cand_lay.addWidget(self.focus_condition_table)
        cand_help = QLabel("영웅문 조건검색 종목을 클릭하면 오른쪽 차트·전략·주문이 즉시 바뀝니다.")
        cand_help.setWordWrap(True); cand_help.setStyleSheet("color:#8fb6d9")
        cand_lay.addWidget(cand_help)
        self.focus_splitter.addWidget(candidates)

        left_panel = QWidget()
        left = QVBoxLayout(left_panel)
        left.setContentsMargins(0, 0, 0, 0)
        self.focus_chart = SwingChart()
        self.focus_chart.viewportChanged.connect(lambda t: self.focus_view_label.setText("차트 구간: " + t))
        left.addWidget(self.focus_chart, 6)

        signals = QGroupBox("전략 3종 동시 분석 · 한 화면")
        sg = QGridLayout(signals)
        self.focus_day_signal = QLabel("오돌이 DAY\n5분봉 분석 대기")
        self.focus_day_signal.setAlignment(Qt.AlignCenter)
        self.focus_day_signal.setStyleSheet("font-size:15px;font-weight:900;color:#f4c95d;background:#122238;border-radius:8px;padding:10px")
        self.focus_swing_signal = QLabel("역매공파 SWING\n분석 대기")
        self.focus_swing_signal.setAlignment(Qt.AlignCenter)
        self.focus_swing_signal.setStyleSheet("font-size:15px;font-weight:900;color:#f4c95d;background:#122238;border-radius:8px;padding:10px")
        self.focus_bowl_signal = QLabel("밥그릇 3번 LONG\n분석 대기")
        self.focus_bowl_signal.setAlignment(Qt.AlignCenter)
        self.focus_bowl_signal.setStyleSheet("font-size:15px;font-weight:900;color:#f4c95d;background:#122238;border-radius:8px;padding:10px")
        sg.addWidget(self.focus_day_signal, 0, 0)
        sg.addWidget(self.focus_swing_signal, 0, 1)
        sg.addWidget(self.focus_bowl_signal, 0, 2)
        self.focus_stage = QLabel("통합판정: 데이터 대기")
        self.focus_stage.setStyleSheet("font-size:16px;font-weight:900;color:#61ff8f;padding:6px")
        sg.addWidget(self.focus_stage, 1, 0, 1, 3)
        left.addWidget(signals, 1)
        self.focus_splitter.addWidget(left_panel)

        right_panel = QWidget()
        right = QVBoxLayout(right_panel)
        right.setContentsMargins(0, 0, 0, 0)
        stagebox = QGroupBox("역매공파 SWING 진행상태")
        st = QGridLayout(stagebox)
        self.focus_stage_labels = {}
        names = ["장기 EMA 역배열", "매집봉/구간", "공구리(박스권)", "박스 상단 돌파", "상단 박스 안착", "파란점선", "수박/화살표"]
        for i, name in enumerate(names):
            a = QLabel(name); b = QLabel("대기")
            b.setStyleSheet("font-weight:800;color:#f4c95d")
            st.addWidget(a, i, 0); st.addWidget(b, i, 1)
            self.focus_stage_labels[name] = b
        right.addWidget(stagebox)

        bowlbox = QGroupBox("밥그릇 3번 · SWING~LONG")
        bg = QGridLayout(bowlbox)
        self.focus_bowl_labels = {}
        bowl_names = ["장기 224EMA 아래", "224EMA 돌파", "224EMA 위 안착", "눌림/지지", "224EMA 거리", "수박/화살표"]
        for i, name in enumerate(bowl_names):
            a = QLabel(name); b = QLabel("대기")
            b.setStyleSheet("font-weight:800;color:#f4c95d")
            bg.addWidget(a, i, 0); bg.addWidget(b, i, 1)
            self.focus_bowl_labels[name] = b
        right.addWidget(bowlbox)

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
            b=QPushButton(text); b.clicked.connect(lambda _, x=n: self.focus_qty.setValue(x)); qr.addWidget(b)
        of.addRow("빠른수량", qr)
        br = QHBoxLayout()
        bb = QPushButton("▲ 매수")
        bb.setStyleSheet("background:#b82f43;border:1px solid #ef5b6d;padding:12px;font-size:15px;font-weight:900")
        sb = QPushButton("▼ 매도")
        sb.setStyleSheet("background:#1e5fc5;border:1px solid #4f8fee;padding:12px;font-size:15px;font-weight:900")
        bb.clicked.connect(lambda: self.focus_submit('BUY'))
        sb.clicked.connect(lambda: self.focus_submit('SELL'))
        br.addWidget(bb); br.addWidget(sb)
        of.addRow(br)
        right.addWidget(order)

        auto = QGroupBox("이 종목만 자동매매")
        af = QFormLayout(auto)
        self.focus_budget = self._spin(10_000, 100_000_000, self.settings.order_budget, 10_000)
        self.focus_tp = self._dspin(0.1, 100, self.settings.take_profit_pct, " %")
        self.focus_sl = self._dspin(-50, -0.1, self.settings.stop_loss_pct, " %")
        self.focus_trail = QCheckBox("트레일링 스탑")
        self.focus_trail.setChecked(self.settings.trailing_enabled)
        self.focus_trail_start = self._dspin(0.1, 100, self.settings.trailing_start_pct, " %")
        self.focus_trail_gap = self._dspin(0.1, 30, self.settings.trailing_gap_pct, " %")
        af.addRow("종목당 투입금", self.focus_budget)
        af.addRow("익절", self.focus_tp)
        af.addRow("손절", self.focus_sl)
        af.addRow(self.focus_trail)
        af.addRow("트레일링 시작", self.focus_trail_start)
        af.addRow("고점대비 하락", self.focus_trail_gap)
        ar = QHBoxLayout()
        start = QPushButton("▶ 선택 종목 자동매매 시작")
        start.setObjectName("startBtn")
        stop = QPushButton("■ 중지")
        stop.setObjectName("stopBtn")
        start.clicked.connect(self.start_focus_auto)
        stop.clicked.connect(self.stop_auto)
        ar.addWidget(start); ar.addWidget(stop)
        af.addRow(ar)
        note = QLabel("오돌이는 아침단타, 역매공파+수박은 스윙, 밥그릇3번+수박은 스윙~중장기로 분리 판정합니다. 수박/화살표 최종식은 추후 연결합니다.")
        note.setWordWrap(True); note.setStyleSheet("color:#9eb4c9")
        af.addRow(note)
        right.addWidget(auto)
        right.addStretch()
        self.focus_splitter.addWidget(right_panel)
        self.focus_splitter.setCollapsible(0, False)
        self.focus_splitter.setCollapsible(1, False)
        self.focus_splitter.setCollapsible(2, False)
        self.focus_splitter.setStretchFactor(0, 1)
        self.focus_splitter.setStretchFactor(1, 5)
        self.focus_splitter.setStretchFactor(2, 2)
        self.focus_splitter.setSizes([240, 820, 360])
        body.addWidget(self.focus_splitter)
        root.addLayout(body, 1)
        return w

    def _strategy_tab(self):
        w = QWidget()
        outer = QVBoxLayout(w)

        selected_row = QHBoxLayout()
        self.strategy_selected_label = QLabel("선택종목: 없음")
        self.strategy_selected_label.setStyleSheet("font-size:17px;font-weight:900;color:#8dc7ff")
        self.strategy_signal_label = QLabel("오돌이 분석: 종목을 선택하세요")
        self.strategy_signal_label.setStyleSheet("font-weight:800;color:#f4c95d")
        strategy_refresh = QPushButton("↻ 선택종목 즉시 분석")
        strategy_refresh.clicked.connect(self.strategy_refresh_selected)
        selected_row.addWidget(self.strategy_selected_label)
        selected_row.addWidget(self.strategy_signal_label)
        selected_row.addStretch()
        selected_row.addWidget(strategy_refresh)
        outer.addLayout(selected_row)

        main = QHBoxLayout()
        outer.addLayout(main, 1)

        buy = QGroupBox("매수 조건 · PUMA 2차 필터")
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
        r.addRow(QLabel("실전은 시작 시 LIVE START를 한 번 더 입력해야 주문이 열립니다."))

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
        save = QPushButton("💾 전체 조건 저장")
        save.clicked.connect(self.save_settings)
        s.addRow(save)

        main.addWidget(buy, 2)
        main.addWidget(risk, 1)
        main.addWidget(sell, 1)
        return w

    def _manual_order_tab(self):
        w = QWidget()
        root = QHBoxLayout(w)

        order = QGroupBox("영웅문 스타일 수동주문")
        f = QFormLayout(order)
        self.manual_code = QLineEdit("005930")
        self.manual_name = QLabel("-")
        self.manual_current = QLabel("-")
        self.manual_current.setStyleSheet("font-size:24px;font-weight:900;color:#ff5a5f")
        quote_btn = QPushButton("현재가 조회")
        quote_btn.clicked.connect(self.manual_quote)
        qrow = QHBoxLayout(); qrow.addWidget(self.manual_code); qrow.addWidget(quote_btn)
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
            b=QPushButton(text); b.clicked.connect(lambda _, x=n: self.manual_qty.setValue(x)); quick.addWidget(b)
        f.addRow("빠른수량", quick)

        buy = QPushButton("▲ 매수 주문")
        buy.setStyleSheet("background:#b82f43;border:1px solid #ef5b6d;padding:14px;font-size:16px;font-weight:900")
        sell = QPushButton("▼ 매도 주문")
        sell.setStyleSheet("background:#1e5fc5;border:1px solid #4f8fee;padding:14px;font-size:16px;font-weight:900")
        buy.clicked.connect(lambda: self.manual_submit('BUY'))
        sell.clicked.connect(lambda: self.manual_submit('SELL'))
        brow=QHBoxLayout(); brow.addWidget(buy); brow.addWidget(sell)
        f.addRow(brow)
        f.addRow(QLabel("실전 계좌 수동주문도 LIVE 1차 잠금이 필요하며, 주문 직전 LIVE ORDER를 다시 확인합니다."))
        root.addWidget(order, 1)

        ema = QGroupBox("EMA 기준 주문 · 설계 준비")
        ef = QFormLayout(ema)
        self.manual_ema_period = QComboBox(); self.manual_ema_period.addItems(["5","20","60","112","224","448"])
        self.manual_ema_offset = self._dspin(-10,10,0.0," %")
        self.manual_ema_action = QComboBox(); self.manual_ema_action.addItems(["도달 시 매수","종가 이탈 시 매도","터치 시 매도"])
        ef.addRow("기준 EMA", self.manual_ema_period)
        ef.addRow("EMA 대비 가격", self.manual_ema_offset)
        ef.addRow("동작", self.manual_ema_action)
        info=QLabel("EMA 주문예약은 다음 단계에서 실시간 시세 스트림과 연결합니다.\n현재 v0.3은 수동 시장가/지정가/스톱지정가 주문까지 실제 API에 연결되어 있습니다.")
        info.setWordWrap(True); info.setStyleSheet("color:#9eb4c9")
        ef.addRow(info)
        root.addWidget(ema, 1)

        helpbox = QGroupBox("주문 방식")
        hv=QVBoxLayout(helpbox)
        hv.addWidget(QLabel("시장가: 현재 시장에서 즉시 체결을 시도\n\n지정가: 원하는 가격을 직접 입력\n\n스톱지정가: 조건가격에 도달하면 지정가 주문으로 전환\n\nPUMA 자동매매와 수동주문은 서로 분리하여 기록합니다."))
        hv.addStretch()
        root.addWidget(helpbox, 1)
        return w

    def _swing_tab(self):
        w = QWidget()
        root = QVBoxLayout(w)

        top = QHBoxLayout()
        title = QLabel("역매공파 SWING · 장기 EMA 역배열 → 매집봉/구간 → 공구리 → 상단 돌파/안착 → 파란점선 → 수박/화살표")
        title.setStyleSheet("font-size:16px;font-weight:800;color:#8dc7ff")
        self.swing_selected_label = QLabel("연동: 선택종목 없음")
        self.swing_selected_label.setStyleSheet("font-weight:800;color:#61ff8f")
        top.addWidget(title)
        top.addWidget(self.swing_selected_label)
        top.addStretch()
        self.swing_code = QLineEdit("100120")
        self.swing_code.setMaximumWidth(110)
        self.swing_code.setPlaceholderText("종목코드")
        top.addWidget(QLabel("종목")); top.addWidget(self.swing_code)
        demo_btn = QPushButton("데모 차트")
        demo_btn.clicked.connect(self.swing_load_demo)
        csv_btn = QPushButton("CSV 불러오기")
        csv_btn.clicked.connect(self.swing_load_csv)
        api_btn = QPushButton("키움 일봉 불러오기")
        api_btn.clicked.connect(self.swing_load_kiwoom)
        top.addWidget(demo_btn); top.addWidget(csv_btn); top.addWidget(api_btn)
        root.addLayout(top)

        body = QHBoxLayout()
        left = QVBoxLayout()
        self.swing_chart = SwingChart()
        left.addWidget(self.swing_chart, 4)

        stages = QGroupBox("역매공파 상태 분석")
        sg = QGridLayout(stages)
        self.swing_stage_labels = {}
        names = ["장기 EMA 역배열", "매집봉/구간", "공구리(박스권)", "박스 상단 돌파", "상단 박스 안착", "파란점선", "수박/화살표"]
        for i, name in enumerate(names):
            n = QLabel(name); n.setStyleSheet("font-weight:700")
            v = QLabel("대기")
            v.setStyleSheet("color:#f4c95d;font-weight:800")
            sg.addWidget(n, i, 0); sg.addWidget(v, i, 1)
            self.swing_stage_labels[name] = v
        self.swing_current_stage = QLabel("현재 단계: 데이터 대기")
        self.swing_current_stage.setStyleSheet("font-size:16px;font-weight:900;color:#62ff9a;padding:8px")
        sg.addWidget(self.swing_current_stage, len(names), 0, 1, 2)
        left.addWidget(stages, 1)
        body.addLayout(left, 3)

        right = QVBoxLayout()
        acc = QGroupBox("매집봉 기준 · 네가 정한 핵심")
        af = QFormLayout(acc)
        self.sw_vol_ratio = self._dspin(1.0, 20.0, 2.0, " 배")
        self.sw_wick_ratio = self._dspin(0.1, 0.9, 0.42)
        self.sw_bear_body = self._dspin(0.2, 0.95, 0.58)
        self.sw_acc_lookback = self._spin(20, 250, 90)
        af.addRow("거래량 평균 대비", self.sw_vol_ratio)
        af.addRow("긴 윗꼬리 / 전체폭 ≥", self.sw_wick_ratio)
        af.addRow("장대음봉 몸통 / 전체폭 ≥", self.sw_bear_body)
        af.addRow("매집 확인 Lookback", self.sw_acc_lookback)
        af.addRow(QLabel("※ 매집봉 = 고거래량 + (긴 윗꼬리 OR 장대음봉). 여러 번 나오면 매집구간으로 누적."))
        right.addWidget(acc)

        box = QGroupBox("공구리(박스권) 기준")
        bf = QFormLayout(box)
        self.sw_box_window = self._spin(5, 60, 18)
        self.sw_box_width = self._dspin(2, 30, 14.0, " %")
        self.sw_accept_window = self._spin(3, 20, 8)
        self.sw_accept_count = self._spin(2, 15, 4)
        bf.addRow("박스 판정 기간", self.sw_box_window)
        bf.addRow("박스 최대 폭", self.sw_box_width)
        bf.addRow("돌파 후 확인봉", self.sw_accept_window)
        bf.addRow("기존 상단 위 종가 최소", self.sw_accept_count)
        bf.addRow(QLabel("※ 공구리 = 기존 박스 상단 돌파 후, 위쪽에서 버티며 새 상단 박스에 안착하는지 확인."))
        right.addWidget(box)

        blue = QGroupBox("파란점선")
        bl = QFormLayout(blue)
        self.sw_blue_period = self._spin(2, 100, 26)
        self.sw_blue_dev = self._dspin(0.1, 5.0, 2.6)
        self.sw_blue_shift = self._spin(0, 100, 26)
        self.sw_blue_near = self._dspin(0.1, 15, 3.0, " %")
        bl.addRow("BBands Period", self.sw_blue_period)
        bl.addRow("편차 D1", self.sw_blue_dev)
        bl.addRow("Shift Period2", self.sw_blue_shift)
        bl.addRow("근접 판정", self.sw_blue_near)
        formula = QLabel("shift(BBandsUp(Period=26, D1=2.6), Period2=26)")
        formula.setStyleSheet("color:#4f9dff;font-weight:800")
        bl.addRow("영웅문 수식", formula)
        right.addWidget(blue)

        action = QPushButton("▶ 현재 데이터 다시 분석")
        action.setObjectName("conditionBtn")
        action.clicked.connect(self.swing_reanalyze)
        right.addWidget(action)
        note = QLabel("수박/화살표는 네 신호식을 받기 전까지 최종 트리거로 연결하지 않습니다.\n실전 자동주문은 기존 LIVE 이중잠금과 리스크 제한을 그대로 사용합니다.")
        note.setWordWrap(True); note.setStyleSheet("color:#9eb4c9;padding:8px")
        right.addWidget(note)
        right.addStretch()
        body.addLayout(right, 1)
        root.addLayout(body, 1)
        return w

    def _hero_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)

        info = QLabel(
            "영웅문4 [0150] 조건검색에서 사용자 조건식을 먼저 저장한 뒤 사용하세요.\n"
            "PUMA는 키움 WebSocket 조건검색 API로 조건식을 불러오고 실시간 편입/이탈 종목을 받습니다."
        )
        lay.addWidget(info)

        box = QGroupBox("영웅문4 조건식 연결")
        form = QFormLayout(box)
        self.condition_combo = QComboBox()
        self.condition_refresh_btn = QPushButton("조건식 목록 불러오기")
        self.condition_refresh_btn.clicked.connect(self.refresh_conditions)
        self.hero_secondary_filter = QCheckBox("영웅문4 편입 후 PUMA 5분봉 조건을 2차로 적용")
        self.hero_secondary_filter.setChecked(self.settings.hero_secondary_filter)
        self.hero_entry_only = QCheckBox("신규 편입(I) 종목만 자동매수 대상으로 사용 (권장)")
        self.hero_entry_only.setChecked(self.settings.hero_entry_only)
        self.condition_start_btn = QPushButton("▶ 실시간 조건검색 시작")
        self.condition_start_btn.setObjectName("conditionBtn")
        self.condition_start_btn.clicked.connect(self.start_condition_stream)
        self.condition_stop_btn = QPushButton("■ 조건검색 중지")
        self.condition_stop_btn.clicked.connect(self.stop_condition_stream)
        form.addRow("저장 조건식", self.condition_combo)
        form.addRow(self.condition_refresh_btn)
        form.addRow(self.hero_secondary_filter)
        form.addRow(self.hero_entry_only)
        row = QHBoxLayout()
        row.addWidget(self.condition_start_btn)
        row.addWidget(self.condition_stop_btn)
        form.addRow(row)
        self.condition_status = QLabel("키움 연결 후 조건식을 불러오세요.")
        form.addRow("상태", self.condition_status)
        lay.addWidget(box)

        self.condition_table = QTableWidget(0, 5)
        self.condition_table.setHorizontalHeaderLabels(["종목코드", "종목명", "상태", "편입시각", "분석·매매"])
        self.condition_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.condition_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.condition_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.condition_table.cellClicked.connect(self._condition_row_clicked)
        lay.addWidget(self.condition_table, 1)
        return w

    def _connection_tab(self):
        w = QWidget()
        lay = QGridLayout(w)

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
        row.addWidget(connect); row.addWidget(forget)

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
        note = QLabel("App Key/Secret은 평문 JSON으로 저장하지 않습니다. Windows DPAPI로 암호화되어 현재 Windows 사용자 계정에서만 복호화됩니다. 자동 연결은 인증만 수행하며 실전주문 잠금은 자동 해제하지 않습니다.")
        note.setWordWrap(True); note.setStyleSheet("color:#9eb4c9")
        al.addRow(note)

        sim = QGroupBox("오프라인 테스트")
        sl = QVBoxLayout(sim)
        sl.addWidget(QLabel("키움 연결 없이 UI와 전략 로직을 시험합니다. 실제 주문은 전송되지 않습니다."))
        btn = QPushButton("SIMULATION 모드로 전환")
        btn.clicked.connect(self.use_sim)
        sl.addWidget(btn)

        safety = QGroupBox("실전 안전장치")
        sf = QVBoxLayout(safety)
        sf.addWidget(QLabel(
            "· 프로그램 시작 시 실전 서버까지 자동 인증 가능\n"
            "· 하지만 실제 주문은 별도의 실전주문 잠금 해제가 있어야 전송\n"
            "· 자동매매 시작 시 LIVE START 재확인\n"
            "· 실제 잔고 동기화 / 일일 주문 상한 / 중복주문 차단 유지"
        ))

        lay.addWidget(api, 0, 0, 1, 2)
        lay.addWidget(sim, 1, 0)
        lay.addWidget(safety, 1, 1)
        return w

    def _update_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)

        current = QGroupBox("PUMA 업데이트")
        form = QFormLayout(current)
        self.update_current = QLabel(f"v{CURRENT_VERSION}")
        self.update_url = QLineEdit()
        self.update_url.setPlaceholderText("업데이트 manifest.json 주소")
        cfg = load_update_config()
        self.update_url.setText(str(cfg.get("manifest_url") or ""))
        self.update_status = QLabel("현재 버전이 설치되어 있습니다.")
        self.update_notes = QLabel("새 버전이 있으면 변경사항이 여기에 표시됩니다.")
        self.update_notes.setWordWrap(True)
        self.update_check_btn = QPushButton("업데이트 확인")
        self.update_apply_btn = QPushButton("업데이트 다운로드 및 적용")
        self.update_apply_btn.setEnabled(False)
        self.update_check_btn.clicked.connect(self.check_update)
        self.update_apply_btn.clicked.connect(self.apply_update)
        form.addRow("현재 버전", self.update_current)
        form.addRow("업데이트 서버", self.update_url)
        form.addRow(self.update_check_btn)
        form.addRow("상태", self.update_status)
        form.addRow("업데이트 내용", self.update_notes)
        form.addRow(self.update_apply_btn)
        lay.addWidget(current)

        info = QGroupBox("업데이트 방식")
        il = QVBoxLayout(info)
        il.addWidget(QLabel(
            "다음 버전부터는 ZIP을 매번 직접 풀 필요 없이 이 화면에서 업데이트합니다.\n"
            "업데이트 시 프로그램 본체만 교체하고 config/.venv/로그/사용자 데이터는 보존합니다.\n"
            "적용 직전 기존 프로그램 파일을 자동 백업하여 문제가 생기면 이전 버전으로 되돌릴 수 있게 합니다.\n"
            "※ 업데이트 서버 주소는 배포 채널(GitHub Releases 등)이 연결되면 1회만 설정하면 됩니다."
        ))
        lay.addWidget(info)
        lay.addStretch()
        self._pending_update = None
        return w

    def check_update(self):
        url = self.update_url.text().strip()
        save_update_config({"manifest_url": url})
        if not url:
            self.update_status.setText("업데이트 서버가 아직 설정되지 않았습니다.")
            self.update_notes.setText("v0.8: 해상도 최적화 + 통합/전략상세/역매공파/고급주문 선택종목 실시간 연동 + 종목 클릭 버그 수정.")
            self.update_apply_btn.setEnabled(False)
            return
        try:
            self.update_status.setText("업데이트 확인 중...")
            QApplication.processEvents()
            info = fetch_manifest(url)
            self._pending_update = info
            self.update_notes.setText(info.notes or "변경사항 설명이 없습니다.")
            if info.newer:
                self.update_status.setText(f"새 버전 v{info.version} 사용 가능")
                self.update_apply_btn.setEnabled(True)
            else:
                self.update_status.setText("현재 최신 버전입니다.")
                self.update_apply_btn.setEnabled(False)
        except Exception as exc:
            self._pending_update = None
            self.update_apply_btn.setEnabled(False)
            self.update_status.setText("업데이트 확인 실패")
            QMessageBox.warning(self, "업데이트 확인", str(exc))

    def apply_update(self):
        info = getattr(self, "_pending_update", None)
        if not info or not info.newer:
            QMessageBox.information(self, "업데이트", "적용할 새 버전이 없습니다.")
            return
        if self.timer.isActive():
            QMessageBox.warning(self, "업데이트", "자동매매를 먼저 중지한 뒤 업데이트하세요.")
            return
        ans = QMessageBox.question(
            self, "업데이트 적용",
            f"v{info.version}을 다운로드하고 적용합니다.\n프로그램이 종료된 뒤 자동으로 백업/교체/재실행됩니다.\n계속할까요?"
        )
        if ans != QMessageBox.Yes:
            return
        try:
            self.update_status.setText("업데이트 다운로드 중...")
            QApplication.processEvents()
            package = download_package(info)
            self.update_status.setText("업데이트 준비 완료. 프로그램을 재시작합니다.")
            stage_and_apply(package, info.version)
            QApplication.quit()
        except Exception as exc:
            self.update_status.setText("업데이트 실패")
            QMessageBox.critical(self, "업데이트 실패", str(exc))

    # ---------- helpers ----------
    def _dspin(self, lo, hi, val, suffix=""):
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

    def _set_status(self, mode, text):
        self.mode_label.setText(mode)
        self.conn_label.setText("● " + text)
        if "REAL" in mode:
            self.mode_label.setStyleSheet("background:#8a2727;padding:8px 14px;border-radius:12px;font-weight:700")
        elif "MOCK" in mode:
            self.mode_label.setStyleSheet("background:#6a5510;padding:8px 14px;border-radius:12px;font-weight:700")
        else:
            self.mode_label.setStyleSheet("background:#0d6942;padding:8px 14px;border-radius:12px;font-weight:700")

    def _source_for_code(self, code: str) -> str:
        parts = []
        if any(x.get("code") == code for x in self.watchlist):
            parts.append("관심")
        if self.condition_candidates.get(code, {}).get("active"):
            parts.append("영웅문4")
        if code in self.engine.positions:
            parts.append("보유")
        if code in self.engine.pending_orders:
            parts.append("주문중")
        return "+".join(parts) or "-"

    def _ensure_market_row(self, code: str, name: str = "", origin: str = "-"):
        if code in self.row_by_code:
            r = self.row_by_code[code]
            if name and self.market_table.item(r, 1).text() in ("", code):
                self.market_table.item(r, 1).setText(name)
            self.market_table.item(r, 2).setText(self._source_for_code(code) or origin)
            return r
        r = self.market_table.rowCount()
        self.market_table.insertRow(r)
        vals = [code, name or code, origin, "-", "대기", "-", "0", "-"]
        for c, v in enumerate(vals):
            self.market_table.setItem(r, c, QTableWidgetItem(str(v)))
        self.row_by_code[code] = r
        return r

    def _load_watchlist_rows(self):
        for item in self.watchlist:
            self._ensure_market_row(item.get("code", ""), item.get("name", ""), "관심")

    # ---------- 수동 주문 ----------
    def manual_quote(self):
        code = self.manual_code.text().strip()
        if not code:
            return
        try:
            name = code
            price = 0.0
            if isinstance(self.broker, KiwoomRestBroker):
                info = self.broker.get_stock_info(code)
                name = str(info.get('stk_nm') or code)
                price = abs(float(str(info.get('cur_prc', 0)).replace(',', '') or 0))
            else:
                rows = self.broker.get_minute_candles(code, 5)
                price = abs(float(str(rows[0].get('cur_prc', 0)).replace(',', '') or 0)) if rows else 0
                name = f"SIM {code}"
            self.manual_name.setText(name)
            self.manual_current.setText(f"{price:,.0f} 원")
            if price > 0 and self.manual_price.value() == 0:
                self.manual_price.setValue(int(price))
        except Exception as exc:
            QMessageBox.critical(self, "현재가 조회 실패", str(exc))

    def manual_submit(self, side: str):
        code = self.manual_code.text().strip()
        qty = self.manual_qty.value()
        order_type = str(self.manual_type.currentData())
        price = self.manual_price.value()
        cond = self.manual_cond_price.value()
        if not code:
            QMessageBox.warning(self, "주문", "종목코드를 입력하세요.")
            return
        if isinstance(self.broker, KiwoomRestBroker) and self.broker.real:
            if not self.real_armed:
                QMessageBox.warning(self, "실전 잠금", "키움 연결 탭에서 실전 LIVE 1차 잠금을 먼저 해제하세요.")
                return
            phrase, ok = QInputDialog.getText(self, "실전 수동주문 확인", f"{side} {code} {qty}주 주문입니다.\n실제 주문을 보내려면 LIVE ORDER 를 입력하세요.")
            if not ok or phrase.strip().upper() != 'LIVE ORDER':
                return
        try:
            resp = self.broker.place_order(side, code, qty, order_type, price, cond)
            self.log(code, side, f"{price:,}" if price else "시장가", str(resp.get('return_msg', resp)))
            QMessageBox.information(self, "주문 전송", f"주문번호: {resp.get('ord_no','-')}\n{resp.get('return_msg','정상 처리')}")
        except Exception as exc:
            QMessageBox.critical(self, "주문 실패", str(exc))

    # ---------- 역매공파 ----------
    def _swing_settings_from_ui(self):
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

    def swing_load_demo(self):
        self.swing_raw = demo_candles()
        self.swing_reanalyze()
        self.log("DEMO", "역매공파", "-", "합성 일봉 데이터를 불러왔습니다. 실제 투자판단용 데이터가 아닙니다.")

    def swing_load_csv(self):
        import csv
        path, _ = QFileDialog.getOpenFileName(self, "일봉 CSV 불러오기", "", "CSV (*.csv);;All Files (*)")
        if not path:
            return
        rows = []
        try:
            with open(path, 'r', encoding='utf-8-sig', newline='') as f:
                for r in csv.DictReader(f):
                    # date/open/high/low/close/volume 또는 키움 필드명을 모두 허용
                    rows.append(r)
            self.swing_raw = rows
            self.swing_reanalyze()
        except Exception as exc:
            QMessageBox.critical(self, "CSV 오류", str(exc))

    def swing_load_kiwoom(self, silent: bool = False):
        code = self.swing_code.text().strip()
        if not code:
            if not silent:
                QMessageBox.warning(self, "종목코드", "종목코드를 입력하세요.")
            return
        getter = getattr(self.broker, 'get_daily_candles', None)
        if not getter:
            if not silent:
                QMessageBox.information(self, "키움 연결 필요", "키움 연결 탭에서 REST API를 먼저 연결하세요.\nSIMULATION에서는 데모 차트를 사용하세요.")
            return
        try:
            self.conn_label.setText("● 일봉 조회 중...")
            QApplication.processEvents()
            rows = getter(code, max_pages=7)
            if not rows:
                raise BrokerError("일봉 데이터가 없습니다.")
            self.swing_raw = rows
            self.swing_reanalyze()
            self.conn_label.setText("● 일봉 분석 완료")
        except Exception as exc:
            self.conn_label.setText("● 조회 실패")
            if not silent:
                QMessageBox.critical(self, "키움 일봉 조회 실패", str(exc))

    def swing_reanalyze(self):
        if not self.swing_raw:
            QMessageBox.information(self, "데이터", "데모 차트, CSV 또는 키움 일봉을 먼저 불러오세요.")
            return
        try:
            analysis, series = analyze_swing(self.swing_raw, self._swing_settings_from_ui())
            self.swing_analysis = analysis
            self.swing_chart.set_data(analysis, series)
            for name, label in self.swing_stage_labels.items():
                text = analysis.details.get(name, "-")
                label.setText(text)
                good = any(k in text for k in ("확인", "감지")) and "미확인" not in text
                near = name == "파란점선" and analysis.blue_near
                label.setStyleSheet(f"color:{'#61ff8f' if (good or near) else '#f4c95d'};font-weight:800")
            self.swing_current_stage.setText(f"현재 단계: {analysis.stage}   ·   진행점수 {analysis.score}/100")
        except Exception as exc:
            QMessageBox.critical(self, "역매공파 분석 오류", str(exc))

    # ---------- settings ----------
    def _collect_settings(self) -> StrategySettings:
        seq = self.settings.hero_condition_seq
        name = self.settings.hero_condition_name
        if self.condition_combo.count() > 0 and self.condition_combo.currentData():
            data = self.condition_combo.currentData()
            if isinstance(data, tuple) and len(data) == 2:
                seq, name = data
        return StrategySettings(
            timeframe_min=int(self.timeframe.currentText()),
            scan_start=self.scan_start.time().toString("HH:mm"),
            scan_end=self.scan_end.time().toString("HH:mm"),
            min_change_pct=self.min_change.value(),
            max_change_pct=self.max_change.value(),
            volume_ratio_min=self.vol_ratio.value(),
            use_ma_stack=self.use_ma.isChecked(),
            ma_fast=self.ma_fast.value(),
            ma_mid=self.ma_mid.value(),
            ma_slow=self.ma_slow.value(),
            use_breakout=self.use_breakout.isChecked(),
            breakout_lookback=self.breakout.value(),
            use_rsi=self.use_rsi.isChecked(),
            rsi_min=self.rsi_min.value(),
            rsi_max=self.rsi_max.value(),
            candidate_source=str(self.source_combo.currentData()),
            hero_condition_seq=str(seq or ""),
            hero_condition_name=str(name or ""),
            hero_secondary_filter=self.hero_secondary_filter.isChecked(),
            hero_entry_only=self.hero_entry_only.isChecked(),
            order_budget=self.order_budget.value(),
            max_positions=self.max_positions.value(),
            cooldown_min=self.cooldown.value(),
            max_daily_orders=self.max_daily_orders.value(),
            account_sync_sec=self.account_sync_sec.value(),
            order_exchange=self.exchange_combo.currentText(),
            take_profit_pct=self.take_profit.value(),
            stop_loss_pct=self.stop_loss.value(),
            trailing_enabled=self.trailing.isChecked(),
            trailing_start_pct=self.trailing_start.value(),
            trailing_gap_pct=self.trailing_gap.value(),
            force_exit_enabled=self.force_exit.isChecked(),
            force_exit_time=self.force_exit_time.time().toString("HH:mm"),
        )

    def save_settings(self):
        self.save_settings_silent()
        QMessageBox.information(self, "저장", "조건과 리스크 설정을 저장했습니다.")

    def save_settings_silent(self):
        self.settings = self._collect_settings()
        self.engine.set_settings(self.settings)
        save_strategy(self.settings)

    # ---------- watchlist ----------
    def add_symbol(self):
        code, ok = QInputDialog.getText(self, "관심종목 추가", "종목코드(예: 005930)")
        if not ok or not code.strip():
            return
        code = code.strip().replace("A", "")
        name, ok2 = QInputDialog.getText(self, "관심종목 추가", "표시할 종목명")
        if not ok2:
            name = code
        if any(x.get("code") == code for x in self.watchlist):
            return
        self.watchlist.append({"code": code, "name": name.strip() or code})
        save_watchlist(self.watchlist)
        self._ensure_market_row(code, name.strip() or code, "관심")

    def delete_symbol(self):
        r = self.market_table.currentRow()
        if r < 0:
            return
        code = self.market_table.item(r, 0).text()
        self.watchlist = [x for x in self.watchlist if x.get("code") != code]
        save_watchlist(self.watchlist)
        self.market_table.item(r, 2).setText(self._source_for_code(code))

    # ---------- broker ----------
    def use_sim(self):
        self.stop_auto()
        self.stop_condition_stream()
        self.broker = SimBroker()
        self.engine.set_broker(self.broker)
        self.real_armed = False
        self._set_status("SIMULATION", "데모 모드")

    def arm_live(self):
        text, ok = QInputDialog.getText(
            self,
            "실전매매 1차 잠금 해제",
            "실제 계좌에 주문이 전송될 수 있습니다. 이해했다면 LIVE 를 입력하세요.",
        )
        if ok and text.strip().upper() == "LIVE":
            self.real_armed = True
            QMessageBox.warning(self, "실전 잠금 1단계 해제", "실전 연결이 허용됐습니다. 자동매매 시작 시 한 번 더 확인합니다.")
        else:
            self.real_armed = False

    def _load_saved_connection(self):
        try:
            data = load_credentials()
        except CredentialError as exc:
            if hasattr(self, "saved_cred_label"):
                self.saved_cred_label.setText("저장정보 읽기 실패")
            return
        if not data:
            return
        self.appkey.setText(data.get("app_key", ""))
        self.secret.setText(data.get("app_secret", ""))
        self.api_env.setCurrentText("실전투자" if data.get("environment") == "REAL" else "모의투자")
        self.remember_kiwoom.setChecked(True)
        self.auto_connect_box.setChecked(bool(data.get("auto_connect", False)))
        self.saved_cred_label.setText("✓ Windows 보안저장소에서 연결정보 불러옴")

    def forget_kiwoom_credentials(self):
        try:
            clear_credentials()
            self.appkey.clear(); self.secret.clear()
            self.auto_connect_box.setChecked(False)
            self.saved_cred_label.setText("저장정보 삭제 완료")
            QMessageBox.information(self, "키움 연결정보", "저장된 App Key/Secret을 삭제했습니다.")
        except Exception as exc:
            QMessageBox.critical(self, "삭제 실패", str(exc))

    def save_and_connect_kiwoom(self):
        if self.remember_kiwoom.isChecked():
            try:
                save_credentials(
                    self.appkey.text(), self.secret.text(),
                    "REAL" if self.api_env.currentText() == "실전투자" else "MOCK",
                    self.auto_connect_box.isChecked(),
                )
                self.saved_cred_label.setText("✓ 보안저장 완료")
            except Exception as exc:
                QMessageBox.critical(self, "보안저장 실패", str(exc)); return
        else:
            clear_credentials()
        self.connect_kiwoom(silent=False)

    def auto_connect_saved(self):
        if not self.appkey.text().strip() or not self.secret.text().strip():
            return
        self.connect_kiwoom(silent=True)

    def quick_connect(self):
        if isinstance(self.broker, KiwoomRestBroker) and self.broker.token:
            self.tabs.setCurrentWidget(self.focus_widget)
            return
        if not self.appkey.text().strip() or not self.secret.text().strip():
            self.tabs.setCurrentWidget(self.connection_widget)
            QMessageBox.information(self, "빠른연결", "처음 한 번만 App Key/Secret을 입력하고 '저장하고 바로 연결'을 눌러주세요.")
            return
        self.connect_kiwoom(silent=False)

    def connect_kiwoom(self, silent: bool = False):
        self.save_settings_silent()
        real = self.api_env.currentText() == "실전투자"
        try:
            broker = KiwoomRestBroker(
                self.appkey.text(), self.secret.text(), real=real, order_exchange=self.settings.order_exchange
            )
            broker.connect()
            self.stop_auto()
            self.stop_condition_stream()
            self.broker = broker
            self.engine.set_broker(broker)
            self.engine.set_settings(self.settings)
            mode = "KIWOOM REAL" if real else "KIWOOM MOCK"
            self._set_status(mode, "REST 연결됨")
            self.quick_connect_btn.setText("✓ 키움 연결됨")
            if real:
                sync = self.engine.sync_account(force=True)
                self._refresh_position_rows()
                msg = (f"키움 실전 서버 연결 성공. 계좌 보유 {sync.get('account_positions', 0)}종목 확인 / "
                       f"PUMA 관리 {sync.get('managed_positions', 0)}종목 동기화.\n실전주문 잠금은 아직 유지됩니다.")
            else:
                msg = "키움 모의투자 서버 연결 성공."
            if not silent:
                QMessageBox.information(self, "연결 성공", msg)
        except Exception as exc:
            self.quick_connect_btn.setText("⚡ 키움 빠른연결")
            self._set_status("SIMULATION", "키움 자동연결 실패")
            if not silent:
                QMessageBox.critical(self, "연결 실패", str(exc))

    # ---------- Hero4 conditions ----------
    def _require_kiwoom(self) -> KiwoomRestBroker | None:
        if not isinstance(self.broker, KiwoomRestBroker) or not self.broker.token:
            QMessageBox.information(self, "키움 연결 필요", "먼저 '키움 연결' 탭에서 REST API 연결을 완료하세요.")
            return None
        return self.broker

    def refresh_conditions(self):
        broker = self._require_kiwoom()
        if broker is None:
            return
        self.condition_status.setText("조건식 목록 조회 중...")
        try:
            rows = fetch_condition_list(broker.token, broker.real)
            self.condition_list = rows
            self.condition_combo.clear()
            for seq, name in rows:
                self.condition_combo.addItem(f"[{seq}] {name}", (seq, name))
            restore = self.settings.hero_condition_seq
            for i in range(self.condition_combo.count()):
                data = self.condition_combo.itemData(i)
                if data and str(data[0]) == str(restore):
                    self.condition_combo.setCurrentIndex(i)
                    break
            self.condition_status.setText(f"저장 조건식 {len(rows)}개 불러옴")
            if not rows:
                QMessageBox.information(self, "조건식 없음", "영웅문4 [0150]에서 사용자 조건식을 저장한 뒤 다시 불러오세요.")
        except Exception as exc:
            self.condition_status.setText("조건식 조회 실패")
            QMessageBox.critical(self, "조건식 조회 실패", str(exc))

    def start_condition_stream(self):
        broker = self._require_kiwoom()
        if broker is None:
            return
        if self.condition_combo.count() == 0:
            self.refresh_conditions()
            if self.condition_combo.count() == 0:
                return
        data = self.condition_combo.currentData()
        if not data:
            return
        seq, name = data
        self.stop_condition_stream()
        self.condition_candidates.clear()
        self.condition_table.setRowCount(0)
        self.save_settings_silent()
        self.settings.hero_condition_seq = str(seq)
        self.settings.hero_condition_name = str(name)
        save_strategy(self.settings)

        thread = ConditionStreamThread(broker.token, broker.real, str(seq), self)
        thread.status.connect(self.on_condition_status)
        thread.error.connect(self.on_condition_error)
        thread.snapshot.connect(self.on_condition_snapshot)
        thread.entered.connect(self.on_condition_enter)
        thread.exited.connect(self.on_condition_exit)
        self.condition_thread = thread
        thread.start()
        self.condition_status.setText(f"[{seq}] {name} 연결 중...")

    def stop_condition_stream(self):
        if self.condition_thread:
            thread = self.condition_thread
            self.condition_thread = None
            thread.stop()
            thread.wait(2500)
        if hasattr(self, "condition_status"):
            self.condition_status.setText("조건검색 중지")

    def on_condition_status(self, text: str):
        self.condition_status.setText(text)
        self.log("HERO4", "COND", "-", text)

    def on_condition_error(self, text: str):
        self.condition_status.setText("오류: " + text)
        self.log("HERO4", "ERROR", "-", text)

    def on_condition_snapshot(self, rows):
        now = datetime.now().strftime("%H:%M:%S")
        for code, name in rows:
            self.condition_candidates[code] = {"name": name or code, "active": True, "entered_at": now, "entry_event": False}
            self._upsert_condition_row(code)
            self._ensure_market_row(code, name or code, "영웅문4")
            if not name or name == code:
                self._queue_name_lookup(code)

    def on_condition_enter(self, code: str, name: str):
        now = datetime.now().strftime("%H:%M:%S")
        old_name = self.condition_candidates.get(code, {}).get("name", "")
        self.condition_candidates[code] = {"name": name or old_name or code, "active": True, "entered_at": now, "entry_event": True}
        self._upsert_condition_row(code)
        self._ensure_market_row(code, name or old_name or code, "영웅문4")
        if not name or name == code:
            self._queue_name_lookup(code)
        self.log(name or old_name or code, "COND IN", "-", "영웅문4 조건식 신규 편입")

    def on_condition_exit(self, code: str):
        item = self.condition_candidates.setdefault(code, {"name": code, "entered_at": "-"})
        item["active"] = False
        self._upsert_condition_row(code)
        if code in self.row_by_code:
            r = self.row_by_code[code]
            self.market_table.item(r, 2).setText(self._source_for_code(code))
            if code not in self.engine.positions:
                self.market_table.item(r, 4).setText("조건이탈")
        self.log(item.get("name", code), "COND OUT", "-", "영웅문4 조건식 이탈")

    def _upsert_condition_row(self, code: str):
        item = self.condition_candidates.get(code, {})
        row = None
        for r in range(self.condition_table.rowCount()):
            if self.condition_table.item(r, 0).text() == code:
                row = r
                break
        if row is None:
            row = self.condition_table.rowCount()
            self.condition_table.insertRow(row)
            for c in range(5):
                self.condition_table.setItem(row, c, QTableWidgetItem(""))
        self.condition_table.item(row, 0).setText(code)
        display_name = item.get("name", "")
        self.condition_table.item(row, 1).setText(display_name if display_name and display_name != code else "조회중...")
        self.condition_table.item(row, 2).setText("편입" if item.get("active") else "이탈")
        self.condition_table.item(row, 3).setText(item.get("entered_at", "-"))
        self.condition_table.item(row, 4).setText("▶ 클릭해서 열기")
        self.condition_table.item(row, 4).setForeground(QColor("#62b8ff"))
        if hasattr(self, "focus_condition_table"):
            frow = None
            for rr in range(self.focus_condition_table.rowCount()):
                if self.focus_condition_table.item(rr, 0).text() == code:
                    frow = rr; break
            if frow is None:
                frow = self.focus_condition_table.rowCount()
                self.focus_condition_table.insertRow(frow)
                for cc in range(3):
                    self.focus_condition_table.setItem(frow, cc, QTableWidgetItem(""))
            self.focus_condition_table.item(frow, 0).setText(code)
            self.focus_condition_table.item(frow, 1).setText(display_name if display_name and display_name != code else "조회중...")
            self.focus_condition_table.item(frow, 2).setText("편입" if item.get("active") else "이탈")

    def _focus_condition_row_clicked(self, row: int, column: int):
        item = self.focus_condition_table.item(row, 0)
        if not item:
            return
        code = item.text().strip()
        if not code:
            return
        name_item = self.focus_condition_table.item(row, 1)
        name = name_item.text().strip() if name_item else code
        self.open_focus_stock(code, name if name != "조회중..." else code)

    # ---------- 종목명 보완 / 통합 분석·매매 ----------
    def _queue_name_lookup(self, code: str):
        code = str(code).strip()
        if not code or code in self.name_cache or code in self.name_lookup_queue:
            return
        if not isinstance(self.broker, KiwoomRestBroker) or not self.broker.token:
            return
        self.name_lookup_queue.append(code)
        if not self.name_lookup_timer.isActive():
            self.name_lookup_timer.start()

    def _resolve_next_name(self):
        if not self.name_lookup_queue:
            self.name_lookup_timer.stop()
            return
        if not isinstance(self.broker, KiwoomRestBroker) or not self.broker.token:
            self.name_lookup_queue.clear(); self.name_lookup_timer.stop(); return
        code = self.name_lookup_queue.pop(0)
        try:
            info = self.broker.get_stock_info(code)
            name = str(info.get('stk_nm') or info.get('name') or code).strip()
            if name and name != code:
                self.name_cache[code] = name
                item = self.condition_candidates.get(code)
                if item is not None:
                    item['name'] = name
                    self._upsert_condition_row(code)
                self._ensure_market_row(code, name, self._source_for_code(code) or '영웅문4')
                if self.selected_code == code:
                    self.selected_name = name
                    self.focus_title.setText(f"{name}  {code}")
                    self._sync_selected_stock_everywhere()
        except Exception:
            item = self.condition_candidates.get(code)
            if item is not None and (not item.get('name') or item.get('name') == code):
                item['name'] = '조회 실패'
                self._upsert_condition_row(code)
        if not self.name_lookup_queue:
            self.name_lookup_timer.stop()

    def _condition_row_clicked(self, row: int, column: int):
        item = self.condition_table.item(row, 0)
        if not item:
            return
        code = item.text().strip()
        name_item = self.condition_table.item(row, 1)
        name = name_item.text().strip() if name_item else code
        self.open_focus_stock(code, name)

    def _sync_selected_stock_everywhere(self):
        code = (self.selected_code or "").strip()
        name = (self.selected_name or code or "-").strip()
        label = f"{name}  ({code})" if code else "없음"
        if hasattr(self, "strategy_selected_label"):
            self.strategy_selected_label.setText(f"선택종목: {label}")
        if hasattr(self, "manual_code") and code:
            self.manual_code.setText(code)
        if hasattr(self, "manual_name"):
            self.manual_name.setText(name if code else "-")
        if hasattr(self, "swing_code") and code:
            self.swing_code.setText(code)
        if hasattr(self, "swing_selected_label"):
            self.swing_selected_label.setText(f"연동: {label}")

    def _on_tab_changed(self, index: int):
        if not self.selected_code:
            return
        widget = self.tabs.widget(index)
        self._sync_selected_stock_everywhere()
        if widget is getattr(self, "strategy_widget", None):
            QTimer.singleShot(0, self.strategy_refresh_selected)
        elif widget is getattr(self, "manual_widget", None):
            QTimer.singleShot(0, self.manual_quote)
        elif widget is getattr(self, "swing_widget", None):
            if isinstance(self.broker, KiwoomRestBroker) and self.broker.token:
                QTimer.singleShot(0, lambda: self.swing_load_kiwoom(silent=True))

    def strategy_refresh_selected(self):
        code = (self.selected_code or "").strip()
        if not code:
            if hasattr(self, "strategy_signal_label"):
                self.strategy_signal_label.setText("오돌이 분석: 종목을 선택하세요")
            return
        name = self.selected_name or code
        self._sync_selected_stock_everywhere()
        try:
            tf = int(self.timeframe.currentText())
            rows = self.broker.get_minute_candles(code, tf)
            settings = self._collect_settings()
            settings.timeframe_min = tf
            sig = evaluate_buy(rows, settings) if rows else None
            if sig:
                status = "매수조건 충족" if sig.passed else sig.reason
                color = "#61ff8f" if sig.passed else "#f4c95d"
                self.strategy_signal_label.setText(f"{tf}분봉 · {status}")
                self.strategy_signal_label.setStyleSheet(f"font-weight:900;color:{color}")
            else:
                self.strategy_signal_label.setText(f"{tf}분봉 · 데이터 없음")
        except Exception as exc:
            self.strategy_signal_label.setText(f"{name} · 분석 실패: {exc}")
            self.strategy_signal_label.setStyleSheet("font-weight:800;color:#ff7b83")

    def open_focus_stock(self, code: str, name: str = ""):
        code = str(code).strip().replace('A', '')
        if not code:
            return
        self.selected_code = code
        self.selected_name = self.name_cache.get(code) or (name if name and name != code else code)
        self.focus_title.setText(f"{self.selected_name}  {code}")
        self._sync_selected_stock_everywhere()
        origin = self._source_for_code(code)
        self.focus_origin.setText(f"유입: {origin}  ·  차트/분석/주문/자동매매 통합 화면")
        self.tabs.setCurrentWidget(self.focus_widget)
        QApplication.processEvents()
        QTimer.singleShot(0, self.focus_refresh)

    def focus_refresh(self):
        code = self.selected_code
        if not code:
            return
        try:
            self.focus_origin.setText("시세·5분봉·과거 일봉을 불러오는 중...")
            QApplication.processEvents()
            name = self.selected_name or code
            price = 0.0
            if isinstance(self.broker, KiwoomRestBroker):
                info = self.broker.get_stock_info(code)
                name = str(info.get('stk_nm') or self.name_cache.get(code) or name).strip()
                price = abs(float(str(info.get('cur_prc', 0)).replace(',', '') or 0))
                if name and name != code:
                    self.name_cache[code] = name
                    self.selected_name = name
                    if code in self.condition_candidates:
                        self.condition_candidates[code]['name'] = name
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

            # 1) 오돌이/아침단타: 5분봉 엔진
            try:
                minute = self.broker.get_minute_candles(code, self.settings.timeframe_min)
                self.focus_minute_raw = minute or []
                sig = evaluate_buy(minute, self.settings) if minute else None
                if sig:
                    self.focus_day_signal.setText(f"오돌이 DAY · 5분봉\n{'매수조건 충족' if sig.passed else sig.reason}")
                    self.focus_day_signal.setStyleSheet(f"font-size:15px;font-weight:900;color:{'#61ff8f' if sig.passed else '#f4c95d'};background:#122238;border-radius:8px;padding:10px")
            except Exception as exc:
                self.focus_day_signal.setText(f"오돌이 DAY · 5분봉\n조회 실패: {exc}")

            # 2) 일봉: 역매공파 + 밥그릇3번을 같은 데이터로 동시에 판정
            getter = getattr(self.broker, 'get_daily_candles', None)
            if getter:
                rows = getter(code, max_pages=self.focus_history_pages)
                if rows:
                    self.focus_daily_raw = rows
                    swing_analysis, swing_series = analyze_swing(rows, self._swing_settings_from_ui())
                    bowl_analysis, _ = analyze_bowl(rows, self.bowl_settings)
                    self.focus_daily_analysis = swing_analysis
                    self.focus_daily_series = swing_series
                    self.focus_bowl_analysis = bowl_analysis
                    self._apply_focus_analyses(swing_analysis, bowl_analysis, "전체")
                    self._set_focus_date_bounds()
                    self._update_focus_chart(False)

            self.focus_origin.setText(
                f"유입: {self._source_for_code(code)} · 일봉 {len(self.focus_daily_series.get('candles',[])) if self.focus_daily_series else 0}봉 로드 · "
                f"마지막 갱신 {datetime.now().strftime('%H:%M:%S')}"
            )
        except Exception as exc:
            self.focus_origin.setText("불러오기 실패")
            QMessageBox.critical(self, "종목 분석 실패", str(exc))

    def _set_focus_date_bounds(self):
        if not self.focus_daily_series or not self.focus_daily_series.get('candles'):
            return
        cs = self.focus_daily_series['candles']
        def qdate(raw):
            ss = ''.join(ch for ch in str(raw or '') if ch.isdigit())[:8]
            if len(ss) == 8:
                return QDate(int(ss[:4]), int(ss[4:6]), int(ss[6:8]))
            return QDate.currentDate()
        first, last = qdate(cs[0].get('date')), qdate(cs[-1].get('date'))
        self.focus_range_start.setMinimumDate(first); self.focus_range_start.setMaximumDate(last)
        self.focus_range_end.setMinimumDate(first); self.focus_range_end.setMaximumDate(last)
        if self.focus_range_start.date() < first or self.focus_range_start.date() > last:
            self.focus_range_start.setDate(first)
        self.focus_range_end.setDate(last)

    def _minute_chart_series(self):
        candles = normalize_candles(self.focus_minute_raw or [])
        closes = [c['close'] for c in candles]
        return candles, {
            'ema5': ema(closes, 5), 'ema20': ema(closes, 20), 'ema60': ema(closes, 60),
            'ema112': ema(closes, 112), 'ema224': ema(closes, 224),
        }

    def _update_focus_chart(self, preserve_view: bool = True):
        mode = str(self.focus_chart_mode_combo.currentData()) if hasattr(self, 'focus_chart_mode_combo') else 'DAY'
        self.focus_chart_mode = mode
        if mode == 'MIN':
            candles, lines = self._minute_chart_series()
            self.focus_chart.set_basic_data(candles, lines, title=f"{self.selected_name or self.selected_code} · {self.settings.timeframe_min}분봉 · 오돌이 DAY", preserve_view=preserve_view)
        elif self.focus_daily_series:
            self.focus_chart.set_data(self.focus_daily_analysis, self.focus_daily_series, title=f"{self.selected_name or self.selected_code} · 일봉 · 역매공파 + 밥그릇3번", preserve_view=preserve_view)

    def focus_chart_mode_changed(self):
        self.focus_chart.clear_analysis_range()
        self._update_focus_chart(False)

    def focus_load_more_history(self):
        if not self.selected_code:
            return
        self.focus_history_pages = min(30, self.focus_history_pages + 5)
        self.focus_origin.setText(f"과거 일봉을 더 불러오는 중... 최대 {self.focus_history_pages}페이지")
        self.focus_refresh()

    @staticmethod
    def _date_num(raw) -> int:
        s = ''.join(ch for ch in str(raw or '') if ch.isdigit())[:8]
        try:
            return int(s)
        except Exception:
            return 0

    def focus_analyze_date_range(self):
        if self.focus_chart_mode != 'DAY' or not self.focus_daily_series:
            QMessageBox.information(self, "구간 분석", "구간 분석은 일봉 차트에서 사용하세요.")
            return
        cs = self.focus_daily_series['candles']
        a = int(self.focus_range_start.date().toString('yyyyMMdd'))
        b = int(self.focus_range_end.date().toString('yyyyMMdd'))
        if a > b: a, b = b, a
        idx = [i for i,c in enumerate(cs) if a <= self._date_num(c.get('date')) <= b]
        if not idx:
            QMessageBox.information(self, "구간 분석", "현재 불러온 과거 데이터 안에 해당 날짜가 없습니다. '과거 데이터 +5페이지'를 눌러 더 불러오세요.")
            return
        self._analyze_focus_range(idx[0], idx[-1], f"{self.focus_range_start.date().toString('yyyy-MM-dd')} ~ {self.focus_range_end.date().toString('yyyy-MM-dd')}")

    def focus_analyze_visible(self):
        if self.focus_chart_mode != 'DAY' or not self.focus_daily_series:
            QMessageBox.information(self, "구간 분석", "현재 보이는 구간 분석은 일봉에서 사용하세요.")
            return
        a, e = self.focus_chart.visible_index_range()
        if e <= a:
            return
        self._analyze_focus_range(a, e-1, "현재 보이는 차트 구간")

    def _analyze_focus_range(self, start_idx: int, end_idx: int, label: str):
        cs = self.focus_daily_series['candles']
        start_idx = max(0, min(start_idx, len(cs)-1)); end_idx = max(start_idx, min(end_idx, len(cs)-1))
        # 선택 구간 '직전'의 장기 이평/매집 이력을 보존해야 하므로 최대 560봉의 사전 컨텍스트를 함께 넣고,
        # 판정 시점은 선택 구간의 끝으로 고정한다.
        context_start = max(0, start_idx - 560)
        sample = cs[context_start:end_idx+1]
        try:
            sa, _ = analyze_swing(sample, self._swing_settings_from_ui())
        except Exception as exc:
            sa = None
            self.focus_swing_signal.setText(f"역매공파 SWING\n구간 분석 불가: {exc}")
        try:
            ba, _ = analyze_bowl(sample, self.bowl_settings)
        except Exception as exc:
            ba = None
            self.focus_bowl_signal.setText(f"밥그릇 3번 LONG\n구간 분석 불가: {exc}")
        self.focus_chart.set_analysis_range(start_idx, end_idx)
        if sa or ba:
            self._apply_focus_analyses(sa, ba, label)
        self.focus_range_status.setText(f"분석: {label}")

    def focus_analyze_all(self):
        self.focus_chart.clear_analysis_range()
        if self.focus_daily_analysis or self.focus_bowl_analysis:
            self._apply_focus_analyses(self.focus_daily_analysis, self.focus_bowl_analysis, "전체")
        self.focus_range_status.setText("분석: 전체")

    def _apply_focus_analyses(self, swing_analysis, bowl_analysis, label: str):
        if swing_analysis:
            self.focus_swing_signal.setText(f"역매공파 SWING\n{swing_analysis.stage} · {swing_analysis.score}/100")
            self.focus_swing_signal.setStyleSheet("font-size:15px;font-weight:900;color:#62b8ff;background:#122238;border-radius:8px;padding:10px")
            for key, lab in self.focus_stage_labels.items():
                text = swing_analysis.details.get(key, '-')
                lab.setText(text)
                good = any(x in text for x in ('확인','감지')) and '미확인' not in text
                near = key == '파란점선' and getattr(swing_analysis, 'blue_near', False)
                lab.setStyleSheet(f"font-weight:800;color:{'#61ff8f' if (good or near) else '#f4c95d'}")
        if bowl_analysis:
            self.focus_bowl_signal.setText(f"밥그릇 3번 LONG\n{bowl_analysis.stage} · {bowl_analysis.score}/100")
            self.focus_bowl_signal.setStyleSheet("font-size:15px;font-weight:900;color:#d58cff;background:#122238;border-radius:8px;padding:10px")
            for key, lab in self.focus_bowl_labels.items():
                text = bowl_analysis.details.get(key, '-')
                lab.setText(text)
                good = '확인' in text and '미확인' not in text
                lab.setStyleSheet(f"font-weight:800;color:{'#61ff8f' if good else '#f4c95d'}")
        s1 = getattr(swing_analysis, 'stage', '대기') if swing_analysis else '대기'
        s2 = getattr(bowl_analysis, 'stage', '대기') if bowl_analysis else '대기'
        self.focus_stage.setText(f"통합판정 · {label}  |  역매공파: {s1}  |  밥그릇3번: {s2}")

    def focus_submit(self, side: str):
        code = self.selected_code
        if not code:
            QMessageBox.information(self, "종목 선택", "조건검색 목록에서 종목을 먼저 선택하세요.")
            return
        qty = self.focus_qty.value()
        order_type = str(self.focus_order_type.currentData())
        price = self.focus_order_price.value()
        cond = self.focus_cond_price.value()
        if isinstance(self.broker, KiwoomRestBroker) and self.broker.real:
            if not self.real_armed:
                QMessageBox.warning(self, "실전 잠금", "키움 연결 탭에서 실전 LIVE 1차 잠금을 먼저 해제하세요.")
                return
            phrase, ok = QInputDialog.getText(self, "실전 수동주문 확인", f"{side} {self.selected_name or code} {qty}주 주문입니다.\n실제 주문을 보내려면 LIVE ORDER 를 입력하세요.")
            if not ok or phrase.strip().upper() != 'LIVE ORDER':
                return
        try:
            resp = self.broker.place_order(side, code, qty, order_type, price, cond)
            self.log(self.selected_name or code, side, f"{price:,}" if price else "시장가", str(resp.get('return_msg', resp)))
            QMessageBox.information(self, "주문 전송", f"주문번호: {resp.get('ord_no','-')}\n{resp.get('return_msg','정상 처리')}")
        except Exception as exc:
            QMessageBox.critical(self, "주문 실패", str(exc))

    def start_focus_auto(self):
        if not self.selected_code:
            QMessageBox.information(self, "종목 선택", "조건검색 목록에서 종목을 먼저 선택하세요.")
            return
        # 통합화면의 리스크 값을 기존 엔진 설정에 반영한다.
        self.order_budget.setValue(self.focus_budget.value())
        self.take_profit.setValue(self.focus_tp.value())
        self.stop_loss.setValue(self.focus_sl.value())
        self.trailing.setChecked(self.focus_trail.isChecked())
        self.trailing_start.setValue(self.focus_trail_start.value())
        self.trailing_gap.setValue(self.focus_trail_gap.value())
        self.save_settings_silent()
        if isinstance(self.broker, KiwoomRestBroker) and self.broker.real:
            if not self.real_armed:
                QMessageBox.warning(self, "실전 잠금", "실전매매 1차 잠금이 해제되지 않았습니다.")
                return
            phrase, ok = QInputDialog.getText(self, "선택 종목 실전 자동매매", f"{self.selected_name or self.selected_code} 한 종목 자동매매를 시작합니다.\n계속하려면 LIVE START 를 입력하세요.")
            if not ok or phrase.strip().upper() != 'LIVE START':
                return
            try:
                self.engine.sync_account(force=True)
            except Exception as exc:
                QMessageBox.critical(self, "실계좌 동기화 실패", str(exc)); return
        self.focus_only_code = self.selected_code
        self.engine.enabled = True
        self.timer.start()
        self.log(self.selected_name or self.selected_code, "AUTO", "-", "선택 종목 전용 자동매매 시작")
        self.scan_one()

    # ---------- trading ----------
    def _active_targets(self) -> list[dict]:
        source = str(self.source_combo.currentData())
        merged: dict[str, dict] = {}

        if self.focus_only_code:
            code = self.focus_only_code
            name = self.name_cache.get(code) or (self.selected_name if self.selected_code == code else code)
            merged[code] = {"code": code, "name": name, "hero": False}
            # 보유/주문 중 종목은 청산/체결 확인을 위해 함께 감시
            for c, pos in self.engine.positions.items():
                merged.setdefault(c, {"code": c, "name": pos.name, "hero": False})
            for c in self.engine.pending_orders:
                merged.setdefault(c, {"code": c, "name": self.name_cache.get(c, c), "hero": False})
            return list(merged.values())

        if source in ("WATCHLIST", "BOTH"):
            for item in self.watchlist:
                code = item.get("code", "")
                if code:
                    merged[code] = {"code": code, "name": item.get("name", code), "hero": False}

        if source in ("HERO4", "BOTH"):
            for code, item in self.condition_candidates.items():
                if item.get("active"):
                    # 실전 안전 기본값: 스트림 시작 시 이미 조건에 들어있던 종목은 사지 않고,
                    # 시작 이후 I(신규 편입) 이벤트를 받은 종목만 신규매수 후보로 사용한다.
                    if self.settings.hero_entry_only and not item.get("entry_event"):
                        continue
                    if code in merged:
                        merged[code]["hero"] = True
                    else:
                        merged[code] = {"code": code, "name": item.get("name", code), "hero": True}

        # 보유/주문 중 종목은 후보에서 이탈해도 매도 및 체결 확인을 위해 계속 감시
        for code, pos in self.engine.positions.items():
            merged.setdefault(code, {"code": code, "name": pos.name, "hero": False})
        for code in self.engine.pending_orders:
            merged.setdefault(code, {"code": code, "name": code, "hero": False})

        return list(merged.values())

    def start_auto(self):
        self.focus_only_code = None
        self.save_settings_silent()
        source = self.settings.candidate_source
        if source == "WATCHLIST" and not self.watchlist:
            QMessageBox.information(self, "대상 없음", "관심종목을 먼저 추가하세요.")
            return
        if source in ("HERO4", "BOTH") and (not self.condition_thread or not self.condition_thread.isRunning()):
            if source == "HERO4":
                QMessageBox.information(self, "조건검색 필요", "'영웅문4 조건검색' 탭에서 실시간 조건검색을 먼저 시작하세요.")
                return

        if isinstance(self.broker, KiwoomRestBroker) and self.broker.real:
            if not self.real_armed:
                QMessageBox.warning(self, "실전 잠금", "실전매매 1차 잠금이 해제되지 않았습니다.")
                return
            phrase, ok = QInputDialog.getText(
                self,
                "실전 자동매매 최종 확인",
                f"실제 주문이 전송됩니다.\n종목당 {self.settings.order_budget:,}원 / 최대 {self.settings.max_positions}종목 / 일일 주문 {self.settings.max_daily_orders}회\n계속하려면 LIVE START 를 입력하세요.",
            )
            if not ok or phrase.strip().upper() != "LIVE START":
                return
            try:
                self.engine.sync_account(force=True)
                self._refresh_position_rows()
            except Exception as exc:
                QMessageBox.critical(self, "실계좌 동기화 실패", f"잔고 동기화에 실패하여 실전 자동매매를 시작하지 않습니다.\n{exc}")
                return

        self.engine.enabled = True
        self.timer.start()
        self.log("SYSTEM", "AUTO", "0", f"자동매매 시작 · {source}")
        self.scan_one()

    def stop_auto(self):
        self.engine.enabled = False
        self.timer.stop()
        self.focus_only_code = None
        if hasattr(self, "log_table"):
            self.log("SYSTEM", "STOP", "0", "자동매매 중지")

    def scan_one(self):
        targets = self._active_targets()
        if not targets:
            return
        item = targets[self.scan_index % len(targets)]
        self.scan_index += 1
        code = item["code"]
        name = item.get("name", code)
        hero = bool(item.get("hero"))
        require_filter = not (hero and not self.settings.hero_secondary_filter)
        try:
            res = self.engine.process(code, name, require_buy_filter=require_filter)
            self.update_row(res)
            if res.get("status") in ("BUY", "SELL", "BUY_SENT", "SELL_SENT"):
                self.log(res["name"], res["status"], f"{res['price']:,.0f}", res["signal"])
            self._refresh_position_rows()
        except BrokerError as exc:
            self.log(name, "ERROR", "0", str(exc))
            self.stop_auto()
        except Exception as exc:
            self.log(name, "ERROR", "0", repr(exc))

    def _refresh_position_rows(self):
        for code, pos in self.engine.positions.items():
            r = self._ensure_market_row(code, pos.name, "보유")
            self.market_table.item(r, 2).setText(self._source_for_code(code))
            self.market_table.item(r, 6).setText(str(pos.qty))
        for code in self.engine.pending_orders:
            self._ensure_market_row(code, code, "주문중")

    def update_row(self, res):
        code = res["code"]
        r = self._ensure_market_row(code, res.get("name", code), self._source_for_code(code))
        self.market_table.item(r, 2).setText(self._source_for_code(code))
        self.market_table.item(r, 3).setText(f"{res.get('price', 0):,.0f}")
        self.market_table.item(r, 4).setText(res.get("status", ""))
        self.market_table.item(r, 5).setText(res.get("signal", ""))
        pos = self.engine.positions.get(code)
        self.market_table.item(r, 6).setText(str(pos.qty if pos else 0))
        self.market_table.item(r, 7).setText(f"{pos.pnl_pct(res.get('price', 0)):+.2f}%" if pos else "-")
        status = res.get("status")
        color = QColor("#59d98e") if status in ("BUY", "BUY_SENT", "READY") else QColor("#ff7070") if status in ("SELL", "SELL_SENT") else QColor("#e8eef7")
        self.market_table.item(r, 4).setForeground(color)

    def log(self, stock, kind, price, text):
        r = 0
        self.log_table.insertRow(r)
        vals = [datetime.now().strftime("%H:%M:%S"), stock, kind, price, text]
        for c, v in enumerate(vals):
            self.log_table.setItem(r, c, QTableWidgetItem(str(v)))
        if self.log_table.rowCount() > 400:
            self.log_table.removeRow(self.log_table.rowCount() - 1)

    def closeEvent(self, event):
        self.stop_auto()
        self.stop_condition_stream()
        event.accept()
