from __future__ import annotations

import random
import time
from datetime import datetime, timedelta
from typing import Dict, List

import requests
from .performance import ChartRequestGate, AnalysisCancelled


class BrokerError(RuntimeError):
    pass


class BaseBroker:
    name = "BASE"
    is_live = False

    def connect(self):
        return True

    def get_minute_candles(self, code: str, timeframe: int, max_pages: int = 1, base_dt: str | None = None) -> List[dict]:
        raise NotImplementedError

    def buy_market(self, code: str, qty: int) -> dict:
        raise NotImplementedError

    def sell_market(self, code: str, qty: int) -> dict:
        raise NotImplementedError

    def place_order(self, side: str, code: str, qty: int, order_type: str = "market", price: int = 0, cond_price: int = 0) -> dict:
        raise NotImplementedError

    def get_best_quote(self, code: str, exchange: str = "KRX") -> dict:
        return {}

    def cancel_order_on(self, code: str, orig_ord_no: str, exchange: str, qty: int = 0) -> dict:
        raise NotImplementedError

    def get_account_positions(self) -> list[dict]:
        return []


class SimBroker(BaseBroker):
    name = "SIMULATION"
    is_live = False

    def __init__(self):
        self._series: Dict[str, List[dict]] = {}
        self._seq = 1000

    def _ensure(self, code):
        if code in self._series:
            return
        seed = sum(ord(c) for c in code)
        rnd = random.Random(seed)
        price = max(1000, 40000 + (seed % 170000))
        now = datetime.now().replace(second=0, microsecond=0)
        rows = []
        for i in range(100):
            t = now - timedelta(minutes=(99 - i) * 5)
            drift = 0.0006 + rnd.uniform(-0.004, 0.005)
            op = price
            cl = max(100, op * (1 + drift))
            hi = max(op, cl) * (1 + rnd.uniform(0, 0.002))
            lo = min(op, cl) * (1 - rnd.uniform(0, 0.002))
            vol = int(20000 + rnd.random() * 180000)
            rows.append({
                "cur_prc": str(int(cl)),
                "open_pric": str(int(op)),
                "high_pric": str(int(hi)),
                "low_pric": str(int(lo)),
                "trde_qty": str(vol),
                "cntr_tm": t.strftime("%Y%m%d%H%M%S"),
            })
            price = cl
        self._series[code] = rows

    def get_minute_candles(self, code: str, timeframe: int, max_pages: int = 1, base_dt: str | None = None):
        self._ensure(code)
        rows = self._series[code]
        last = rows[-1]
        p = float(last["cur_prc"])
        p2 = max(100, p * (1 + random.uniform(-0.004, 0.008)))
        vol = int(float(last["trde_qty"]) * random.uniform(0.7, 2.8))
        row = {
            "cur_prc": str(int(p2)),
            "open_pric": last["cur_prc"],
            "high_pric": str(int(max(p, p2) * 1.001)),
            "low_pric": str(int(min(p, p2) * 0.999)),
            "trde_qty": str(vol),
            "cntr_tm": datetime.now().strftime("%Y%m%d%H%M%S"),
        }
        rows.append(row)
        self._series[code] = rows[-120:]
        return list(reversed(self._series[code]))

    def buy_market(self, code: str, qty: int):
        self._seq += 1
        return {"ord_no": f"SIM-B-{self._seq}", "return_code": 0, "return_msg": "모의 매수 체결"}

    def sell_market(self, code: str, qty: int):
        self._seq += 1
        return {"ord_no": f"SIM-S-{self._seq}", "return_code": 0, "return_msg": "모의 매도 체결"}

    def place_order(self, side: str, code: str, qty: int, order_type: str = "market", price: int = 0, cond_price: int = 0):
        self._seq += 1
        tag = "B" if side.upper() == "BUY" else "S"
        return {"ord_no": f"SIM-{tag}-{self._seq}", "return_code": 0,
                "return_msg": f"SIM {side.upper()} {order_type} 주문 접수"}


class KiwoomRestBroker(BaseBroker):
    """키움 REST API 연결부.

    App Key/Secret은 설정 파일에 저장하지 않으며 실행 중 메모리에만 둔다.
    실전(real=True)일 때만 운영 서버로 주문이 전송된다.
    """

    name = "KIWOOM REST"
    REAL_HOST = "https://api.kiwoom.com"
    MOCK_HOST = "https://mockapi.kiwoom.com"

    def __init__(self, app_key: str, app_secret: str, real: bool = False, order_exchange: str = "KRX"):
        self.app_key = app_key.strip()
        self.app_secret = app_secret.strip()
        self.real = bool(real)
        self.is_live = bool(real)
        self.host = self.REAL_HOST if real else self.MOCK_HOST
        self.order_exchange = order_exchange if order_exchange in ("KRX", "NXT", "SOR") else "KRX"
        self.token = ""
        self.token_expire_epoch = 0.0
        self.session = requests.Session()
        self._chart_gate = ChartRequestGate()
        self._chart_cancelled = lambda: False
        self.last_account_balance_summary: dict = {}
        self.last_account_positions_snapshot: list[dict] = []

    def connect(self):
        if not self.app_key or not self.app_secret:
            raise BrokerError("App Key / App Secret을 입력하세요.")
        self._ensure_token(force=True)
        return True

    def _ensure_token(self, force=False):
        if not force and self.token and time.time() < self.token_expire_epoch - 300:
            return
        url = self.host + "/oauth2/token"
        body = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "secretkey": self.app_secret,
        }
        try:
            r = self.session.post(
                url,
                json=body,
                headers={"Content-Type": "application/json;charset=UTF-8"},
                timeout=10,
            )
            r.raise_for_status()
            data = r.json()
        except requests.RequestException as exc:
            raise BrokerError(f"키움 인증 통신 실패: {exc}") from exc
        if data.get("return_code") not in (None, 0):
            raise BrokerError(data.get("return_msg", "토큰 발급 실패"))
        self.token = data.get("token", "")
        if not self.token:
            raise BrokerError("접근 토큰이 없습니다.")
        # 만료일 파싱에 실패해도 보수적으로 23시간 후 재발급
        expires_dt = str(data.get("expires_dt", "")).strip()
        try:
            dt = datetime.strptime(expires_dt, "%Y%m%d%H%M%S")
            self.token_expire_epoch = dt.timestamp()
        except Exception:
            self.token_expire_epoch = time.time() + 23 * 3600

    def _post_page(self, path: str, api_id: str, body: dict, cont_yn: str = "", next_key: str = ""):
        if path in ("/api/dostk/chart", "/api/dostk/stkinfo"):
            self._chart_gate.wait(self._chart_cancelled)
        self._ensure_token()
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "authorization": f"Bearer {self.token}",
            "api-id": api_id,
        }
        if cont_yn:
            headers["cont-yn"] = cont_yn
        if next_key:
            headers["next-key"] = next_key
        try:
            r = self.session.post(self.host + path, json=body, headers=headers, timeout=10)
            r.raise_for_status()
            data = r.json()
        except requests.RequestException as exc:
            raise BrokerError(f"키움 {api_id} 통신 실패: {exc}") from exc
        if data.get("return_code") not in (None, 0):
            raise BrokerError(data.get("return_msg", f"{api_id} 호출 실패"))
        return data, r.headers.get("cont-yn", ""), r.headers.get("next-key", "")

    def _post(self, path: str, api_id: str, body: dict):
        data, _, _ = self._post_page(path, api_id, body)
        return data

    def iter_chart_pages(self, code, kind, max_pages, *, timeframe=5, base_dt=None, cancelled=lambda: False):
        """Yield immutable cumulative snapshots; stop obsolete work between requests."""
        is_minute = kind == "minute"
        body = {"stk_cd": code, "upd_stkpc_tp": "1",
                "base_dt": base_dt or datetime.now().strftime("%Y%m%d")}
        if is_minute:
            body["tic_scope"] = str(timeframe)
        api_id = "ka10080" if is_minute else "ka10081"
        field = "stk_min_pole_chart_qry" if is_minute else "stk_dt_pole_chart_qry"
        limit = max(1, min(10 if is_minute else 30, int(max_pages or 1)))
        rows, seen, continuation_keys = [], set(), set()
        cont_yn = next_key = ""
        for page in range(limit):
            if cancelled():
                raise AnalysisCancelled()
            data, cont_yn, next_key = self._post_page("/api/dostk/chart", api_id, body, cont_yn, next_key)
            if cancelled():
                raise AnalysisCancelled()
            part = data.get(field, [])
            if isinstance(part, list):
                for row in part:
                    if not isinstance(row, dict):
                        continue
                    key = str(row.get("cntr_tm") or row.get("dt") or row.get("date") or "")
                    if key and key in seen:
                        continue
                    if key:
                        seen.add(key)
                    rows.append(row)
            has_more = cont_yn == "Y" and bool(next_key) and next_key not in continuation_keys
            if next_key:
                continuation_keys.add(next_key)
            complete = not has_more or page + 1 == limit
            yield list(rows), complete
            if complete:
                break

    def get_minute_candles(self, code: str, timeframe: int, max_pages: int = 1, base_dt: str | None = None):
        rows = []
        for rows, _ in self.iter_chart_pages(code, "minute", max_pages, timeframe=timeframe, base_dt=base_dt):
            pass
        return rows

    def get_minute_candles_for_exchange(
        self,
        code: str,
        timeframe: int,
        exchange: str,
        max_pages: int = 1,
        base_dt: str | None = None,
    ):
        """Request venue-specific minute bars using Kiwoom's documented code suffix.

        KRX: 039490, NXT: 039490_NX, SOR(integrated): 039490_AL.
        """
        base = str(code or "").strip()
        if "_" in base:
            base = base.split("_", 1)[0]
        ex = str(exchange or "KRX").upper()
        chart_code = base
        if ex == "NXT":
            chart_code = f"{base}_NX"
        elif ex == "SOR":
            chart_code = f"{base}_AL"
        return self.get_minute_candles(chart_code, timeframe, max_pages=max_pages, base_dt=base_dt)

    @staticmethod
    def _venue_code(code: str, exchange: str) -> str:
        base = str(code or "").strip()
        if "_" in base:
            base = base.split("_", 1)[0]
        ex = str(exchange or "KRX").upper()
        if ex == "NXT":
            return f"{base}_NX"
        if ex == "SOR":
            return f"{base}_AL"
        return base

    @staticmethod
    def _abs_int(raw) -> int:
        try:
            return abs(int(float(str(raw or "0").replace(",", "").strip())))
        except Exception:
            return 0

    def get_best_quote(self, code: str, exchange: str = "KRX") -> dict:
        """Return the venue's best ask/bid from official ka10004 quote book."""
        ex = str(exchange or "KRX").upper()
        if ex not in ("KRX", "NXT", "SOR"):
            raise BrokerError(f"지원하지 않는 호가 거래소: {exchange}")
        quote_code = self._venue_code(code, ex)
        data = self._post("/api/dostk/mrkcond", "ka10004", {"stk_cd": quote_code})
        return {
            "exchange": ex,
            "code": str(code or "").split("_", 1)[0],
            "quote_code": quote_code,
            "best_ask": self._abs_int(data.get("sel_fpr_bid")),
            "best_ask_qty": self._abs_int(data.get("sel_fpr_req")),
            "best_bid": self._abs_int(data.get("buy_fpr_bid")),
            "best_bid_qty": self._abs_int(data.get("buy_fpr_req")),
            "quote_time": str(data.get("bid_req_base_tm") or ""),
        }

    def place_limit_on(self, side: str, code: str, qty: int, price: int, exchange: str):
        ex = str(exchange or "").upper()
        if ex not in ("KRX", "NXT", "SOR"):
            raise BrokerError(f"지원하지 않는 주문 거래소: {exchange}")
        if int(price or 0) <= 0:
            raise BrokerError("지정가 주문가격이 없습니다.")
        original = self.order_exchange
        try:
            self.order_exchange = ex
            return self.place_order(side, code, qty, "limit", price=int(price))
        finally:
            self.order_exchange = original

    def buy_limit_on(self, code: str, qty: int, price: int, exchange: str):
        return self.place_limit_on("BUY", code, qty, price, exchange)

    def sell_limit_on(self, code: str, qty: int, price: int, exchange: str):
        return self.place_limit_on("SELL", code, qty, price, exchange)

    def cancel_order_on(self, code: str, orig_ord_no: str, exchange: str, qty: int = 0):
        ex = str(exchange or "").upper()
        if ex not in ("KRX", "NXT", "SOR"):
            raise BrokerError(f"지원하지 않는 주문 거래소: {exchange}")
        if not str(orig_ord_no or "").strip():
            raise BrokerError("취소할 원주문번호가 없습니다.")
        body = {
            "dmst_stex_tp": ex,
            "orig_ord_no": str(orig_ord_no).strip(),
            "stk_cd": str(code or "").split("_", 1)[0],
            "cncl_qty": str(max(0, int(qty or 0))),
        }
        return self._post("/api/dostk/ordr", "kt10003", body)

    def get_stock_info(self, code: str) -> dict:
        return self._post("/api/dostk/stkinfo", "ka10001", {"stk_cd": code})

    def get_stock_themes(self, code: str, stex_tp: str = "3") -> list[dict]:
        """Return Kiwoom theme groups containing this stock (ka90001).

        Used only as a candidate-ranking bonus. Theme membership never bypasses
        the normal PUMA strength filter or Gaboja entry pattern.
        """
        base = str(code or "").strip()
        if "_" in base:
            base = base.split("_", 1)[0]
        data = self._post("/api/dostk/thme", "ka90001", {
            "qry_tp": "2",
            "date_tp": "1",
            "flu_pl_amt_tp": "3",
            "stex_tp": str(stex_tp or "3"),
            "stk_cd": base,
            "thema_nm": "",
        })
        rows = data.get("thema_grp", [])
        return list(rows) if isinstance(rows, list) else []

    def get_nxt_premarket_candidates(self, limit: int = 30) -> list[dict]:
        """Supply strong NXT premarket candidates for the 08:00 live Gaboja pool.

        Kiwoom ranking endpoints ka10027 and ka10023 explicitly support
        stex_tp=2 (NXT). Candidate discovery never bypasses PUMA/Gaboja;
        an actual NXT order is sent only after the same live filters pass.
        """
        if not self.real:
            return []

        def num(raw, default=0.0):
            text = str(raw or "").strip().replace(",", "").replace("%", "")
            try:
                return float(text or default)
            except (TypeError, ValueError):
                return float(default)

        def code_of(raw):
            text = str(raw or "").strip()
            if text.startswith("A") and len(text) >= 7:
                text = text[1:]
            if "_" in text:
                text = text.split("_", 1)[0]
            digits = "".join(ch for ch in text if ch.isdigit())
            return digits[-6:] if len(digits) >= 6 else text

        limit = max(1, min(100, int(limit or 30)))
        merged: dict[str, dict] = {}

        gain_data = self._post("/api/dostk/rkinfo", "ka10027", {
            "mrkt_tp": "000",
            "sort_tp": "1",
            "trde_qty_cnd": "0000",
            "stk_cnd": "0",
            "crd_cnd": "0",
            "updown_incls": "1",
            "pric_cnd": "0",
            "trde_prica_cnd": "0",
            "stex_tp": "2",
        })
        gain_rows = gain_data.get("pred_pre_flu_rt_upper", [])
        if isinstance(gain_rows, list):
            for rank, row in enumerate(gain_rows[:limit], start=1):
                if not isinstance(row, dict):
                    continue
                code = code_of(row.get("stk_cd"))
                if not code:
                    continue
                item = merged.setdefault(code, {
                    "code": code,
                    "name": str(row.get("stk_nm") or code).strip(),
                    "price": abs(num(row.get("cur_prc"))),
                    "change_pct": num(row.get("flu_rt")),
                    "volume": abs(num(row.get("now_trde_qty"))),
                    "surge_pct": 0.0,
                    "rise_rank": 9999,
                    "volume_rank": 9999,
                    "sources": [],
                })
                item["rise_rank"] = min(int(item.get("rise_rank", 9999)), rank)
                item["change_pct"] = num(row.get("flu_rt"), item.get("change_pct", 0.0))
                item["price"] = abs(num(row.get("cur_prc"), item.get("price", 0.0)))
                item["volume"] = max(float(item.get("volume", 0.0)), abs(num(row.get("now_trde_qty"))))
                if "NXT상승" not in item["sources"]:
                    item["sources"].append("NXT상승")

        volume_data = self._post("/api/dostk/rkinfo", "ka10023", {
            "mrkt_tp": "000",
            "sort_tp": "2",
            "tm_tp": "1",
            "trde_qty_tp": "5",
            "stk_cnd": "0",
            "pric_tp": "0",
            "stex_tp": "2",
            "tm": "5",
        })
        volume_rows = volume_data.get("trde_qty_sdnin", [])
        if isinstance(volume_rows, list):
            for rank, row in enumerate(volume_rows[:limit], start=1):
                if not isinstance(row, dict):
                    continue
                code = code_of(row.get("stk_cd"))
                if not code:
                    continue
                item = merged.setdefault(code, {
                    "code": code,
                    "name": str(row.get("stk_nm") or code).strip(),
                    "price": abs(num(row.get("cur_prc"))),
                    "change_pct": num(row.get("flu_rt")),
                    "volume": abs(num(row.get("now_trde_qty"))),
                    "surge_pct": num(row.get("sdnin_rt")),
                    "rise_rank": 9999,
                    "volume_rank": 9999,
                    "sources": [],
                })
                if str(row.get("stk_nm") or "").strip():
                    item["name"] = str(row.get("stk_nm")).strip()
                item["volume_rank"] = min(int(item.get("volume_rank", 9999)), rank)
                item["surge_pct"] = num(row.get("sdnin_rt"), item.get("surge_pct", 0.0))
                item["change_pct"] = num(row.get("flu_rt"), item.get("change_pct", 0.0))
                item["price"] = abs(num(row.get("cur_prc"), item.get("price", 0.0)))
                item["volume"] = max(float(item.get("volume", 0.0)), abs(num(row.get("now_trde_qty"))))
                if "NXT거래량" not in item["sources"]:
                    item["sources"].append("NXT거래량")

        ranked = list(merged.values())
        ranked.sort(key=lambda x: (
            -len(x.get("sources") or []),
            min(int(x.get("rise_rank", 9999)), int(x.get("volume_rank", 9999))),
            -float(x.get("change_pct", 0.0) or 0.0),
        ))
        return ranked[:limit]

    def list_domestic_stocks(self, market_types=("0", "10", "8")) -> list[dict]:
        """Load a searchable KRX stock universe via official ka10099.

        0=KOSPI, 10=KOSDAQ, 8=ETF. Results are normalized and de-duplicated
        by stock code so the UI can cache the list and search locally.
        """
        out: dict[str, dict] = {}
        for market_type in market_types:
            cont_yn = ""
            next_key = ""
            seen_keys = set()
            for _ in range(20):
                data, cont_yn, next_key = self._post_page(
                    "/api/dostk/stkinfo", "ka10099",
                    {"mrkt_tp": str(market_type)}, cont_yn, next_key
                )
                rows = data.get("list", [])
                if isinstance(rows, list):
                    for row in rows:
                        if not isinstance(row, dict):
                            continue
                        code = str(row.get("code") or row.get("stk_cd") or "").strip()
                        name = str(row.get("name") or row.get("stk_nm") or "").strip()
                        if not code or not name:
                            continue
                        out[code] = {
                            "code": code,
                            "name": name,
                            "market_code": str(row.get("marketCode") or market_type),
                            "market_name": str(row.get("marketName") or "").strip(),
                        }
                has_more = cont_yn == "Y" and bool(next_key) and next_key not in seen_keys
                if next_key:
                    seen_keys.add(next_key)
                if not has_more:
                    break
                time.sleep(0.08)
        return list(out.values())

    def get_daily_candles(self, code: str, max_pages: int = 6) -> list[dict]:
        rows = []
        for rows, _ in self.iter_chart_pages(code, "daily", max_pages):
            pass
        return rows

    def get_account_positions(self) -> list[dict]:
        """Read holdings from both KRX and NXT so 08:00 NXT fills are never missed.

        The same fungible holding can be reported through more than one venue view;
        de-duplicate by normalized stock code and keep the row with the larger
        remaining quantity instead of summing it.
        """
        merged: dict[str, dict] = {}

        def norm_code(row: dict) -> str:
            raw = str(row.get("stk_cd") or "").strip()
            if raw.startswith("A"):
                raw = raw[1:]
            if "_" in raw:
                raw = raw.split("_", 1)[0]
            digits = "".join(ch for ch in raw if ch.isdigit())
            return digits[-6:] if len(digits) >= 6 else raw

        def qty_of(row: dict) -> int:
            try:
                return abs(int(float(str(row.get("rmnd_qty") or "0").replace(",", ""))))
            except Exception:
                return 0

        for exchange in ("KRX", "NXT"):
            body = {"qry_tp": "1", "dmst_stex_tp": exchange}
            cont_yn = ""
            next_key = ""
            seen_keys = set()
            for page in range(10):
                data, cont_yn, next_key = self._post_page(
                    "/api/dostk/acnt", "kt00018", body, cont_yn, next_key
                )
                if exchange == "KRX":
                    self.last_account_balance_summary = {
                        "tot_pur_amt": data.get("tot_pur_amt", ""),
                        "tot_evlt_amt": data.get("tot_evlt_amt", ""),
                        "tot_evlt_pl": data.get("tot_evlt_pl", ""),
                        "tot_prft_rt": data.get("tot_prft_rt", ""),
                        "prsm_dpst_aset_amt": data.get("prsm_dpst_aset_amt", ""),
                    }
                part = data.get("acnt_evlt_remn_indv_tot", [])
                if isinstance(part, list):
                    for raw in part:
                        if not isinstance(raw, dict):
                            continue
                        code = norm_code(raw)
                        if not code:
                            continue
                        item = dict(raw)
                        item["_puma_exchange"] = exchange
                        if code not in merged or qty_of(item) > qty_of(merged[code]):
                            merged[code] = item
                has_more = cont_yn == "Y" and bool(next_key) and next_key not in seen_keys
                if next_key:
                    seen_keys.add(next_key)
                if not has_more:
                    break
                time.sleep(0.21)
            # Keep account synchronization responsive while still covering both venues.
            time.sleep(0.05)

        snapshot = list(merged.values())
        self.last_account_positions_snapshot = [dict(x) for x in snapshot]
        return snapshot

    def get_account_overview(self) -> dict:
        """Compact account data for the app header.

        ka00001 supplies the account number, kt00001 supplies cash/buying power,
        and kt00018 totals are reused from normal holdings sync when available.
        """
        def money(value) -> int:
            raw = str(value or "0").strip().replace(",", "")
            try:
                return int(float(raw))
            except Exception:
                return 0

        def number(value) -> float:
            raw = str(value or "0").strip().replace(",", "")
            try:
                return float(raw)
            except Exception:
                return 0.0

        out = {
            "environment": "REAL" if self.real else "MOCK",
            "account_no": "",
            "deposit": 0,
            "order_available": 0,
            "withdrawable": 0,
            "d2_deposit": 0,
            "cash_unsettled": 0,
            "holding_count": 0,
            "total_purchase": 0,
            "total_evaluation": 0,
            "total_profit_loss": 0,
            "total_profit_rate": 0.0,
            "estimated_assets": 0,
            "holdings": [],
            "errors": [],
        }

        try:
            acct = self._post("/api/dostk/acnt", "ka00001", {})
            out["account_no"] = str(acct.get("acctNo") or acct.get("acnt_no") or "").strip()
        except Exception as exc:
            out["errors"].append(f"계좌번호:{exc}")

        try:
            dep = self._post("/api/dostk/acnt", "kt00001", {"qry_tp": "2"})
            out["deposit"] = money(dep.get("entr"))
            out["order_available"] = money(dep.get("ord_alow_amt"))
            out["withdrawable"] = money(dep.get("pymn_alow_amt"))
            out["d2_deposit"] = money(dep.get("d2_entra"))
            out["cash_unsettled"] = money(dep.get("ch_uncla"))
        except Exception as exc:
            out["errors"].append(f"예수금:{exc}")

        summary = dict(self.last_account_balance_summary or {})
        if not summary:
            try:
                data = self._post(
                    "/api/dostk/acnt", "kt00018",
                    {"qry_tp": "1", "dmst_stex_tp": "KRX"},
                )
                summary = {
                    "tot_pur_amt": data.get("tot_pur_amt", ""),
                    "tot_evlt_amt": data.get("tot_evlt_amt", ""),
                    "tot_evlt_pl": data.get("tot_evlt_pl", ""),
                    "tot_prft_rt": data.get("tot_prft_rt", ""),
                    "prsm_dpst_aset_amt": data.get("prsm_dpst_aset_amt", ""),
                }
                self.last_account_balance_summary = dict(summary)
                rows = data.get("acnt_evlt_remn_indv_tot", [])
                if isinstance(rows, list):
                    self.last_account_positions_snapshot = [dict(x) for x in rows if isinstance(x, dict)]
            except Exception as exc:
                out["errors"].append(f"잔고:{exc}")

        out["total_purchase"] = money(summary.get("tot_pur_amt"))
        out["total_evaluation"] = money(summary.get("tot_evlt_amt"))
        out["total_profit_loss"] = money(summary.get("tot_evlt_pl"))
        out["total_profit_rate"] = number(summary.get("tot_prft_rt"))
        out["estimated_assets"] = money(summary.get("prsm_dpst_aset_amt"))

        holdings = []
        for row in list(self.last_account_positions_snapshot or []):
            qty = money(row.get("rmnd_qty"))
            if qty <= 0:
                continue
            raw_code = str(row.get("stk_cd") or "").strip()
            code = raw_code[1:] if raw_code.startswith("A") else raw_code
            if "_" in code:
                code = code.split("_", 1)[0]
            holdings.append({
                "code": code,
                "name": str(row.get("stk_nm") or code).strip(),
                "qty": qty,
                "current": money(row.get("cur_prc")),
                "profit_loss": money(row.get("evltv_prft")),
                "profit_rate": number(row.get("prft_rt")),
            })
        out["holdings"] = holdings
        out["holding_count"] = len(holdings)
        return out

    def place_order(self, side: str, code: str, qty: int, order_type: str = "market", price: int = 0, cond_price: int = 0):
        if qty <= 0:
            raise BrokerError("주문 수량이 0입니다.")
        side = side.upper().strip()
        if side not in ("BUY", "SELL"):
            raise BrokerError("주문 방향은 BUY 또는 SELL이어야 합니다.")
        exchange = "KRX" if not self.real else self.order_exchange
        order_type = order_type.lower().strip()
        if order_type == "market":
            trde_tp, ord_uv, cond_uv = "3", "", ""
        elif order_type == "limit":
            if price <= 0:
                raise BrokerError("지정가 주문가격을 입력하세요.")
            trde_tp, ord_uv, cond_uv = "0", str(int(price)), ""
        elif order_type == "stop_limit":
            if price <= 0 or cond_price <= 0:
                raise BrokerError("스톱지정가의 주문가격과 조건가격을 입력하세요.")
            trde_tp, ord_uv, cond_uv = "28", str(int(price)), str(int(cond_price))
        else:
            raise BrokerError(f"지원하지 않는 주문유형: {order_type}")
        body = {
            "dmst_stex_tp": exchange, "stk_cd": code, "ord_qty": str(int(qty)),
            "ord_uv": ord_uv, "trde_tp": trde_tp, "cond_uv": cond_uv,
        }
        api_id = "kt10000" if side == "BUY" else "kt10001"
        return self._post("/api/dostk/ordr", api_id, body)

    def _market_order(self, code: str, qty: int, api_id: str):
        side = "BUY" if api_id == "kt10000" else "SELL"
        return self.place_order(side, code, qty, "market")

    def buy_market(self, code: str, qty: int):
        return self.place_order("BUY", code, qty, "market")

    def sell_market(self, code: str, qty: int):
        return self.place_order("SELL", code, qty, "market")

    def buy_market_on(self, code: str, qty: int, exchange: str):
        ex = str(exchange or "").upper()
        if ex not in ("KRX", "NXT", "SOR"):
            raise BrokerError(f"지원하지 않는 주문 거래소: {exchange}")
        original = self.order_exchange
        try:
            self.order_exchange = ex
            return self.place_order("BUY", code, qty, "market")
        finally:
            self.order_exchange = original

    def sell_market_on(self, code: str, qty: int, exchange: str):
        ex = str(exchange or "").upper()
        if ex not in ("KRX", "NXT", "SOR"):
            raise BrokerError(f"지원하지 않는 주문 거래소: {exchange}")
        original = self.order_exchange
        try:
            self.order_exchange = ex
            return self.place_order("SELL", code, qty, "market")
        finally:
            self.order_exchange = original
