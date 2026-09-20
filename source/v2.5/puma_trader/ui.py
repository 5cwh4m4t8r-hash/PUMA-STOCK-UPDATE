from __future__ import annotations

from datetime import datetime
import time

from PySide6.QtCore import QTime, QTimer, Qt, QDate, QSettings, QThread, Signal, QEvent
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractSpinBox,
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
    QPlainTextEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QScrollArea,
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
from .storage import load_strategy, load_watchlist, save_strategy, save_watchlist, load_swing_settings, save_swing_settings
from .swing import SwingSettings, analyze as analyze_swing, demo_candles, normalize_candles, ema
from .strategy import evaluate_buy
from .bowl import BowlSettings, analyze_bowl
from .danta import analyze_danta, analyze_danta_for_date, available_minute_dates, slice_series_for_date
from .classification import classify_scores
from .watermelon_proxy import build_puma_watermelon
from .probability import estimate_from_flags, strategy_flags
from .entry_signal import evaluate_core_entry
from .market_path import analyze_market_path
from .swing_chart import SwingChart
from .updater import CURRENT_VERSION, download_package, fetch_manifest, load_update_config, save_update_config, stage_and_apply
from .secure_credentials import load_credentials, save_credentials, clear_credentials, CredentialError

DARK = """
QMainWindow, QWidget { background: #0b1626; color: #e8eef7; font-family: 'Malgun Gothic'; }
QGroupBox { border: 1px solid #29415f; border-radius: 8px; margin-top: 10px; padding: 8px; font-weight: 700; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 6px; }
QPushButton { background: #183457; border: 1px solid #315b89; border-radius: 7px; padding: 6px 9px; font-weight: 700; }
QPushButton:hover { background: #21456f; }
QPushButton#startBtn { background:#078a50; border-color:#19b36f; }
QPushButton#stopBtn { background:#9e2e39; border-color:#d14b58; }
QPushButton#liveBtn { background:#7a5313; border-color:#b37c1e; }
QPushButton#conditionBtn { background:#164b7a; border-color:#2d79b8; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTimeEdit, QDateEdit { background:#101f33; border:1px solid #35506d; border-radius:5px; padding:5px; }
QTableWidget { background:#0f1d2f; gridline-color:#263d58; alternate-background-color:#12253b; }
QHeaderView::section { background:#162b45; color:#e8eef7; padding:7px; border:0; font-weight:700; }
QTabWidget::pane { border:1px solid #29415f; }
QTabBar::tab { background:#13253b; padding:6px 10px; margin-right:2px; }
QTabBar::tab:selected { background:#1d4776; }
QScrollArea { border:0; background:transparent; }
"""


class StrategySummaryBox(QPlainTextEdit):
    """Scrollable strategy summary; no ellipsis and no hover tooltip needed."""
    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setPlainText(text)
        self.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setMinimumHeight(132)
        self.setMaximumHeight(178)
        self.document().setDocumentMargin(7)

    def setText(self, text):
        self.setPlainText(str(text))



class NoWheelComboBox(QComboBox):
    """Dropdown-only combo: mouse wheel never changes the current value."""
    def wheelEvent(self, event):
        event.ignore()



class NumericComboBox(NoWheelComboBox):
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



class TimeComboBox(NoWheelComboBox):
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
        payload = {"classification": "분석실패", "detail": "-", "danta": 0, "swing": 0, "bowl": 0, "name": ""}
        try:
            try:
                info = self.broker.get_stock_info(self.code)
                payload["name"] = str(info.get("stk_nm") or info.get("name") or "").strip()
            except Exception:
                pass
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


class FocusDataThread(QThread):
    """Fetch quote/minute/daily data outside the GUI thread.

    Windows used to show '응답 없음' because requests + continuation sleeps
    ran directly inside focus_refresh(). This worker keeps the event loop alive.
    """
    loaded = Signal(object)
    failed = Signal(str)

    def __init__(self, broker, code: str, daily_pages: int, parent=None):
        super().__init__(parent)
        self.broker = broker
        self.code = str(code)
        self.daily_pages = int(daily_pages)

    def _thread_broker(self):
        if isinstance(self.broker, KiwoomRestBroker):
            # requests.Session is not shared across threads. Copy credentials/token
            # into a fresh broker/session so UI/condition threads stay isolated.
            b = KiwoomRestBroker(
                self.broker.app_key,
                self.broker.app_secret,
                real=self.broker.real,
                order_exchange=self.broker.order_exchange,
            )
            b.token = self.broker.token
            b.token_expire_epoch = self.broker.token_expire_epoch
            return b
        return self.broker

    def run(self):
        try:
            broker = self._thread_broker()
            info = {}
            if isinstance(broker, KiwoomRestBroker):
                info = broker.get_stock_info(self.code) or {}
            minute = broker.get_minute_candles(self.code, 5, max_pages=4) or []
            getter = getattr(broker, "get_daily_candles", None)
            daily = getter(self.code, max_pages=self.daily_pages) if getter else []
            self.loaded.emit({
                "code": self.code,
                "info": info,
                "minute": minute or [],
                "daily": daily or [],
                "daily_pages": self.daily_pages,
                "loaded_at": time.time(),
            })
        except Exception as exc:
            self.failed.emit(str(exc))



class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PUMA STOCK PRO v2.5")
        self.setMinimumSize(1024, 680)
        self.resize(1280, 800)
        self.setStyleSheet(DARK)

        # 최종 안전망: 앱 전체의 숫자/드롭다운 값은 휠로 변경되지 않는다.
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

        self.settings = load_strategy()
        self.watchlist = load_watchlist()
        self.condition_candidates: dict[str, dict] = {}
        self.condition_thread: ConditionStreamThread | None = None
        self.condition_list: list[tuple[str, str]] = []
        self.row_by_code: dict[str, int] = {}
        self.name_cache: dict[str, str] = {}
        self.name_lookup_queue: list[str] = []
        self.classification_queue: list[str] = []
        self.classification_thread: CandidateClassifier | None = None
        self.selected_code: str = ""
        self.selected_name: str = ""
        self.focus_only_code: str | None = None

        self.broker = SimBroker()
        self.engine = TradeEngine(self.broker, self.settings)
        self.real_armed = False
        self.scan_index = 0
        self.swing_settings = load_swing_settings()
        self.ui_state = QSettings("PUMA", "PUMA_STOCK_PRO")
        self.swing_raw = []
        self.swing_analysis = None
        self.bowl_settings = BowlSettings()
        self.focus_daily_raw: list[dict] = []
        self.focus_daily_series = None
        self.focus_daily_analysis = None
        self.focus_bowl_analysis = None
        self.focus_danta_analysis = None
        self.focus_danta_series = None
        self.focus_minute_raw: list[dict] = []
        self.intraday_days: list[str] = []
        self.intraday_selected_day: str = ""
        self.danta_raw_minute: list[dict] = []
        self.danta_raw_daily: list[dict] = []
        self.danta_cache_code: str = ""
        self.focus_chart_mode = "DAY"
        self.focus_history_pages = 8
        self.focus_range_label = "전체"

        # Non-blocking data loader / short-lived fetch cache.
        self.focus_load_thread: FocusDataThread | None = None
        self.focus_loading_code: str = ""
        self.focus_refresh_pending: bool = False
        self.focus_fetch_cache: dict[tuple[str, int], dict] = {}
        self.focus_data_code: str = ""
        self._strategy_refresh_after_focus: bool = False

        self.timer = QTimer(self)
        self.timer.setInterval(1800)
        self.timer.timeout.connect(self.scan_one)

        # 조건검색 WebSocket은 종목명 없이 코드만 주는 경우가 있어 REST 종목정보로 천천히 보완한다.
        self.name_lookup_timer = QTimer(self)
        self.name_lookup_timer.setInterval(320)
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
        title = QLabel("🐆  PUMA STOCK PRO  v2.5")
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

        self.connection_widget = self._connection_tab()
        self.update_widget = self._update_tab()
        self.tabs.addTab(self.focus_widget, "통합 트레이딩")
        self.tabs.addTab(self.hero_widget, "조건검색")
        self.tabs.addTab(self.dashboard_widget, "잔고 · 로그")
        self.tabs.addTab(self.strategy_widget, "단타 분석")
        self.tabs.addTab(self.manual_widget, "직접 주문")
        self.tabs.addTab(self.connection_widget, "설정 · 키움연결")
        self.tabs.addTab(self.update_widget, "업데이트")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        outer.addWidget(self.tabs)

        self._load_saved_connection()
        self._apply_display_profile()
        QTimer.singleShot(0, self._restore_ui_layout)
        if getattr(self, "auto_connect_box", None) is not None and self.auto_connect_box.isChecked():
            QTimer.singleShot(900, self.auto_connect_saved)

    def _dashboard_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("자동매매 대상"))
        self.source_combo = NoWheelComboBox()
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

    def _focus_tab(self):
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
        self.focus_chart_mode_combo = NoWheelComboBox()
        self.focus_chart_mode_combo.addItem("일봉 · 스윙/중장기", "DAY")
        self.focus_chart_mode_combo.addItem("5분봉 · 단타", "MIN")
        self.focus_chart_mode_combo.currentIndexChanged.connect(self.focus_chart_mode_changed)
        tools.addWidget(self.focus_chart_mode_combo)

        tools.addWidget(QLabel("단타 날짜"))
        self.focus_intraday_date_combo = NoWheelComboBox()
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
        self.focus_range_start = NoWheelDateEdit(QDate.currentDate().addYears(-1))
        self.focus_range_end = NoWheelDateEdit(QDate.currentDate())
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
        self.focus_condition_table = QTableWidget(0, 4)
        self.focus_condition_table.setHorizontalHeaderLabels(["코드", "종목명", "분류", "상태"])
        hdr = self.focus_condition_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hdr.setMinimumSectionSize(54)
        self.focus_condition_table.verticalHeader().setVisible(False)
        self.focus_condition_table.verticalHeader().setDefaultSectionSize(31)
        self.focus_condition_table.setAlternatingRowColors(True)
        self.focus_condition_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.focus_condition_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.focus_condition_table.cellClicked.connect(self._focus_condition_row_clicked)
        self.focus_condition_table.setMinimumWidth(360)
        self.focus_condition_table.setMaximumWidth(560)
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

        signals = QGroupBox("전략 3종 통합 분석")
        sg = QGridLayout(signals)
        self.focus_danta_signal = StrategySummaryBox("단타 DAY · 5분봉\n분석 대기")
        self.focus_swing_signal = StrategySummaryBox("역매공파 SWING\n분석 대기")
        self.focus_bowl_signal = StrategySummaryBox("밥그릇 3번 LONG\n분석 대기")
        for lab in (self.focus_danta_signal, self.focus_swing_signal, self.focus_bowl_signal):
            lab.setStyleSheet("QPlainTextEdit{font-size:12px;font-weight:900;color:#f4c95d;background:#122238;border:0;border-radius:8px;padding:3px;} QScrollBar:vertical{width:9px;}")
        sg.addWidget(self.focus_danta_signal, 0, 0)
        sg.addWidget(self.focus_swing_signal, 0, 1)
        sg.addWidget(self.focus_bowl_signal, 0, 2)
        self.focus_stage = QLabel("통합판정: 데이터 대기")
        self.focus_stage.setWordWrap(True)
        self.focus_stage.setAlignment(Qt.AlignCenter)
        self.focus_stage.setMinimumHeight(34)
        self.focus_stage.setStyleSheet("font-size:12px;font-weight:900;color:#61ff8f;padding:4px")
        sg.addWidget(self.focus_stage, 1, 0, 1, 3)
        sg.setColumnStretch(0, 1); sg.setColumnStretch(1, 1); sg.setColumnStretch(2, 1)
        signals.setMinimumHeight(205)
        center.addWidget(signals, 2)
        self.focus_splitter.addWidget(center_panel)

        # 오른쪽은 세로로 억지로 쌓지 않고 기능별 소형 탭으로 분리.
        # 어느 해상도에서도 버튼/입력창 높이가 눌리지 않는다.
        self.focus_side_tabs = QTabWidget()

        analysis_page = QWidget()
        av = QVBoxLayout(analysis_page)
        av.setContentsMargins(5, 5, 5, 5)
        dantabox = QGroupBox("단타 DAY · 5분봉")
        dg = QGridLayout(dantabox)
        self.focus_danta_labels = {}
        danta_names = ["패턴 점수", "핵심 진입 신호", "공통 수급·돌파 경로", "간단 이유", "PUMA 수박근사", "유사구간 확률", "PUMA 판단", "화살표 신호", "검색 시간", "PUMA 기준선(26)", "EMA 5·20·60", "현재 5분봉 거래량", "최근 고점 돌파", "눌림 지지"]
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

        stagebox = QGroupBox("역매공파 SWING 진행상태")
        st = QGridLayout(stagebox)
        self.focus_stage_labels = {}
        names = ["핵심 진입 신호", "공통 수급·돌파 경로", "간단 이유", "PUMA 수박근사", "유사구간 확률", "PUMA 판단", "기준봉 눌림", "장기 EMA 역배열", "매집봉/구간", "공구리(박스권)", "박스 상단 돌파", "상단 박스 안착", "재돌파", "파란점선", "화살표 신호"]
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
        bowl_names = ["핵심 진입 신호", "공통 수급·돌파 경로", "간단 이유", "PUMA 수박근사", "유사구간 확률", "PUMA 판단", "장기 224EMA 아래", "224EMA 돌파", "224EMA 위 안착", "눌림/지지", "224EMA 거리", "화살표 신호"]
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

        ema_box = QGroupBox("장기 EMA · 고정 기준")
        ef = QFormLayout(ema_box)
        ef.addRow("중장기 기준", QLabel("EMA 112 / 224 / 448"))
        ef.addRow("역배열", QLabel("112 < 224 < 448"))
        sv.addWidget(ema_box)

        acc = QGroupBox("매집봉/매집구간 · PUMA 표준값")
        af = QFormLayout(acc)
        self.sw_vol_period = self._spin(5, 60, ss.volume_period)
        self.sw_vol_ratio = self._dspin(1.0, 20.0, ss.volume_ratio, " 배")
        self.sw_wick_ratio = self._dspin(0.1, 0.9, ss.upper_wick_ratio)
        self.sw_wick_body = self._dspin(0.5, 5.0, max(ss.upper_wick_vs_body, 1.35))
        self.sw_bear_body = self._dspin(0.2, 0.95, ss.bearish_body_ratio)
        self.sw_acc_lookback = self._spin(60, 112, ss.accumulation_lookback)
        self.sw_acc_min = self._spin(2, 6, max(2, ss.accumulation_min_count))
        self.sw_acc_cluster = self._spin(5, 60, ss.accumulation_cluster_window)
        af.addRow("거래량 평균 기간", self.sw_vol_period)
        af.addRow("거래량 평균 대비 (최소 300%)", self.sw_vol_ratio)
        af.addRow("긴 윗꼬리 / 전체폭 ≥", self.sw_wick_ratio)
        af.addRow("윗꼬리 / 몸통 ≥", self.sw_wick_body)
        af.addRow("장대음봉 몸통 / 전체폭 ≥", self.sw_bear_body)
        af.addRow("매집 Lookback", self.sw_acc_lookback)
        af.addRow("확정 최소 후보 수", self.sw_acc_min)
        af.addRow("후보 반복 간격(봉)", self.sw_acc_cluster)
        sv.addWidget(acc)

        box = QGroupBox("공구리(박스권) · 기간 자동")
        bf = QFormLayout(box)
        auto_period = QLabel("자동 판정 · 지지/저항 반복이 실제로 이어진 구간만 사용")
        auto_period.setStyleSheet("color:#61ff8f;font-weight:800")
        self.sw_box_lookback = self._spin(40, 400, ss.box_search_lookback)
        self.sw_box_width = self._dspin(5, 50, ss.box_width_pct, " %")
        self.sw_box_coverage = self._dspin(0.50, 0.95, ss.box_min_coverage)
        self.sw_box_touches = self._spin(2, 10, ss.box_min_touches)
        self.sw_box_alternations = self._spin(1, 10, ss.box_min_alternations)
        self.sw_box_touch_tol = self._dspin(0.5, 8.0, ss.box_touch_tolerance_pct, " %")
        self.sw_box_drift = self._dspin(1.0, 20.0, ss.box_max_drift_pct, " %")
        self.sw_breakout_buffer = self._dspin(0.0, 5.0, ss.breakout_buffer_pct, " %")
        self.sw_breakout_vol = self._dspin(1.0, 10.0, ss.breakout_volume_ratio, " 배")
        self.sw_pullback_vol = self._dspin(0.10, 1.00, ss.pullback_volume_max_ratio)
        self.sw_pullback_base_vol = self._dspin(0.10, 1.20, ss.pullback_base_volume_max_ratio)
        self.sw_pullback_tol = self._dspin(0.5, 8.0, ss.pullback_support_tolerance_pct, " %")
        self.sw_pullback_bars = self._spin(1, 5, ss.pullback_confirm_bars)
        self.sw_rebreak_vol = self._dspin(1.0, 10.0, ss.rebreak_volume_ratio, " 배")
        self.sw_path_bars = self._spin(3, 30, ss.path_max_pullback_bars)
        bf.addRow("박스 기간", auto_period)
        bf.addRow("과거 탐색 범위", self.sw_box_lookback)
        bf.addRow("박스 최대 폭", self.sw_box_width)
        bf.addRow("박스 내 종가 비율 ≥", self.sw_box_coverage)
        bf.addRow("상·하단 최소 독립접촉", self.sw_box_touches)
        bf.addRow("상↔하 최소 왕복", self.sw_box_alternations)
        bf.addRow("접촉 허용오차", self.sw_box_touch_tol)
        bf.addRow("박스 기울기 최대", self.sw_box_drift)
        bf.addRow("상단 돌파 버퍼", self.sw_breakout_buffer)
        bf.addRow("돌파 거래량강도 ≥", self.sw_breakout_vol)
        bf.addRow("눌림 거래량/돌파봉 ≤", self.sw_pullback_vol)
        bf.addRow("눌림 거래량/20봉평균 ≤", self.sw_pullback_base_vol)
        bf.addRow("돌파선 지지 허용", self.sw_pullback_tol)
        bf.addRow("눌림 저거래량 최소봉", self.sw_pullback_bars)
        bf.addRow("확정 재돌파 거래량 ≥", self.sw_rebreak_vol)
        bf.addRow("눌림 추적 최대봉", self.sw_path_bars)
        note = QLabel(
            "공개 주식단테 강의의 핵심을 반영: 박스/매물대 돌파는 거래량이 확 붙어야 하고 "
            "(전봉 또는 최근20봉 평균 대비 300% 이상), 돌파 뒤 눌림에서는 거래량이 확 줄어야 합니다. "
            "박스 기간은 고정하지 않고 실제 수평 지지·저항 왕복구간을 자동 판정합니다."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#9eb4c9")
        bf.addRow(note)
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

        preset = QPushButton("↺ PUMA 표준값 적용")
        preset.clicked.connect(self.apply_swing_preset)
        sv.addWidget(preset)

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
        self.focus_order_type = NoWheelComboBox()
        self.focus_order_type.addItem("시장가", "market")
        self.focus_order_type.addItem("지정가", "limit")
        self.focus_order_type.addItem("스톱지정가", "stop_limit")
        self.focus_qty = self._spin(1, 10_000_000, 1)
        self.focus_order_price = PriceComboBox()
        self.focus_cond_price = PriceComboBox()
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
        self.focus_splitter.setSizes([390, 760, 400])
        root.addWidget(self.focus_splitter, 1)
        return w

    def _strategy_tab(self):
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
        self.danta_date_combo = NoWheelComboBox()
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

        info = QLabel("5분봉 고정 · 거래일별 선택/복기 · PUMA 기준선(26) · 장초반 거래량 · EMA 5/20/60 · 돌파/눌림을 함께 판정합니다. 공개 개념을 PUMA 방식으로 수치화한 분석판이며 비공개/유료 검색식을 복제한 것은 아닙니다.")
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
        self.timeframe = NoWheelComboBox()
        self.timeframe.addItem("5")
        self.timeframe.setCurrentText("5")
        self.timeframe.setEnabled(False)
        self.scan_start = TimeComboBox(QTime.fromString(self.settings.scan_start, "HH:mm"), 10)
        self.scan_end = TimeComboBox(QTime.fromString(self.settings.scan_end, "HH:mm"), 10)
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
        self.exchange_combo = NoWheelComboBox()
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
        self.force_exit_time = TimeComboBox(QTime.fromString(self.settings.force_exit_time, "HH:mm"), 10)
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

    def _manual_order_tab(self):
        w = QWidget()
        root = QVBoxLayout(w)
        root.setContentsMargins(6, 6, 6, 6)

        self.manual_splitter = QSplitter(Qt.Horizontal)

        order = QGroupBox("직접 주문")
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

        self.manual_type = NoWheelComboBox()
        self.manual_type.addItem("시장가", "market")
        self.manual_type.addItem("지정가", "limit")
        self.manual_type.addItem("스톱지정가", "stop_limit")
        self.manual_qty = self._spin(1, 10_000_000, 1)
        self.manual_price = PriceComboBox()
        self.manual_cond_price = PriceComboBox()
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
        self.manual_ema_period = NoWheelComboBox()
        self.manual_ema_period.addItems(["5","20","60","112","224","448"])
        self.manual_ema_offset = self._dspin(-10,10,0.0," %")
        self.manual_ema_action = NoWheelComboBox()
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
        names = ["간단 이유", "PUMA 수박근사", "유사구간 확률", "PUMA 판단", "장기 EMA 역배열", "매집봉/구간", "공구리(박스권)", "박스 상단 돌파", "상단 박스 안착", "재돌파", "파란점선", "화살표 신호"]
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
        af.addRow("거래량 평균 대비 (최소 300%)", self.sw_vol_ratio)
        af.addRow("긴 윗꼬리 / 전체폭 ≥", self.sw_wick_ratio)
        af.addRow("장대음봉 몸통 / 전체폭 ≥", self.sw_bear_body)
        af.addRow("매집 확인 Lookback", self.sw_acc_lookback)
        af.addRow(QLabel("※ 단독 1회는 매집후보로만 기록. 고거래량 + (긴 윗꼬리 OR 장대음봉)이 20봉 안에 2회 이상 반복될 때만 '매집확정/매집구간'으로 판정."))
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
        self.condition_combo = NoWheelComboBox()
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

        self.condition_table = QTableWidget(0, 6)
        self.condition_table.setHorizontalHeaderLabels(["종목코드", "종목명", "분류", "상태", "편입시각", "분석·매매"])
        ch = self.condition_table.horizontalHeader()
        ch.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        ch.setSectionResizeMode(1, QHeaderView.Stretch)
        ch.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        ch.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        ch.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        ch.setSectionResizeMode(5, QHeaderView.Stretch)
        ch.setMinimumSectionSize(70)
        self.condition_table.verticalHeader().setDefaultSectionSize(32)
        self.condition_table.setAlternatingRowColors(True)
        self.condition_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.condition_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.condition_table.cellClicked.connect(self._condition_row_clicked)
        lay.addWidget(self.condition_table, 1)
        return w

    def _connection_tab(self):
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
        self.api_env = NoWheelComboBox()
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
            self.update_notes.setText("v2.5: 응답없음 성능 수정. 키움 시세/5분봉/일봉 REST 호출을 GUI 스레드에서 분리하고, 박스권 계산은 거래량 300% 후보봉에서만 실행. 동일 차트의 공통경로 결과를 캐시해 스윙/중장기/UI 중복계산과 단타탭 중복 REST 호출을 제거.")
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
            # 종목명/분류가 잘리지 않도록 조건검색 패널을 우선 확보.
            left = max(360, min(500, int(width * 0.22)))
            right = max(330, min(470, int(width * 0.23)))
            center = max(500, width - left - right - 90)
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
        return NumericComboBox(lo, hi, val, decimals=2, suffix=suffix)

    def _spin(self, lo, hi, val, step=1):
        return NumericComboBox(lo, hi, val, step=step, decimals=0)

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
            if price > 0:
                for widget in (self.manual_price, self.manual_cond_price):
                    widget.set_reference_price(int(price), force=False)
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
        if order_type == "stop_limit" and cond <= 0:
            QMessageBox.warning(self, "조건가격", "스톱지정가는 조건가격을 입력하세요.")
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
        x.volume_period = self.sw_vol_period.value()
        x.volume_ratio = self.sw_vol_ratio.value()
        x.upper_wick_ratio = self.sw_wick_ratio.value()
        x.upper_wick_vs_body = self.sw_wick_body.value()
        x.bearish_body_ratio = self.sw_bear_body.value()
        x.accumulation_lookback = self.sw_acc_lookback.value()
        x.accumulation_min_count = max(2, self.sw_acc_min.value())
        x.accumulation_cluster_window = self.sw_acc_cluster.value()
        x.box_search_lookback = self.sw_box_lookback.value()
        x.box_width_pct = self.sw_box_width.value()
        x.box_min_coverage = self.sw_box_coverage.value()
        x.box_min_touches = self.sw_box_touches.value()
        x.box_min_alternations = self.sw_box_alternations.value()
        x.box_touch_tolerance_pct = self.sw_box_touch_tol.value()
        x.box_max_drift_pct = self.sw_box_drift.value()
        x.breakout_buffer_pct = self.sw_breakout_buffer.value()
        x.breakout_volume_ratio = self.sw_breakout_vol.value()
        x.pullback_volume_max_ratio = self.sw_pullback_vol.value()
        x.pullback_base_volume_max_ratio = self.sw_pullback_base_vol.value()
        x.pullback_support_tolerance_pct = self.sw_pullback_tol.value()
        x.pullback_confirm_bars = self.sw_pullback_bars.value()
        x.rebreak_volume_ratio = self.sw_rebreak_vol.value()
        x.path_max_pullback_bars = self.sw_path_bars.value()
        x.blue_period = self.sw_blue_period.value()
        x.blue_dev = self.sw_blue_dev.value()
        x.blue_shift = self.sw_blue_shift.value()
        x.blue_near_pct = self.sw_blue_near.value()
        self.swing_settings = x
        save_swing_settings(x)
        return x

    def apply_swing_preset(self):
        """PUMA operational defaults, not a claimed proprietary formula."""
        values = {
            "sw_vol_period": 20,
            "sw_vol_ratio": 3.0,
            "sw_wick_ratio": 0.42,
            "sw_wick_body": 1.35,
            "sw_bear_body": 0.58,
            "sw_acc_lookback": 112,
            "sw_acc_min": 2,
            "sw_acc_cluster": 20,
            "sw_box_lookback": 160,
            "sw_box_width": 30.0,
            "sw_box_coverage": 0.68,
            "sw_box_touches": 2,
            "sw_box_alternations": 2,
            "sw_box_touch_tol": 2.5,
            "sw_box_drift": 7.5,
            "sw_breakout_buffer": 0.15,
            "sw_breakout_vol": 3.0,
            "sw_pullback_vol": 0.60,
            "sw_pullback_base_vol": 1.00,
            "sw_pullback_tol": 3.0,
            "sw_pullback_bars": 1,
            "sw_rebreak_vol": 3.0,
            "sw_path_bars": 12,
            "sw_blue_period": 26,
            "sw_blue_dev": 2.6,
            "sw_blue_shift": 26,
            "sw_blue_near": 3.0,
        }
        for name, value in values.items():
            widget = getattr(self, name, None)
            if widget is not None:
                widget.setValue(value)
        self.focus_swing_settings_status.setText(
            "PUMA 표준값 적용 · 박스기간 자동 · 돌파강도300% · 눌림≤60%/평균≤100% · 재돌파300% · 파란점선26/2.6/26"
        )

    def save_swing_and_reanalyze(self):
        try:
            settings = self._swing_settings_from_ui()
            self.focus_swing_settings_status.setText("설정 저장 완료")
            if self.focus_daily_raw:
                sa, series = analyze_swing(self.focus_daily_raw, settings)
                self.focus_daily_analysis = sa
                self.focus_daily_series = series
                self._apply_focus_analyses(self.focus_danta_analysis, sa, self.focus_bowl_analysis, "전체")
                self._update_focus_chart(True)
                self.focus_swing_settings_status.setText(f"저장 + 재분석 완료 · {sa.stage} · {sa.score}/100")
        except Exception as exc:
            self.focus_swing_settings_status.setText(f"저장/재분석 실패: {exc}")

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
        if hasattr(self, "focus_condition_table"):
            self.focus_condition_table.setRowCount(0)
        self.classification_queue.clear()
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
            self.condition_candidates[code] = {"name": name or code, "active": True, "entered_at": now, "entry_event": False, "classification": "분석중", "class_detail": "-"}
            self._upsert_condition_row(code)
            self._ensure_market_row(code, name or code, "영웅문4")
            if not name or name == code:
                self._queue_name_lookup(code)
            self._queue_candidate_classification(code)

    def on_condition_enter(self, code: str, name: str):
        now = datetime.now().strftime("%H:%M:%S")
        old_name = self.condition_candidates.get(code, {}).get("name", "")
        self.condition_candidates[code] = {"name": name or old_name or code, "active": True, "entered_at": now, "entry_event": True, "classification": "분석중", "class_detail": "-"}
        self._upsert_condition_row(code)
        self._ensure_market_row(code, name or old_name or code, "영웅문4")
        if not name or name == code:
            self._queue_name_lookup(code)
        self._queue_candidate_classification(code)
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

    def _classification_color(self, label: str) -> QColor:
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
        resolved_name = str(data.get("name") or "").strip()
        if resolved_name and resolved_name != code:
            self.name_cache[code] = resolved_name
            item = self.condition_candidates.get(code)
            if item is not None:
                item["name"] = resolved_name
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

        display_name = str(item.get("name", "") or "").strip()
        readable_name = display_name if display_name and display_name != code else "종목명 조회중…"
        self.condition_table.item(row, 0).setText(code)
        name_cell = self.condition_table.item(row, 1)
        name_cell.setText(readable_name)
        name_cell.setToolTip(readable_name)
        name_cell.setFont(QFont("Malgun Gothic", 10, QFont.Bold))
        name_cell.setForeground(QColor("#f3f8ff"))
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
            fname = self.focus_condition_table.item(frow, 1)
            fname.setText(readable_name)
            fname.setToolTip(readable_name)
            fname.setFont(QFont("Malgun Gothic", 10, QFont.Bold))
            fname.setForeground(QColor("#f3f8ff"))
            self.focus_condition_table.item(frow, 2).setText(classification)
            self.focus_condition_table.item(frow, 2).setToolTip(detail)
            self.focus_condition_table.item(frow, 2).setForeground(self._classification_color(classification))
            self.focus_condition_table.item(frow, 3).setText("편입" if item.get("active") else "이탈")

    def _focus_condition_row_clicked(self, row: int, column: int):
        item = self.focus_condition_table.item(row, 0)
        if not item:
            return
        code = item.text().strip()
        if not code:
            return
        name_item = self.focus_condition_table.item(row, 1)
        name = name_item.text().strip() if name_item else code
        self.open_focus_stock(code, name if "조회중" not in name else code)

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
            QTimer.singleShot(0, self._resolve_next_name)

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

    @staticmethod
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
            result, series = self._enrich_setup_stats(result, series, "DAY")
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
            result, series = self._enrich_setup_stats(result, series, "DAY")
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

    def _enrich_setup_stats(self, analysis, series: dict, strategy: str):
        if not analysis or not series or not series.get("candles"):
            return analysis, series
        try:
            # 모든 기법의 최상위 공통경로.
            # SWING 분석기가 이미 계산한 값이면 그대로 재사용한다.
            if (
                isinstance(series.get("core_path"), dict)
                and isinstance(series.get("path_breakout"), list)
                and isinstance(series.get("path_pullback"), list)
                and isinstance(series.get("path_rebreakout"), list)
            ):
                path_bundle = {
                    "current": series.get("core_path"),
                    "path_breakout": series.get("path_breakout"),
                    "path_pullback": series.get("path_pullback"),
                    "path_rebreakout": series.get("path_rebreakout"),
                    "box": series.get("box"),
                }
            else:
                path_bundle = analyze_market_path(series["candles"], self.swing_settings)
                series["core_path"] = path_bundle.get("current", {})
                series["path_breakout"] = path_bundle.get("path_breakout", [])
                series["path_pullback"] = path_bundle.get("path_pullback", [])
                series["path_rebreakout"] = path_bundle.get("path_rebreakout", [])
                if path_bundle.get("box") and not series.get("box"):
                    series["box"] = path_bundle.get("box")
            p = series["core_path"]
            analysis.details["공통 수급·돌파 경로"] = (
                f"{'활성' if p.get('active') else '대기'} · {p.get('stage','-')} · {p.get('reason','-')}"
            )

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

            path_quality = int((series.get("core_path") or {}).get("quality_score", 0) or 0)
            analysis.details["공통 경로 품질"] = f"{path_quality}/100"
            est = estimate_from_flags(
                series["candles"],
                flags,
                horizon_bars=horizon,
                tp_pct=tp,
                sl_pct=sl,
                current_score=(path_quality if path_quality > 0 else int(getattr(analysis, "score", 0) or 0)),
                current_active=core.active,
                core_signal_name=core.name,
                core_signal_reason=core.reason,
            )
            analysis.details["유사구간 확률"] = est.summary()
            analysis.details["PUMA 판단"] = f"{est.verdict} · {est.reason}"
            analysis.details["확률 기준"] = (
                f"현재와 동일한 확정 단계의 TP-before-SL 통계 · TP {tp:.1f}% / SL {sl:.1f}% · {horizon}봉"
            )
        except Exception as exc:
            analysis.details["PUMA 수박근사"] = f"계산 실패: {exc}"
            analysis.details["핵심 진입 신호"] = "계산 실패"
            analysis.details["유사구간 확률"] = "계산 불가"
            analysis.details["PUMA 판단"] = "판단 유보"
        return analysis, series

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

    def strategy_refresh_selected(self):
        code = (self.selected_code or "").strip()
        if not code:
            if hasattr(self, "strategy_signal_label"):
                self.strategy_signal_label.setText("PUMA 단타 분석: 종목을 선택하세요")
            return

        self._sync_selected_stock_everywhere()

        if self.focus_data_code == code and self.focus_minute_raw:
            self.danta_raw_minute = list(self.focus_minute_raw)
            self.danta_raw_daily = list(self.focus_daily_raw)
            self.danta_cache_code = code
            self._populate_intraday_dates(self.danta_raw_minute)
            self._render_danta_detail_from_cache()
            return

        self._strategy_refresh_after_focus = True
        self.strategy_signal_label.setText("데이터를 백그라운드에서 불러오는 중...")
        self.focus_refresh()


    def open_focus_stock(self, code: str, name: str = ""):
        code = str(code).strip().replace('A', '')
        if not code:
            return
        changed_stock = code != self.selected_code
        self.selected_code = code
        self.selected_name = self.name_cache.get(code) or (name if name and name != code else code)
        if changed_stock:
            self.intraday_selected_day = ""
            self.danta_cache_code = ""
            self.danta_raw_minute = []
            self.danta_raw_daily = []
        self.focus_title.setText(f"{self.selected_name}  {code}")
        self._sync_selected_stock_everywhere()
        origin = self._source_for_code(code)
        self.focus_origin.setText(f"유입: {origin}  ·  차트/분석/주문/자동매매 통합 화면")
        self.tabs.setCurrentWidget(self.focus_widget)
        QApplication.processEvents()
        QTimer.singleShot(0, self.focus_refresh)

    def focus_refresh(self):
        code = (self.selected_code or "").strip()
        if not code:
            return

        # If a request is already running, do not stack more synchronous work.
        if self.focus_load_thread is not None and self.focus_load_thread.isRunning():
            self.focus_refresh_pending = True
            self.focus_origin.setText(
                f"{self.focus_loading_code} 불러오는 중 · 다음 요청은 자동으로 이어서 처리합니다."
            )
            return

        cache_key = (code, int(self.focus_history_pages))
        cached = self.focus_fetch_cache.get(cache_key)
        if cached and time.time() - float(cached.get("loaded_at", 0)) <= 8.0:
            self._apply_focus_loaded(cached)
            return

        self.focus_loading_code = code
        self.focus_refresh_pending = False
        self.focus_origin.setText("시세·5분봉·일봉을 백그라운드에서 불러오는 중... 화면은 계속 사용할 수 있습니다.")

        worker = FocusDataThread(self.broker, code, self.focus_history_pages, self)
        self.focus_load_thread = worker
        worker.loaded.connect(self._focus_load_ready)
        worker.failed.connect(self._focus_load_failed)
        worker.finished.connect(self._focus_load_finished)
        worker.start()

    def _focus_load_ready(self, payload):
        code = str(payload.get("code", ""))
        key = (code, int(payload.get("daily_pages", self.focus_history_pages)))
        self.focus_fetch_cache[key] = payload
        # Keep cache bounded.
        if len(self.focus_fetch_cache) > 12:
            oldest = min(
                self.focus_fetch_cache,
                key=lambda k: float(self.focus_fetch_cache[k].get("loaded_at", 0))
            )
            self.focus_fetch_cache.pop(oldest, None)

        if code != self.selected_code:
            return
        self._apply_focus_loaded(payload)

    def _focus_load_failed(self, message: str):
        if self.focus_loading_code == self.selected_code:
            self.focus_origin.setText(f"불러오기 실패 · {message}")
            if hasattr(self, "strategy_signal_label") and self._strategy_refresh_after_focus:
                self.strategy_signal_label.setText(f"데이터 불러오기 실패: {message}")

    def _focus_load_finished(self):
        self.focus_load_thread = None
        loading_code = self.focus_loading_code
        self.focus_loading_code = ""
        pending = self.focus_refresh_pending
        self.focus_refresh_pending = False

        if pending and self.selected_code and self.selected_code != loading_code:
            QTimer.singleShot(0, self.focus_refresh)

    def _apply_focus_loaded(self, payload: dict):
        code = str(payload.get("code", "")).strip()
        if not code or code != self.selected_code:
            return

        try:
            info = payload.get("info") or {}
            name = self.selected_name or code
            price = 0.0
            if info:
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
            if price:
                for widget_name in ("manual_price", "manual_cond_price", "focus_order_price", "focus_cond_price"):
                    widget = getattr(self, widget_name, None)
                    if isinstance(widget, PriceComboBox):
                        widget.set_reference_price(int(price), force=False)

            self.focus_minute_raw = list(payload.get("minute") or [])
            self.focus_daily_raw = list(payload.get("daily") or [])
            self.focus_data_code = code
            self._populate_intraday_dates(self.focus_minute_raw)

            daily_rows = self.focus_daily_raw
            swing_analysis = None
            bowl_analysis = None

            if daily_rows:
                # CPU analysis is now fast because market_path runs candidate-first
                # and its result is cached/reused across SWING/LONG.
                swing_analysis, swing_series = analyze_swing(daily_rows, self._swing_settings_from_ui())
                bowl_analysis, bowl_series = analyze_bowl(daily_rows, self.bowl_settings)
                swing_series = dict(swing_series)
                bowl_series = dict(bowl_series)

                swing_analysis, swing_series = self._enrich_setup_stats(swing_analysis, swing_series, "SWING")
                bowl_analysis, bowl_series = self._enrich_setup_stats(bowl_analysis, bowl_series, "LONG")

                self.focus_daily_analysis = swing_analysis
                self.focus_daily_series = swing_series
                self.focus_bowl_analysis = bowl_analysis
                self._set_focus_date_bounds()

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
                    danta_analysis, danta_series = self._enrich_setup_stats(danta_analysis, danta_series, "DAY")
                    self.focus_danta_analysis = danta_analysis
                    self.focus_danta_series = danta_series

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

            if code in self.condition_candidates and (latest_danta_for_classification or swing_analysis or bowl_analysis):
                ds = getattr(latest_danta_for_classification, "score", 0) if latest_danta_for_classification else 0
                ss = getattr(swing_analysis, "score", 0) if swing_analysis else 0
                bs = getattr(bowl_analysis, "score", 0) if bowl_analysis else 0
                label, detail = classify_scores(ds, ss, bs)
                self._set_candidate_classification(code, label, detail, {"danta": ds, "swing": ss, "bowl": bs})

            # Share loaded data with the separate 단타 tab: no duplicate REST call.
            self.danta_raw_minute = list(self.focus_minute_raw)
            self.danta_raw_daily = list(self.focus_daily_raw)
            self.danta_cache_code = code

            self._update_focus_chart(False)
            day_count = len(self.focus_daily_series.get("candles", [])) if self.focus_daily_series else 0
            self.focus_origin.setText(
                f"유입: {self._source_for_code(code)} · 일봉 {day_count}봉 · 백그라운드 로딩/고속분석 · "
                f"마지막 갱신 {datetime.now().strftime('%H:%M:%S')}"
            )

            if self._strategy_refresh_after_focus:
                self._strategy_refresh_after_focus = False
                QTimer.singleShot(0, self._render_danta_detail_from_cache)

        except Exception as exc:
            self.focus_origin.setText(f"분석 실패 · {exc}")


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
        }
        if self.intraday_selected_day:
            series = slice_series_for_date(series, self.intraday_selected_day)
        return series.get("candles", []), {k: v for k, v in series.items() if k != "candles"}

    def _update_focus_chart(self, preserve_view: bool = True):
        mode = str(self.focus_chart_mode_combo.currentData()) if hasattr(self, 'focus_chart_mode_combo') else 'DAY'
        self.focus_chart_mode = mode
        is_min = mode == 'MIN'
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
            self.focus_chart.set_data(self.focus_daily_analysis, self.focus_daily_series, title=f"{self.selected_name or self.selected_code} · 일봉 · 역매공파 + 밥그릇3번", preserve_view=preserve_view)

    def focus_chart_mode_changed(self):
        self.focus_chart.clear_analysis_range()
        self._update_focus_chart(False)
        if self.focus_chart_mode == "MIN":
            self.focus_range_status.setText(
                "단타: 전체 날짜 구분" if not self.intraday_selected_day
                else f"단타 날짜: {self._pretty_intraday_day(self.intraday_selected_day)}"
            )
        else:
            self.focus_range_status.setText("분석: 전체")

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
            self._apply_focus_analyses(self.focus_danta_analysis, sa, ba, label)
        self.focus_range_status.setText(f"분석: {label}")

    def focus_analyze_all(self):
        self.focus_chart.clear_analysis_range()
        if self.focus_daily_analysis or self.focus_bowl_analysis:
            self._apply_focus_analyses(self.focus_danta_analysis, self.focus_daily_analysis, self.focus_bowl_analysis, "전체")
        self.focus_range_status.setText("분석: 전체")

    def _apply_focus_analyses(self, danta_analysis, swing_analysis, bowl_analysis, label: str):
        if danta_analysis:
            color = "#61ff8f" if danta_analysis.candidate else ("#62b8ff" if danta_analysis.score >= 55 else "#f4c95d")
            dreason = str(danta_analysis.details.get("간단 이유", "-"))
            djudge = danta_analysis.details.get("PUMA 판단", "판단 유보")
            dprob = danta_analysis.details.get("유사구간 확률", "-")
            dcore = danta_analysis.details.get("핵심 진입 신호", "-")
            self.focus_danta_signal.setText(
                f"단타 DAY · 5분봉\n"
                f"핵심: {dcore}\n"
                f"단계: {danta_analysis.stage}\n"
                f"점수: {danta_analysis.score}/100\n"
                f"유사구간 확률: {dprob}\n"
                f"판단: {djudge}\n"
                f"이유: {dreason}"
            )
            self.focus_danta_signal.setStyleSheet(f"QPlainTextEdit{{font-size:12px;font-weight:900;color:{color};background:#122238;border:0;border-radius:8px;padding:3px;}} QScrollBar:vertical{{width:9px;}}")
            if hasattr(self, "focus_danta_labels"):
                detail_map = {
                    "패턴 점수": f"{danta_analysis.score}/100 · {danta_analysis.stage}",
                    "핵심 진입 신호": danta_analysis.details.get("핵심 진입 신호", "-"),
                    "공통 수급·돌파 경로": danta_analysis.details.get("공통 수급·돌파 경로", "-"),
                    "간단 이유": dreason,
                    "PUMA 수박근사": danta_analysis.details.get("PUMA 수박근사", "-"),
                    "유사구간 확률": danta_analysis.details.get("유사구간 확률", "-"),
                    "PUMA 판단": danta_analysis.details.get("PUMA 판단", "-"),
                    "화살표 신호": danta_analysis.details.get("화살표 신호", "현재봉 화살표 없음"),
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
            sjudge = swing_analysis.details.get("PUMA 판단", "판단 유보")
            sprob = swing_analysis.details.get("유사구간 확률", "-")
            score_core = swing_analysis.details.get("핵심 진입 신호", "-")
            self.focus_swing_signal.setText(
                f"역매공파 SWING\n"
                f"핵심: {score_core}\n"
                f"단계: {swing_analysis.stage}\n"
                f"점수: {swing_analysis.score}/100\n"
                f"유사구간 확률: {sprob}\n"
                f"판단: {sjudge}\n"
                f"이유: {sreason}"
            )
            self.focus_swing_signal.setStyleSheet("QPlainTextEdit{font-size:12px;font-weight:900;color:#62b8ff;background:#122238;border:0;border-radius:8px;padding:3px;} QScrollBar:vertical{width:9px;}")
            for key, lab in self.focus_stage_labels.items():
                text = swing_analysis.details.get(key, "-")
                lab.setText(text)
                good = any(x in text for x in ("확인","감지")) and "미확인" not in text
                near = key == "파란점선" and getattr(swing_analysis, "blue_near", False)
                lab.setStyleSheet(f"font-weight:800;color:{'#61ff8f' if (good or near) else '#f4c95d'}")

        if bowl_analysis:
            breason = str(bowl_analysis.details.get("간단 이유", "-"))
            bjudge = bowl_analysis.details.get("PUMA 판단", "판단 유보")
            bprob = bowl_analysis.details.get("유사구간 확률", "-")
            bcore = bowl_analysis.details.get("핵심 진입 신호", "-")
            self.focus_bowl_signal.setText(
                f"밥그릇 3번 LONG\n"
                f"핵심: {bcore}\n"
                f"단계: {bowl_analysis.stage}\n"
                f"점수: {bowl_analysis.score}/100\n"
                f"유사구간 확률: {bprob}\n"
                f"판단: {bjudge}\n"
                f"이유: {breason}"
            )
            self.focus_bowl_signal.setStyleSheet("QPlainTextEdit{font-size:12px;font-weight:900;color:#d58cff;background:#122238;border:0;border-radius:8px;padding:3px;} QScrollBar:vertical{width:9px;}")
            for key, lab in self.focus_bowl_labels.items():
                text = bowl_analysis.details.get(key, "-")
                lab.setText(text)
                good = "확인" in text and "미확인" not in text
                lab.setStyleSheet(f"font-weight:800;color:{'#61ff8f' if good else '#f4c95d'}")

        d = getattr(danta_analysis, "stage", "대기") if danta_analysis else "대기"
        s = getattr(swing_analysis, "stage", "대기") if swing_analysis else "대기"
        b = getattr(bowl_analysis, "stage", "대기") if bowl_analysis else "대기"
        self.focus_stage.setText(f"통합판정 · {label}  |  단타: {d}  |  역매공파: {s}  |  밥그릇3번: {b}")

    def focus_submit(self, side: str):
        code = self.selected_code
        if not code:
            QMessageBox.information(self, "종목 선택", "조건검색 목록에서 종목을 먼저 선택하세요.")
            return
        qty = self.focus_qty.value()
        order_type = str(self.focus_order_type.currentData())
        price = self.focus_order_price.value()
        cond = self.focus_cond_price.value()
        if order_type == "stop_limit" and cond <= 0:
            QMessageBox.warning(self, "조건가격", "스톱지정가는 조건가격을 입력하세요.")
            return
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
        self._save_ui_layout()
        self.stop_auto()
        self.stop_condition_stream()
        self.classification_queue.clear()
        worker = self.classification_thread
        if worker is not None and worker.isRunning():
            worker.wait(1200)
        event.accept()
