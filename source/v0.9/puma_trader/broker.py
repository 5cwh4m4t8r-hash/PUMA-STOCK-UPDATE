from __future__ import annotations

import random
import time
from datetime import datetime, timedelta
from typing import Dict, List

import requests


class BrokerError(RuntimeError):
    pass


class BaseBroker:
    name = "BASE"
    is_live = False

    def connect(self):
        return True

    def get_minute_candles(self, code: str, timeframe: int) -> List[dict]:
        raise NotImplementedError

    def buy_market(self, code: str, qty: int) -> dict:
        raise NotImplementedError

    def sell_market(self, code: str, qty: int) -> dict:
        raise NotImplementedError

    def place_order(self, side: str, code: str, qty: int, order_type: str = "market", price: int = 0, cond_price: int = 0) -> dict:
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

    def get_minute_candles(self, code: str, timeframe: int):
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

    def get_minute_candles(self, code: str, timeframe: int):
        body = {
            "stk_cd": code,
            "tic_scope": str(timeframe),
            "upd_stkpc_tp": "1",
            "base_dt": datetime.now().strftime("%Y%m%d"),
        }
        data = self._post("/api/dostk/chart", "ka10080", body)
        return data.get("stk_min_pole_chart_qry", [])

    def get_stock_info(self, code: str) -> dict:
        return self._post("/api/dostk/stkinfo", "ka10001", {"stk_cd": code})

    def get_daily_candles(self, code: str, max_pages: int = 6) -> list[dict]:
        """키움 주식일봉차트조회(ka10081). 최신순 원본 rows 반환."""
        body = {
            "stk_cd": code,
            "base_dt": datetime.now().strftime("%Y%m%d"),
            "upd_stkpc_tp": "1",
        }
        rows: list[dict] = []
        cont_yn = ""
        next_key = ""
        for _ in range(max_pages):
            data, cont_yn, next_key = self._post_page(
                "/api/dostk/chart", "ka10081", body, cont_yn, next_key
            )
            part = data.get("stk_dt_pole_chart_qry", [])
            if isinstance(part, list):
                rows.extend(x for x in part if isinstance(x, dict))
            if cont_yn != "Y":
                break
            time.sleep(0.21)
        return rows

    def get_account_positions(self) -> list[dict]:
        # kt00018 공식 예제: qry_tp 1=합산, dmst_stex_tp KRX/NXT
        # 국내 현물 기본 KRX 동기화를 기준으로 한다.
        body = {"qry_tp": "1", "dmst_stex_tp": "KRX"}
        rows: list[dict] = []
        cont_yn = ""
        next_key = ""
        for page in range(10):
            data, cont_yn, next_key = self._post_page(
                "/api/dostk/acnt", "kt00018", body, cont_yn, next_key
            )
            part = data.get("acnt_evlt_remn_indv_tot", [])
            if isinstance(part, list):
                rows.extend(x for x in part if isinstance(x, dict))
            if cont_yn != "Y":
                break
            time.sleep(0.21)
        return rows

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
