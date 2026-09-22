from __future__ import annotations

from datetime import datetime, timedelta
import time
from typing import Dict

from .models import Position, SignalResult, StrategySettings
from .storage import load_runtime, save_runtime
from .strategy import evaluate_buy, evaluate_sell, in_scan_window
from .gabozha import analyze_gabozha


def _num(v):
    try:
        return abs(float(str(v).replace(",", "").strip()))
    except Exception:
        return 0.0


class TradeEngine:
    def __init__(self, broker, settings: StrategySettings):
        self.broker = broker
        self.settings = settings
        # positions에는 PUMA가 관리하는 포지션만 들어간다. 계좌의 다른 보유종목은 자동매도 금지.
        self.positions: Dict[str, Position] = {}
        self.account_held_codes: set[str] = set()
        self.account_qty: Dict[str, int] = {}
        self.cooldowns: Dict[str, datetime] = {}
        self.pending_orders: Dict[str, dict] = {}
        self.enabled = False
        self.last_account_sync: datetime | None = None

        self.daily_order_date = datetime.now().date()
        self.daily_order_count = 0
        self.managed_qty: Dict[str, int] = {}
        self.position_meta: Dict[str, dict] = {}
        self._gabozha_daily_cache: Dict[str, tuple[float, list]] = {}

    def _persist_runtime(self):
        # 실제 계좌용 상태만 영구 저장한다. 모의투자가 실전 관리상태를 덮어쓰지 않게 한다.
        if not self.live_mode:
            return
        save_runtime({
            "daily_order_date": self.daily_order_date.isoformat(),
            "daily_order_count": self.daily_order_count,
            "managed_qty": self.managed_qty,
            "pending_orders": self.pending_orders,
            "position_meta": self.position_meta,
        })

    def set_broker(self, broker):
        self.broker = broker
        self.positions.clear()
        self.account_held_codes.clear()
        self.account_qty.clear()
        self.pending_orders.clear()
        self.position_meta.clear()
        self._gabozha_daily_cache.clear()
        self.last_account_sync = None
        self.daily_order_date = datetime.now().date()
        if self.live_mode:
            runtime = load_runtime()
            today = self.daily_order_date.isoformat()
            self.daily_order_count = int(runtime.get("daily_order_count", 0)) if runtime.get("daily_order_date") == today else 0
            self.managed_qty = {
                str(k): int(v) for k, v in dict(runtime.get("managed_qty", {})).items() if int(v) > 0
            }
            self.position_meta = {
                str(k): dict(v) for k, v in dict(runtime.get("position_meta", {})).items() if isinstance(v, dict)
            }
            restored = {}
            for code, item in dict(runtime.get("pending_orders", {})).items():
                if not isinstance(item, dict):
                    continue
                x = dict(item)
                try:
                    x["created_at"] = datetime.fromisoformat(str(x.get("created_at", "")))
                except Exception:
                    x["created_at"] = datetime.now()
                restored[str(code)] = x
            self.pending_orders = restored
        else:
            self.daily_order_count = 0
            self.managed_qty = {}
            self.position_meta = {}

    def set_settings(self, settings):
        self.settings = settings
        if hasattr(self.broker, "order_exchange"):
            self.broker.order_exchange = settings.order_exchange

    @property
    def live_mode(self) -> bool:
        return bool(getattr(self.broker, "is_live", False))

    def _roll_daily_counter(self):
        today = datetime.now().date()
        if today != self.daily_order_date:
            self.daily_order_date = today
            self.daily_order_count = 0
            self._persist_runtime()

    def can_open(self, code):
        self._roll_daily_counter()
        # 계좌에 사용자가 이미 보유한 종목도 중복매수하지 않는다.
        if code in self.account_held_codes or code in self.positions or code in self.pending_orders:
            return False
        if len(self.positions) + sum(1 for x in self.pending_orders.values() if x.get("side") == "BUY") >= self.settings.max_positions:
            return False
        if self.daily_order_count >= self.settings.max_daily_orders:
            return False
        until = self.cooldowns.get(code)
        return not until or datetime.now() >= until

    def sync_account(self, force=False):
        """키움 계좌 잔고를 동기화하되 PUMA가 직접 만든 포지션만 자동매도 대상으로 등록한다."""
        getter = getattr(self.broker, "get_account_positions", None)
        if not getter or self.broker.__class__.__name__ == "SimBroker":
            return {"synced": False, "reason": "simulation"}

        now = datetime.now()
        if not force and self.last_account_sync:
            if (now - self.last_account_sync).total_seconds() < max(2, self.settings.account_sync_sec):
                return {"synced": False, "reason": "interval"}

        rows = getter()
        self.last_account_sync = now
        account: dict[str, dict] = {}

        for row in rows:
            raw_code = str(row.get("stk_cd", "")).strip()
            code = raw_code[1:] if raw_code.startswith("A") else raw_code
            if "_" in code:
                code = code.split("_", 1)[0]
            if not code:
                continue
            qty = int(_num(row.get("rmnd_qty")))
            if qty <= 0:
                continue
            account[code] = {
                "code": code,
                "qty": qty,
                "name": str(row.get("stk_nm") or code).strip(),
                "entry": _num(row.get("pur_pric")),
                "current": _num(row.get("cur_prc")),
            }

        self.account_held_codes = set(account)
        self.account_qty = {code: item["qty"] for code, item in account.items()}

        # 매수 주문 확인: 주문수량만큼(또는 그 이상) 계좌에 보이면 PUMA 관리 포지션으로 확정.
        for code, pending in list(self.pending_orders.items()):
            if pending.get("side") != "BUY":
                continue
            item = account.get(code)
            if not item:
                continue
            requested = max(1, int(pending.get("qty", 0) or 0))
            if item["qty"] >= requested:
                self.managed_qty[code] = requested
                self.pending_orders.pop(code, None)

        # PUMA가 관리하도록 기록된 종목만 positions에 반영한다.
        seen_managed: set[str] = set()
        for code, managed in list(self.managed_qty.items()):
            item = account.get(code)
            if not item:
                # 아직 매수주문 확인 중이면 유지. 그 외 계좌에서 사라졌다면 수동/자동 매도된 것으로 정리.
                pending = self.pending_orders.get(code)
                if pending and pending.get("side") == "BUY":
                    continue
                if pending and pending.get("side") == "SELL":
                    self.pending_orders.pop(code, None)
                    self.cooldowns[code] = now + timedelta(minutes=self.settings.cooldown_min)
                self.positions.pop(code, None)
                self.managed_qty.pop(code, None)
                self.position_meta.pop(code, None)
                continue

            seen_managed.add(code)
            qty = min(max(1, int(managed)), item["qty"])
            entry = item["entry"] or item["current"]
            current = item["current"] or entry
            old = self.positions.get(code)
            high = max(current, entry, old.highest_price if old else 0)
            meta = self.position_meta.get(code, {})
            self.positions[code] = Position(
                code=code,
                name=item["name"],
                qty=qty,
                entry_price=entry or current,
                highest_price=high,
                opened_at=old.opened_at if old else now.isoformat(timespec="seconds"),
                broker_order_no=old.broker_order_no if old else "ACCOUNT",
                basis_open=float(meta.get("basis_open", 0) or 0),
                partial_taken=bool(meta.get("partial_taken", False)),
                entry_kind=str(meta.get("entry_kind", "")),
            )

        # 매도 주문 확인: 주문 전 계좌수량에서 PUMA 매도수량만큼 줄었으면 완료로 본다.
        for code, pending in list(self.pending_orders.items()):
            if pending.get("side") != "SELL":
                continue
            before = int(pending.get("account_qty_before", self.account_qty.get(code, 0)) or 0)
            sold_qty = int(pending.get("qty", 0) or 0)
            now_qty = int(self.account_qty.get(code, 0) or 0)
            if now_qty <= max(0, before - sold_qty):
                partial = bool(pending.get("partial", False))
                remaining = int(pending.get("remaining_managed_qty", 0) or 0)
                self.pending_orders.pop(code, None)
                if partial and remaining > 0 and now_qty > 0:
                    keep = min(remaining, now_qty)
                    self.managed_qty[code] = keep
                    meta = self.position_meta.setdefault(code, {})
                    meta["partial_taken"] = True
                    pos = self.positions.get(code)
                    if pos:
                        pos.qty = keep
                        pos.partial_taken = True
                else:
                    self.positions.pop(code, None)
                    self.managed_qty.pop(code, None)
                    self.position_meta.pop(code, None)
                    self.cooldowns[code] = now + timedelta(minutes=self.settings.cooldown_min)

        # 계좌에 일부만 들어온 매수는 포지션 표시만 하되 pending을 유지해 추가 주문을 막는다.
        for code, pending in self.pending_orders.items():
            if pending.get("side") != "BUY" or code in self.positions:
                continue
            item = account.get(code)
            if not item:
                continue
            requested = max(1, int(pending.get("qty", 0) or 0))
            qty = min(requested, item["qty"])
            entry = item["entry"] or item["current"]
            current = item["current"] or entry
            meta = self.position_meta.get(code, {})
            self.positions[code] = Position(
                code, item["name"], qty, entry, max(entry, current), now.isoformat(timespec="seconds"),
                str(pending.get("ord_no", "")),
                float(meta.get("basis_open", 0) or 0),
                bool(meta.get("partial_taken", False)),
                str(meta.get("entry_kind", "")),
            )

        self._persist_runtime()
        return {
            "synced": True,
            "account_positions": len(account),
            "managed_positions": len(self.positions),
        }

    def _submit_buy(self, code: str, name: str, current: float, reason: str, basis_open: float = 0.0, entry_kind: str = ""):
        qty = int(self.settings.order_budget // current)
        if qty < 1:
            return {"code": code, "name": name, "status": "WAIT", "price": current, "signal": "종목당 투입금보다 현재가가 높음"}
        resp = self.broker.buy_market(code, qty)
        self.daily_order_count += 1
        if self.broker.__class__.__name__ != "SimBroker":
            # 앱이 재시작되어도 체결된 종목을 PUMA 포지션으로 복구할 수 있도록 주문수량을 먼저 기록.
            self.managed_qty[code] = qty
            self.position_meta[code] = {
                "basis_open": float(basis_open or 0),
                "partial_taken": False,
                "entry_kind": str(entry_kind or ""),
            }
            self.pending_orders[code] = {
                "side": "BUY",
                "qty": qty,
                "ord_no": str(resp.get("ord_no", "")),
                "created_at": datetime.now(),
            }
            self._persist_runtime()
            return {"code": code, "name": name, "status": "BUY_SENT", "price": current, "signal": reason, "order": resp}

        pos = Position(code, name, qty, current, current, datetime.now().isoformat(timespec="seconds"), str(resp.get("ord_no", "")), float(basis_open or 0), False, str(entry_kind or ""))
        self.position_meta[code] = {"basis_open": float(basis_open or 0), "partial_taken": False, "entry_kind": str(entry_kind or "")}
        self.positions[code] = pos
        self._persist_runtime()
        return {"code": code, "name": name, "status": "BUY", "price": current, "signal": reason, "order": resp}

    def _submit_sell(self, code: str, pos: Position, current: float, reason: str):
        resp = self.broker.sell_market(code, pos.qty)
        self.daily_order_count += 1
        if self.broker.__class__.__name__ != "SimBroker":
            self.pending_orders[code] = {
                "side": "SELL",
                "qty": pos.qty,
                "ord_no": str(resp.get("ord_no", "")),
                "created_at": datetime.now(),
                "account_qty_before": int(self.account_qty.get(code, pos.qty)),
                "partial": False,
                "remaining_managed_qty": 0,
            }
            self._persist_runtime()
            return {"code": code, "name": pos.name, "status": "SELL_SENT", "price": current, "signal": reason, "order": resp}

        del self.positions[code]
        self.position_meta.pop(code, None)
        self.cooldowns[code] = datetime.now() + timedelta(minutes=self.settings.cooldown_min)
        self._persist_runtime()
        return {"code": code, "name": pos.name, "status": "SELL", "price": current, "signal": reason, "order": resp}

    def _gabozha_daily_rows(self, code: str):
        ttl = max(1, int(getattr(self.settings, "gabozha_daily_cache_sec", 30) or 30))
        now_mono = time.monotonic()
        cached = self._gabozha_daily_cache.get(code)
        if cached and now_mono - cached[0] < ttl:
            return cached[1]
        getter = getattr(self.broker, "get_daily_candles", None)
        if not getter:
            rows = []
        else:
            try:
                rows = getter(code, max_pages=6)
            except TypeError:
                rows = getter(code)
        rows = list(rows or [])
        self._gabozha_daily_cache[code] = (now_mono, rows)
        return rows

    def _submit_partial_sell(self, code: str, pos: Position, current: float, reason: str):
        if pos.qty <= 1:
            return self._submit_sell(code, pos, current, reason + " · 1주라 전량청산")
        qty = max(1, pos.qty // 2)
        remaining = max(0, pos.qty - qty)
        resp = self.broker.sell_market(code, qty)
        self.daily_order_count += 1
        if self.broker.__class__.__name__ != "SimBroker":
            self.pending_orders[code] = {
                "side": "SELL",
                "qty": qty,
                "ord_no": str(resp.get("ord_no", "")),
                "created_at": datetime.now(),
                "account_qty_before": int(self.account_qty.get(code, pos.qty)),
                "partial": True,
                "remaining_managed_qty": remaining,
            }
            self._persist_runtime()
            return {"code": code, "name": pos.name, "status": "PARTIAL_SELL_SENT", "price": current, "signal": reason, "order": resp}

        pos.qty = remaining
        pos.partial_taken = True
        meta = self.position_meta.setdefault(code, {})
        meta["partial_taken"] = True
        self._persist_runtime()
        return {"code": code, "name": pos.name, "status": "PARTIAL_SELL", "price": current, "signal": reason, "order": resp}

    def _gabozha_exit_action(self, pos: Position, current: float):
        pnl = pos.pnl_pct(current)
        pos.highest_price = max(pos.highest_price, current)

        if pos.basis_open > 0 and current < pos.basis_open:
            return "FULL", f"가보자 손절 · 기준봉 시가 {pos.basis_open:,.0f} 이탈"

        half_tp = float(getattr(self.settings, "gabozha_half_take_profit_pct", 4.0) or 4.0)
        if not pos.partial_taken and pnl >= half_tp:
            return "HALF", f"가보자 +{half_tp:.1f}% 도달 · 절반 익절 {pnl:.2f}%"

        if pos.partial_taken and self.settings.trailing_enabled and pnl >= self.settings.trailing_start_pct:
            drop_from_high = (current / pos.highest_price - 1) * 100 if pos.highest_price else 0.0
            if drop_from_high <= -abs(self.settings.trailing_gap_pct):
                return "FULL", f"가보자 잔량 트레일링 {drop_from_high:.2f}%"

        now = datetime.now()
        if self.settings.force_exit_enabled and now.strftime("%H:%M") >= self.settings.force_exit_time:
            return "FULL", "장 종료 전 청산"
        return "HOLD", "가보자 보유"

    def process(self, code, name, require_buy_filter: bool = True):
        self._roll_daily_counter()
        if self.broker.__class__.__name__ != "SimBroker":
            self.sync_account(force=False)

        candles = self.broker.get_minute_candles(code, self.settings.timeframe_min)
        if not candles:
            return {"code": code, "name": name, "status": "NO DATA", "price": 0, "signal": "데이터 없음"}

        try:
            current = abs(float(str(candles[0].get("cur_prc", "0")).replace(",", "")))
        except Exception:
            current = 0

        pending = self.pending_orders.get(code)
        if pending:
            return {
                "code": code,
                "name": self.positions.get(code).name if code in self.positions else name,
                "status": f"{pending.get('side')}_PENDING",
                "price": current,
                "signal": f"주문 확인 중 · {pending.get('ord_no', '')}",
            }

        if code in self.positions:
            pos = self.positions[code]
            if pos.entry_kind in ("PULLBACK", "REBREAK") and pos.basis_open > 0:
                action, reason = self._gabozha_exit_action(pos, current)
                if self.enabled and action in ("FULL", "HALF"):
                    if self.daily_order_count >= self.settings.max_daily_orders:
                        return {"code": code, "name": pos.name, "status": "HOLD", "price": current, "signal": "PUMA 일일 주문 제한 도달"}
                    if action == "HALF":
                        return self._submit_partial_sell(code, pos, current, reason)
                    return self._submit_sell(code, pos, current, reason)
                return {"code": code, "name": pos.name, "status": "HOLD", "price": current, "signal": f"{reason} / {pos.pnl_pct(current):+.2f}%"}
            should_sell, reason = evaluate_sell(pos, current, self.settings)
            if self.enabled and should_sell:
                if self.daily_order_count >= self.settings.max_daily_orders:
                    return {"code": code, "name": pos.name, "status": "HOLD", "price": current, "signal": "PUMA 일일 주문 제한 도달"}
                return self._submit_sell(code, pos, current, reason)
            return {"code": code, "name": pos.name, "status": "HOLD", "price": current, "signal": f"{reason} / {pos.pnl_pct(current):+.2f}%"}

        basis_open = 0.0
        entry_kind = ""
        if bool(getattr(self.settings, "gabozha_enabled", True)):
            daily_rows = self._gabozha_daily_rows(code)
            gsig = analyze_gabozha(candles, daily_rows, self.settings)
            sig = SignalResult(
                bool(gsig.passed),
                str(gsig.reason),
                current_price=float(gsig.current_price or current),
                volume_ratio=float(gsig.volume_ratio or 0),
            )
            basis_open = float(gsig.basis_open or 0)
            entry_kind = str(gsig.entry_kind or "")
        elif require_buy_filter:
            sig = evaluate_buy(candles, self.settings)
        else:
            sig = SignalResult(True, "영웅문4 조건식 편입", current_price=current)

        if self.enabled and in_scan_window(self.settings) and sig.passed and self.can_open(code) and current > 0:
            return self._submit_buy(code, name, current, sig.reason, basis_open=basis_open, entry_kind=entry_kind)

        if self.daily_order_count >= self.settings.max_daily_orders:
            return {"code": code, "name": name, "status": "LIMIT", "price": current, "signal": "PUMA 일일 주문 제한 도달"}
        if code in self.account_held_codes and code not in self.positions:
            return {"code": code, "name": name, "status": "HELD-EXTERNAL", "price": current, "signal": "계좌 기존보유 · PUMA 자동매도 제외"}

        status = "READY" if sig.passed else "WAIT"
        return {
            "code": code,
            "name": name,
            "status": status,
            "price": current,
            "signal": sig.reason,
            "change": sig.change_pct,
            "volume_ratio": sig.volume_ratio,
            "rsi": sig.rsi,
        }
