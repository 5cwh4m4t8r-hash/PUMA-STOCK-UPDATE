from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ui_path = ROOT / "work" / "PUMA_STOCK_PRO_v0.7" / "puma_trader" / "ui.py"
app_path = ROOT / "work" / "PUMA_STOCK_PRO_v0.7" / "app.py"
updater_path = ROOT / "work" / "PUMA_STOCK_PRO_v0.7" / "puma_trader" / "updater.py"
init_path = ROOT / "work" / "PUMA_STOCK_PRO_v0.7" / "puma_trader" / "__init__.py"

def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"v0.8 patch target not found: {label}")
    return text.replace(old, new, 1)

ui = ui_path.read_text(encoding="utf-8")
app = app_path.read_text(encoding="utf-8")
updater = updater_path.read_text(encoding="utf-8")
init = init_path.read_text(encoding="utf-8")

# ----- version / resolution profile -----
ui = replace_once(ui, 'self.setWindowTitle("PUMA STOCK PRO v0.7")', 'self.setWindowTitle("PUMA STOCK PRO v0.8")', "window version")
ui = replace_once(ui, 'self.resize(1560, 950)', 'self.setMinimumSize(1024, 680)\\n        self.resize(1280, 800)', "window geometry")
ui = replace_once(ui, 'title = QLabel("🐆  PUMA STOCK PRO  v0.7")', 'title = QLabel("🐆  PUMA STOCK PRO  v0.8")', "header version")
ui = replace_once(ui, 'QTabBar::tab { background:#13253b; padding:9px 18px; margin-right:2px; }',
                  'QTabBar::tab { background:#13253b; padding:7px 11px; margin-right:2px; }',
                  "compact tabs")

# Add splitter import.
ui = replace_once(ui, '    QSpinBox,\\n    QTabWidget,',
                  '    QSpinBox,\\n    QSplitter,\\n    QTabWidget,',
                  "QSplitter import")

# Keep explicit widget refs so every tab can react to the same selected stock.
old_tabs = '''        self.tabs = QTabWidget()
        self.focus_widget = self._focus_tab()
        self.tabs.addTab(self.focus_widget, "통합 트레이딩")
        self.tabs.addTab(self._hero_tab(), "조건검색")
        self.tabs.addTab(self._dashboard_tab(), "잔고 · 로그")
        self.tabs.addTab(self._strategy_tab(), "전략 상세설정")
        self.tabs.addTab(self._manual_order_tab(), "고급 주문")
        self.tabs.addTab(self._swing_tab(), "역매공파 상세")
        self.connection_widget = self._connection_tab()
        self.tabs.addTab(self.connection_widget, "설정 · 키움연결")
        self.tabs.addTab(self._update_tab(), "업데이트")
        outer.addWidget(self.tabs)
'''
new_tabs = '''        self.tabs = QTabWidget()
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
'''
ui = replace_once(ui, old_tabs, new_tabs, "tab refs")

# ----- integrated screen: stable 3-column splitter -----
ui = replace_once(ui, '        body = QHBoxLayout()\\n\\n        candidates = QGroupBox("조건검색 결과")',
                  '        body = QHBoxLayout()\\n        self.focus_splitter = QSplitter(Qt.Horizontal)\\n\\n        candidates = QGroupBox("조건검색 결과")',
                  "focus splitter start")
ui = replace_once(ui, '        self.focus_condition_table.setMinimumWidth(280)',
                  '        self.focus_condition_table.setMinimumWidth(210)\\n        self.focus_condition_table.setMaximumWidth(340)',
                  "condition width")
ui = replace_once(ui, '        body.addWidget(candidates, 1)\\n\\n        left = QVBoxLayout()',
                  '        self.focus_splitter.addWidget(candidates)\\n\\n        left_panel = QWidget()\\n        left = QVBoxLayout(left_panel)\\n        left.setContentsMargins(0, 0, 0, 0)',
                  "left panel")
ui = replace_once(ui, '        body.addLayout(left, 4)\\n\\n        right = QVBoxLayout()',
                  '        self.focus_splitter.addWidget(left_panel)\\n\\n        right_panel = QWidget()\\n        right = QVBoxLayout(right_panel)\\n        right.setContentsMargins(0, 0, 0, 0)',
                  "right panel")
ui = replace_once(ui, '        body.addLayout(right, 2)\\n        root.addLayout(body, 1)',
                  '''        self.focus_splitter.addWidget(right_panel)
        self.focus_splitter.setCollapsible(0, False)
        self.focus_splitter.setCollapsible(1, False)
        self.focus_splitter.setCollapsible(2, False)
        self.focus_splitter.setStretchFactor(0, 1)
        self.focus_splitter.setStretchFactor(1, 5)
        self.focus_splitter.setStretchFactor(2, 2)
        self.focus_splitter.setSizes([240, 820, 360])
        body.addWidget(self.focus_splitter)
        root.addLayout(body, 1)''',
                  "splitter finish")

# ----- strategy detail gets live selected-stock banner -----
ui = replace_once(ui, '''    def _strategy_tab(self):
        w = QWidget()
        main = QHBoxLayout(w)

        buy = QGroupBox("매수 조건 · PUMA 2차 필터")
''',
'''    def _strategy_tab(self):
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
''',
"strategy selected banner")

# ----- swing detail also shows linkage -----
ui = replace_once(ui,
'''        title = QLabel("역매공파 SWING · 장기 EMA 역배열 → 매집봉/구간 → 공구리 → 상단 돌파/안착 → 파란점선 → 수박/화살표")
        title.setStyleSheet("font-size:16px;font-weight:800;color:#8dc7ff")
        top.addWidget(title)
        top.addStretch()
''',
'''        title = QLabel("역매공파 SWING · 장기 EMA 역배열 → 매집봉/구간 → 공구리 → 상단 돌파/안착 → 파란점선 → 수박/화살표")
        title.setStyleSheet("font-size:16px;font-weight:800;color:#8dc7ff")
        self.swing_selected_label = QLabel("연동: 선택종목 없음")
        self.swing_selected_label.setStyleSheet("font-weight:800;color:#61ff8f")
        top.addWidget(title)
        top.addWidget(self.swing_selected_label)
        top.addStretch()
''',
"swing selected banner")

# Critical bug: integrated condition result used a non-existent method.
ui = replace_once(ui, '        self.open_focus(code, name if name != "조회중..." else code)',
                  '        self.open_focus_stock(code, name if name != "조회중..." else code)',
                  "integrated click target")

# When name lookup finishes, propagate it to every screen.
ui = replace_once(ui, '''                if self.selected_code == code:
                    self.selected_name = name
                    self.focus_title.setText(f"{name}  {code}")
''',
'''                if self.selected_code == code:
                    self.selected_name = name
                    self.focus_title.setText(f"{name}  {code}")
                    self._sync_selected_stock_everywhere()
''',
"name sync")

# Inject cross-tab stock synchronization helpers.
anchor = '''    def open_focus_stock(self, code: str, name: str = ""):
'''
helpers = '''    def _sync_selected_stock_everywhere(self):
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
                text = "매수조건 충족" if sig.passed else sig.reason
                color = "#61ff8f" if sig.passed else "#f4c95d"
                self.strategy_signal_label.setText(f"{tf}분봉 · {text}")
                self.strategy_signal_label.setStyleSheet(f"font-weight:900;color:{color}")
            else:
                self.strategy_signal_label.setText(f"{tf}분봉 · 데이터 없음")
        except Exception as exc:
            self.strategy_signal_label.setText(f"{name} · 분석 실패: {exc}")
            self.strategy_signal_label.setStyleSheet("font-weight:800;color:#ff7b83")

''' + anchor
ui = replace_once(ui, anchor, helpers, "sync helpers")

# Selecting a stock updates every tab immediately, then refreshes data without blocking the click handler.
ui = replace_once(ui, '''        self.selected_code = code
        self.selected_name = self.name_cache.get(code) or (name if name and name != code else code)
        self.focus_title.setText(f"{self.selected_name}  {code}")
''',
'''        self.selected_code = code
        self.selected_name = self.name_cache.get(code) or (name if name and name != code else code)
        self.focus_title.setText(f"{self.selected_name}  {code}")
        self._sync_selected_stock_everywhere()
''',
"open stock sync")
ui = replace_once(ui, '''        self.tabs.setCurrentWidget(self.focus_widget)
        QApplication.processEvents()
        self.focus_refresh()
''',
'''        self.tabs.setCurrentWidget(self.focus_widget)
        QApplication.processEvents()
        QTimer.singleShot(0, self.focus_refresh)
''',
"nonblocking focus refresh")

# Refresh result also pushes latest name/current price into other linked tabs.
ui = replace_once(ui, '''            self.focus_title.setText(f"{name}  {code}")
            self.focus_price.setText(f"{price:,.0f} 원" if price else "-")
            if price and self.focus_order_price.value() == 0:
                self.focus_order_price.setValue(int(price))
''',
'''            self.selected_name = name or self.selected_name or code
            self.focus_title.setText(f"{self.selected_name}  {code}")
            self.focus_price.setText(f"{price:,.0f} 원" if price else "-")
            self._sync_selected_stock_everywhere()
            if hasattr(self, "manual_current"):
                self.manual_current.setText(f"{price:,.0f} 원" if price else "-")
            if price and hasattr(self, "manual_price") and self.manual_price.value() == 0:
                self.manual_price.setValue(int(price))
            if price and self.focus_order_price.value() == 0:
                self.focus_order_price.setValue(int(price))
''',
"refresh cross tab sync")

# Swing tab: automatic linkage can load silently; manual button keeps dialogs.
ui = replace_once(ui, '    def swing_load_kiwoom(self):',
                  '    def swing_load_kiwoom(self, silent: bool = False):',
                  "swing silent signature")
ui = replace_once(ui, '''        if not code:
            QMessageBox.warning(self, "종목코드", "종목코드를 입력하세요.")
            return
''',
'''        if not code:
            if not silent:
                QMessageBox.warning(self, "종목코드", "종목코드를 입력하세요.")
            return
''',
"swing empty code")
ui = replace_once(ui, '''        if not getter:
            QMessageBox.information(self, "키움 연결 필요", "키움 연결 탭에서 REST API를 먼저 연결하세요.\\nSIMULATION에서는 데모 차트를 사용하세요.")
            return
''',
'''        if not getter:
            if not silent:
                QMessageBox.information(self, "키움 연결 필요", "키움 연결 탭에서 REST API를 먼저 연결하세요.\\nSIMULATION에서는 데모 차트를 사용하세요.")
            return
''',
"swing no broker")
ui = replace_once(ui, '''        except Exception as exc:
            self.conn_label.setText("● 조회 실패")
            QMessageBox.critical(self, "키움 일봉 조회 실패", str(exc))
''',
'''        except Exception as exc:
            self.conn_label.setText("● 조회 실패")
            if not silent:
                QMessageBox.critical(self, "키움 일봉 조회 실패", str(exc))
''',
"swing silent error")

# v0.8 updater notes.
ui = ui.replace("v0.7: 통합 트레이딩 화면 + 키움 보안저장/자동연결 + 빠른연결이 추가되었습니다.",
                "v0.8: 해상도 최적화 + 통합/전략상세/역매공파/고급주문 선택종목 실시간 연동 + 종목 클릭 버그 수정.")

# App always opens maximized to the current Windows working area; Qt keeps DPI scaling native.
app = replace_once(app, "    win.show()", "    win.showMaximized()", "maximized startup")

# Version metadata.
updater = replace_once(updater, 'CURRENT_VERSION = "0.7.0"', 'CURRENT_VERSION = "0.8.0"', "updater version")
updater = updater.replace("PUMA-STOCK-UPDATER/0.7", "PUMA-STOCK-UPDATER/0.8")
init = init.replace('__version__ = "0.7.0"', '__version__ = "0.8.0"')

ui_path.write_text(ui, encoding="utf-8")
app_path.write_text(app, encoding="utf-8")
updater_path.write_text(updater, encoding="utf-8")
init_path.write_text(init, encoding="utf-8")
print("v0.8 source patch applied")
