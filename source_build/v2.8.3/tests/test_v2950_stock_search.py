from pathlib import Path

from puma_trader.broker import KiwoomRestBroker


class DummyStockListBroker:
    list_domestic_stocks = KiwoomRestBroker.list_domestic_stocks

    def __init__(self):
        self.calls = []

    def _post_page(self, path, api_id, body, cont_yn="", next_key=""):
        self.calls.append((path, api_id, dict(body)))
        market = body["mrkt_tp"]
        if market == "0":
            return {
                "list": [
                    {"code": "001520", "name": "동양", "marketName": "코스피"},
                    {"code": "005930", "name": "삼성전자", "marketName": "코스피"},
                ]
            }, "", ""
        if market == "10":
            return {
                "list": [
                    {"code": "123456", "name": "동양테크", "marketName": "코스닥"},
                ]
            }, "", ""
        if market == "8":
            return {
                "list": [
                    {"code": "069500", "name": "KODEX 200", "marketName": "ETF"},
                    {"code": "005930", "name": "삼성전자중복", "marketName": "ETF"},
                ]
            }, "", ""
        return {"list": []}, "", ""


def test_ka10099_universe_is_normalized_and_deduplicated():
    broker = DummyStockListBroker()
    rows = broker.list_domestic_stocks()
    by_code = {row["code"]: row for row in rows}
    assert {"001520", "005930", "123456", "069500"} <= set(by_code)
    assert len([row for row in rows if row["code"] == "005930"]) == 1
    assert all(call[1] == "ka10099" for call in broker.calls)
    assert {call[2]["mrkt_tp"] for call in broker.calls} == {"0", "10", "8"}


def test_integrated_trading_has_name_and_code_search():
    src = Path("puma_trader/ui.py").read_text(encoding="utf-8")
    assert "self.focus_stock_search = QLineEdit()" in src
    assert "종목명 또는 6자리 코드" in src
    assert "def search_focus_stock(self):" in src
    assert "StockUniverseThread" in src
    assert "self.open_focus_stock(query, name)" in src
    assert "n.startswith(q)" in src
    assert "q in n" in src


def test_stock_universe_worker_uses_isolated_reader():
    src = Path("puma_trader/chart_loader.py").read_text(encoding="utf-8")
    block = src[src.index("class StockUniverseThread"):]
    assert "reader_broker(self.broker" in block
    assert "list_domestic_stocks()" in block
