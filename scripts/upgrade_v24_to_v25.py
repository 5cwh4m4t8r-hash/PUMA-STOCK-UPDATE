from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
pkg = ROOT / "work" / "PUMA_STOCK_PRO_v2.4"
market_path = pkg / "puma_trader" / "market_path.py"
ui_path = pkg / "puma_trader" / "ui.py"
updater_path = pkg / "puma_trader" / "updater.py"

market = market_path.read_text(encoding="utf-8")
ui = ui_path.read_text(encoding="utf-8")
updater = updater_path.read_text(encoding="utf-8")

def once(text, old, new, label):
    if old not in text:
        raise RuntimeError(f"target not found: {label}")
    return text.replace(old, new, 1)

# ------------------------------------------------------------------
# market_path.py: candidate-first + shared LRU-style result cache
# ------------------------------------------------------------------
cache_block = r'''

# Heavy box detection is shared by SWING/LONG/UI enrichment.
# Cache exact candle/settings signatures so the same chart is not analyzed
# three or four times during one screen refresh.
_PATH_CACHE: dict[tuple, dict] = {}
_PATH_CACHE_ORDER: list[tuple] = []
_PATH_CACHE_MAX = 32


def clear_market_path_cache():
    _PATH_CACHE.clear()
    _PATH_CACHE_ORDER.clear()


def _settings_key(settings: Any) -> tuple:
    names = (
        "box_search_lookback", "box_width_pct", "box_min_coverage",
        "box_min_touches", "box_min_alternations", "box_touch_tolerance_pct",
        "box_max_drift_pct", "box_max_directionality",
        "breakout_volume_ratio", "pullback_volume_max_ratio",
        "pullback_base_volume_max_ratio", "pullback_support_tolerance_pct",
        "rebreak_volume_ratio", "path_max_pullback_bars",
        "path_duplicate_suppress_bars", "breakout_buffer_pct",
    )
    return tuple((name, _s(settings, name, None)) for name in names)


def _candles_key(candles: list[dict]) -> tuple:
    # O(n) cheap fingerprint. The old algorithm was far more expensive because
    # it sorted/scanned hundreds of candidate boxes for every candle.
    h = 1469598103934665603
    mask = (1 << 64) - 1
    for c in candles:
        item = (
            str(c.get("date", "")),
            round(float(c.get("open", 0) or 0), 4),
            round(float(c.get("high", 0) or 0), 4),
            round(float(c.get("low", 0) or 0), 4),
            round(float(c.get("close", 0) or 0), 4),
            int(float(c.get("volume", 0) or 0)),
        )
        h ^= hash(item) & mask
        h = (h * 1099511628211) & mask
    return (len(candles), h)


def _path_cache_get(key: tuple):
    return _PATH_CACHE.get(key)


def _path_cache_put(key: tuple, value: dict):
    if key in _PATH_CACHE:
        return
    _PATH_CACHE[key] = value
    _PATH_CACHE_ORDER.append(key)
    while len(_PATH_CACHE_ORDER) > _PATH_CACHE_MAX:
        old = _PATH_CACHE_ORDER.pop(0)
        _PATH_CACHE.pop(old, None)

'''
anchor = "def _s(settings: Any, name: str, default):\n"
idx = market.index(anchor)
# Insert cache helpers after _s function, not before it, because helpers call _s.
end_s = market.index("\n\ndef _quantile", idx)
market = market[:end_s] + cache_block + market[end_s:]

market = once(
    market,
    "def analyze_market_path(candles: list[dict], settings: Any=None) -> dict:\n",
    "def _analyze_market_path_uncached(candles: list[dict], settings: Any=None) -> dict:\n",
    "rename uncached analyzer",
)

old_loop = '''    events=[]
    recent_levels=[]

    for i in range(15,n):
        structure=_structure_before(candles,i-1,settings)
        if not structure:
            continue
        ok,info=_confirm_breakout(candles,i,structure,settings)
        if not ok:
            continue
'''
new_loop = '''    events=[]
    recent_levels=[]
    structure_cache: dict[int, dict | None] = {}

    def structure_at(end_idx: int):
        if end_idx not in structure_cache:
            structure_cache[end_idx] = _structure_before(candles, end_idx, settings)
        return structure_cache[end_idx]

    # PERFORMANCE CRITICAL:
    # The old v2.2~v2.4 code performed the expensive dynamic box search on
    # EVERY candle and checked volume afterwards. We invert that order.
    # Only a candle whose volume can possibly satisfy the 300% breakout rule
    # is allowed to run the box/resistance search.
    for i in range(15,n):
        strength, _, _ = _volume_strength(candles, i)
        if strength < breakout_req:
            continue

        structure=structure_at(i-1)
        if not structure:
            continue
        ok,info=_confirm_breakout(candles,i,structure,settings)
        if not ok:
            continue
'''
market = once(market, old_loop, new_loop, "candidate-first loop")

# Append cached public wrapper.
market += r'''


def analyze_market_path(candles: list[dict], settings: Any=None) -> dict:
    if not candles:
        return _analyze_market_path_uncached(candles, settings)

    key = (_candles_key(candles), _settings_key(settings))
    cached = _path_cache_get(key)
    if cached is not None:
        return cached

    result = _analyze_market_path_uncached(candles, settings)
    _path_cache_put(key, result)
    return result
'''

# ------------------------------------------------------------------
# ui.py: background REST fetch + reuse data; no network calls on UI thread
# ------------------------------------------------------------------
ui = once(ui, "from datetime import datetime\n", "from datetime import datetime\nimport time\n", "time import")

worker_anchor = "\n\nclass MainWindow(QMainWindow):\n"
worker_class = r'''

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

''' + worker_anchor
ui = once(ui, worker_anchor, worker_class, "background focus worker")

# MainWindow state.
state_anchor = '''        self.focus_range_label = "전체"

        self.timer = QTimer(self)
'''
state_new = '''        self.focus_range_label = "전체"

        # Non-blocking data loader / short-lived fetch cache.
        self.focus_load_thread: FocusDataThread | None = None
        self.focus_loading_code: str = ""
        self.focus_refresh_pending: bool = False
        self.focus_fetch_cache: dict[tuple[str, int], dict] = {}
        self.focus_data_code: str = ""
        self._strategy_refresh_after_focus: bool = False

        self.timer = QTimer(self)
'''
ui = once(ui, state_anchor, state_new, "focus worker state")

# Reuse already-loaded data in the separate day-trading tab instead of issuing
# the same REST calls again.
start = ui.index("    def strategy_refresh_selected(self):")
end = ui.index("\n    def open_focus_stock", start)
new_strategy_refresh = r'''    def strategy_refresh_selected(self):
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

'''
ui = ui[:start] + new_strategy_refresh + ui[end:]

# Replace blocking focus_refresh with async fetch + fast apply.
start = ui.index("    def focus_refresh(self):")
end = ui.index("\n    def _set_focus_date_bounds", start)
new_focus = r'''    def focus_refresh(self):
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

'''
ui = ui[:start] + new_focus + ui[end:]

# Skip redundant market-path computation when a strategy analyzer already
# supplied the same core_path arrays (SWING does this itself).
old_enrich_head = '''            # 모든 기법의 최상위 공통경로: 거래량 유입 -> 저항 돌파 -> 거래량 감소 눌림 -> 재돌파.
            path_bundle = analyze_market_path(series["candles"], self.swing_settings)
            series["core_path"] = path_bundle.get("current", {})
            series["path_breakout"] = path_bundle.get("path_breakout", [])
            series["path_pullback"] = path_bundle.get("path_pullback", [])
            series["path_rebreakout"] = path_bundle.get("path_rebreakout", [])
            if path_bundle.get("box") and not series.get("box"):
                series["box"] = path_bundle.get("box")
'''
new_enrich_head = '''            # 모든 기법의 최상위 공통경로.
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
'''
ui = once(ui, old_enrich_head, new_enrich_head, "reuse precomputed market path")

# Version note if present.
ui = ui.replace(
    "v2.4: 차트 상단의 EMA/기준선/파란점선/일목/수박 지표명 범례를 숨겨 차트를 정리. 분홍·파랑·빨강·검정 4종 화살표를 큰 화살표+흰 외곽선+개별 lane으로 그려 겹침과 검정배경 묻힘을 개선. 검정 화살표 발생식은 사용자 수식 전까지 임의 생성하지 않음.",
    "v2.5: 응답없음 성능 수정. 키움 시세/5분봉/일봉 REST 호출을 GUI 스레드에서 분리하고, 박스권 계산은 거래량 300% 후보봉에서만 실행. 동일 차트의 공통경로 결과를 캐시해 스윙/중장기/UI 중복계산과 단타탭 중복 REST 호출을 제거."
)

ui = ui.replace('self.setWindowTitle("PUMA STOCK PRO v2.4")', 'self.setWindowTitle("PUMA STOCK PRO v2.5")')
ui = ui.replace('title = QLabel("🐆  PUMA STOCK PRO  v2.4")', 'title = QLabel("🐆  PUMA STOCK PRO  v2.5")')

updater = once(updater, 'CURRENT_VERSION = "2.4.0"', 'CURRENT_VERSION = "2.5.0"', "updater version")
updater = updater.replace("PUMA-STOCK-UPDATER/2.4", "PUMA-STOCK-UPDATER/2.5")

market_path.write_text(market, encoding="utf-8")
ui_path.write_text(ui, encoding="utf-8")
updater_path.write_text(updater, encoding="utf-8")
(pkg / "puma_trader" / "__init__.py").write_text('__version__ = "2.5.0"\n', encoding="utf-8")
print("PUMA v2.5 performance patch applied")
