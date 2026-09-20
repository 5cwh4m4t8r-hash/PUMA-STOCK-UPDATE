from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
pkg = ROOT / "work" / "PUMA_STOCK_PRO_v1.2"
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

# ---------- version ----------
ui = once(ui, 'self.setWindowTitle("PUMA STOCK PRO v1.2")', 'self.setWindowTitle("PUMA STOCK PRO v1.3")', "window version")
ui = once(ui, 'title = QLabel("🐆  PUMA STOCK PRO  v1.2")', 'title = QLabel("🐆  PUMA STOCK PRO  v1.3")', "header version")

# ---------- name lookup responsiveness ----------
ui = once(
    ui,
    "        self.name_lookup_timer.setInterval(420)",
    "        self.name_lookup_timer.setInterval(320)",
    "name lookup interval",
)

# ---------- integrated condition table readability ----------
old_focus_table = """        self.focus_condition_table = QTableWidget(0, 4)
        self.focus_condition_table.setHorizontalHeaderLabels(["종목", "종목명", "분류", "상태"])
        hdr = self.focus_condition_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.focus_condition_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.focus_condition_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.focus_condition_table.cellClicked.connect(self._focus_condition_row_clicked)
        self.focus_condition_table.setMinimumWidth(200)
        self.focus_condition_table.setMaximumWidth(430)
"""
new_focus_table = """        self.focus_condition_table = QTableWidget(0, 4)
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
"""
ui = once(ui, old_focus_table, new_focus_table, "focus condition readability")

# Wider initial layout and adaptive profile.
ui = once(
    ui,
    "        self.focus_splitter.setSizes([230, 850, 400])",
    "        self.focus_splitter.setSizes([390, 760, 400])",
    "initial focus split",
)
ui = once(
    ui,
    """        if hasattr(self, "focus_splitter"):
            left = max(195, min(300, int(width * 0.15)))
            right = max(340, min(480, int(width * 0.25)))
            center = max(520, width - left - right - 90)
            self.focus_splitter.setSizes([left, center, right])
""",
    """        if hasattr(self, "focus_splitter"):
            # 종목명/분류가 잘리지 않도록 조건검색 패널을 우선 확보.
            left = max(360, min(500, int(width * 0.22)))
            right = max(330, min(470, int(width * 0.23)))
            center = max(500, width - left - right - 90)
            self.focus_splitter.setSizes([left, center, right])
""",
    "display profile focus width",
)

# ---------- full condition-search table readability ----------
old_hero_table = """        self.condition_table = QTableWidget(0, 6)
        self.condition_table.setHorizontalHeaderLabels(["종목코드", "종목명", "분류", "상태", "편입시각", "분석·매매"])
        self.condition_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.condition_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.condition_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.condition_table.cellClicked.connect(self._condition_row_clicked)
"""
new_hero_table = """        self.condition_table = QTableWidget(0, 6)
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
"""
ui = once(ui, old_hero_table, new_hero_table, "hero table readability")

# ---------- classifier also resolves stock name ----------
old_payload = """    def run(self):
        payload = {"classification": "분석실패", "detail": "-", "danta": 0, "swing": 0, "bowl": 0}
        try:
            minute = self.broker.get_minute_candles(self.code, 5)
"""
new_payload = """    def run(self):
        payload = {"classification": "분석실패", "detail": "-", "danta": 0, "swing": 0, "bowl": 0, "name": ""}
        try:
            try:
                info = self.broker.get_stock_info(self.code)
                payload["name"] = str(info.get("stk_nm") or info.get("name") or "").strip()
            except Exception:
                pass
            minute = self.broker.get_minute_candles(self.code, 5)
"""
ui = once(ui, old_payload, new_payload, "classifier name lookup")

old_on_classified = """    def _on_candidate_classified(self, code: str, payload: object):
        data = payload if isinstance(payload, dict) else {}
        self._set_candidate_classification(
            code,
            str(data.get("classification") or "분석실패"),
            str(data.get("detail") or "-"),
            {"danta": data.get("danta", 0), "swing": data.get("swing", 0), "bowl": data.get("bowl", 0)},
        )
"""
new_on_classified = """    def _on_candidate_classified(self, code: str, payload: object):
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
"""
ui = once(ui, old_on_classified, new_on_classified, "apply classifier name")

# Queue name lookup before heavier classification so names become readable first.
ui = once(
    ui,
    """            self._upsert_condition_row(code)
            self._ensure_market_row(code, name or code, "영웅문4")
            self._queue_candidate_classification(code)
            if not name or name == code:
                self._queue_name_lookup(code)
""",
    """            self._upsert_condition_row(code)
            self._ensure_market_row(code, name or code, "영웅문4")
            if not name or name == code:
                self._queue_name_lookup(code)
            self._queue_candidate_classification(code)
""",
    "snapshot name priority",
)
ui = once(
    ui,
    """        self._upsert_condition_row(code)
        self._ensure_market_row(code, name or old_name or code, "영웅문4")
        self._queue_candidate_classification(code)
        if not name or name == code:
            self._queue_name_lookup(code)
""",
    """        self._upsert_condition_row(code)
        self._ensure_market_row(code, name or old_name or code, "영웅문4")
        if not name or name == code:
            self._queue_name_lookup(code)
        self._queue_candidate_classification(code)
""",
    "entry name priority",
)

# Immediate first lookup instead of always waiting for timer interval.
ui = once(
    ui,
    """        self.name_lookup_queue.append(code)
        if not self.name_lookup_timer.isActive():
            self.name_lookup_timer.start()
""",
    """        self.name_lookup_queue.append(code)
        if not self.name_lookup_timer.isActive():
            self.name_lookup_timer.start()
            QTimer.singleShot(0, self._resolve_next_name)
""",
    "immediate name lookup",
)

# ---------- name cells: bold, white, full tooltip ----------
old_display = """        display_name = item.get("name", "")
        self.condition_table.item(row, 0).setText(code)
        self.condition_table.item(row, 1).setText(display_name if display_name and display_name != code else "조회중...")
        self.condition_table.item(row, 2).setText(classification)
"""
new_display = """        display_name = str(item.get("name", "") or "").strip()
        readable_name = display_name if display_name and display_name != code else "종목명 조회중…"
        self.condition_table.item(row, 0).setText(code)
        name_cell = self.condition_table.item(row, 1)
        name_cell.setText(readable_name)
        name_cell.setToolTip(readable_name)
        name_cell.setFont(QFont("Malgun Gothic", 10, QFont.Bold))
        name_cell.setForeground(QColor("#f3f8ff"))
        self.condition_table.item(row, 2).setText(classification)
"""
ui = once(ui, old_display, new_display, "hero name cell")

old_focus_display = """            self.focus_condition_table.item(frow, 0).setText(code)
            self.focus_condition_table.item(frow, 1).setText(display_name if display_name and display_name != code else "조회중...")
            self.focus_condition_table.item(frow, 2).setText(classification)
"""
new_focus_display = """            self.focus_condition_table.item(frow, 0).setText(code)
            fname = self.focus_condition_table.item(frow, 1)
            fname.setText(readable_name)
            fname.setToolTip(readable_name)
            fname.setFont(QFont("Malgun Gothic", 10, QFont.Bold))
            fname.setForeground(QColor("#f3f8ff"))
            self.focus_condition_table.item(frow, 2).setText(classification)
"""
ui = once(ui, old_focus_display, new_focus_display, "focus name cell")

# Click handler understands new loading text.
ui = ui.replace('name if name != "조회중..." else code', 'name if "조회중" not in name else code')

# ---------- update note ----------
ui = ui.replace(
    "v1.2: 단타 5분봉은 유지하면서 거래일별 선택/복기, 전일·다음일 이동, 전체보기 날짜 구분선, 과거 날짜 분석 시 미래 데이터 차단을 추가.",
    "v1.3: 일봉에는 날짜 경계선을 표시하지 않도록 정리하고, 조건검색 종목명 열 폭/글꼴/조회 우선순위를 개선해 종목명이 확실히 보이도록 수정.",
)

# ---------- chart: date separators only for true intraday data ----------
old_sep = """        visible_days = [day_key(c.get('date', '')) for c in cs]
        unique_days = [d for i, d in enumerate(visible_days) if d and (i == 0 or d != visible_days[i-1])]
        if len(unique_days) > 1:
"""
new_sep = """        visible_days = [day_key(c.get('date', '')) for c in cs]
        unique_days = [d for i, d in enumerate(visible_days) if d and (i == 0 or d != visible_days[i-1])]
        # 일봉은 날짜 경계선을 그리지 않는다. 같은 거래일에 여러 봉이 존재하는 분봉에서만 표시.
        valid_days = [d for d in visible_days if d]
        is_intraday = len(valid_days) > len(set(valid_days))
        if is_intraday and len(unique_days) > 1:
"""
chart = once(chart, old_sep, new_sep, "intraday-only date separators")

# ---------- versions ----------
updater = once(updater, 'CURRENT_VERSION = "1.2.0"', 'CURRENT_VERSION = "1.3.0"', "updater version")
updater = updater.replace("PUMA-STOCK-UPDATER/1.2", "PUMA-STOCK-UPDATER/1.3")

ui_path.write_text(ui, encoding="utf-8")
chart_path.write_text(chart, encoding="utf-8")
updater_path.write_text(updater, encoding="utf-8")
(pkg / "puma_trader" / "__init__.py").write_text('__version__ = "1.3.0"\n', encoding="utf-8")
print("PUMA v1.3 readability patch applied")
