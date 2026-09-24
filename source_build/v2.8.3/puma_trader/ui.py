from __future__ import annotations

from datetime import datetime
import json
import re
import importlib
import shutil
from pathlib import Path
import time
from copy import deepcopy
from .performance import DisplayCache, settings_key, data_revision, analysis_scope, check_cancelled, AnalysisCancelled, DEVICE_PROFILE
from .chart_loader import FocusDataThread, NameLookupThread, reader_broker

from PySide6.QtCore import QTime, QTimer, Qt, QDate, QSettings, QThread, Signal, QEvent, QStandardPaths
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
from .conditions import (
    ConditionStreamThread,
    ConditionListThread,
    MultiConditionStreamThread,
    PUMA_DANTA_CONDITION_NAMES,
    fetch_condition_list,
    is_puma_danta_condition,
    normalize_condition_name,
    select_puma_conditions,
    update_candidate_source,
)
from .engine import TradeEngine
from .models import StrategySettings
from .storage import load_strategy, load_watchlist, save_strategy, save_watchlist, load_swing_settings, save_swing_settings
from .swing import SwingSettings, analyze as analyze_swing, demo_candles, normalize_candles, ema
from .strategy import evaluate_buy
from .bowl import BowlSettings, analyze_bowl
from .danta import analyze_danta, analyze_danta_for_date, available_minute_dates, slice_series_for_date
from .classification import classify_scores, bucket_scores, source_display_buckets
from .watermelon_proxy import build_puma_watermelon
from .probability import estimate_from_flags, strategy_flags
from .entry_signal import evaluate_core_entry
from .market_path import analyze_market_path
from .swing_chart import SwingChart
from .updater import CURRENT_VERSION, download_package, fetch_manifest, load_update_config, save_update_config, stage_and_apply, restart_app
from .secure_credentials import load_credentials, save_credentials, clear_credentials, CredentialError
from .mobile_bridge import MobileBridge

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
        self.swing_settings = deepcopy(swing_settings)
        self.bowl_settings = deepcopy(bowl_settings)
        self.context_key = None
        self.lightweight = DEVICE_PROFILE.low_power

    def run(self):
        broker = reader_broker(self.broker, self.isInterruptionRequested)
        try:
            with analysis_scope(self.isInterruptionRequested):
                self._run_analysis(broker)
        except AnalysisCancelled:
            pass
        finally:
            if broker is not self.broker:
                broker.session.close()

    def _run_analysis(self, broker):
        payload = {"classification": "분석실패", "detail": "-", "danta": 0, "swing": 0, "bowl": 0, "name": ""}
        info = {}
        try:
            check_cancelled()
            try:
                info = broker.get_stock_info(self.code)
                payload["name"] = str(info.get("stk_nm") or info.get("name") or "").strip()
            except Exception:
                pass
            minute = broker.get_minute_candles(self.code, 5)
            getter = getattr(broker, "get_daily_candles", None)
            daily = getter(self.code, max_pages=2) if getter else []
            loaded_at = time.time()
            check_cancelled()
            danta, ds, day = analyze_danta_for_date(minute, daily, None, scan_start=self.scan_start, scan_end=self.scan_end)
            check_cancelled()
            swing, ss = analyze_swing(daily, self.swing_settings)
            check_cancelled()
            bowl, bs = analyze_bowl(daily, self.bowl_settings)
            prepared = None
            if self.context_key:
                if not self.lightweight:
                    tp, sl = self.context_key[-2:]
                    danta, ds = _enrich_danta_pure(danta, ds)
                    swing, ss = _enrich_analysis_pure(swing, ss, "SWING", self.swing_settings, tp, sl)
                    bowl, bs = _enrich_analysis_pure(bowl, bs, "LONG", self.swing_settings, tp, sl)
                source = dict(code=self.code, info=info, minute=minute, daily=daily,
                    daily_pages=2, complete=False, loaded_at=loaded_at, errors=[], revision=data_revision(minute, daily))
                result = dict(code=self.code, request_id=-1, context_key=self.context_key, source_payload=source,
                    target_day="", swing_analysis=swing, swing_series=ss, bowl_analysis=bowl, bowl_series=bs,
                    danta_analysis=danta, danta_series=ds, danta_day=day, latest_danta_score=danta.score,
                    minute_days=available_minute_dates(minute), errors=[], analysis_complete=True)
                prepared = {"payload": source, "result": result}
            check_cancelled()
            label, detail = classify_scores(danta.score, swing.score, bowl.score)
            payload = {
                "prepared": prepared,
                "name": payload["name"],
                "classification": label,
                "detail": detail,
                "danta": danta.score,
                "swing": swing.score,
                "bowl": bowl.score,
            }
        except AnalysisCancelled:
            return
        except Exception as exc:
            payload["detail"] = str(exc)
        self.resultReady.emit(self.code, payload)


def _enrich_danta_pure(analysis, series: dict):
    """Keep DAY/5-minute analysis visually clean.

    Danta does not use daily arrow/concrete/watermelon overlays.  Real entry
    decisions are made separately by TradeEngine -> evaluate_gaboja().
    """
    if not analysis or not series:
        return analysis, series

    series = dict(series)
    for key in (
        "signal_pink", "signal_blue", "signal_red", "signal_black",
        "signal_sar", "signal_bb40_22",
        "box", "boxes", "core_path", "path_breakout", "path_pullback",
        "path_rebreakout", "path_breakout_ma", "path_pullback_ma",
        "watermelon_stage", "watermelon_score", "watermelon_reason",
        "watermelon_confirmed", "watermelon_display",
        "acc_flags",
    ):
        series.pop(key, None)

    for key in (
        "화살표 신호", "공통 수급·돌파 경로", "공통 경로 품질",
        "PUMA 수박근사", "유사구간 확률", "확률 기준",
    ):
        analysis.details.pop(key, None)

    analysis.details["자동매매 기준"] = (
        "7개 조건검색 합집합 → PUMA 장중 힘 2차 선별 → "
        "영1 후 차 눌림 또는 전고 몸통돌파에서만 진입"
    )
    if not getattr(analysis, "in_time", False):
        analysis.details["PUMA 판단"] = "자동매수 시간 외 · 후보/구조만 관찰"
    elif getattr(analysis, "breakout", False) or getattr(analysis, "pullback_hold", False):
        analysis.details["PUMA 판단"] = "가보자 엔진 실시간 정밀판정 대상 · 조건 충족 시에만 주문"
    else:
        analysis.details["PUMA 판단"] = "가보자 타점 대기 · 자동주문 없음"

    return analysis, series


def _enrich_analysis_pure(analysis, series: dict, strategy: str, swing_settings, tp: float, sl: float):
    """Pure CPU helper. No QWidget access: safe to run in a QThread."""
    if not analysis or not series or not series.get("candles"):
        return analysis, series

    series = dict(series)
    try:
        if (
            isinstance(series.get("core_path"), dict)
            and isinstance(series.get("path_breakout"), list)
            and isinstance(series.get("path_pullback"), list)
            and isinstance(series.get("path_rebreakout"), list)
            and isinstance(series.get("boxes"), list)
        ):
            path_bundle = {
                "current": series.get("core_path"),
                "path_breakout": series.get("path_breakout"),
                "path_pullback": series.get("path_pullback"),
                "path_rebreakout": series.get("path_rebreakout"),
                "box": series.get("box"),
                "boxes": series.get("boxes", []),
            }
        else:
            path_bundle = analyze_market_path(series["candles"], swing_settings)
            series["core_path"] = path_bundle.get("current", {})
            series["path_breakout"] = path_bundle.get("path_breakout", [])
            series["path_pullback"] = path_bundle.get("path_pullback", [])
            series["path_rebreakout"] = path_bundle.get("path_rebreakout", [])
            series["boxes"] = path_bundle.get("boxes", [])
            if path_bundle.get("box") and not series.get("box"):
                series["box"] = path_bundle.get("box")

        p = series.get("core_path") or {}
        analysis.details["공통 수급·돌파 경로"] = (
            f"{'활성' if p.get('active') else '대기'} · {p.get('stage','-')} · {p.get('reason','-')}"
        )

        # swing/bowl/danta analyzers already calculate watermelon. Reuse it.
        if not isinstance(series.get("watermelon_stage"), list):
            series.update(build_puma_watermelon(series["candles"], series))

        scores = series.get("watermelon_score", [])
        reasons = series.get("watermelon_reason", [])
        confirmed = series.get("watermelon_confirmed", [])
        display = series.get("watermelon_display", [])
        wscore = int(scores[-1]) if scores else 0
        wreason = str(reasons[-1]) if reasons else "조건 미충족"
        wconfirmed = bool(confirmed[-1]) if confirmed else False
        recent_display = bool(display and any(bool(x) for x in display[max(0, len(display)-20):]))
        if wconfirmed:
            analysis.details["PUMA 수박근사"] = f"확정구간 · {wscore}/100 · {wreason}"
        elif recent_display:
            analysis.details["PUMA 수박근사"] = f"최근 확정수박 존재 · 현재는 해제 · {wscore}/100"
        else:
            analysis.details["PUMA 수박근사"] = f"표시 없음 · 확정조건 미충족 · {wscore}/100"

        core = evaluate_core_entry(analysis, series, strategy)
        analysis.details["핵심 진입 신호"] = core.status_text

        flags = strategy_flags(series, strategy)
        horizon = 12 if strategy == "DAY" else 20 if strategy == "SWING" else 60
        path_quality = int((series.get("core_path") or {}).get("quality_score", 0) or 0)
        analysis.details["공통 경로 품질"] = f"{path_quality}/100"

        est = estimate_from_flags(
            series["candles"],
            flags,
            horizon_bars=horizon,
            tp_pct=float(tp),
            sl_pct=abs(float(sl)),
            current_score=(path_quality if path_quality > 0 else int(getattr(analysis, "score", 0) or 0)),
            current_active=core.active,
            core_signal_name=core.name,
            core_signal_reason=core.reason,
        )
        analysis.details["유사구간 확률"] = est.summary()
        analysis.details["PUMA 판단"] = f"{est.verdict} · {est.reason}"
        analysis.details["확률 기준"] = (
            f"현재와 동일한 확정 단계의 TP-before-SL 통계 · "
            f"TP {float(tp):.1f}% / SL {abs(float(sl)):.1f}% · {horizon}봉"
        )
    except AnalysisCancelled:
        raise
    except Exception as exc:
        analysis.details["PUMA 수박근사"] = f"계산 실패: {exc}"
        analysis.details["핵심 진입 신호"] = "계산 실패"
        analysis.details["유사구간 확률"] = "계산 불가"
        analysis.details["PUMA 판단"] = "판단 유보"

    return analysis, series


class FocusAnalysisThread(QThread):
    """Analyze the visible strategy first, publishing completed stages immediately."""
    analyzed = Signal(object)
    failed = Signal(str)

    def __init__(self, code, minute_rows, daily_rows, target_day, scan_start, scan_end,
                 swing_settings, bowl_settings, tp, sl, parent=None):
        super().__init__(parent)
        self.code = str(code)
        self.minute_rows, self.daily_rows = list(minute_rows or []), list(daily_rows or [])
        self.target_day, self.scan_start, self.scan_end = target_day, scan_start, scan_end
        self.swing_settings, self.bowl_settings = deepcopy(swing_settings), deepcopy(bowl_settings)
        self.tp, self.sl = float(tp), float(sl)
        self.mode = "DAY"
        self.request_id = 0
        self.context_key = None
        self.source_payload = {}

    def run(self):
        started = time.perf_counter()
        out = dict(code=self.code, request_id=self.request_id, context_key=self.context_key,
                   source_payload=self.source_payload, target_day=self.target_day,
                   swing_analysis=None, swing_series=None, bowl_analysis=None, bowl_series=None,
                   danta_analysis=None, danta_series=None, danta_day="", latest_danta_score=0,
                   minute_days=[], errors=[], analysis_complete=False)
        try:
            with analysis_scope(self.isInterruptionRequested):
                out["minute_days"] = available_minute_dates(self.minute_rows)
                order = ["danta", "swing", "bowl"] if self.mode == "MIN" else ["swing", "bowl", "danta"]
                for kind in order:
                    check_cancelled()
                    try:
                        if kind == "danta" and self.minute_rows:
                            a, series, day = analyze_danta_for_date(self.minute_rows, self.daily_rows,
                                self.target_day or None, scan_start=self.scan_start, scan_end=self.scan_end)
                            a, series = _enrich_danta_pure(a, series)
                            out["danta_day"] = day
                            if not self.target_day:
                                out["latest_danta_score"] = int(a.score)
                            else:
                                latest, _, _ = analyze_danta_for_date(self.minute_rows, self.daily_rows,
                                    None, scan_start=self.scan_start, scan_end=self.scan_end)
                                out["latest_danta_score"] = int(latest.score)
                        elif kind == "swing" and self.daily_rows:
                            a, series = analyze_swing(self.daily_rows, self.swing_settings)
                            a, series = _enrich_analysis_pure(a, series, "SWING", self.swing_settings, self.tp, self.sl)
                        elif kind == "bowl" and self.daily_rows:
                            a, series = analyze_bowl(self.daily_rows, self.bowl_settings)
                            a, series = _enrich_analysis_pure(a, series, "LONG", self.swing_settings, self.tp, self.sl)
                        else:
                            continue
                        check_cancelled()
                        out[kind + "_analysis"], out[kind + "_series"] = a, series
                    except AnalysisCancelled:
                        raise
                    except Exception as exc:
                        out["errors"].append(f"{kind}: {exc}")
                    check_cancelled()
                    self.analyzed.emit({**out, "errors": list(out["errors"])})
                out["analysis_complete"] = True
                out["analysis_ms"] = (time.perf_counter() - started) * 1000
                self.analyzed.emit(out)
        except AnalysisCancelled:
            pass
        except Exception as exc:
            if not self.isInterruptionRequested():
                self.failed.emit(str(exc))


class DantaAnalysisThread(QThread):
    """Background recompute for date switching / detailed danta tab."""
    analyzed = Signal(object)
    failed = Signal(str)

    def __init__(
        self, code: str, minute_rows, daily_rows, target_day: str,
        scan_start: str, scan_end: str, swing_settings, tp: float, sl: float,
        parent=None
    ):
        super().__init__(parent)
        self.code = str(code)
        self.minute_rows = list(minute_rows or [])
        self.daily_rows = list(daily_rows or [])
        self.target_day = str(target_day or "")
        self.scan_start = str(scan_start)
        self.scan_end = str(scan_end)
        self.swing_settings = swing_settings
        self.tp = float(tp)
        self.sl = float(sl)

    def run(self):
        with analysis_scope(self.isInterruptionRequested):
            self._run_analysis()

    def _run_analysis(self):
        try:
            check_cancelled()
            result, series, day = analyze_danta_for_date(
                self.minute_rows,
                self.daily_rows,
                self.target_day or None,
                scan_start=self.scan_start,
                scan_end=self.scan_end,
            )
            result, series = _enrich_danta_pure(result, dict(series))
            check_cancelled()
            self.analyzed.emit({
                "request_id": getattr(self, "request_id", 0),
                "revision": getattr(self, "revision", ""),
                "context_key": getattr(self, "context_key", None),
                "code": self.code,
                "target_day": self.target_day,
                "analysis": result,
                "series": series,
                "day": day,
            })
        except AnalysisCancelled:
            pass
        except Exception as exc:
            self.failed.emit(str(exc))



class AutoScanThread(QThread):
    """Run one trading scan outside the GUI event loop.

    Only one instance is allowed at a time by MainWindow.scan_one(), preventing
    overlapping engine.process() calls from timer re-entry.
    """
    resultReady = Signal(object)
    failed = Signal(object)

    def __init__(self, engine, code: str, name: str, require_buy_filter: bool, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.code = str(code)
        self.name = str(name)
        self.require_buy_filter = bool(require_buy_filter)

    def run(self):
        try:
            result = self.engine.process(
                self.code,
                self.name,
                require_buy_filter=self.require_buy_filter,
            )
            self.resultReady.emit(result)
        except Exception as exc:
            self.failed.emit(exc)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"PUMA STOCK PRO v{CURRENT_VERSION}")
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
        self.condition_thread: MultiConditionStreamThread | None = None
        self.condition_list_thread: ConditionListThread | None = None
        self.condition_stream_generation = 0
        self.manual_condition_thread: ConditionStreamThread | None = None
        self.manual_condition_generation = 0
        self.condition_pending_action: str = ""
        self.manual_condition_name: str = ""
        self.manual_condition_seq: str = ""
        self.manual_condition_rows: dict[str, str] = {}
        self._manual_import_after_snapshot = False
        self.session_excluded_codes: set[str] = set()
        self.condition_list: list[tuple[str, str]] = []
        self.row_by_code: dict[str, int] = {}
        self.name_cache: dict[str, str] = {}
        self.name_lookup_queue: list[str] = []
        self.classification_queue: list[str] = []
        self.classification_thread: CandidateClassifier | None = None
        self.selected_code: str = ""
        self.selected_name: str = ""
        self.focus_only_code: str | None = None
        self.focus_auto_danta_pool: bool = False

        self.broker = SimBroker()
        self.engine = TradeEngine(self.broker, self.settings)
        self.real_armed = False
        self.live_auto_confirmed_session = False
        self.condition_snapshot_seen: set[str] = set()
        self.condition_live_registered_count = 0
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
        self.focus_bowl_series = None
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
        self._focus_readers = set()
        self._focus_request_id = 0
        self._focus_fetch_pending = False
        self._display_cache = DisplayCache(DEVICE_PROFILE.display_cache_entries)
        self._analysis_cache = DisplayCache(DEVICE_PROFILE.analysis_cache_entries)
        self._closing = False
        self._name_worker = None
        self._range_worker = None
        self._range_pending = None
        self._range_request_id = 0
        self._range_cache = DisplayCache(DEVICE_PROFILE.range_cache_entries)
        self._preview_series = {}
        self._shown_daily_revision = ""
        self._focus_revision = ""
        self._click_started = 0.0
        self.focus_latency_ms = {}
        self._perf_log_scheduled_id = 0
        self.focus_loading_code: str = ""
        self.focus_refresh_pending: bool = False
        self.focus_fetch_cache: dict[tuple[str, int], dict] = {}
        self.focus_data_code: str = ""
        self._strategy_refresh_after_focus: bool = False

        # Mobile companion bridge. HTTP thread never touches Qt widgets directly.
        self.mobile_bridge = MobileBridge(self)
        self.mobile_bridge.commandReceived.connect(self._on_mobile_command)
        self.mobile_publish_timer = QTimer(self)
        self.mobile_publish_timer.setInterval(750)
        self.mobile_publish_timer.timeout.connect(self._publish_mobile_snapshot)

        # CPU analysis workers. Heavy calculations never run in the GUI event loop.
        self.focus_analysis_thread: FocusAnalysisThread | None = None
        self.focus_analysis_pending: dict | None = None
        self.danta_analysis_thread: DantaAnalysisThread | None = None
        self.danta_analysis_pending: bool = False
        self.auto_scan_thread: AutoScanThread | None = None

        self.timer = QTimer(self)
        self.timer.setInterval(1800)
        self.timer.timeout.connect(self.scan_one)

        # 조건검색 WebSocket은 종목명 없이 코드만 주는 경우가 있어 REST 종목정보로 천천히 보완한다.
        self.name_lookup_timer = QTimer(self)
        self.name_lookup_timer.setInterval(650 if DEVICE_PROFILE.low_power else 320)
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
        title = QLabel(f"🐆  PUMA STOCK PRO  v{CURRENT_VERSION}")
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
        self.mobile_widget = self._mobile_tab()
        self.update_widget = self._update_tab()
        self.tabs.addTab(self.focus_widget, "통합 트레이딩")
        self.tabs.addTab(self.hero_widget, "조건검색")
        self.tabs.addTab(self.dashboard_widget, "잔고 · 로그")
        # 단타 상세분석은 통합 트레이딩의 버튼에서 별도 창으로 연다.
        self.tabs.addTab(self.manual_widget, "직접 주문")
        self.tabs.addTab(self.connection_widget, "설정 · 키움연결")
        self.tabs.addTab(self.mobile_widget, "모바일 연동")
        self.tabs.addTab(self.update_widget, "업데이트")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        outer.addWidget(self.tabs)

        self._load_saved_connection()
        self._apply_display_profile()
        QTimer.singleShot(0, self._restore_ui_layout)
        if getattr(self, "auto_connect_box", None) is not None and self.auto_connect_box.isChecked():
            QTimer.singleShot(900, self.auto_connect_saved)
        self.mobile_publish_timer.start()
        self._publish_mobile_snapshot()
        if getattr(self, "mobile_auto_box", None) is not None and self.mobile_auto_box.isChecked():
            QTimer.singleShot(1200, self._mobile_start)

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
        self.focus_perf_label = QLabel("성능: 대기")
        self.focus_perf_label.setStyleSheet("color:#7fd3ff;font-weight:800")
        tools.addWidget(self.focus_perf_label)
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

        cand_tools = QHBoxLayout()
        self.focus_candidate_count = QLabel("0종목")
        self.focus_candidate_count.setStyleSheet("color:#8fb6d9;font-weight:800")
        self.focus_candidate_delete_btn = QPushButton("선택 삭제")
        self.focus_candidate_delete_btn.setObjectName("stopBtn")
        self.focus_candidate_delete_btn.setToolTip("선택 종목을 현재 세션의 신규 자동매매 후보에서도 제외합니다.")
        self.focus_candidate_delete_btn.clicked.connect(self.delete_selected_focus_candidate)
        cand_tools.addWidget(self.focus_candidate_count)
        cand_tools.addStretch()
        cand_tools.addWidget(self.focus_candidate_delete_btn)
        cand_lay.addLayout(cand_tools)

        # 조건검색 결과는 한 개 리스트로 유지하고 버튼으로 분류만 전환한다.
        self.focus_candidate_filter = "all"
        self.focus_filter_buttons = {}
        filter_row = QHBoxLayout()
        filter_row.setSpacing(3)
        for key, title in (
            ("all", "전체"),
            ("danta", "단타"),
            ("swing", "스윙"),
            ("bowl", "중장기"),
        ):
            btn = QPushButton(title)
            btn.setCheckable(True)
            btn.setFixedHeight(25)
            btn.setMaximumWidth(64 if key != "bowl" else 72)
            btn.setStyleSheet(
                "QPushButton{font-weight:900;padding:1px 5px;font-size:11px;}"
                "QPushButton:checked{border:2px solid #61d4ff;background:#17304a;}"
            )
            btn.clicked.connect(lambda checked=False, k=key: self._set_focus_candidate_filter(k))
            self.focus_filter_buttons[key] = btn
            filter_row.addWidget(btn)
        filter_row.addStretch()
        self.focus_filter_buttons["all"].setChecked(True)
        cand_lay.addLayout(filter_row)

        self.focus_condition_table = QTableWidget(0, 3)
        self.focus_condition_table.setHorizontalHeaderLabels(["코드", "종목명", "상태"])
        hdr = self.focus_condition_table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.Interactive)
        hdr.setStretchLastSection(False)
        hdr.setMinimumSectionSize(48)
        self.focus_condition_table.setColumnWidth(0, 72)
        self.focus_condition_table.setColumnWidth(1, 135)
        self.focus_condition_table.setColumnWidth(2, 200)
        self.focus_condition_table.verticalHeader().setVisible(False)
        self.focus_condition_table.verticalHeader().setDefaultSectionSize(29)
        self.focus_condition_table.setAlternatingRowColors(True)
        self.focus_condition_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.focus_condition_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.focus_condition_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.focus_condition_table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.focus_condition_table.cellClicked.connect(self._focus_condition_row_clicked)
        cand_lay.addWidget(self.focus_condition_table, 1)
        candidates.setMinimumWidth(250)
        candidates.setMaximumWidth(340)

        cand_help = QLabel("단타 검색기 결과는 단타에만 표시 · 아래 가로바로 열 이동")
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
        self.focus_chart.paintMeasured.connect(self._focus_chart_painted)
        center.addWidget(self.focus_chart, 9)

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
        signals.setMinimumHeight(155)
        center.addWidget(signals, 1)
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
        danta_names = ["자동매매 기준", "PUMA 판단", "간단 이유", "검색 시간", "PUMA 기준선(26)", "EMA 5·20·60", "현재 5분봉 거래량", "최근 고점 돌파", "눌림 지지"]
        for i, name in enumerate(danta_names):
            a = QLabel(name)
            b = QLabel("대기")
            b.setWordWrap(True)
            b.setStyleSheet("font-weight:800;color:#f4c95d")
            dg.addWidget(a, i, 0)
            dg.addWidget(b, i, 1)
            self.focus_danta_labels[name] = b
        open_danta = QPushButton("단타 상세분석 열기")
        open_danta.clicked.connect(self.open_danta_detail_window)
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
        af.addRow("상대 거래량 참고선", self.sw_vol_ratio)
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
        order_note = QLabel("자동매매는 LIVE 1회 잠금 해제 후 추가 입력 없이 시작합니다. 수동 주문은 LIVE ORDER 확인을 유지합니다.")
        order_note.setWordWrap(True)
        order_note.setStyleSheet("color:#9eb4c9")
        ov.addWidget(order_note)
        ov.addStretch()
        self.focus_side_tabs.addTab(self._scroll_wrap(order_page), "주문")

        auto_page = QWidget()
        auv = QVBoxLayout(auto_page)
        auv.setContentsMargins(5, 5, 5, 5)
        auto = QGroupBox("가보자 자동매매")
        afm = QFormLayout(auto)
        self.focus_budget = self._spin(500_000, 500_000, 500_000, 10_000)
        self.focus_budget.setEnabled(False)
        self.focus_tp = self._dspin(0.1, 100, self.settings.take_profit_pct, " %")
        self.focus_sl = self._dspin(-50, -0.1, self.settings.stop_loss_pct, " %")
        self.focus_trail = QCheckBox("트레일링 스탑")
        self.focus_trail.setChecked(self.settings.trailing_enabled)
        self.focus_trail_start = self._dspin(0.1, 100, self.settings.trailing_start_pct, " %")
        self.focus_trail_gap = self._dspin(0.1, 30, self.settings.trailing_gap_pct, " %")
        afm.addRow("종목당 투입금(고정)", self.focus_budget)
        afm.addRow("익절", self.focus_tp)
        afm.addRow("손절", self.focus_sl)
        afm.addRow(self.focus_trail)
        afm.addRow("트레일링 시작", self.focus_trail_start)
        afm.addRow("고점대비 하락", self.focus_trail_gap)
        ar = QHBoxLayout()
        start = QPushButton("▶ 전체 후보 자동매매 시작")
        start.setObjectName("startBtn")
        selected_start = QPushButton("선택 종목만")
        stop = QPushButton("■ 중지")
        stop.setObjectName("stopBtn")
        start.clicked.connect(self.start_danta_pool_auto)
        selected_start.clicked.connect(self.start_focus_auto)
        stop.clicked.connect(self.stop_auto)
        ar.addWidget(start)
        ar.addWidget(selected_start)
        ar.addWidget(stop)
        afm.addRow(ar)
        auv.addWidget(auto)
        note = QLabel("단타 검색기 7개 결과 합집합 → 종목코드 중복 제거 → PUMA 단타 2차 선별 → 가보자 차 눌림/전고 몸통돌파에서만 50만원 매수. 관심종목 등록은 필요 없습니다. '선택 종목만'은 수동 점검용 보조 기능입니다.")
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
        self.focus_splitter.setSizes([290, 900, 360])
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

        info = QLabel("가보자 단타는 5분봉 고정입니다. 단타 화면에는 화살표·공구리·수박 같은 장기 패턴 표시는 사용하지 않습니다. 조건검색 후보를 PUMA가 장중 힘으로 2차 선별하고, 영1 후 차 눌림 또는 전고 몸통돌파에서만 자동진입합니다.")
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
        self.order_budget = self._spin(500_000, 500_000, 500_000, 10_000)
        self.order_budget.setEnabled(False)
        self.max_positions = self._spin(1, 20, self.settings.max_positions)
        self.cooldown = self._spin(0, 240, self.settings.cooldown_min)
        self.max_daily_orders = self._spin(1, 100, self.settings.max_daily_orders)
        self.account_sync_sec = self._spin(2, 60, self.settings.account_sync_sec)
        self.exchange_combo = NoWheelComboBox()
        self.exchange_combo.addItems(["KRX", "NXT", "SOR"])
        self.exchange_combo.setCurrentText(self.settings.order_exchange)
        rf.addRow("종목당 투입금(고정)", self.order_budget)
        rf.addRow("최대 보유종목", self.max_positions)
        rf.addRow("재진입 대기(분)", self.cooldown)
        rf.addRow("PUMA 일일 주문 상한", self.max_daily_orders)
        rf.addRow("실계좌 동기화(초)", self.account_sync_sec)
        rf.addRow("주문 거래소", self.exchange_combo)
        risk_note = QLabel("가보자 자동매수는 종목당 50만원으로 고정합니다. 실전 자동주문은 LIVE 1회 잠금 해제와 실제 잔고 동기화를 사용합니다.")
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

        stages = QGroupBox("PUMA 스윙 상태 분석 · 사용자 검색기 3종 참고")
        sg = QGridLayout(stages)
        self.swing_stage_labels = {}
        names = ["간단 이유", "스윙검색기 종합", "스윙검색기 A · 224근접", "스윙검색기 B · 급등후눌림", "스윙검색기 C · 장기돌파", "PUMA 수박근사", "유사구간 확률", "PUMA 판단", "장기 EMA 역배열", "매집봉/구간", "공구리(박스권)", "박스 상단 돌파", "상단 박스 안착", "재돌파", "파란점선", "화살표 신호"]
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
        self.sw_vol_ratio = self._dspin(1.0, 20.0, 1.8, " 배")
        self.sw_wick_ratio = self._dspin(0.1, 0.9, 0.42)
        self.sw_bear_body = self._dspin(0.2, 0.95, 0.58)
        self.sw_acc_lookback = self._spin(20, 250, 90)
        af.addRow("상대 거래량 참고선", self.sw_vol_ratio)
        af.addRow("긴 윗꼬리 / 전체폭 ≥", self.sw_wick_ratio)
        af.addRow("장대음봉 몸통 / 전체폭 ≥", self.sw_bear_body)
        af.addRow("매집 확인 Lookback", self.sw_acc_lookback)
        af.addRow(QLabel("※ 고정 3배 컷 없음. 최근 20봉 평균과 최근 60봉 거래량 상위권을 함께 비교. 긴 윗꼬리·장대음봉·가격반응 대비 이상거래량을 매집후보로 보고, 반복되면 매집확정/매집구간으로 판정."))
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
        note = QLabel("수박/화살표는 네 신호식을 받기 전까지 최종 트리거로 연결하지 않습니다.\n실전 자동주문은 LIVE 1회 잠금과 리스크 제한을 사용합니다.")
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
            "단타 자동 후보는 지정된 단타 검색기 7개를 동시에 실행해 합집합으로 받습니다. 종목코드 기준 중복은 한 번만 저장하고, 단타 목록에는 자동편입한 뒤 PUMA가 다시 선별합니다. 단타1 하나만 특별취급하지 않습니다."
        )
        lay.addWidget(info)

        box = QGroupBox("영웅문4 조건식 연결")
        form = QFormLayout(box)
        self.condition_combo = NoWheelComboBox()
        self.condition_combo.setMaxVisibleItems(18)
        self.condition_refresh_btn = QPushButton("조건식 목록 불러오기")
        self.condition_refresh_btn.clicked.connect(lambda: self.refresh_conditions())
        self.hero_secondary_filter = QCheckBox("단타 검색기 후보 → PUMA 2차 선별 적용(필수)")
        self.hero_secondary_filter.setChecked(True)
        self.hero_secondary_filter.setEnabled(False)
        self.hero_entry_only = QCheckBox()
        self.hero_entry_only.setChecked(False)
        self.hero_entry_only.hide()
        self.condition_start_btn = QPushButton("▶ 단타 검색기들 동시 시작")
        self.condition_start_btn.setObjectName("conditionBtn")
        self.condition_start_btn.clicked.connect(self.start_condition_stream)
        self.condition_stop_btn = QPushButton("■ 조건검색 중지")
        self.condition_stop_btn.clicked.connect(self.stop_condition_stream)
        form.addRow("조건식", self.condition_combo)
        manual_row = QHBoxLayout()
        self.manual_condition_view_btn = QPushButton("선택 조건식 종목 보기")
        self.manual_condition_import_btn = QPushButton("→ 종합 트레이딩에 편입")
        self.manual_condition_import_btn.setObjectName("startBtn")
        self.manual_condition_stop_btn = QPushButton("조회 중지")
        self.manual_condition_view_btn.clicked.connect(self.start_manual_condition_preview)
        self.manual_condition_import_btn.clicked.connect(self.import_selected_condition_to_focus)
        self.manual_condition_stop_btn.clicked.connect(self.stop_manual_condition_preview)
        manual_row.addWidget(self.manual_condition_view_btn)
        manual_row.addWidget(self.manual_condition_import_btn)
        manual_row.addWidget(self.manual_condition_stop_btn)
        form.addRow(manual_row)
        self.manual_condition_status = QLabel("원하는 조건식을 선택한 뒤 '종목 보기'를 누르세요.")
        self.manual_condition_status.setStyleSheet("color:#8fb6d9")
        form.addRow("수동 조회", self.manual_condition_status)
        bundle = QLabel("단타 자동 후보 7개 합집합: 단타단타(시원놈) · 5분봉_단타(시원놈) · 단타1 · 시초가1번 · 시초가1-1번 · 시초가2번 · 시초가멀티\n※ 중복 종목은 한 번만 편입합니다. 아래 콤보박스는 다른 조건식을 수동 조회/편입할 때 사용합니다.")
        bundle.setWordWrap(True)
        bundle.setStyleSheet("color:#9eb4c9")
        form.addRow(bundle)
        form.addRow(self.condition_refresh_btn)
        form.addRow(self.hero_secondary_filter)
        all_candidates_note = QLabel("초기 조회 + 이후 신규 편입 종목 전부 자동검토 · 조건식 편입 자체는 매수신호가 아니며 PUMA 2차 선별 + 가보자 타점 통과 시에만 주문")
        all_candidates_note.setWordWrap(True)
        all_candidates_note.setStyleSheet("color:#61d4ff;font-weight:700")
        form.addRow(all_candidates_note)
        row = QHBoxLayout()
        row.addWidget(self.condition_start_btn)
        row.addWidget(self.condition_stop_btn)
        form.addRow(row)
        self.condition_status = QLabel("키움 연결 후 조건식을 불러오세요.")
        form.addRow("상태", self.condition_status)
        lay.addWidget(box)

        manual_box = QGroupBox("선택 조건식 현재 종목 · 수동 확인용")
        mv = QVBoxLayout(manual_box)
        self.manual_condition_table = QTableWidget(0, 3)
        self.manual_condition_table.setHorizontalHeaderLabels(["종목코드", "종목명", "상태"])
        mh = self.manual_condition_table.horizontalHeader()
        mh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        mh.setSectionResizeMode(1, QHeaderView.Stretch)
        mh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.manual_condition_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.manual_condition_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.manual_condition_table.cellDoubleClicked.connect(self._manual_condition_row_clicked)
        mv.addWidget(self.manual_condition_table)
        manual_box.setMaximumHeight(260)
        lay.addWidget(manual_box)

        auto_title = QLabel("단타 검색기 7개 · 통합 합집합")
        auto_title.setStyleSheet("font-weight:900;color:#61ff8f;padding-top:4px")
        lay.addWidget(auto_title)

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
            "· 자동매매 시작 시 추가 확인 입력 없음\n"
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
        self.desktop_launcher_btn = QPushButton("바탕화면 PUMA 실행파일 만들기")
        self.desktop_launcher_btn.clicked.connect(self.create_desktop_launcher)
        form.addRow(self.desktop_launcher_btn)
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

    def create_desktop_launcher(self):
        root = Path(__file__).resolve().parent.parent
        src = root / "PUMA_STOCK_PRO.exe"
        if not src.exists():
            QMessageBox.warning(
                self, "실행파일 없음",
                "PUMA_STOCK_PRO.exe가 아직 설치되지 않았습니다. 최신 버전으로 업데이트한 뒤 다시 누르세요."
            )
            return
        desktop = Path(QStandardPaths.writableLocation(QStandardPaths.DesktopLocation))
        if not desktop:
            QMessageBox.warning(self, "바탕화면", "바탕화면 경로를 찾지 못했습니다.")
            return
        dst = desktop / "PUMA_STOCK_PRO.exe"
        try:
            shutil.copy2(src, dst)
            QMessageBox.information(
                self, "완료",
                f"바탕화면에 PUMA_STOCK_PRO.exe를 만들었습니다.\n{dst}\n\n이 EXE는 설치 폴더 밖에서도 원래 PUMA 위치를 찾아 실행합니다."
            )
        except Exception as exc:
            QMessageBox.critical(self, "바탕화면 실행파일", str(exc))

    def check_update(self):
        url = self.update_url.text().strip()
        save_update_config({"manifest_url": url})
        if not url:
            self.update_status.setText("업데이트 서버가 아직 설정되지 않았습니다.")
            self.update_notes.setText('v2.7: 차트 첫 응답 선표시, 완성 분석 캐시 즉시 재사용, 조건검색 사전분석 재사용, 최신 클릭 우선 처리, 과거 데이터 보완 중에도 화면 유지, 박스 중복계산 최적화.')
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
            f"v{info.version}을 다운로드하고 적용합니다.\n프로그램 안에서 SHA256 검증 후 소스만 안전하게 교체하고 바로 재시작합니다.\n계속할까요?"
        )
        if ans != QMessageBox.Yes:
            return
        try:
            self.update_status.setText("업데이트 다운로드 중...")
            QApplication.processEvents()
            package = download_package(info)
            self.update_status.setText("업데이트 검증 완료 · 프로그램 파일 적용 중...")
            QApplication.processEvents()
            stage_and_apply(package, info.version)
            self.update_status.setText(f"v{info.version} 적용 완료 · 새 실행기를 불러와 재시작합니다.")
            QApplication.processEvents()

            # updater.py itself may have been replaced by this update.
            # Reload it from disk so the NEW restart code is used, not the stale
            # function object imported when the old PUMA process started.
            from . import updater as updater_module
            updater_module = importlib.reload(updater_module)
            updater_module.write_install_marker(Path(__file__).resolve().parent.parent)
            updater_module.restart_app()
            QTimer.singleShot(250, QApplication.quit)
        except Exception as exc:
            self.update_status.setText("업데이트 실패")
            QMessageBox.critical(self, "업데이트 실패", str(exc))

    # ---------- helpers ----------
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel:
            # 수동/예비 조건식은 목록을 펼친 동안에만 휠 스크롤을 허용한다.
            # 접힌 콤보/숫자 입력값은 기존처럼 휠 오조작을 막는다.
            combo = getattr(self, "condition_combo", None)
            if combo is not None:
                try:
                    view = combo.view()
                    if view.isVisible() and (obj is view or obj is view.viewport() or obj is combo):
                        return super().eventFilter(obj, event)
                except Exception:
                    pass
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
            # 조건검색은 좁게 유지하고 중앙 차트에 화면을 우선 배분한다.
            left = max(260, min(320, int(width * 0.17)))
            right = max(315, min(400, int(width * 0.21)))
            center = max(620, width - left - right - 80)
            self.focus_splitter.setSizes([left, center, right])
        if hasattr(self, "focus_chart"):
            self.focus_chart.setMinimumHeight(330 if height < 850 else 420)

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
        cond = self.condition_candidates.get(code, {})
        if cond.get("active"):
            auto_count, manual_count = self._candidate_source_counts(cond)
            if auto_count:
                parts.append(f"영웅문4×{auto_count}" if auto_count > 1 else "영웅문4")
            if manual_count:
                parts.append("수동조건")
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
            QMessageBox.critical(self, "PUMA 스윙 분석 오류", str(exc))

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
            hero_condition_names=([str(name)] if str(name or "").strip() else []),
            hero_secondary_filter=self.hero_secondary_filter.isChecked(),
            hero_entry_only=False,
            order_budget=500_000,
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
        self.live_auto_confirmed_session = False
        self._set_status("SIMULATION", "데모 모드")

    def arm_live(self):
        text, ok = QInputDialog.getText(
            self,
            "실전매매 1차 잠금 해제",
            "실제 계좌에 주문이 전송될 수 있습니다. 이해했다면 LIVE 를 입력하세요.",
        )
        if ok and text.strip().upper() == "LIVE":
            self.real_armed = True
            self.live_auto_confirmed_session = False
            QMessageBox.warning(self, "실전 잠금 해제", "실전 주문 잠금이 해제됐습니다. 자동매매는 추가 확인 입력 없이 시작됩니다.")
        else:
            self.real_armed = False
            self.live_auto_confirmed_session = False

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
            self.real_armed = False
            self.live_auto_confirmed_session = False
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

    def _puma_condition_rows(self) -> list[tuple[str, str]]:
        # 자동 단타 후보는 지정된 7개 검색기의 합집합이다.
        # 특정 하나(예: 단타1)에 고정하지 않는다.
        return select_puma_conditions(self.condition_list, PUMA_DANTA_CONDITION_NAMES)

    def refresh_conditions(self, after_action: str = ""):
        broker = self._require_kiwoom()
        if broker is None:
            return

        if after_action:
            self.condition_pending_action = str(after_action)

        if self.condition_list_thread and self.condition_list_thread.isRunning():
            self.condition_status.setText("조건식 목록 조회 중... 완료되면 자동으로 계속합니다.")
            return

        self.condition_status.setText("조건식 목록 조회 중...")
        self.condition_refresh_btn.setEnabled(False)
        self.condition_start_btn.setEnabled(False)
        self.manual_condition_view_btn.setEnabled(False)

        thread = ConditionListThread(broker.token, broker.real, self)
        thread.loaded.connect(self._on_condition_list_loaded)
        thread.error.connect(self._on_condition_list_error)
        thread.finished.connect(lambda: self.condition_refresh_btn.setEnabled(True))
        self.condition_list_thread = thread
        thread.start()

    def _apply_condition_list(self, rows):
        rows = list(rows or [])
        self.condition_list = rows

        current = self.condition_combo.currentData()
        current_seq = str(current[0]) if isinstance(current, tuple) and len(current) == 2 else ""

        self.condition_combo.blockSignals(True)
        self.condition_combo.clear()
        self.condition_combo.addItem("조건식을 선택하세요", None)
        for seq, name in rows:
            self.condition_combo.addItem(f"[{seq}] {name}", (seq, name))

        restore = current_seq or str(self.settings.hero_condition_seq or "").strip()
        restored = False
        if restore and "," not in restore:
            for i in range(1, self.condition_combo.count()):
                data = self.condition_combo.itemData(i)
                if data and str(data[0]) == restore:
                    self.condition_combo.setCurrentIndex(i)
                    restored = True
                    break
        if not restored:
            self.condition_combo.setCurrentIndex(0)
        self.condition_combo.blockSignals(False)

        matched = select_puma_conditions(rows, PUMA_DANTA_CONDITION_NAMES)
        found = {normalize_condition_name(name) for _, name in matched}
        missing = [
            name for name in PUMA_DANTA_CONDITION_NAMES
            if normalize_condition_name(name) not in found
        ]
        text = f"저장 조건식 {len(rows)}개 · 단타 자동 검색기 {len(matched)}/{len(PUMA_DANTA_CONDITION_NAMES)}개 확인"
        if missing:
            text += " · 미확인: " + ", ".join(missing)
        self.condition_status.setText(text)

    def _on_condition_list_loaded(self, rows):
        self.condition_list_thread = None
        self.condition_refresh_btn.setEnabled(True)
        self.condition_start_btn.setEnabled(True)
        self.manual_condition_view_btn.setEnabled(True)
        self._apply_condition_list(rows)

        if not rows:
            self.condition_pending_action = ""
            QMessageBox.information(self, "조건식 없음", "영웅문4 [0150]에서 사용자 조건식을 저장한 뒤 다시 불러오세요.")
            return

        action = self.condition_pending_action
        self.condition_pending_action = ""
        if action == "auto":
            QTimer.singleShot(0, self.start_condition_stream)
        elif action == "manual":
            QTimer.singleShot(0, self.start_manual_condition_preview)

    def _on_condition_list_error(self, text: str):
        self.condition_list_thread = None
        self.condition_pending_action = ""
        self.condition_refresh_btn.setEnabled(True)
        self.condition_start_btn.setEnabled(True)
        self.manual_condition_view_btn.setEnabled(True)
        self.condition_status.setText("조건식 조회 실패")
        QMessageBox.critical(self, "조건식 조회 실패", str(text))

    def start_manual_condition_preview(self):
        broker = self._require_kiwoom()
        if broker is None:
            return
        if not self.condition_list:
            self.refresh_conditions("manual")
            return

        data = self.condition_combo.currentData()
        if not (isinstance(data, tuple) and len(data) == 2):
            QMessageBox.information(self, "조건식 선택", "확인할 조건식을 선택하세요.")
            return
        seq, name = str(data[0]), str(data[1])

        # 같은 조건식이 이미 정상 감시 중이면 재연결하지 않는다.
        running = self.manual_condition_thread
        if (
            running is not None
            and running.isRunning()
            and self.manual_condition_seq == seq
            and self.manual_condition_name == name
        ):
            self.manual_condition_status.setText(
                f"{name} · 현재 {len(self.manual_condition_rows)}종목 · 이미 조회 중"
            )
            return

        self.stop_manual_condition_preview(update_status=False)
        self.manual_condition_generation += 1
        generation = self.manual_condition_generation
        self.manual_condition_seq = seq
        self.manual_condition_name = name
        self.manual_condition_rows.clear()
        self.manual_condition_table.setRowCount(0)
        self.manual_condition_status.setText(f"[{seq}] {name} · 현재 종목 불러오는 중...")
        self.manual_condition_view_btn.setEnabled(False)

        thread = ConditionStreamThread(broker.token, broker.real, seq, self)
        thread.status.connect(
            lambda text, g=generation, n=name:
                self._manual_status_if_current(g, f"{n} · {text}")
        )
        thread.error.connect(
            lambda text, g=generation, n=name:
                self._manual_error_if_current(g, n, text)
        )
        thread.snapshot.connect(
            lambda rows, g=generation:
                self._manual_snapshot_if_current(g, rows)
        )
        thread.entered.connect(
            lambda code, stock_name, g=generation:
                self._manual_enter_if_current(g, code, stock_name)
        )
        thread.exited.connect(
            lambda code, g=generation:
                self._manual_exit_if_current(g, code)
        )
        thread.finished.connect(
            lambda g=generation:
                self._manual_finished_if_current(g)
        )
        self.manual_condition_thread = thread
        thread.start()

    def _manual_status_if_current(self, generation: int, text: str):
        if generation != self.manual_condition_generation:
            return
        self.manual_condition_status.setText(text)

    def _manual_error_if_current(self, generation: int, name: str, text: str):
        if generation != self.manual_condition_generation:
            return
        self.manual_condition_view_btn.setEnabled(True)
        self.manual_condition_status.setText(f"{name} · 오류: {text}")

    def _manual_snapshot_if_current(self, generation: int, rows):
        if generation != self.manual_condition_generation:
            return
        self.on_manual_condition_snapshot(rows)
        self.manual_condition_view_btn.setEnabled(True)

    def _manual_enter_if_current(self, generation: int, code: str, name: str):
        if generation == self.manual_condition_generation:
            self.on_manual_condition_enter(code, name)

    def _manual_exit_if_current(self, generation: int, code: str):
        if generation == self.manual_condition_generation:
            self.on_manual_condition_exit(code)

    def _manual_finished_if_current(self, generation: int):
        if generation != self.manual_condition_generation:
            return
        self.manual_condition_thread = None
        self.manual_condition_view_btn.setEnabled(True)

    def stop_manual_condition_preview(self, update_status: bool = True):
        self.manual_condition_generation += 1
        thread = self.manual_condition_thread
        self.manual_condition_thread = None
        if thread is not None:
            thread.stop()
            # GUI를 기다리게 하지 않는다. 늦게 오는 신호는 generation으로 무시한다.
            thread.finished.connect(thread.deleteLater)
        if hasattr(self, "manual_condition_view_btn"):
            self.manual_condition_view_btn.setEnabled(True)
        if update_status and hasattr(self, "manual_condition_status") and self.manual_condition_name:
            self.manual_condition_status.setText(f"{self.manual_condition_name} · 조회 중지")

    def _upsert_manual_condition_row(self, code: str, name: str = "", status: str = "편입"):
        code = str(code or "").strip()
        if not code:
            return
        resolved = str(name or self.name_cache.get(code) or code).strip()
        self.manual_condition_rows[code] = resolved
        row = None
        for r in range(self.manual_condition_table.rowCount()):
            cell = self.manual_condition_table.item(r, 0)
            if cell and cell.text() == code:
                row = r
                break
        if row is None:
            row = self.manual_condition_table.rowCount()
            self.manual_condition_table.insertRow(row)
            for c in range(3):
                self.manual_condition_table.setItem(row, c, QTableWidgetItem(""))
        self.manual_condition_table.item(row, 0).setText(code)
        self.manual_condition_table.item(row, 1).setText(resolved if resolved != code else "종목명 조회중…")
        self.manual_condition_table.item(row, 2).setText(status)
        if not name or name == code:
            self._queue_name_lookup(code)

    def on_manual_condition_snapshot(self, rows):
        # 초기 결과는 행별 insert/검색을 반복하지 않고 한 번에 채운다.
        rows = list(rows or [])
        self.manual_condition_rows.clear()
        self.manual_condition_table.setUpdatesEnabled(False)
        try:
            self.manual_condition_table.setRowCount(len(rows))
            for row, (code, name) in enumerate(rows):
                code = str(code or "").strip()
                if not code:
                    continue
                resolved = str(name or self.name_cache.get(code) or code).strip()
                self.manual_condition_rows[code] = resolved
                self.manual_condition_table.setItem(row, 0, QTableWidgetItem(code))
                self.manual_condition_table.setItem(
                    row, 1, QTableWidgetItem(resolved if resolved != code else "종목명 조회중…")
                )
                self.manual_condition_table.setItem(row, 2, QTableWidgetItem("편입"))
                if not name or name == code:
                    self._queue_name_lookup(code)
        finally:
            self.manual_condition_table.setUpdatesEnabled(True)
            self.manual_condition_table.viewport().update()

        self.manual_condition_status.setText(
            f"{self.manual_condition_name} · 현재 {len(self.manual_condition_rows)}종목"
        )
        if self._manual_import_after_snapshot:
            self._manual_import_after_snapshot = False
            self._import_manual_rows_to_candidates()

    def on_manual_condition_enter(self, code: str, name: str):
        self._upsert_manual_condition_row(code, name, "신규편입")
        self.manual_condition_status.setText(
            f"{self.manual_condition_name} · 현재 {len(self.manual_condition_rows)}종목"
        )

    def on_manual_condition_exit(self, code: str):
        code = str(code or "").strip()
        self.manual_condition_rows.pop(code, None)
        for r in range(self.manual_condition_table.rowCount() - 1, -1, -1):
            cell = self.manual_condition_table.item(r, 0)
            if cell and cell.text() == code:
                self.manual_condition_table.removeRow(r)
                break
        self.manual_condition_status.setText(
            f"{self.manual_condition_name} · 현재 {len(self.manual_condition_rows)}종목"
        )

    def _manual_condition_row_clicked(self, row: int, column: int):
        cell = self.manual_condition_table.item(row, 0)
        if not cell:
            return
        code = cell.text().strip()
        name_cell = self.manual_condition_table.item(row, 1)
        name = name_cell.text().strip() if name_cell else code
        self.open_focus_stock(code, code if "조회중" in name else name)

    def import_selected_condition_to_focus(self):
        data = self.condition_combo.currentData()
        if not (isinstance(data, tuple) and len(data) == 2):
            QMessageBox.information(self, "조건식 선택", "편입할 조건식을 먼저 선택하세요.")
            return

        seq, name = str(data[0]), str(data[1])
        same_loaded = (
            self.manual_condition_seq == seq
            and self.manual_condition_name == name
            and bool(self.manual_condition_rows)
        )
        if same_loaded:
            self._import_manual_rows_to_candidates()
            return

        self._manual_import_after_snapshot = True
        self.start_manual_condition_preview()

    def _import_manual_rows_to_candidates(self):
        if not self.manual_condition_rows:
            QMessageBox.information(self, "편입할 종목 없음", "선택 조건식의 현재 검색 결과가 없습니다.")
            return

        seq = str(self.manual_condition_seq or "").strip()
        name = str(self.manual_condition_name or "수동 조건식").strip()
        if not seq:
            QMessageBox.warning(self, "조건식", "조건식 번호를 확인할 수 없습니다.")
            return

        source_seq = f"MANUAL:{seq}"
        now = datetime.now().strftime("%H:%M:%S")
        added = 0

        for code, stock_name in list(self.manual_condition_rows.items()):
            code = str(code or "").strip()
            if not code:
                continue

            # 사용자가 다시 편입하면 이전 수동 제외를 해제한다.
            self.session_excluded_codes.discard(code)

            item = update_candidate_source(
                self.condition_candidates,
                seq=source_seq,
                condition_name=f"수동 · {name}",
                code=code,
                stock_name=stock_name or self.name_cache.get(code) or code,
                active=True,
                entry_event=False,
                now=now,
            )
            item["manual_pinned"] = True
            self._upsert_condition_row(code)
            self._ensure_market_row(code, item.get("name", code), "수동조건")
            if not stock_name or stock_name == code:
                self._queue_name_lookup(code)
            self._queue_candidate_classification(code)
            added += 1

        self._refresh_focus_candidate_count()
        self.log("HERO4", "MANUAL IN", "-", f"{name} · {added}종목 종합 트레이딩 편입")
        self.manual_condition_status.setText(f"{name} · {added}종목 종합 트레이딩 편입 완료")
        if self.engine.enabled and added:
            QTimer.singleShot(0, self.scan_one)

    def _candidate_has_manual_source(self, item: dict) -> bool:
        for seq, src in (item.get("sources") or {}).items():
            if str(seq).startswith("MANUAL:") and src.get("active"):
                return True
        return False

    def _candidate_source_counts(self, item: dict) -> tuple[int, int]:
        auto_count = 0
        manual_count = 0
        for seq, src in (item.get("sources") or {}).items():
            if not src.get("active"):
                continue
            if str(seq).startswith("MANUAL:"):
                manual_count += 1
            else:
                auto_count += 1
        return auto_count, manual_count

    def _remove_code_from_table(self, table: QTableWidget, code: str):
        for row in range(table.rowCount() - 1, -1, -1):
            cell = table.item(row, 0)
            if cell and cell.text().strip() == code:
                table.removeRow(row)

    def _candidate_in_danta_feed(self, item: dict) -> bool:
        if not item or not item.get("active"):
            return False
        for source_seq, src in (item.get("sources") or {}).items():
            if not src.get("active"):
                continue
            if str(source_seq).startswith("MANUAL:"):
                continue
            if is_puma_danta_condition(str(src.get("name") or "")):
                return True
        return False

    def _focus_filter_accepts(self, item: dict, key: str | None = None) -> bool:
        if not item or not item.get("active"):
            return False
        key = str(key or getattr(self, "focus_candidate_filter", "all"))
        if key == "all":
            return True

        buckets = source_display_buckets(
            item.get("scores"),
            danta_source=self._candidate_in_danta_feed(item),
            threshold=55,
        )
        return key in buckets

    def _focus_status_text(self, item: dict) -> str:
        auto_count, manual_count = self._candidate_source_counts(item)
        if not item.get("active"):
            return "이탈"
        if self._candidate_in_danta_feed(item):
            scores = dict(item.get("scores") or {})
            dscore = int(scores.get("danta", 0) or 0)
            puma = f"PUMA {dscore}점" if scores else "PUMA 분석중"
            overlap = f"{auto_count}식" if auto_count > 1 else "1식"
            return f"단타검색 {overlap} · {puma}"
        if auto_count and manual_count:
            return f"자동 {auto_count}식 + 수동"
        if manual_count:
            return "수동편입"
        return f"편입 · {auto_count}식" if auto_count > 1 else "편입"

    def _refresh_focus_candidate_count(self):
        if not hasattr(self, "focus_filter_buttons"):
            return
        counts = {"all": 0, "danta": 0, "swing": 0, "bowl": 0}
        for code, item in self.condition_candidates.items():
            if code in self.session_excluded_codes or not item.get("active"):
                continue
            counts["all"] += 1
            buckets = source_display_buckets(
                item.get("scores"),
                danta_source=self._candidate_in_danta_feed(item),
                threshold=55,
            )
            for key in buckets:
                counts[key] += 1

        titles = {"all": "전체", "danta": "단타", "swing": "스윙", "bowl": "중장기"}
        for key, btn in self.focus_filter_buttons.items():
            btn.setText(titles[key])
            btn.setToolTip(f"{titles[key]} {counts[key]}종목")

        current = str(getattr(self, "focus_candidate_filter", "all"))
        if hasattr(self, "focus_candidate_count"):
            self.focus_candidate_count.setText(f"{titles.get(current, '전체')} {counts.get(current, 0)}종목")

    def _set_focus_candidate_filter(self, key: str):
        key = key if key in ("all", "danta", "swing", "bowl") else "all"
        self.focus_candidate_filter = key
        for button_key, btn in self.focus_filter_buttons.items():
            btn.blockSignals(True)
            btn.setChecked(button_key == key)
            btn.blockSignals(False)
        self._refresh_focus_candidate_table()

    def _refresh_focus_candidate_table(self):
        if not hasattr(self, "focus_condition_table"):
            return
        selected_code = ""
        row = self.focus_condition_table.currentRow()
        if row >= 0:
            cell = self.focus_condition_table.item(row, 0)
            selected_code = cell.text().strip() if cell else ""

        self.focus_condition_table.setRowCount(0)
        for code, item in self.condition_candidates.items():
            if code in self.session_excluded_codes:
                continue
            if not self._focus_filter_accepts(item):
                continue
            self._upsert_focus_candidate_row(code, refresh_count=False)

        if selected_code:
            for r in range(self.focus_condition_table.rowCount()):
                cell = self.focus_condition_table.item(r, 0)
                if cell and cell.text().strip() == selected_code:
                    self.focus_condition_table.selectRow(r)
                    break
        self._refresh_focus_candidate_count()

    def _upsert_focus_candidate_row(self, code: str, refresh_count: bool = True):
        if not hasattr(self, "focus_condition_table"):
            return
        item = self.condition_candidates.get(code, {})
        row = None
        for r in range(self.focus_condition_table.rowCount()):
            cell = self.focus_condition_table.item(r, 0)
            if cell and cell.text().strip() == code:
                row = r
                break

        visible = (
            code not in self.session_excluded_codes
            and self._focus_filter_accepts(item)
        )
        if not visible:
            if row is not None:
                self.focus_condition_table.removeRow(row)
            if refresh_count:
                self._refresh_focus_candidate_count()
            return

        if row is None:
            row = self.focus_condition_table.rowCount()
            self.focus_condition_table.insertRow(row)
            for col in range(3):
                self.focus_condition_table.setItem(row, col, QTableWidgetItem(""))

        display_name = str(item.get("name", "") or "").strip()
        readable_name = display_name if display_name and display_name != code else "종목명 조회중…"
        detail = str(item.get("class_detail") or "-")
        status_text = self._focus_status_text(item)

        self.focus_condition_table.item(row, 0).setText(code)
        name_cell = self.focus_condition_table.item(row, 1)
        name_cell.setText(readable_name)
        name_cell.setToolTip(readable_name)
        name_cell.setFont(QFont("Malgun Gothic", 10, QFont.Bold))
        name_cell.setForeground(QColor("#f3f8ff"))
        self.focus_condition_table.item(row, 2).setText(status_text)
        self.focus_condition_table.item(row, 2).setToolTip(detail)

        if refresh_count:
            self._refresh_focus_candidate_count()

    def delete_selected_focus_candidate(self):
        table = getattr(self, "focus_condition_table", None)
        if table is None or table.currentRow() < 0:
            QMessageBox.information(self, "선택 삭제", "삭제할 종목을 먼저 선택하세요.")
            return
        row = table.currentRow()
        cell = table.item(row, 0)
        if not cell:
            return
        code = cell.text().strip()
        if not code:
            return

        if code in self.engine.positions or code in self.engine.pending_orders:
            QMessageBox.warning(
                self,
                "삭제 불가",
                "보유 중이거나 주문 처리 중인 종목은 청산/체결 감시 때문에 삭제할 수 없습니다."
            )
            return

        name = self.condition_candidates.get(code, {}).get("name", code)
        self.session_excluded_codes.add(code)
        self.classification_queue = [x for x in self.classification_queue if x != code]

        if hasattr(self, "focus_condition_table"):
            self._remove_code_from_table(self.focus_condition_table, code)
        if hasattr(self, "condition_table"):
            self._remove_code_from_table(self.condition_table, code)

        self._refresh_focus_candidate_count()
        self.log(name, "CANDIDATE DEL", "-", "사용자 삭제 · 현재 세션 신규 자동매매 후보 제외")

        if self.selected_code == code:
            self.focus_origin.setText(f"{name} · 후보에서 삭제됨")

    def start_condition_stream(self):
        broker = self._require_kiwoom()
        if broker is None:
            return
        if not self.condition_list:
            self.refresh_conditions("auto")
            return

        running = self.condition_thread
        if running is not None and running.isRunning():
            self._update_condition_union_status()
            self.condition_status.setText(self.condition_status.text() + " · 이미 실행 중")
            return

        rows = self._puma_condition_rows()
        if not rows:
            QMessageBox.information(
                self,
                "단타 검색기 없음",
                "지정한 단타 검색기 7개를 영웅문4 조건검색에 저장한 뒤 목록을 다시 불러오세요.",
            )
            return
        if len(rows) > 10:
            QMessageBox.warning(self, "조건식 제한", "키움 실시간 조건검색은 한 세션에서 최대 10개까지 사용합니다.")
            rows = rows[:10]

        # 이전 스레드가 종료 중이어도 UI에서 기다리지 않는다.
        self.stop_condition_stream(update_status=False, block=False)
        self.condition_snapshot_seen.clear()
        self.condition_live_registered_count = 0
        self.condition_start_btn.setEnabled(False)

        self.settings.hero_condition_names = [name for _, name in rows]
        self.settings.hero_condition_seq = ",".join(seq for seq, _ in rows)
        self.settings.hero_condition_name = " + ".join(name for _, name in rows)
        save_strategy(self.settings)

        thread = MultiConditionStreamThread(broker.token, broker.real, rows, self)
        thread.status.connect(
            lambda text, t=thread:
                self.on_condition_status(text) if self.condition_thread is t else None
        )
        thread.error.connect(
            lambda text, t=thread:
                self.on_condition_error(text) if self.condition_thread is t else None
        )
        thread.initial_union.connect(
            lambda payload, t=thread:
                self.on_condition_initial_union(payload) if self.condition_thread is t else None
        )
        thread.snapshot.connect(
            lambda seq, name, result_rows, t=thread:
                self.on_condition_snapshot(seq, name, result_rows) if self.condition_thread is t else None
        )
        thread.entered.connect(
            lambda seq, name, code, stock_name, t=thread:
                self.on_condition_enter(seq, name, code, stock_name) if self.condition_thread is t else None
        )
        thread.exited.connect(
            lambda seq, name, code, t=thread:
                self.on_condition_exit(seq, name, code) if self.condition_thread is t else None
        )
        thread.finished.connect(
            lambda t=thread:
                self._condition_thread_finished(t)
        )
        self.condition_thread = thread
        thread.start()

        self.condition_status.setText(
            f"단타 검색기 {len(rows)}개 · 초기 합집합 만드는 중... 기존 목록은 완료될 때까지 유지"
        )

    def _condition_thread_finished(self, thread):
        if self.condition_thread is thread:
            self.condition_thread = None
            self.condition_start_btn.setEnabled(True)
        thread.deleteLater()

    def stop_condition_stream(self, update_status: bool = True, block: bool = False):
        thread = self.condition_thread
        self.condition_thread = None
        if thread is not None:
            thread.stop()
            if block:
                thread.wait(2500)
                thread.deleteLater()
            else:
                thread.finished.connect(thread.deleteLater)
        if hasattr(self, "condition_start_btn"):
            self.condition_start_btn.setEnabled(True)
        if update_status and hasattr(self, "condition_status"):
            self.condition_status.setText("조건검색 중지")

    def on_condition_initial_union(self, payload):
        """Atomically replace automatic candidates after all initial searches finish."""
        entries = list(payload or [])
        now = datetime.now().strftime("%H:%M:%S")

        # 성공한 자동 검색기는 새 결과로 교체한다.
        # 단, 키움의 일시적 timeout/오류로 초기조회에 실패한 검색기는
        # 직전 정상 활성 후보를 버리지 않는다. 수동 고정 종목은 항상 유지한다.
        successful = {
            str(entry.get("seq") or "").strip()
            for entry in entries
            if isinstance(entry, dict) and entry.get("ok")
        }
        failed = {
            str(entry.get("seq") or "").strip()
            for entry in entries
            if isinstance(entry, dict) and not entry.get("ok")
        }

        new_candidates: dict[str, dict] = {}
        for code, old_item in self.condition_candidates.items():
            for source_seq, src in (old_item.get("sources") or {}).items():
                source_seq = str(source_seq)
                is_manual = source_seq.startswith("MANUAL:")
                keep_failed_auto = source_seq in failed and src.get("active")
                if not ((is_manual and src.get("active")) or keep_failed_auto):
                    continue

                item = update_candidate_source(
                    new_candidates,
                    seq=source_seq,
                    condition_name=str(src.get("name") or ("수동 조건식" if is_manual else source_seq)),
                    code=code,
                    stock_name=str(old_item.get("name") or self.name_cache.get(code) or code),
                    active=True,
                    entry_event=False,
                    now=str(src.get("entered_at") or now),
                )
                if is_manual:
                    item["manual_pinned"] = True

        for entry in entries:
            if not isinstance(entry, dict):
                continue
            seq = str(entry.get("seq") or "").strip()
            condition_name = str(entry.get("name") or seq)

            # 실패 응답에 일부 페이지 결과가 남아 있으면 기존 fallback과 합쳐 둔다.
            # 이후 실시간 I/D 이벤트가 상태를 계속 보정한다.
            for code, stock_name in entry.get("rows") or []:
                update_candidate_source(
                    new_candidates,
                    seq=seq,
                    condition_name=condition_name,
                    code=code,
                    stock_name=stock_name or self.name_cache.get(code) or code,
                    active=True,
                    entry_event=False,
                    now=now,
                )

        self.condition_candidates = new_candidates
        self.condition_snapshot_seen = successful
        self.classification_queue.clear()

        tables = [getattr(self, "condition_table", None), getattr(self, "focus_condition_table", None)]
        for table in tables:
            if table is not None:
                table.setUpdatesEnabled(False)
                table.setRowCount(0)

        unresolved_names = []
        classify_codes = []
        try:
            for code, item in self.condition_candidates.items():
                self._upsert_condition_row(code, refresh_focus_count=False)
                self._ensure_market_row(code, item.get("name", code), "영웅문4")
                if not item.get("name") or item.get("name") == code:
                    unresolved_names.append(code)
                if code not in self.session_excluded_codes:
                    classify_codes.append(code)
        finally:
            for table in tables:
                if table is not None:
                    table.setUpdatesEnabled(True)
                    table.viewport().update()

        self._refresh_focus_candidate_count()

        # 렌더링을 먼저 끝낸 뒤 이름조회/차트분석을 백그라운드 큐에 넣는다.
        for code in unresolved_names:
            if code not in self.name_cache and code not in self.name_lookup_queue:
                self.name_lookup_queue.append(code)
        if unresolved_names and not self.name_lookup_timer.isActive():
            self.name_lookup_timer.start()
            QTimer.singleShot(0, self._resolve_next_name)

        for code in classify_codes:
            if code not in self.classification_queue:
                self.classification_queue.append(code)
        QTimer.singleShot(0, self._start_next_candidate_classification)
        self.condition_start_btn.setEnabled(False)
        self._update_condition_union_status()

        if self.engine.enabled and self.condition_candidates:
            QTimer.singleShot(0, self.scan_one)

    def _update_condition_union_status(self):
        if not hasattr(self, "condition_status"):
            return
        configured = self._puma_condition_rows()
        active_union = sum(
            1 for item in self.condition_candidates.values()
            if item.get("active") and self._candidate_in_danta_feed(item)
        )
        received = len(getattr(self, "condition_snapshot_seen", set()))
        total = len(configured)
        live_registered = int(getattr(self, "condition_live_registered_count", 0) or 0)
        self.condition_status.setText(
            f"단타 검색기 통합 · 초기통합 {received}/{total} · 실시간 {live_registered}/{total} · 합집합 {active_union}종목"
        )

    def on_condition_status(self, text: str):
        m = re.search(r"실시간 등록 완료\s*·\s*전체\s*(\d+)/(\d+)", str(text or ""))
        if m:
            self.condition_live_registered_count = max(
                int(getattr(self, "condition_live_registered_count", 0) or 0),
                int(m.group(1)),
            )
        self._update_condition_union_status()
        self.log("HERO4", "COND", "-", text)

    def on_condition_error(self, text: str):
        self.condition_status.setText("오류: " + text)
        self.log("HERO4", "ERROR", "-", text)

    def on_condition_snapshot(self, seq: str, condition_name: str, rows):
        # 실시간 등록 응답의 누락분만 추가한다. 초기통합 카운트는 initial_union에서만 확정한다.
        now = datetime.now().strftime("%H:%M:%S")
        for code, name in rows:
            item = update_candidate_source(
                self.condition_candidates,
                seq=seq,
                condition_name=condition_name,
                code=code,
                stock_name=name or code,
                active=True,
                entry_event=False,
                now=now,
            )
            self._upsert_condition_row(code)
            self._ensure_market_row(code, item.get("name", code), "영웅문4")
            if not name or name == code:
                self._queue_name_lookup(code)
            self._queue_candidate_classification(code)
        self._update_condition_union_status()
        if self.engine.enabled and rows:
            QTimer.singleShot(0, self.scan_one)

    def on_condition_enter(self, seq: str, condition_name: str, code: str, name: str):
        now = datetime.now().strftime("%H:%M:%S")
        old_name = self.condition_candidates.get(code, {}).get("name", "")
        item = update_candidate_source(
            self.condition_candidates,
            seq=seq,
            condition_name=condition_name,
            code=code,
            stock_name=name or old_name or code,
            active=True,
            entry_event=True,
            now=now,
        )
        self._upsert_condition_row(code)
        self._ensure_market_row(code, item.get("name", code), "영웅문4")
        if not name or name == code:
            self._queue_name_lookup(code)
        self._queue_candidate_classification(code)
        self.log(
            item.get("name", code),
            "COND IN",
            "-",
            f"{condition_name} 신규 편입 · 현재 활성 검색기 {item.get('source_count', 1)}개",
        )
        self._update_condition_union_status()
        if self.engine.enabled:
            QTimer.singleShot(0, self.scan_one)

    def on_condition_exit(self, seq: str, condition_name: str, code: str):
        now = datetime.now().strftime("%H:%M:%S")
        item = update_candidate_source(
            self.condition_candidates,
            seq=seq,
            condition_name=condition_name,
            code=code,
            stock_name=self.condition_candidates.get(code, {}).get("name", code),
            active=False,
            entry_event=False,
            now=now,
        )
        self._upsert_condition_row(code)
        if code in self.row_by_code:
            r = self.row_by_code[code]
            self.market_table.item(r, 2).setText(self._source_for_code(code))
            if not item.get("active") and code not in self.engine.positions:
                self.market_table.item(r, 4).setText("조건이탈")
        self.log(
            item.get("name", code),
            "COND OUT",
            "-",
            f"{condition_name} 이탈 · 남은 활성 검색기 {item.get('source_count', 0)}개",
        )
        self._update_condition_union_status()

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
        if not code or code in self.session_excluded_codes or code in self.classification_queue:
            return
        if not isinstance(self.broker, KiwoomRestBroker) or not self.broker.token:
            return
        if self.classification_thread is not None and self.classification_thread.isRunning():
            if getattr(self.classification_thread, "code", "") == code:
                return
        self.classification_queue.append(code)
        if DEVICE_PROFILE.low_power:
            QTimer.singleShot(DEVICE_PROFILE.background_delay_ms, self._start_next_candidate_classification)
        else:
            self._start_next_candidate_classification()

    def _start_next_candidate_classification(self):
        if self._closing or self._focus_readers or self.focus_analysis_thread is not None:
            return
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
                self._swing_settings_from_ui(),
                self.bowl_settings,
                self,
            )
            key = self._focus_view_key(code)
            worker.context_key = key[:3] + ("",) + key[4:]
            worker.resultReady.connect(self._on_candidate_classified)
            worker.finished.connect(self._candidate_classifier_finished)
            self.classification_thread = worker
            worker.start()
            return

    def _on_candidate_classified(self, code: str, payload: object):
        data = payload if isinstance(payload, dict) else {}
        # CandidateClassifier intentionally uses only a short daily sample for
        # background list classification. Never cache that partial sample as
        # the visual chart/arrow result: EMA112/224/448 and BB40 crossings can
        # shift when the full adjusted-price history arrives (especially around
        # splits/consolidations such as Signetics 2026-08).
        prepared = data.get("prepared")
        resolved_name = str(data.get("name") or "").strip()
        if resolved_name and resolved_name != code:
            self.name_cache[code] = resolved_name
            item = self.condition_candidates.get(code)
            if item is not None:
                item["name"] = resolved_name
        scores = {
            "danta": int(data.get("danta", 0) or 0),
            "swing": int(data.get("swing", 0) or 0),
            "bowl": int(data.get("bowl", 0) or 0),
        }
        item = self.condition_candidates.get(code, {})
        if self._candidate_in_danta_feed(item):
            label = "단타"
            detail = (
                f"단타 검색기 통합후보 · PUMA 단타 {scores['danta']}/100 · "
                "스윙/밥3 점수는 목록 분류에 사용하지 않음"
            )
        else:
            # 비단타 후보만 스윙/중장기 분류에 사용한다.
            label, detail = classify_scores(0, scores["swing"], scores["bowl"])
        self._set_candidate_classification(code, label, detail, scores)

    def _candidate_classifier_finished(self):
        worker = self.sender()
        if self.classification_thread is worker:
            self.classification_thread = None
        if worker is not None:
            worker.deleteLater()
        if not self._closing:
            QTimer.singleShot(DEVICE_PROFILE.background_delay_ms, self._start_next_candidate_classification)

    def _upsert_condition_row(self, code: str, refresh_focus_count: bool = True):
        item = self.condition_candidates.get(code, {})

        if (
            not item.get("active")
            and code not in self.engine.positions
            and code not in self.engine.pending_orders
        ):
            if hasattr(self, "condition_table"):
                self._remove_code_from_table(self.condition_table, code)
            if hasattr(self, "focus_condition_table"):
                self._remove_code_from_table(self.focus_condition_table, code)
                self._refresh_focus_candidate_count()
            return

        if code in self.session_excluded_codes and code not in self.engine.positions and code not in self.engine.pending_orders:
            if hasattr(self, "condition_table"):
                self._remove_code_from_table(self.condition_table, code)
            if hasattr(self, "focus_condition_table"):
                self._remove_code_from_table(self.focus_condition_table, code)
                self._refresh_focus_candidate_count()
            return
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
        status_text = self._focus_status_text(item)
        self.condition_table.item(row, 3).setText(status_text)
        self.condition_table.item(row, 4).setText(item.get("entered_at", "-"))
        self.condition_table.item(row, 5).setText("▶ 클릭해서 열기")
        self.condition_table.item(row, 5).setForeground(QColor("#62b8ff"))

        if hasattr(self, "focus_condition_table"):
            self._upsert_focus_candidate_row(code, refresh_count=refresh_focus_count)

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
        if self._closing or self._name_worker is not None:
            return
        if self._focus_readers or self.focus_analysis_thread is not None or self.classification_thread is not None:
            return
        while self.name_lookup_queue and self.name_lookup_queue[0] in self.name_cache:
            self.name_lookup_queue.pop(0)
        if not self.name_lookup_queue:
            self.name_lookup_timer.stop()
            return
        if not isinstance(self.broker, KiwoomRestBroker) or not self.broker.token:
            self.name_lookup_queue.clear(); self.name_lookup_timer.stop(); return
        worker = NameLookupThread(self.broker, self.name_lookup_queue.pop(0), self)
        self._name_worker = worker
        worker.resolved.connect(self._name_resolved)
        worker.finished.connect(self._name_finished)
        worker.start()

    def _name_resolved(self, code, name):
        if self._closing or not name:
            return
        self.name_cache[code] = name
        item = self.condition_candidates.get(code)
        if item is not None:
            item['name'] = name
            self._upsert_condition_row(code)
        if code in self.manual_condition_rows:
            self._upsert_manual_condition_row(code, name, "편입")
        self._ensure_market_row(code, name, self._source_for_code(code))
        if self.selected_code == code:
            self.selected_name = name
            self.focus_title.setText(f"{name}  {code}")
            self._sync_selected_stock_everywhere()

    def _name_finished(self):
        worker = self.sender()
        if self._name_worker is worker:
            self._name_worker = None
        if worker is not None:
            worker.deleteLater()

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

    def _start_danta_background(self):
        if self._closing or not self.focus_minute_raw or self.focus_data_code != self.selected_code:
            return

        if self.danta_analysis_thread is not None and self.danta_analysis_thread.isRunning():
            self.danta_analysis_pending = True
            self.danta_analysis_thread.requestInterruption()
            return

        self.danta_analysis_pending = False
        tp = float(self.focus_tp.value()) if hasattr(self, "focus_tp") else float(self.settings.take_profit_pct)
        sl = abs(float(self.focus_sl.value())) if hasattr(self, "focus_sl") else abs(float(self.settings.stop_loss_pct))
        worker = DantaAnalysisThread(
            self.selected_code,
            self.focus_minute_raw,
            self.focus_daily_raw,
            self.intraday_selected_day or "",
            self.scan_start.time().toString("HH:mm"),
            self.scan_end.time().toString("HH:mm"),
            self._swing_settings_from_ui(),
            tp,
            sl,
            self,
        )
        worker.request_id = self._focus_request_id
        worker.revision = self._focus_revision
        worker.context_key = self._focus_view_key()
        self.danta_analysis_thread = worker
        worker.analyzed.connect(self._danta_background_ready)
        worker.failed.connect(self._danta_background_failed)
        worker.finished.connect(self._danta_background_finished)
        worker.start()

    def _danta_background_failed(self, message: str):
        if hasattr(self, "strategy_signal_label"):
            self.strategy_signal_label.setText(f"단타 분석 실패: {message}")

    def _danta_background_finished(self):
        worker = self.sender()
        if worker is not None:
            worker.deleteLater()
        self.danta_analysis_thread = None
        if not self._closing and self.danta_analysis_pending:
            self.danta_analysis_pending = False
            QTimer.singleShot(0, self._start_danta_background)

    def _danta_background_ready(self, payload: dict):
        if self._closing or payload.get("request_id") != self._focus_request_id:
            return
        if payload.get("revision") != self._focus_revision or payload.get("context_key") != self._focus_view_key():
            return
        if str(payload.get("code", "")) != self.selected_code:
            return
        if str(payload.get("target_day", "")) != (self.intraday_selected_day or ""):
            return

        result = payload.get("analysis")
        series = payload.get("series")
        day = payload.get("day") or ""
        if not result or not series:
            return

        self.focus_danta_analysis = result
        self.focus_danta_series = series
        self.danta_analysis = result
        self.danta_series = series

        label = self._pretty_intraday_day(day)
        if not self.intraday_selected_day:
            label = f"최신 {label}"
        self._apply_focus_analyses(result, self.focus_daily_analysis, self.focus_bowl_analysis, label)
        self._render_danta_from_focus_cache()
        if self.focus_chart_mode == "MIN":
            self._update_focus_chart(False)

    def _refresh_focus_danta_date(self):
        self._start_danta_background()

    def _render_danta_detail_from_cache(self):
        # Never recompute indicators on the GUI thread.
        if (
            self.focus_danta_analysis is not None
            and self.focus_danta_series is not None
            and not self.intraday_selected_day
        ):
            self._render_danta_from_focus_cache()
            return
        self._start_danta_background()


    def _enrich_setup_stats(self, analysis, series: dict, strategy: str):
        tp = float(self.focus_tp.value()) if hasattr(self, "focus_tp") else float(self.settings.take_profit_pct)
        sl = abs(float(self.focus_sl.value())) if hasattr(self, "focus_sl") else abs(float(self.settings.stop_loss_pct))
        return _enrich_analysis_pure(
            analysis, series, strategy, self.swing_settings, tp, sl
        )


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

    def open_danta_detail_window(self):
        if not self.selected_code:
            QMessageBox.information(self, "단타 상세분석", "조건검색 목록에서 종목을 먼저 선택하세요.")
            return
        self.strategy_widget.setWindowTitle(f"단타 상세분석 · {self.selected_name or self.selected_code} {self.selected_code}")
        self.strategy_widget.resize(1180, 820)
        self.strategy_widget.show()
        self.strategy_widget.raise_()
        self.strategy_widget.activateWindow()
        QTimer.singleShot(0, self.strategy_refresh_selected)

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
            if self.focus_danta_analysis is not None and not self.intraday_selected_day:
                self._render_danta_from_focus_cache()
            else:
                self._start_danta_background()
            return

        self._strategy_refresh_after_focus = True
        self.strategy_signal_label.setText("데이터를 백그라운드에서 불러오는 중...")
        self.focus_refresh()


    def open_focus_stock(self, code: str, name: str = ""):
        code = str(code).strip().replace('A', '')
        if not code:
            return
        self._click_started = time.perf_counter()
        self.focus_latency_ms = {}
        if hasattr(self, "focus_perf_label"):
            self.focus_perf_label.setText("성능: 측정 중")
        changed = code != self.selected_code
        self.selected_code = code
        self.selected_name = self.name_cache.get(code) or name or code
        if changed:
            self._focus_request_id += 1
            self.intraday_selected_day = ""
            self._clear_focus_display()
            for worker in self._focus_readers:
                worker.requestInterruption()
            for worker in (self.focus_analysis_thread, self.danta_analysis_thread, self._range_worker):
                if worker is not None:
                    worker.requestInterruption()
            self.focus_analysis_pending = None
            self._range_request_id += 1
            self._range_pending = None
        self.focus_title.setText(f"{self.selected_name}  {code}")
        self._sync_selected_stock_everywhere()
        self.tabs.setCurrentWidget(self.focus_widget)
        self.focus_refresh(force=False)

    def _clear_focus_display(self):
        self.focus_data_code = self.danta_cache_code = ""
        self.focus_daily_raw = []; self.focus_minute_raw = []
        self.danta_raw_daily = []; self.danta_raw_minute = []
        self.focus_daily_analysis = self.focus_bowl_analysis = self.focus_danta_analysis = None
        self.focus_daily_series = self.focus_bowl_series = self.focus_danta_series = None
        self.danta_analysis = self.danta_series = None
        self._preview_series = {}
        self._shown_daily_revision = ""
        self._focus_revision = ""
        self.focus_chart.set_data(None, {}, title=f"{self.selected_name} · 불러오는 중")
        self.focus_chart.clear_analysis_range()
        self.danta_chart.set_data(None, {}, title="불러오는 중")
        self.focus_price.setText("-")
        self.manual_current.setText("-")
        self.focus_stage.setText("선택 종목 분석 대기")
        for widget in (self.focus_danta_signal, self.focus_swing_signal, self.focus_bowl_signal):
            widget.setText("선택 종목 분석 중...")
        for mapping in (self.focus_danta_labels, self.focus_stage_labels, self.focus_bowl_labels):
            for label in mapping.values():
                label.setText("-")
        self.danta_details.setRowCount(0)
        self.danta_score_label.setText("-")
        self.danta_stage_label.setText("분석 중")
        self.strategy_signal_label.setText("선택 종목 분석 중")
        self._set_intraday_days_fast([])

    def _focus_view_key(self, code=None):
        return (id(self.broker), code or self.selected_code, int(self.focus_history_pages),
                self.intraday_selected_day or "", self.scan_start.time().toString("HH:mm"),
                self.scan_end.time().toString("HH:mm"), settings_key(self._swing_settings_from_ui()),
                settings_key(self.bowl_settings), float(self.focus_tp.value()), abs(float(self.focus_sl.value())))

    def focus_refresh(self, checked=False, *, force=True):
        if self._closing or not self.selected_code:
            return
        key = self._focus_view_key()
        for worker in self._focus_readers:
            if worker.isRunning() and worker.context_key == key and not worker.isInterruptionRequested():
                return
        self._focus_request_id += 1
        classifier = self.classification_thread
        if classifier is not None and classifier.isRunning():
            classifier.requestInterruption()
            if classifier.code != self.selected_code and classifier.code not in self.classification_queue:
                self.classification_queue.insert(0, classifier.code)
        self._focus_fetch_pending = False
        record = self._display_cache.get(key)
        if record:
            payload = record["payload"]
            self._apply_focus_metadata(payload)
            cached_result = {**record["result"], "request_id": self._focus_request_id, "cached": True}
            self._focus_analysis_ready(cached_result)
            age = max(0, time.time() - payload.get("loaded_at", 0))
            if not force and age <= 2 and payload.get("complete") and not payload.get("errors"):
                return
            stamp = datetime.fromtimestamp(payload.get("loaded_at", 0)).strftime("%H:%M:%S")
            self.focus_origin.setText(f"저장된 차트·분석 {stamp} 표시 · 최신 시세 갱신 중")
        else:
            self.focus_origin.setText("선택 종목 차트 우선 조회 중...")
        for reader in self._focus_readers:
            reader.requestInterruption()
        max_readers = 1 if DEVICE_PROFILE.low_power else 2
        if len(self._focus_readers) >= max_readers:
            self._focus_fetch_pending = True
            return
        worker = FocusDataThread(self.broker, self.selected_code, self.focus_history_pages, self,
                                 mode=self.focus_chart_mode, request_id=self._focus_request_id)
        worker.context_key = key
        self._focus_readers.add(worker)
        self.focus_load_thread = worker
        self.focus_loading_code = self.selected_code
        worker.preview.connect(self._focus_preview_ready)
        worker.loaded.connect(self._focus_load_ready)
        worker.failed.connect(self._focus_load_failed)
        worker.finished.connect(self._focus_load_finished)
        worker.start()

    def _focus_preview_ready(self, payload):
        if self._closing or payload.get("request_id") != self._focus_request_id or payload.get("code") != self.selected_code:
            return
        kind = payload.get("preview_kind")
        self._merge_fetch_timings(payload)
        self._record_focus_latency("preview_" + str(kind))
        candles = payload.get("preview_candles") or []
        self._preview_series[kind] = candles
        if (kind == "minute" and self.focus_chart_mode == "MIN") or (kind == "daily" and self.focus_chart_mode == "DAY"):
            # Keep completed cached indicators visible until a new analyzed result arrives.
            ready = self.focus_danta_series if kind == "minute" else self.focus_daily_series
            if candles and not ready:
                self.focus_chart.set_basic_data(candles, title=f"{self.selected_name} · 차트 선표시 / 분석 중")
                self._record_focus_latency("chart")
                self.focus_origin.setText("차트 표시 완료 · 지표·분석과 과거 데이터 갱신 중")

    def _record_focus_latency(self, stage, value=None):
        if not self._click_started:
            return
        if value is None:
            if stage in self.focus_latency_ms:
                return
            value = round((time.perf_counter() - self._click_started) * 1000, 2)
        self.focus_latency_ms[stage] = round(float(value), 2)
        self._refresh_focus_perf_label()

    def _focus_chart_painted(self, paint_ms: float):
        if not self._click_started:
            return
        series = getattr(self.focus_chart, "series", None) or {}
        if not series.get("candles"):
            return
        self.focus_latency_ms["paint_last_ms"] = round(float(paint_ms), 2)
        self.focus_latency_ms["paint_max_ms"] = round(max(
            float(self.focus_latency_ms.get("paint_max_ms", 0.0)),
            float(paint_ms),
        ), 2)
        if "first_paint" not in self.focus_latency_ms:
            self._record_focus_latency("first_paint")
        else:
            self._refresh_focus_perf_label()

    def _refresh_focus_perf_label(self):
        label = getattr(self, "focus_perf_label", None)
        if label is None:
            return
        m = self.focus_latency_ms
        parts = []
        if "first_paint" in m:
            parts.append(f"첫화면 {m['first_paint']:.0f}ms")
        if "daily_first_ms" in m:
            parts.append(f"일봉API {m['daily_first_ms']:.0f}ms")
        if "minute_first_ms" in m:
            parts.append(f"5분API {m['minute_first_ms']:.0f}ms")
        if "analysis_cpu_ms" in m:
            parts.append(f"분석 {m['analysis_cpu_ms']:.0f}ms")
        if "paint_last_ms" in m:
            parts.append(f"렌더 {m['paint_last_ms']:.0f}ms")
        if "complete" in m:
            parts.append(f"전체 {m['complete']:.0f}ms")
        label.setText("성능: " + (" / ".join(parts) if parts else "측정 중"))

    def _merge_fetch_timings(self, payload: dict):
        timings = payload.get("timings") or {}
        for key, value in timings.items():
            if isinstance(value, (int, float)):
                self.focus_latency_ms[key] = round(float(value), 2)
        elapsed = payload.get("fetch_elapsed_ms")
        if isinstance(elapsed, (int, float)):
            self.focus_latency_ms["fetch_elapsed_ms"] = round(float(elapsed), 2)
        self._refresh_focus_perf_label()

    def _schedule_focus_perf_log(self):
        rid = self._focus_request_id
        self._perf_log_scheduled_id = rid
        QTimer.singleShot(350, lambda rid=rid: self._flush_focus_perf_log(rid))

    def _flush_focus_perf_log(self, request_id: int):
        if request_id != self._perf_log_scheduled_id or request_id != self._focus_request_id:
            return
        try:
            root = Path(__file__).resolve().parent.parent
            logdir = root / "logs"
            logdir.mkdir(parents=True, exist_ok=True)
            record = {
                "time": datetime.now().isoformat(timespec="seconds"),
                "code": self.selected_code,
                "name": self.selected_name,
                "mode": self.focus_chart_mode,
                "device_low_power": bool(DEVICE_PROFILE.low_power),
                "metrics_ms": dict(self.focus_latency_ms),
            }
            with (logdir / "performance_log.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _focus_load_ready(self, payload):
        if self._closing or payload.get("request_id") != self._focus_request_id or payload.get("code") != self.selected_code:
            return
        self._merge_fetch_timings(payload)
        record = self._display_cache.get(self._focus_view_key())
        if not payload.get("complete") and record:
            # A cached full chart already provides instant feedback. Do not replace
            # its history with the short first page or recompute a reduced sample.
            self._apply_focus_metadata({**record["payload"], "info": payload.get("info") or {},
                                        "quote_at": payload.get("quote_at")})
            return
        if not payload.get("complete") and self.focus_chart_mode == "DAY":
            # Show candles immediately via preview, but never publish provisional
            # swing arrows from an incomplete history. EAVG112/224/448 and BB40
            # are history-sensitive, especially across corporate actions.
            self._apply_focus_metadata(payload)
            self.focus_origin.setText("차트 선표시 완료 · 수정주가 전체 일봉 수집 후 화살표 확정 계산 중")
            return
        self._start_focus_analysis(payload)

    def _focus_load_failed(self, message: str):
        worker = self.sender()
        if self._closing or getattr(worker, "request_id", -1) != self._focus_request_id:
            return
        self.focus_origin.setText(f"최신 조회 실패 · 기존 표시값은 저장분입니다 · {message}")

    def _focus_load_finished(self):
        worker = self.sender()
        self._focus_readers.discard(worker)
        if self.focus_load_thread is worker:
            self.focus_load_thread = None
            self.focus_loading_code = ""
        if worker is not None:
            worker.deleteLater()
        if not self._closing and self._focus_fetch_pending:
            self._focus_fetch_pending = False
            QTimer.singleShot(0, self.focus_refresh)
        if not self._closing:
            delay = DEVICE_PROFILE.background_delay_ms if DEVICE_PROFILE.low_power else 0
            QTimer.singleShot(delay, self._start_next_candidate_classification)

    def _apply_focus_metadata(self, payload: dict):
        """UI-only, intentionally cheap: no indicators/backtests here."""
        code = str(payload.get("code", "")).strip()
        if not code or code != self.selected_code:
            return

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

        self._focus_revision = payload.get("revision", "")
        self.focus_minute_raw = list(payload.get("minute") or [])
        self.focus_daily_raw = list(payload.get("daily") or [])
        self.focus_data_code = code
        self.danta_raw_minute = list(self.focus_minute_raw)
        self.danta_raw_daily = list(self.focus_daily_raw)
        self.danta_cache_code = code

    def _start_focus_analysis(self, payload: dict):
        if self._closing or payload.get("code") != self.selected_code or payload.get("request_id") != self._focus_request_id:
            return
        self._apply_focus_metadata(payload)
        key = self._focus_view_key()
        cached = self._analysis_cache.get((key, payload.get("revision")))
        if cached:
            self._focus_analysis_ready({**cached, "source_payload": payload,
                "request_id": self._focus_request_id, "cached": False})
            return
        if self.focus_analysis_thread is not None:
            self.focus_analysis_pending = payload
            if self.focus_analysis_thread.request_id != self._focus_request_id:
                self.focus_analysis_thread.requestInterruption()
            return
        self.focus_analysis_pending = None
        worker = FocusAnalysisThread(self.selected_code, payload.get("minute"), payload.get("daily"),
            self.intraday_selected_day or "", self.scan_start.time().toString("HH:mm"),
            self.scan_end.time().toString("HH:mm"), self._swing_settings_from_ui(), self.bowl_settings,
            float(self.focus_tp.value()), abs(float(self.focus_sl.value())), self)
        worker.mode = self.focus_chart_mode
        worker.request_id, worker.context_key, worker.source_payload = self._focus_request_id, key, payload
        self.focus_analysis_thread = worker
        worker.analyzed.connect(self._focus_analysis_ready)
        worker.failed.connect(self._focus_analysis_failed)
        worker.finished.connect(self._focus_analysis_finished)
        worker.start()

    def _focus_analysis_failed(self, message: str):
        worker = self.sender()
        if not self._closing and getattr(worker, "request_id", -1) == self._focus_request_id:
            self.focus_origin.setText(f"분석 실패 · {message}")

    def _focus_analysis_finished(self):
        worker = self.sender()
        if self.focus_analysis_thread is worker:
            self.focus_analysis_thread = None
        if worker is not None:
            worker.deleteLater()
        pending = self.focus_analysis_pending
        self.focus_analysis_pending = None
        if not self._closing and pending and pending.get("request_id") == self._focus_request_id:
            self._start_focus_analysis(pending)
        if not self._closing:
            delay = DEVICE_PROFILE.background_delay_ms if DEVICE_PROFILE.low_power else 0
            QTimer.singleShot(delay, self._start_next_candidate_classification)

    def _set_intraday_days_fast(self, days):
        days = list(days or [])
        if days == self.intraday_days and (not self.intraday_selected_day or self.intraday_selected_day in days):
            return
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

    def _focus_analysis_ready(self, result: dict):
        key = result.get("context_key")
        payload = result.get("source_payload") or {}
        if result.get("analysis_complete") and not result.get("cached") and key:
            record = self._display_cache.get(key)
            if not record or payload.get("loaded_at", 0) >= record["payload"].get("loaded_at", 0):
                self._display_cache.put(key, {"result": result, "payload": payload})
            if not result.get("errors"):
                self._analysis_cache.put((key, payload.get("revision")), result)
        if self._closing or result.get("request_id") != self._focus_request_id or key != self._focus_view_key():
            return
        code = str(result.get("code", "")).strip()
        if not code or code != self.selected_code:
            return

        swing_analysis = result.get("swing_analysis")
        swing_series = result.get("swing_series")
        bowl_analysis = result.get("bowl_analysis")
        bowl_series = result.get("bowl_series")
        danta_analysis = result.get("danta_analysis")
        danta_series = result.get("danta_series")

        prev_swing_analysis = self.focus_daily_analysis
        prev_daily_series = self.focus_daily_series
        prev_bowl_analysis = self.focus_bowl_analysis
        prev_danta_analysis = self.focus_danta_analysis
        prev_danta_series = self.focus_danta_series
        changed_parts = set()

        minute_days = result.get("minute_days") or []
        if minute_days != self.intraday_days:
            self._set_intraday_days_fast(minute_days)

        if swing_analysis is not None and swing_series:
            if swing_analysis is not prev_swing_analysis or swing_series is not prev_daily_series:
                changed_parts.add("swing")
            self.focus_daily_analysis = swing_analysis
            self.focus_daily_series = swing_series
            self._shown_daily_revision = payload.get("revision", "")
            if "swing" in changed_parts:
                self._set_focus_date_bounds()
        elif result.get("analysis_complete"):
            if self.focus_daily_analysis is not None or self.focus_daily_series is not None:
                changed_parts.add("swing")
            self.focus_daily_analysis = None
            self.focus_daily_series = None

        if bowl_analysis is not None or result.get("analysis_complete"):
            if bowl_analysis is not prev_bowl_analysis or bowl_series is not self.focus_bowl_series:
                changed_parts.add("bowl")
            self.focus_bowl_analysis = bowl_analysis
            self.focus_bowl_series = bowl_series
        if danta_analysis is not None or result.get("analysis_complete"):
            if danta_analysis is not prev_danta_analysis or danta_series is not prev_danta_series:
                changed_parts.add("danta")
            self.focus_danta_analysis = danta_analysis
            self.focus_danta_series = danta_series
        if result.get("analysis_complete"):
            for value, widget in ((swing_analysis, self.focus_swing_signal),
                                  (bowl_analysis, self.focus_bowl_signal),
                                  (danta_analysis, self.focus_danta_signal)):
                if value is None:
                    widget.setText("분석 결과 없음 · 데이터 부족 또는 조회/분석 실패")

        danta_label = self._pretty_intraday_day(result.get("danta_day") or self.intraday_selected_day) if danta_analysis else "최신"
        self._apply_focus_analyses(danta_analysis, swing_analysis, bowl_analysis, danta_label, changed_parts)

        if code in self.condition_candidates and (danta_analysis or swing_analysis or bowl_analysis):
            ds = int(result.get("latest_danta_score", 0) or 0)
            ss = int(getattr(swing_analysis, "score", 0) or 0) if swing_analysis else 0
            bs = int(getattr(bowl_analysis, "score", 0) or 0) if bowl_analysis else 0
            label, detail = classify_scores(ds, ss, bs)
            self._set_candidate_classification(code, label, detail, {"danta": ds, "swing": ss, "bowl": bs})

        chart_changed = (
            (
                self.focus_chart_mode == "DAY"
                and ("swing" in changed_parts or "bowl" in changed_parts)
            )
            or (self.focus_chart_mode == "MIN" and "danta" in changed_parts)
        )
        if chart_changed or not (self.focus_chart.series and self.focus_chart.series.get("candles")):
            self._update_focus_chart(bool(self.focus_chart.series and self.focus_data_code == code))
        if isinstance(result.get("analysis_ms"), (int, float)):
            self.focus_latency_ms["analysis_cpu_ms"] = round(float(result["analysis_ms"]), 2)
            self._refresh_focus_perf_label()
        self._record_focus_latency("analysis")
        day_count = len(self.focus_daily_series.get("candles", [])) if self.focus_daily_series else 0
        errors = result.get("errors") or []
        err_text = f" · 일부 분석: {' / '.join(errors)}" if errors else ""
        all_done = bool(result.get("analysis_complete") and payload.get("complete"))
        stamp = datetime.fromtimestamp(payload.get("loaded_at", time.time())).strftime("%H:%M:%S")
        state = "저장분 즉시 표시" if result.get("cached") else "분석 완료" if all_done else "현재 수신분 분석 · 과거 데이터/나머지 분석 갱신 중"
        fetch_errors = payload.get("errors") or []
        if fetch_errors:
            state += " · 일부 조회 실패: " + " / ".join(fetch_errors)
        self.focus_origin.setText(f"{state} · 일봉 {day_count}봉 · 자료 조회 {stamp}{err_text}")
        if all_done:
            self._record_focus_latency("complete")
            self._schedule_focus_perf_log()

        if self._strategy_refresh_after_focus:
            self._strategy_refresh_after_focus = False
            self._render_danta_from_focus_cache()

    def _render_danta_from_focus_cache(self):
        if not self.focus_danta_analysis or not self.focus_danta_series:
            return
        self.danta_analysis = self.focus_danta_analysis
        self.danta_series = self.focus_danta_series
        result = self.danta_analysis
        series = self.danta_series
        day = self.intraday_selected_day or str(result.details.get("분석 기준일", "")).replace("-", "")
        name = self.selected_name or self.selected_code

        chart_series = series
        if self.intraday_selected_day:
            chart_series = slice_series_for_date(series, self.intraday_selected_day)
        candles = chart_series.get("candles", [])
        lines = {k: v for k, v in chart_series.items() if k != "candles"}
        day_label = self._pretty_intraday_day(day)
        title_suffix = day_label if self.intraday_selected_day else f"전체 · 최신분석 {day_label}"
        self.danta_chart.set_basic_data(
            candles, lines,
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
        candles = self._preview_series.get("minute") or normalize_candles(self.focus_minute_raw or [])
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
            daily_series = dict(self.focus_daily_series)
            bowl_series = self.focus_bowl_series if isinstance(self.focus_bowl_series, dict) else {}
            if (
                bowl_series
                and len(bowl_series.get("candles", [])) == len(daily_series.get("candles", []))
            ):
                for key in (
                    "bowl_stage2_ready",
                    "bowl_breakout_idx",
                    "bowl_accepted_idx",
                    "bowl_retest_idx",
                    "bowl3_markers",
                ):
                    if key in bowl_series:
                        daily_series[key] = bowl_series[key]
            self.focus_chart.set_data(
                self.focus_daily_analysis,
                daily_series,
                title=f"{self.selected_name or self.selected_code} · 일봉 · 역매공파 + 밥그릇3번",
                preserve_view=preserve_view,
            )
        elif self._preview_series.get("daily"):
            self.focus_chart.set_basic_data(self._preview_series["daily"], title=f"{self.selected_name} · 일봉 / 분석 중")

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
        start_idx = max(0, min(start_idx, len(cs)-1))
        end_idx = max(start_idx, min(end_idx, len(cs)-1))
        self._range_request_id += 1
        args = (start_idx, end_idx, label)
        self.focus_chart.set_analysis_range(start_idx, end_idx)
        self.focus_range_status.setText(f"구간 분석 중: {label}")
        if self._range_worker is not None:
            self._range_worker.requestInterruption()
            self._range_pending = args
            return
        self._launch_range_analysis(args)

    def _launch_range_analysis(self, args):
        if self._closing or not self.focus_daily_series:
            return
        start_idx, end_idx, label = args
        cs = self.focus_daily_series['candles']
        sample = cs[max(0, start_idx - 560):end_idx+1]
        key = (self._focus_view_key(), self._shown_daily_revision, start_idx, end_idx)
        cached = self._range_cache.get(key)
        if cached:
            self._apply_focus_analyses(self.focus_danta_analysis, *cached, label)
            self.focus_range_status.setText(f"분석: {label}")
            return
        worker = FocusAnalysisThread(self.selected_code, [], sample, "", "08:50", "10:00",
            self._swing_settings_from_ui(), self.bowl_settings, float(self.focus_tp.value()),
            abs(float(self.focus_sl.value())), self)
        worker.request_id = self._focus_request_id
        worker.context_key = self._focus_view_key()
        worker.range_id, worker.range_label, worker.range_key = self._range_request_id, label, key
        self._range_worker = worker
        worker.analyzed.connect(self._range_analysis_ready)
        worker.finished.connect(self._range_analysis_finished)
        worker.start()

    def _range_analysis_ready(self, result):
        worker = self.sender()
        if not result.get("analysis_complete") or self._closing or worker is None:
            return
        if worker.request_id != self._focus_request_id or worker.range_id != self._range_request_id or worker.context_key != self._focus_view_key():
            return
        sa, ba = result.get("swing_analysis"), result.get("bowl_analysis")
        if sa or ba:
            self._range_cache.put(worker.range_key, (sa, ba))
            self._apply_focus_analyses(self.focus_danta_analysis, sa, ba, worker.range_label)
        errors = " / ".join(result.get("errors") or [])
        self.focus_range_status.setText(f"분석: {worker.range_label}" + (f" · {errors}" if errors else ""))

    def _range_analysis_finished(self):
        worker = self.sender()
        if self._range_worker is worker:
            self._range_worker = None
        if worker is not None:
            worker.deleteLater()
        pending, self._range_pending = self._range_pending, None
        if pending and not self._closing:
            self._launch_range_analysis(pending)

    def focus_analyze_all(self):
        self._range_request_id += 1
        self._range_pending = None
        if self._range_worker is not None:
            self._range_worker.requestInterruption()
        self.focus_chart.clear_analysis_range()
        if self.focus_daily_analysis or self.focus_bowl_analysis:
            self._apply_focus_analyses(self.focus_danta_analysis, self.focus_daily_analysis, self.focus_bowl_analysis, "전체")
        self.focus_range_status.setText("분석: 전체")

    def _apply_focus_analyses(self, danta_analysis, swing_analysis, bowl_analysis, label: str, changed_parts=None):
        changed_parts = set(changed_parts or ("danta", "swing", "bowl"))
        if danta_analysis and "danta" in changed_parts:
            color = "#61ff8f" if danta_analysis.candidate else ("#62b8ff" if danta_analysis.score >= 55 else "#f4c95d")
            dreason = str(danta_analysis.details.get("간단 이유", "-"))
            djudge = danta_analysis.details.get("PUMA 판단", "판단 유보")
            dauto = danta_analysis.details.get("자동매매 기준", "-")
            self.focus_danta_signal.setText(
                f"가보자 단타 · 5분봉\n"
                f"자동매매: {dauto}\n"
                f"PUMA 판단: {djudge}\n"
                f"현재 단계: {danta_analysis.stage}\n"
                f"이유: {dreason}"
            )
            self.focus_danta_signal.setStyleSheet(f"QPlainTextEdit{{font-size:12px;font-weight:900;color:{color};background:#122238;border:0;border-radius:8px;padding:3px;}} QScrollBar:vertical{{width:9px;}}")
            if hasattr(self, "focus_danta_labels"):
                detail_map = {
                    "자동매매 기준": danta_analysis.details.get("자동매매 기준", "-"),
                    "PUMA 판단": danta_analysis.details.get("PUMA 판단", "-"),
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

        if swing_analysis and "swing" in changed_parts:
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

        if bowl_analysis and "bowl" in changed_parts:
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

    def _confirm_live_auto_once(self, title: str, message: str) -> bool:
        """Real auto-trading requires only the primary LIVE arm.

        The former second-stage text prompt was intentionally removed.
        Manual real orders still keep their separate LIVE ORDER confirmation.
        """
        if not (isinstance(self.broker, KiwoomRestBroker) and self.broker.real):
            return True
        if not self.real_armed:
            QMessageBox.warning(self, "실전 잠금", "실전매매 잠금이 해제되지 않았습니다. 키움 연결 탭에서 LIVE를 입력하세요.")
            return False
        self.live_auto_confirmed_session = True
        return True

    def start_focus_auto(self):
        if not self.selected_code:
            QMessageBox.information(self, "종목 선택", "조건검색 목록에서 종목을 먼저 선택하세요.")
            return
        # 통합화면의 리스크 값을 기존 엔진 설정에 반영한다.
        self.order_budget.setValue(500_000)
        self.focus_budget.setValue(500_000)
        self.take_profit.setValue(self.focus_tp.value())
        self.stop_loss.setValue(self.focus_sl.value())
        self.trailing.setChecked(self.focus_trail.isChecked())
        self.trailing_start.setValue(self.focus_trail_start.value())
        self.trailing_gap.setValue(self.focus_trail_gap.value())
        self.save_settings_silent()
        if isinstance(self.broker, KiwoomRestBroker) and self.broker.real:
            if not self._confirm_live_auto_once(
                "선택 종목 실전 자동매매",
                f"{self.selected_name or self.selected_code} 한 종목 자동매매를 시작합니다.",
            ):
                return
            try:
                self.engine.sync_account(force=True)
            except Exception as exc:
                QMessageBox.critical(self, "실계좌 동기화 실패", str(exc)); return
        self.focus_auto_danta_pool = False
        self.focus_only_code = self.selected_code
        self.engine.enabled = True
        self.timer.start()
        self.log(self.selected_name or self.selected_code, "AUTO", "-", "선택 종목 전용 가보자 자동매매 시작")
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

        if self.focus_auto_danta_pool:
            # 통합 트레이딩의 '전체 후보 자동매매'는 관심종목과 무관하다.
            # 단타 검색기 7개 합집합 전체를 감시하되, 실제 신규매수는 아래 scan_one()
            # 에서 PUMA 장중 2차 선별 + 가보자 진입조건을 모두 통과한 경우만 허용한다.
            for code, item in self.condition_candidates.items():
                if code in self.session_excluded_codes:
                    continue
                if self._candidate_in_danta_feed(item):
                    merged[code] = {"code": code, "name": item.get("name", code), "hero": True}

            # 이미 보유/주문 중인 종목은 선별 상태가 바뀌어도 청산/체결 확인을 계속한다.
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
                if code in self.session_excluded_codes and code not in self.engine.positions and code not in self.engine.pending_orders:
                    continue
                if item.get("active"):
                    # 초기 조회 종목과 이후 신규 편입 종목을 모두 PUMA 자동검토 대상으로 사용한다.
                    # 조건검색 편입은 후보 공급일 뿐이며 실제 주문은 엔진의 2차 선별/가보자 타점을 통과해야 한다.
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

    def start_danta_pool_auto(self):
        # 통합 트레이딩 전용: 관심종목 등록 여부를 보지 않는다.
        # 필요하면 단타 검색기 7개 스트림부터 자동으로 시작한다.
        self.focus_only_code = None
        self.focus_auto_danta_pool = True

        # 통합화면 리스크 값을 엔진 설정에 반영.
        self.order_budget.setValue(500_000)
        self.focus_budget.setValue(500_000)
        self.take_profit.setValue(self.focus_tp.value())
        self.stop_loss.setValue(self.focus_sl.value())
        self.trailing.setChecked(self.focus_trail.isChecked())
        self.trailing_start.setValue(self.focus_trail_start.value())
        self.trailing_gap.setValue(self.focus_trail_gap.value())
        self.hero_secondary_filter.setChecked(True)
        self.save_settings_silent()

        if not isinstance(self.broker, KiwoomRestBroker) or not self.broker.token:
            self.focus_auto_danta_pool = False
            QMessageBox.information(self, "키움 연결 필요", "전체 후보 자동매매는 키움 연결 후 단타 검색기 7개 결과를 사용합니다.")
            return

        if not self.condition_thread or not self.condition_thread.isRunning():
            self.start_condition_stream()

        # start() 직후 QThread.isRunning()은 스케줄링 시점에 따라 잠깐 False일 수 있으므로
        # 스레드 객체 생성 여부만 확인하고 초기 스냅샷은 비동기로 기다린다.
        if self.condition_thread is None:
            self.focus_auto_danta_pool = False
            QMessageBox.information(self, "단타 후보 없음", "단타 검색기 7개 실시간 검색을 시작하지 못했습니다.")
            return

        if isinstance(self.broker, KiwoomRestBroker) and self.broker.real:
            if not self._confirm_live_auto_once(
                "단타 전체 후보 실전 자동매매",
                f"단타 검색기 통합 합집합 → PUMA 2차 선별 → 가보자 진입조건 통과 종목에 실제 주문이 전송됩니다.\n"
                f"종목당 {self.settings.order_budget:,}원 / 최대 {self.settings.max_positions}종목 / 일일 주문 {self.settings.max_daily_orders}회",
            ):
                self.focus_auto_danta_pool = False
                return
            try:
                self.engine.sync_account(force=True)
                self._refresh_position_rows()
            except Exception as exc:
                self.focus_auto_danta_pool = False
                QMessageBox.critical(self, "실계좌 동기화 실패", f"잔고 동기화에 실패하여 실전 자동매매를 시작하지 않습니다.\n{exc}")
                return

        self.engine.enabled = True
        self.timer.start()
        candidate_count = sum(
            1 for item in self.condition_candidates.values()
            if self._candidate_in_danta_feed(item)
        )
        self.log("SYSTEM", "AUTO", "0", f"단타 검색기 합집합 → PUMA 실시간 2차선별 → 가보자 자동매매 시작 · 현재 후보 {candidate_count}종목")
        self.scan_one()

    def start_auto(self):
        self.focus_auto_danta_pool = False
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
            if not self._confirm_live_auto_once(
                "실전 자동매매 최종 확인",
                f"실제 주문이 전송됩니다.\n종목당 {self.settings.order_budget:,}원 / 최대 {self.settings.max_positions}종목 / 일일 주문 {self.settings.max_daily_orders}회",
            ):
                return
            try:
                self.engine.sync_account(force=True)
                self._refresh_position_rows()
            except Exception as exc:
                QMessageBox.critical(self, "실계좌 동기화 실패", f"잔고 동기화에 실패하여 실전 자동매매를 시작하지 않습니다.\n{exc}")
                return

        self.engine.enabled = True
        self.timer.start()
        self.log("SYSTEM", "AUTO", "0", f"가보자 자동매매 시작 · {source}")
        self.scan_one()

    def stop_auto(self):
        self.engine.enabled = False
        self.timer.stop()
        self.focus_only_code = None
        self.focus_auto_danta_pool = False
        if hasattr(self, "log_table"):
            self.log("SYSTEM", "STOP", "0", "자동매매 중지")

    def scan_one(self):
        # REST 조회/주문은 GUI event loop에서 절대 직접 실행하지 않는다.
        # 1.8초 타이머가 다시 울려도 이전 scan이 끝나지 않았다면 겹쳐 실행하지 않는다.
        worker = self.auto_scan_thread
        if worker is not None and worker.isRunning():
            return

        targets = self._active_targets()
        if not targets:
            return
        item = targets[self.scan_index % len(targets)]
        self.scan_index += 1
        code = item["code"]
        name = item.get("name", code)
        hero = bool(item.get("hero"))
        # 조건검색 후보는 반드시 PUMA 2차 선별을 거친 뒤 가보자 진입조건을 평가한다.
        require_filter = True

        worker = AutoScanThread(self.engine, code, name, require_filter, self)
        self.auto_scan_thread = worker
        worker.resultReady.connect(self._on_auto_scan_result)
        worker.failed.connect(self._on_auto_scan_error)
        worker.finished.connect(self._on_auto_scan_finished)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _on_auto_scan_result(self, res):
        if self._closing:
            return
        self.update_row(res)
        if res.get("status") in (
            "BUY", "SELL", "BUY_SENT", "SELL_SENT",
            "PARTIAL_SELL", "PARTIAL_SELL_SENT",
        ):
            self.log(res["name"], res["status"], f"{res['price']:,.0f}", res["signal"])
        self._refresh_position_rows()

    def _on_auto_scan_error(self, exc):
        if self._closing:
            return
        name = getattr(self.auto_scan_thread, "name", "SYSTEM") if self.auto_scan_thread else "SYSTEM"
        if isinstance(exc, BrokerError):
            self.log(name, "ERROR", "0", str(exc))
            self.stop_auto()
        else:
            self.log(name, "ERROR", "0", repr(exc))

    def _on_auto_scan_finished(self):
        self.auto_scan_thread = None

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
        color = QColor("#59d98e") if status in ("BUY", "BUY_SENT", "READY") else QColor("#ff7070") if status in ("SELL", "SELL_SENT", "PARTIAL_SELL", "PARTIAL_SELL_SENT") else QColor("#e8eef7")
        self.market_table.item(r, 4).setForeground(color)

    def log(self, stock, kind, price, text):
        r = 0
        self.log_table.insertRow(r)
        vals = [datetime.now().strftime("%H:%M:%S"), stock, kind, price, text]
        for c, v in enumerate(vals):
            self.log_table.setItem(r, c, QTableWidgetItem(str(v)))
        if self.log_table.rowCount() > 400:
            self.log_table.removeRow(self.log_table.rowCount() - 1)

    # ---------- 모바일 연동 ----------
    def _mobile_tab(self):
        w = QWidget()
        root = QVBoxLayout(w)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        info = QGroupBox("PUMA STOCK MOBILE · 아이폰/안드로이드")
        form = QGridLayout(info)

        title = QLabel("PC의 PUMA 엔진을 휴대폰에서 그대로 연동합니다.")
        title.setStyleSheet("font-size:16px;font-weight:900;color:#ffffff")
        form.addWidget(title, 0, 0, 1, 4)

        desc = QLabel(
            "같은 Wi-Fi에서 아이폰 Safari로 아래 주소에 접속한 뒤 연결코드 6자리를 입력하세요. "
            "Safari 공유 → 홈 화면에 추가를 누르면 앱처럼 설치됩니다. "
            "키움 App Key/Secret은 휴대폰으로 전송하지 않습니다."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color:#9eb4c9")
        form.addWidget(desc, 1, 0, 1, 4)

        self.mobile_url_label = QLabel("서버 중지")
        self.mobile_url_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.mobile_url_label.setStyleSheet("font-size:18px;font-weight:900;color:#6fc4ff;padding:8px")
        form.addWidget(QLabel("접속 주소"), 2, 0)
        form.addWidget(self.mobile_url_label, 2, 1, 1, 2)

        copy_url = QPushButton("주소 복사")
        copy_url.clicked.connect(lambda: QApplication.clipboard().setText(
            self.mobile_bridge.url() if self.mobile_bridge.running else self.mobile_url_label.text()
        ))
        form.addWidget(copy_url, 2, 3)

        self.mobile_demo_url_label = QLabel("서버 중지")
        self.mobile_demo_url_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.mobile_demo_url_label.setStyleSheet("font-size:16px;font-weight:900;color:#ffd65a;padding:8px")
        form.addWidget(QLabel("작동형 데모"), 3, 0)
        form.addWidget(self.mobile_demo_url_label, 3, 1, 1, 2)
        copy_demo = QPushButton("데모주소 복사")
        copy_demo.clicked.connect(lambda: QApplication.clipboard().setText(
            f"{self.mobile_bridge.url()}/demo" if self.mobile_bridge.running else self.mobile_demo_url_label.text()
        ))
        form.addWidget(copy_demo, 3, 3)

        self.mobile_token_label = QLabel(self.mobile_bridge.token)
        self.mobile_token_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.mobile_token_label.setAlignment(Qt.AlignCenter)
        self.mobile_token_label.setStyleSheet(
            "font-size:30px;font-weight:900;letter-spacing:8px;color:#ffd65a;"
            "background:#101f33;border:1px solid #35506d;border-radius:8px;padding:10px"
        )
        form.addWidget(QLabel("연결코드"), 4, 0)
        form.addWidget(self.mobile_token_label, 4, 1, 1, 2)
        regen = QPushButton("코드 재발급")
        regen.clicked.connect(self._mobile_regenerate_token)
        form.addWidget(regen, 4, 3)

        self.mobile_port = QSpinBox()
        self.mobile_port.setRange(1024, 65535)
        self.mobile_port.setValue(self.mobile_bridge.port)
        form.addWidget(QLabel("포트"), 5, 0)
        form.addWidget(self.mobile_port, 5, 1)

        self.mobile_auto_box = QCheckBox("PUMA 실행 시 모바일 서버 자동 시작")
        self.mobile_auto_box.setChecked(bool(self.ui_state.value("mobile/autoStart", False, type=bool)))
        self.mobile_auto_box.toggled.connect(
            lambda checked: self.ui_state.setValue("mobile/autoStart", bool(checked))
        )
        form.addWidget(self.mobile_auto_box, 5, 2, 1, 2)

        buttons = QHBoxLayout()
        start = QPushButton("▶ 모바일 서버 시작")
        start.setObjectName("startBtn")
        stop = QPushButton("■ 모바일 서버 중지")
        stop.setObjectName("stopBtn")
        start.clicked.connect(self._mobile_start)
        stop.clicked.connect(self._mobile_stop)
        buttons.addWidget(start)
        buttons.addWidget(stop)
        form.addLayout(buttons, 6, 0, 1, 4)

        self.mobile_status_label = QLabel("서버 중지 · 휴대폰 연결 없음")
        self.mobile_status_label.setStyleSheet("font-weight:800;color:#8fb6d9")
        form.addWidget(self.mobile_status_label, 7, 0, 1, 4)
        root.addWidget(info)

        security = QGroupBox("모바일 실전 잠금")
        sec = QVBoxLayout(security)
        self.mobile_lock_state_label = QLabel(
            "실전 잠금은 모바일에서 최초 1회만 해제합니다. "
            "해제 상태는 저장되며 연결코드 재발급 또는 모바일의 '실전 잠금 다시 걸기' 전까지 유지됩니다."
        )
        self.mobile_lock_state_label.setWordWrap(True)
        self.mobile_lock_state_label.setStyleSheet("color:#f4c95d;font-weight:800")
        sec.addWidget(self.mobile_lock_state_label)
        root.addWidget(security)

        features = QGroupBox("모바일 제공 기능")
        fv = QVBoxLayout(features)
        feature_text = QLabel(
            "• 조건검색 편입/이탈 및 단타·스윙·밥그릇 분류\n"
            "• 종목 선택 시 PC 통합 트레이딩 화면도 같은 종목으로 연동\n"
            "• 일봉 / 5분봉 차트 전환\n"
            "• EMA112/224/448, 4종 화살표, 수박 표시\n"
            "• 단타 / 역매공파 / 밥그릇3 분석 결과\n"
            "• PUMA 관리 보유종목 / 주문·신호 로그\n"
            "• 최초 1회 모바일 실전 잠금 해제 후 시장가·지정가·스톱지정가 수동 주문\n"
            "• 최초 1회 모바일 실전 잠금 해제 후 전체 후보/선택 종목 자동매매 시작·중지와 리스크값 설정"
        )
        feature_text.setWordWrap(True)
        feature_text.setStyleSheet("color:#c7d8e8;line-height:1.5")
        fv.addWidget(feature_text)
        root.addWidget(features)
        root.addStretch()
        return self._scroll_wrap(w)

    def _mobile_start(self):
        try:
            info = self.mobile_bridge.start(self.mobile_port.value())
            self.mobile_port.setValue(int(info["port"]))
            self.mobile_url_label.setText(str(info["url"]))
            self.mobile_demo_url_label.setText(f"{info['url']}/demo")
            self.mobile_token_label.setText(str(info["token"]))
            self.mobile_status_label.setText("모바일 서버 실행 중 · 같은 Wi-Fi에서 접속 가능")
            self.mobile_status_label.setStyleSheet("font-weight:900;color:#61ff8f")
            self.log("PUMA MOBILE", "SERVER", "-", f"모바일 서버 시작 {info['url']}")
            self._publish_mobile_snapshot()
        except Exception as exc:
            self.mobile_status_label.setText(f"시작 실패: {exc}")
            self.mobile_status_label.setStyleSheet("font-weight:900;color:#ff6b78")
            QMessageBox.critical(self, "모바일 서버 시작 실패", str(exc))

    def _mobile_stop(self):
        self.mobile_bridge.stop()
        self.mobile_url_label.setText("서버 중지")
        self.mobile_demo_url_label.setText("서버 중지")
        self.mobile_status_label.setText("서버 중지 · 휴대폰 연결 없음")
        self.mobile_status_label.setStyleSheet("font-weight:800;color:#8fb6d9")

    def _mobile_regenerate_token(self):
        token = self.mobile_bridge.regenerate_token()
        self.mobile_token_label.setText(token)
        self.mobile_status_label.setText("새 연결코드 발급 · 모바일 실전 잠금 다시 활성화")
        self.log("PUMA MOBILE", "PAIR", "-", "모바일 연결코드 재발급 · 실전 잠금 재설정")
        self._publish_mobile_snapshot()

    def _apply_mobile_auto_settings(self, data: dict):
        source = str(data.get("candidate_source") or self.settings.candidate_source or "WATCHLIST")
        if source not in ("WATCHLIST", "HERO4", "BOTH"):
            raise ValueError("자동매매 후보 소스가 올바르지 않습니다.")
        idx = self.source_combo.findData(source)
        if idx >= 0:
            self.source_combo.setCurrentIndex(idx)

        budget = 500_000
        max_pos = max(1, min(20, int(float(data.get("max_positions") or self.settings.max_positions))))
        daily = max(1, min(100, int(float(data.get("max_daily_orders") or self.settings.max_daily_orders))))
        tp = max(0.1, min(100.0, float(data.get("take_profit_pct") or self.settings.take_profit_pct)))
        sl_raw = float(data.get("stop_loss_pct") if data.get("stop_loss_pct") not in (None, "") else self.settings.stop_loss_pct)
        sl = max(-50.0, min(-0.1, sl_raw))
        trail_start = max(0.1, min(100.0, float(data.get("trailing_start_pct") or self.settings.trailing_start_pct)))
        trail_gap = max(0.1, min(30.0, float(data.get("trailing_gap_pct") or self.settings.trailing_gap_pct)))
        trailing = bool(data.get("trailing_enabled", self.settings.trailing_enabled))

        self.order_budget.setValue(500_000)
        self.max_positions.setValue(max_pos)
        self.max_daily_orders.setValue(daily)
        self.take_profit.setValue(tp)
        self.stop_loss.setValue(sl)
        self.trailing.setChecked(trailing)
        self.trailing_start.setValue(trail_start)
        self.trailing_gap.setValue(trail_gap)

        if getattr(self, "focus_budget", None) is not None:
            self.focus_budget.setValue(500_000)
            self.focus_tp.setValue(tp)
            self.focus_sl.setValue(sl)
            self.focus_trail.setChecked(trailing)
            self.focus_trail_start.setValue(trail_start)
            self.focus_trail_gap.setValue(trail_gap)

        self.save_settings_silent()

    @staticmethod
    def _mobile_number(value):
        try:
            x = float(str(value).replace(",", "").replace("원", "").replace("%", "").strip())
            if x != x or x in (float("inf"), float("-inf")):
                return 0.0
            return x
        except Exception:
            return 0.0

    def _mobile_chart_payload(self):
        # 모바일 차트는 현재 PC에서 선택한 일봉/5분봉 모드와 동기화한다.
        series = self.focus_daily_series if self.focus_chart_mode == "DAY" else self.focus_danta_series
        series = series or {}
        candles = list(series.get("candles") or [])
        limit = 180 if self.focus_chart_mode == "DAY" else 220
        start = max(0, len(candles) - limit)
        trimmed = []
        for row in candles[start:]:
            trimmed.append({
                "date": str(row.get("date") or ""),
                "open": self._mobile_number(row.get("open")),
                "high": self._mobile_number(row.get("high")),
                "low": self._mobile_number(row.get("low")),
                "close": self._mobile_number(row.get("close")),
                "volume": self._mobile_number(row.get("volume")),
            })

        out = {"candles": trimmed}
        numeric_keys = ("ema112", "ema224", "ema448")
        flag_keys = ("signal_pink", "signal_blue", "signal_red", "signal_black", "watermelon_display")
        for key in numeric_keys:
            arr = list(series.get(key) or [])
            out[key] = [
                (self._mobile_number(v) if v is not None else None)
                for v in arr[start:start + len(trimmed)]
            ]
            if len(out[key]) < len(trimmed):
                out[key] = [None] * (len(trimmed) - len(out[key])) + out[key]
        for key in flag_keys:
            arr = list(series.get(key) or [])
            vals = arr[start:start + len(trimmed)]
            if len(vals) < len(trimmed):
                vals = [False] * (len(trimmed) - len(vals)) + vals
            out[key] = [bool(v) for v in vals]
        return out

    def _publish_mobile_snapshot(self):
        if self._closing:
            return
        try:
            candidates = []
            for code, item in self.condition_candidates.items():
                scores = dict(item.get("scores") or {})
                candidates.append({
                    "code": str(code),
                    "name": str(item.get("name") or code),
                    "active": bool(item.get("active")),
                    "classification": str(item.get("classification") or "분석중"),
                    "detail": str(item.get("class_detail") or "-"),
                    "entered_at": str(item.get("entered_at") or "-"),
                    "scores": {
                        "danta": int(scores.get("danta", 0) or 0),
                        "swing": int(scores.get("swing", 0) or 0),
                        "bowl": int(scores.get("bowl", 0) or 0),
                    },
                })
            candidates.sort(key=lambda x: (not x["active"], x["name"], x["code"]))

            price = 0.0
            if self.focus_daily_analysis is not None:
                price = self._mobile_number(getattr(self.focus_daily_analysis, "current_price", 0))
            if price <= 0 and getattr(self, "focus_price", None) is not None:
                price = self._mobile_number(self.focus_price.text())

            positions = []
            for code, pos in self.engine.positions.items():
                current = 0.0
                row = self.row_by_code.get(code)
                if row is not None and row < self.market_table.rowCount():
                    cell = self.market_table.item(row, 3)
                    current = self._mobile_number(cell.text() if cell else 0)
                if current <= 0:
                    current = self._mobile_number(getattr(pos, "entry_price", 0))
                entry = self._mobile_number(getattr(pos, "entry_price", 0))
                pnl = ((current / entry - 1) * 100.0) if entry > 0 else 0.0
                positions.append({
                    "code": str(code),
                    "name": str(getattr(pos, "name", code)),
                    "qty": int(getattr(pos, "qty", 0) or 0),
                    "avg_price": entry,
                    "current_price": current,
                    "pnl_pct": round(pnl, 2),
                })

            logs = []
            if getattr(self, "log_table", None) is not None:
                for row in range(min(80, self.log_table.rowCount())):
                    vals = []
                    for col in range(5):
                        cell = self.log_table.item(row, col)
                        vals.append(cell.text() if cell else "")
                    logs.append({
                        "time": vals[0], "stock": vals[1], "kind": vals[2],
                        "price": vals[3], "text": vals[4],
                    })

            connected = isinstance(self.broker, KiwoomRestBroker) and bool(getattr(self.broker, "token", ""))
            live = isinstance(self.broker, KiwoomRestBroker) and bool(getattr(self.broker, "real", False))
            state = {
                "version": CURRENT_VERSION,
                "updated_at": datetime.now().strftime("%H:%M:%S"),
                "connected": connected,
                "live": live,
                "real_armed": bool(self.real_armed),
                "status": self.conn_label.text() if getattr(self, "conn_label", None) is not None else "-",
                "mode": self.mode_label.text() if getattr(self, "mode_label", None) is not None else "-",
                "auto": {
                    "enabled": bool(self.engine.enabled),
                    "scope": "SELECTED" if self.focus_only_code else "ALL",
                    "scope_label": (
                        f"선택종목 {self.name_cache.get(self.focus_only_code, self.focus_only_code)}"
                        if self.focus_only_code else
                        {"WATCHLIST": "관심종목", "HERO4": "영웅문 조건검색", "BOTH": "관심+조건검색"}.get(
                            str(self.settings.candidate_source), str(self.settings.candidate_source)
                        )
                    ),
                    "focus_only_code": self.focus_only_code or "",
                    "settings": {
                        "candidate_source": str(self.settings.candidate_source),
                        "order_budget": int(self.settings.order_budget),
                        "max_positions": int(self.settings.max_positions),
                        "max_daily_orders": int(self.settings.max_daily_orders),
                        "take_profit_pct": float(self.settings.take_profit_pct),
                        "stop_loss_pct": float(self.settings.stop_loss_pct),
                        "trailing_enabled": bool(self.settings.trailing_enabled),
                        "trailing_start_pct": float(self.settings.trailing_start_pct),
                        "trailing_gap_pct": float(self.settings.trailing_gap_pct),
                    },
                },
                "candidates": candidates,
                "positions": positions,
                "logs": logs,
                "selected": {
                    "code": self.selected_code,
                    "name": self.selected_name,
                    "price": price,
                    "chart_mode": self.focus_chart_mode,
                    "stage": self.focus_stage.text() if getattr(self, "focus_stage", None) is not None else "데이터 대기",
                    "analysis": {
                        "danta": self.focus_danta_signal.toPlainText() if getattr(self, "focus_danta_signal", None) is not None else "-",
                        "swing": self.focus_swing_signal.toPlainText() if getattr(self, "focus_swing_signal", None) is not None else "-",
                        "bowl": self.focus_bowl_signal.toPlainText() if getattr(self, "focus_bowl_signal", None) is not None else "-",
                    },
                    "chart": self._mobile_chart_payload(),
                },
            }
            self.mobile_bridge.publish(state)
        except Exception:
            # 모바일 스냅샷 실패가 메인 트레이딩 UI에 영향을 주면 안 된다.
            pass

    def _on_mobile_command(self, request_id: str, payload: object):
        data = payload if isinstance(payload, dict) else {}
        command = str(data.get("type") or "").strip()
        try:
            if command == "select_stock":
                code = str(data.get("code") or "").strip()
                name = str(data.get("name") or code).strip()
                if not code or len(code) > 12:
                    raise ValueError("종목코드가 올바르지 않습니다.")
                self.open_focus_stock(code, name or code)
                self.mobile_bridge.complete_command(
                    request_id,
                    {"message": f"{name or code} 선택", "code": code},
                )
                return

            if command == "set_chart_mode":
                mode = str(data.get("mode") or "").upper()
                if mode not in ("DAY", "MIN"):
                    raise ValueError("차트 모드는 DAY 또는 MIN만 가능합니다.")
                idx = self.focus_chart_mode_combo.findData(mode)
                if idx < 0:
                    raise ValueError("차트 모드를 찾을 수 없습니다.")
                self.focus_chart_mode_combo.setCurrentIndex(idx)
                self.mobile_bridge.complete_command(
                    request_id, {"message": f"{mode} 차트 전환", "mode": mode}
                )
                return

            if command == "unlock_live":
                phrase = str(data.get("phrase") or "").strip().upper()
                if phrase != "PUMA LIVE":
                    raise PermissionError("실전 잠금 해제 문구가 올바르지 않습니다.")
                self.mobile_bridge.unlock_live()
                self.log("PUMA MOBILE", "UNLOCK", "-", "모바일 실전 기능 최초 1회 잠금 해제")
                self.mobile_bridge.complete_command(
                    request_id, {"message": "실전 기능 잠금 해제 완료"}
                )
                self._publish_mobile_snapshot()
                return

            if command == "lock_live":
                self.mobile_bridge.lock_live()
                self.log("PUMA MOBILE", "LOCK", "-", "모바일 실전 기능 잠금")
                self.mobile_bridge.complete_command(
                    request_id, {"message": "실전 기능 잠금 완료"}
                )
                self._publish_mobile_snapshot()
                return

            if command == "auto_stop":
                self.stop_auto()
                self.mobile_bridge.complete_command(
                    request_id, {"message": "자동매매 중지 완료"}
                )
                self._publish_mobile_snapshot()
                return

            if command == "auto_start":
                if not self.mobile_bridge.live_unlocked:
                    raise PermissionError("모바일에서 실전 잠금을 최초 1회 해제하세요.")

                scope = str(data.get("scope") or "ALL").upper()
                if scope not in ("ALL", "SELECTED"):
                    raise ValueError("자동매매 대상 구분이 올바르지 않습니다.")

                self._apply_mobile_auto_settings(data)
                source = str(self.settings.candidate_source)

                if scope == "SELECTED":
                    code = str(data.get("code") or self.selected_code or "").strip()
                    name = str(data.get("name") or self.name_cache.get(code) or code).strip()
                    if not code:
                        raise ValueError("선택 종목이 없습니다.")
                    self.focus_only_code = code
                    if code != self.selected_code:
                        self.open_focus_stock(code, name or code)
                else:
                    self.focus_only_code = None
                    if source == "WATCHLIST" and not self.watchlist:
                        raise ValueError("관심종목이 없습니다.")
                    if source == "HERO4" and (not self.condition_thread or not self.condition_thread.isRunning()):
                        raise ValueError("영웅문 조건검색 실시간 연결을 먼저 시작하세요.")
                    if source == "BOTH":
                        active_hero = any(x.get("active") for x in self.condition_candidates.values())
                        if not self.watchlist and not active_hero:
                            raise ValueError("관심종목 또는 활성 조건검색 종목이 없습니다.")

                if isinstance(self.broker, KiwoomRestBroker) and self.broker.real:
                    try:
                        self.engine.sync_account(force=True)
                        self._refresh_position_rows()
                    except Exception as exc:
                        raise RuntimeError(f"실계좌 잔고 동기화 실패: {exc}") from exc

                self.engine.enabled = True
                self.timer.start()
                if scope == "SELECTED":
                    name = self.name_cache.get(self.focus_only_code) or self.selected_name or self.focus_only_code
                    self.log(name, "MOBILE AUTO", "-", "선택 종목 전용 자동매매 시작")
                    message = f"{name} 선택 종목 자동매매 시작"
                else:
                    self.log("SYSTEM", "MOBILE AUTO", "0", f"전체 후보 자동매매 시작 · {source}")
                    message = f"전체 후보 자동매매 시작 · {source}"

                self.mobile_bridge.complete_command(request_id, {"message": message})
                self._publish_mobile_snapshot()
                QTimer.singleShot(0, self.scan_one)
                return

            if command == "order":
                if not self.mobile_bridge.live_unlocked:
                    raise PermissionError("모바일에서 실전 잠금을 최초 1회 해제하세요.")
                side = str(data.get("side") or "").upper()
                code = str(data.get("code") or "").strip()
                qty = int(data.get("qty") or 0)
                order_type = str(data.get("order_type") or "market")
                price = int(float(data.get("price") or 0))
                cond_price = int(float(data.get("cond_price") or 0))
                if side not in ("BUY", "SELL"):
                    raise ValueError("매수/매도 구분이 올바르지 않습니다.")
                if not code or qty < 1 or qty > 10_000_000:
                    raise ValueError("종목코드 또는 주문수량이 올바르지 않습니다.")
                if order_type not in ("market", "limit", "stop_limit"):
                    raise ValueError("지원하지 않는 주문방식입니다.")
                if order_type == "limit" and price <= 0:
                    raise ValueError("지정가는 주문가격이 필요합니다.")
                if order_type == "stop_limit" and (price <= 0 or cond_price <= 0):
                    raise ValueError("스톱지정가는 가격과 조건가격이 필요합니다.")

                resp = self.broker.place_order(side, code, qty, order_type, price, cond_price)
                name = self.name_cache.get(code) or (
                    self.selected_name if code == self.selected_code else code
                )
                self.log(
                    name, f"MOBILE {side}",
                    f"{price:,}" if price else "시장가",
                    str(resp.get("return_msg", resp)),
                )
                self.mobile_bridge.complete_command(
                    request_id,
                    {
                        "message": str(resp.get("return_msg") or "주문 요청 처리"),
                        "ord_no": str(resp.get("ord_no") or ""),
                    },
                )
                self._publish_mobile_snapshot()
                return

            raise ValueError("지원하지 않는 모바일 명령입니다.")
        except Exception as exc:
            self.mobile_bridge.complete_command(request_id, error=str(exc))

    def closeEvent(self, event):
        if not self._closing:
            self._closing = True
            self._save_ui_layout()
            self.stop_auto()
            self.stop_condition_stream(block=True)
            self.stop_manual_condition_preview()
            self.name_lookup_timer.stop()
            self.mobile_publish_timer.stop()
            self.mobile_bridge.stop()
            if getattr(self, "strategy_widget", None) is not None:
                self.strategy_widget.close()
            self.classification_queue.clear()
            self.focus_analysis_pending = None
            self.danta_analysis_pending = False
            self._range_pending = None
        workers = list(self._focus_readers) + [self.focus_analysis_thread, self.danta_analysis_thread,
            self.classification_thread, self._name_worker, self._range_worker, self.auto_scan_thread]
        running = [w for w in workers if w is not None and w.isRunning()]
        for worker in running:
            worker.requestInterruption()
        if running:
            event.ignore()
            QTimer.singleShot(100, self.close)
        else:
            event.accept()
