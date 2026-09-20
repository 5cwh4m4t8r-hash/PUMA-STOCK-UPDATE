from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
pkg = ROOT / "work" / "PUMA_STOCK_PRO_v2.5"
ui_path = pkg / "puma_trader" / "ui.py"
market_path = pkg / "puma_trader" / "market_path.py"
updater_path = pkg / "puma_trader" / "updater.py"

ui = ui_path.read_text(encoding="utf-8")
market = market_path.read_text(encoding="utf-8")
updater = updater_path.read_text(encoding="utf-8")

def once(text, old, new, label):
    if old not in text:
        raise RuntimeError(f"target not found: {label}")
    return text.replace(old, new, 1)

# ------------------------------------------------------------
# 1) Pure enrichment helper + CPU analysis QThreads
# ------------------------------------------------------------
anchor = "\n\nclass MainWindow(QMainWindow):\n"
helper = r'''

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
        ):
            path_bundle = {
                "current": series.get("core_path"),
                "path_breakout": series.get("path_breakout"),
                "path_pullback": series.get("path_pullback"),
                "path_rebreakout": series.get("path_rebreakout"),
                "box": series.get("box"),
            }
        else:
            path_bundle = analyze_market_path(series["candles"], swing_settings)
            series["core_path"] = path_bundle.get("current", {})
            series["path_breakout"] = path_bundle.get("path_breakout", [])
            series["path_pullback"] = path_bundle.get("path_pullback", [])
            series["path_rebreakout"] = path_bundle.get("path_rebreakout", [])
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
    except Exception as exc:
        analysis.details["PUMA 수박근사"] = f"계산 실패: {exc}"
        analysis.details["핵심 진입 신호"] = "계산 실패"
        analysis.details["유사구간 확률"] = "계산 불가"
        analysis.details["PUMA 판단"] = "판단 유보"

    return analysis, series


class FocusAnalysisThread(QThread):
    """Run ALL CPU-heavy chart analysis outside the GUI event loop."""
    analyzed = Signal(object)
    failed = Signal(str)

    def __init__(
        self, code: str, minute_rows, daily_rows, target_day: str,
        scan_start: str, scan_end: str, swing_settings, bowl_settings,
        tp: float, sl: float, parent=None
    ):
        super().__init__(parent)
        self.code = str(code)
        self.minute_rows = list(minute_rows or [])
        self.daily_rows = list(daily_rows or [])
        self.target_day = str(target_day or "")
        self.scan_start = str(scan_start)
        self.scan_end = str(scan_end)
        self.swing_settings = swing_settings
        self.bowl_settings = bowl_settings
        self.tp = float(tp)
        self.sl = float(sl)

    def run(self):
        try:
            out = {
                "code": self.code,
                "swing_analysis": None,
                "swing_series": None,
                "bowl_analysis": None,
                "bowl_series": None,
                "danta_analysis": None,
                "danta_series": None,
                "danta_day": "",
                "latest_danta_score": 0,
                "errors": [],
            }

            if self.daily_rows:
                try:
                    sa, ss = analyze_swing(self.daily_rows, self.swing_settings)
                    sa, ss = _enrich_analysis_pure(sa, dict(ss), "SWING", self.swing_settings, self.tp, self.sl)
                    out["swing_analysis"], out["swing_series"] = sa, ss
                except Exception as exc:
                    out["errors"].append(f"스윙: {exc}")

                try:
                    ba, bs = analyze_bowl(self.daily_rows, self.bowl_settings)
                    ba, bs = _enrich_analysis_pure(ba, dict(bs), "LONG", self.swing_settings, self.tp, self.sl)
                    out["bowl_analysis"], out["bowl_series"] = ba, bs
                except Exception as exc:
                    out["errors"].append(f"중장기: {exc}")

            if self.minute_rows:
                try:
                    da, ds, day = analyze_danta_for_date(
                        self.minute_rows,
                        self.daily_rows,
                        self.target_day or None,
                        scan_start=self.scan_start,
                        scan_end=self.scan_end,
                    )
                    da, ds = _enrich_analysis_pure(da, dict(ds), "DAY", self.swing_settings, self.tp, self.sl)
                    out["danta_analysis"], out["danta_series"], out["danta_day"] = da, ds, day

                    if not self.target_day:
                        out["latest_danta_score"] = int(getattr(da, "score", 0) or 0)
                    else:
                        latest, _, _ = analyze_danta_for_date(
                            self.minute_rows,
                            self.daily_rows,
                            None,
                            scan_start=self.scan_start,
                            scan_end=self.scan_end,
                        )
                        out["latest_danta_score"] = int(getattr(latest, "score", 0) or 0)
                except Exception as exc:
                    out["errors"].append(f"단타: {exc}")

            # Date list computation is also done here, not on the GUI thread.
            try:
                out["minute_days"] = available_minute_dates(self.minute_rows)
            except Exception:
                out["minute_days"] = []

            self.analyzed.emit(out)
        except Exception as exc:
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
        try:
            result, series, day = analyze_danta_for_date(
                self.minute_rows,
                self.daily_rows,
                self.target_day or None,
                scan_start=self.scan_start,
                scan_end=self.scan_end,
            )
            result, series = _enrich_analysis_pure(
                result, dict(series), "DAY", self.swing_settings, self.tp, self.sl
            )
            self.analyzed.emit({
                "code": self.code,
                "target_day": self.target_day,
                "analysis": result,
                "series": series,
                "day": day,
            })
        except Exception as exc:
            self.failed.emit(str(exc))

''' + anchor
ui = once(ui, anchor, helper, "analysis worker classes")

# ------------------------------------------------------------
# 2) State for CPU workers
# ------------------------------------------------------------
old_state = '''        self.focus_data_code: str = ""
        self._strategy_refresh_after_focus: bool = False

        self.timer = QTimer(self)
'''
new_state = '''        self.focus_data_code: str = ""
        self._strategy_refresh_after_focus: bool = False

        # CPU analysis workers. Heavy calculations never run in the GUI event loop.
        self.focus_analysis_thread: FocusAnalysisThread | None = None
        self.focus_analysis_pending: dict | None = None
        self.danta_analysis_thread: DantaAnalysisThread | None = None
        self.danta_analysis_pending: bool = False

        self.timer = QTimer(self)
'''
ui = once(ui, old_state, new_state, "analysis worker state")

# ------------------------------------------------------------
# 3) Existing UI enrichment method becomes a thin pure wrapper
# ------------------------------------------------------------
start = ui.index("    def _enrich_setup_stats(self, analysis, series: dict, strategy: str):")
end = ui.index("\n    def _sync_selected_stock_everywhere", start)
new_method = r'''    def _enrich_setup_stats(self, analysis, series: dict, strategy: str):
        tp = float(self.focus_tp.value()) if hasattr(self, "focus_tp") else float(self.settings.take_profit_pct)
        sl = abs(float(self.focus_sl.value())) if hasattr(self, "focus_sl") else abs(float(self.settings.stop_loss_pct))
        return _enrich_analysis_pure(
            analysis, series, strategy, self.swing_settings, tp, sl
        )

'''
ui = ui[:start] + new_method + ui[end:]

# ------------------------------------------------------------
# 4) Focus loading: REST worker -> CPU worker -> UI-only apply
# ------------------------------------------------------------
ui = ui.replace(
'''        cached = self.focus_fetch_cache.get(cache_key)
        if cached and time.time() - float(cached.get("loaded_at", 0)) <= 8.0:
            self._apply_focus_loaded(cached)
            return
''',
'''        cached = self.focus_fetch_cache.get(cache_key)
        if cached and time.time() - float(cached.get("loaded_at", 0)) <= 8.0:
            self._start_focus_analysis(cached)
            return
'''
)

start = ui.index("    def _focus_load_ready(self, payload):")
end = ui.index("\n    def _set_focus_date_bounds", start)
new_focus_block = r'''    def _focus_load_ready(self, payload):
        code = str(payload.get("code", ""))
        key = (code, int(payload.get("daily_pages", self.focus_history_pages)))
        self.focus_fetch_cache[key] = payload
        if len(self.focus_fetch_cache) > 12:
            oldest = min(
                self.focus_fetch_cache,
                key=lambda k: float(self.focus_fetch_cache[k].get("loaded_at", 0))
            )
            self.focus_fetch_cache.pop(oldest, None)

        if code != self.selected_code:
            return
        self._start_focus_analysis(payload)

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

        self.focus_minute_raw = list(payload.get("minute") or [])
        self.focus_daily_raw = list(payload.get("daily") or [])
        self.focus_data_code = code
        self.danta_raw_minute = list(self.focus_minute_raw)
        self.danta_raw_daily = list(self.focus_daily_raw)
        self.danta_cache_code = code

    def _start_focus_analysis(self, payload: dict):
        code = str(payload.get("code", "")).strip()
        if not code or code != self.selected_code:
            return

        self._apply_focus_metadata(payload)

        if self.focus_analysis_thread is not None and self.focus_analysis_thread.isRunning():
            # Keep only the newest request. Do not stack analysis jobs.
            self.focus_analysis_pending = payload
            self.focus_origin.setText("이전 분석 마무리 중 · 최신 종목 분석을 바로 이어서 실행합니다.")
            return

        self.focus_analysis_pending = None
        self.focus_origin.setText("지표·박스·돌파·눌림·확률을 백그라운드 분석 중... UI는 계속 사용 가능합니다.")

        swing_settings = self._swing_settings_from_ui()
        tp = float(self.focus_tp.value()) if hasattr(self, "focus_tp") else float(self.settings.take_profit_pct)
        sl = abs(float(self.focus_sl.value())) if hasattr(self, "focus_sl") else abs(float(self.settings.stop_loss_pct))

        worker = FocusAnalysisThread(
            code,
            payload.get("minute") or [],
            payload.get("daily") or [],
            self.intraday_selected_day or "",
            self.scan_start.time().toString("HH:mm"),
            self.scan_end.time().toString("HH:mm"),
            swing_settings,
            self.bowl_settings,
            tp,
            sl,
            self,
        )
        self.focus_analysis_thread = worker
        worker.analyzed.connect(self._focus_analysis_ready)
        worker.failed.connect(self._focus_analysis_failed)
        worker.finished.connect(self._focus_analysis_finished)
        worker.start()

    def _focus_analysis_failed(self, message: str):
        self.focus_origin.setText(f"분석 실패 · {message}")

    def _focus_analysis_finished(self):
        self.focus_analysis_thread = None
        pending = self.focus_analysis_pending
        self.focus_analysis_pending = None
        if pending and str(pending.get("code", "")) == self.selected_code:
            QTimer.singleShot(0, lambda p=pending: self._start_focus_analysis(p))

    def _set_intraday_days_fast(self, days):
        days = list(days or [])
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
        code = str(result.get("code", "")).strip()
        if not code or code != self.selected_code:
            return

        swing_analysis = result.get("swing_analysis")
        swing_series = result.get("swing_series")
        bowl_analysis = result.get("bowl_analysis")
        danta_analysis = result.get("danta_analysis")
        danta_series = result.get("danta_series")

        self._set_intraday_days_fast(result.get("minute_days") or [])

        if swing_analysis is not None and swing_series:
            self.focus_daily_analysis = swing_analysis
            self.focus_daily_series = swing_series
            self._set_focus_date_bounds()
        else:
            self.focus_daily_analysis = None
            self.focus_daily_series = None

        self.focus_bowl_analysis = bowl_analysis
        self.focus_danta_analysis = danta_analysis
        self.focus_danta_series = danta_series

        danta_label = self._pretty_intraday_day(result.get("danta_day") or self.intraday_selected_day) if danta_analysis else "최신"
        self._apply_focus_analyses(danta_analysis, swing_analysis, bowl_analysis, danta_label)

        if code in self.condition_candidates and (danta_analysis or swing_analysis or bowl_analysis):
            ds = int(result.get("latest_danta_score", 0) or 0)
            ss = int(getattr(swing_analysis, "score", 0) or 0) if swing_analysis else 0
            bs = int(getattr(bowl_analysis, "score", 0) or 0) if bowl_analysis else 0
            label, detail = classify_scores(ds, ss, bs)
            self._set_candidate_classification(code, label, detail, {"danta": ds, "swing": ss, "bowl": bs})

        self._update_focus_chart(False)
        day_count = len(self.focus_daily_series.get("candles", [])) if self.focus_daily_series else 0
        errors = result.get("errors") or []
        err_text = f" · 일부 분석: {' / '.join(errors)}" if errors else ""
        self.focus_origin.setText(
            f"유입: {self._source_for_code(code)} · 일봉 {day_count}봉 · 비동기 고속분석 완료 · "
            f"{datetime.now().strftime('%H:%M:%S')}{err_text}"
        )

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

'''
ui = ui[:start] + new_focus_block + ui[end:]

# ------------------------------------------------------------
# 5) Danta date/tab recomputes also backgrounded
# ------------------------------------------------------------
start = ui.index("    def _refresh_focus_danta_date(self):")
end = ui.index("\n    def _enrich_setup_stats", start)
new_danta_block = r'''    def _start_danta_background(self):
        if not self.focus_minute_raw:
            return

        if self.danta_analysis_thread is not None and self.danta_analysis_thread.isRunning():
            self.danta_analysis_pending = True
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
        self.danta_analysis_thread = worker
        worker.analyzed.connect(self._danta_background_ready)
        worker.failed.connect(self._danta_background_failed)
        worker.finished.connect(self._danta_background_finished)
        worker.start()

    def _danta_background_failed(self, message: str):
        if hasattr(self, "strategy_signal_label"):
            self.strategy_signal_label.setText(f"단타 분석 실패: {message}")

    def _danta_background_finished(self):
        self.danta_analysis_thread = None
        if self.danta_analysis_pending:
            self.danta_analysis_pending = False
            QTimer.singleShot(0, self._start_danta_background)

    def _danta_background_ready(self, payload: dict):
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

'''
ui = ui[:start] + new_danta_block + ui[end:]

# strategy tab fast path should render cached result without recomputing.
ui = ui.replace(
'''        if self.focus_data_code == code and self.focus_minute_raw:
            self.danta_raw_minute = list(self.focus_minute_raw)
            self.danta_raw_daily = list(self.focus_daily_raw)
            self.danta_cache_code = code
            self._populate_intraday_dates(self.danta_raw_minute)
            self._render_danta_detail_from_cache()
            return
''',
'''        if self.focus_data_code == code and self.focus_minute_raw:
            self.danta_raw_minute = list(self.focus_minute_raw)
            self.danta_raw_daily = list(self.focus_daily_raw)
            self.danta_cache_code = code
            if self.focus_danta_analysis is not None and not self.intraday_selected_day:
                self._render_danta_from_focus_cache()
            else:
                self._start_danta_background()
            return
'''
)

# ------------------------------------------------------------
# 6) Faster box search itself: coarse pass + local refinement
# ------------------------------------------------------------
old_find = '''def find_box_before(candles: list[dict], end_idx: int, settings: Any=None) -> dict | None:
    if end_idx < 9:
        return None
    lookback = max(30, min(400, int(_s(settings, "box_search_lookback", 160))))
    earliest = max(0, end_idx-lookback+1)

    best = None
    for end_lag in range(0, 4):
        e = end_idx-end_lag
        available = e-earliest+1
        for length in range(10, available+1, 2):
            start = e-length+1
            item = _evaluate_box(candles, start, e, settings)
            if not item:
                continue
            item["recency_lag"] = end_lag
            item["score"] -= end_lag*1.5
            if best is None or item["score"] > best["score"]+2:
                best = item
            elif best and abs(item["score"]-best["score"]) <= 2 and item["period"] > best["period"]:
                best = item
    return best
'''
new_find = '''def find_box_before(candles: list[dict], end_idx: int, settings: Any=None) -> dict | None:
    """Fast adaptive box finder.

    v2.4 evaluated virtually every even length for four end lags.
    v2.6 does a coarse scan, then refines around the best few candidates.
    The horizontal support/resistance tests themselves are unchanged.
    """
    if end_idx < 9:
        return None
    lookback = max(30, min(400, int(_s(settings, "box_search_lookback", 160))))
    earliest = max(0, end_idx-lookback+1)

    coarse_valid = []
    for end_lag in range(0, 3):
        e = end_idx-end_lag
        available = e-earliest+1
        if available < 10:
            continue

        # About 15-25 candidates instead of ~75 per end-lag.
        step = 8 if available >= 80 else 6 if available >= 50 else 4
        lengths = list(range(10, available+1, step))
        if available not in lengths:
            lengths.append(available)

        for length in lengths:
            start = e-length+1
            item = _evaluate_box(candles, start, e, settings)
            if not item:
                continue
            item["recency_lag"] = end_lag
            item["score"] -= end_lag*1.5
            coarse_valid.append(item)

    if not coarse_valid:
        return None

    coarse_valid.sort(key=lambda x: (float(x.get("score", 0)), int(x.get("period", 0))), reverse=True)
    seeds = coarse_valid[:3]
    best = seeds[0]

    # Refine only near the strongest coarse periods.
    seen = set()
    for seed in seeds:
        seed_len = int(seed["period"])
        for end_lag in range(max(0, int(seed.get("recency_lag", 0))-1), min(2, int(seed.get("recency_lag", 0))+1)+1):
            e = end_idx-end_lag
            available = e-earliest+1
            lo = max(10, seed_len-8)
            hi = min(available, seed_len+8)
            for length in range(lo, hi+1, 2):
                key = (end_lag, length)
                if key in seen:
                    continue
                seen.add(key)
                start = e-length+1
                item = _evaluate_box(candles, start, e, settings)
                if not item:
                    continue
                item["recency_lag"] = end_lag
                item["score"] -= end_lag*1.5
                if item["score"] > best["score"]+2:
                    best = item
                elif abs(item["score"]-best["score"]) <= 2 and item["period"] > best["period"]:
                    best = item
    return best
'''
market = once(market, old_find, new_find, "fast adaptive box finder")

# ------------------------------------------------------------
# 7) Version strings / release note
# ------------------------------------------------------------
ui = ui.replace('self.setWindowTitle("PUMA STOCK PRO v2.5")', 'self.setWindowTitle("PUMA STOCK PRO v2.6")')
ui = ui.replace('title = QLabel("🐆  PUMA STOCK PRO  v2.5")', 'title = QLabel("🐆  PUMA STOCK PRO  v2.6")')
ui = ui.replace(
    "v2.5: 응답없음 성능 수정. 키움 시세/5분봉/일봉 REST 호출을 GUI 스레드에서 분리하고, 박스권 계산은 거래량 300% 후보봉에서만 실행. 동일 차트의 공통경로 결과를 캐시해 스윙/중장기/UI 중복계산과 단타탭 중복 REST 호출을 제거.",
    "v2.6: 응답없음 2차 수정. REST뿐 아니라 스윙/중장기/단타/수박/확률/박스 CPU 분석 전체를 GUI 스레드 밖으로 이동. 날짜 변경 단타 재계산도 백그라운드 처리하며 박스 탐색은 coarse→refine 방식으로 추가 고속화."
)

updater = once(updater, 'CURRENT_VERSION = "2.5.0"', 'CURRENT_VERSION = "2.6.0"', "updater version")
updater = updater.replace("PUMA-STOCK-UPDATER/2.5", "PUMA-STOCK-UPDATER/2.6")

ui_path.write_text(ui, encoding="utf-8")
market_path.write_text(market, encoding="utf-8")
updater_path.write_text(updater, encoding="utf-8")
(pkg / "puma_trader" / "__init__.py").write_text('__version__ = "2.6.0"\n', encoding="utf-8")
print("PUMA v2.6 full non-blocking analysis patch applied")
