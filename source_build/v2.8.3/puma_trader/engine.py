from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict

from .models import Position, SignalResult, StrategySettings
from .storage import load_runtime, save_runtime
from .strategy import evaluate_buy, evaluate_sell, in_scan_window
from .gaboja import evaluate_gaboja
from .swing import normalize_candles
from .broker import BrokerError, OrderStateUnknown

INITIAL_SEED_CAPITAL = 500_000
PHASE1_TARGET_CAPITAL = 3_000_000
# Backward-compatible public constant; sizing is no longer fixed to this amount.
AUTO_ORDER_BUDGET = INITIAL_SEED_CAPITAL


class AutoOrderError(RuntimeError):
    """Order/cancel state may be unknown; automatic trading must stop for safety."""
    pass


def _max_buyable_qty_from_error(exc) -> int:
    """Parse Kiwoom's deterministic '[... N주 매수가능]' rejection message."""
    import re
    text = str(exc or "")
    m = re.search(r"(\d[\d,]*)\s*주\s*매수가능", text)
    if not m:
        return 0
    try:
        return max(0, int(m.group(1).replace(",", "")))
    except Exception:
        return 0


def _num(v):
    try:
        return abs(float(str(v).replace(",", "").strip()))
    except Exception:
        return 0.0


def _minute_bucket_key(row: dict, timeframe: int) -> str:
    """Return a stable intraday bucket key even if raw timestamps contain seconds."""
    raw = str(row.get("cntr_tm") or row.get("dt") or row.get("date") or "")
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) < 12:
        return digits
    try:
        minute = int(digits[10:12])
        tf = max(1, int(timeframe or 5))
        bucket = (minute // tf) * tf
        return digits[:10] + f"{bucket:02d}"
    except Exception:
        return digits[:12]


def _gaboja_trend_stop_from_rows(
    rows,
    *,
    current_bar_key: str,
    timeframe: int,
    current_stop: float,
    entry_price: float,
) -> float:
    """Return the newest confirmed higher '차' low without looking into the live bar.

    A pullback is 1~3 completed bars containing at least one bearish candle.
    It becomes confirmed only when the next completed bullish bar closes back
    above the pullback bodies.  The stop can only move upward.
    """
    completed_raw = [
        row for row in (rows or [])
        if _minute_bucket_key(row, timeframe) != str(current_bar_key or "")
    ]
    candles = normalize_candles(completed_raw)
    if len(candles) < 5:
        return float(current_stop or 0)

    best = float(current_stop or 0)
    entry = float(entry_price or 0)
    start = max(2, len(candles) - 14)

    for rebound_i in range(start, len(candles)):
        rebound = candles[rebound_i]
        if float(rebound["close"]) <= float(rebound["open"]):
            continue

        for span in (1, 2, 3):
            pb_start = rebound_i - span
            if pb_start < 1:
                continue
            pullback = candles[pb_start:rebound_i]
            prior = candles[max(0, pb_start - 4):pb_start]
            if not prior or not pullback:
                continue
            if not any(float(x["close"]) < float(x["open"]) for x in pullback):
                continue

            prior_high = max(float(x["high"]) for x in prior)
            pull_low = min(float(x["low"]) for x in pullback)
            pull_body_high = max(max(float(x["open"]), float(x["close"])) for x in pullback)

            # 상승 뒤 눌림이어야 하고, 다음 양봉이 눌림 몸통을 회복해야 확정.
            if prior_high <= max(entry, best):
                continue
            if float(rebound["close"]) <= pull_body_high:
                continue
            if pull_low <= best or pull_low >= float(rebound["close"]):
                continue

            best = max(best, pull_low)
            break

    return best


def _gaboja_quick_profit_exit_from_rows(
    rows,
    *,
    current_bar_key: str,
    timeframe: int,
    entry_price: float,
    opened_at: str = "",
    min_profit_pct: float = 1.0,
    peak_retreat_pct: float = 0.35,
) -> tuple[bool, float, float]:
    """Take profit quickly when a post-entry run makes a local high and starts to roll over.

    This is intentionally different from the +4% partial-profit rule. It matches the
    user's Young-Cha-Young2 scalping intent: after a valid entry, once price has run
    at least the configured minimum and then retreats from the new post-entry peak,
    lock the gain instead of waiting for a later 3-wave structure.
    """
    candles = normalize_candles(rows or [])
    if len(candles) < 2 or float(entry_price or 0) <= 0:
        return False, 0.0, 0.0

    entry_stamp = ""
    try:
        dt = datetime.fromisoformat(str(opened_at or ""))
        entry_stamp = dt.strftime("%Y%m%d%H%M")
    except Exception:
        entry_stamp = ""

    if entry_stamp:
        post = []
        for row in candles:
            digits = "".join(ch for ch in str(row.get("date") or "") if ch.isdigit())
            if len(digits) >= 12 and digits[:12] >= entry_stamp:
                post.append(row)
        if len(post) >= 2:
            candles = post
        else:
            candles = candles[-6:]
    else:
        candles = candles[-6:]

    if len(candles) < 2:
        return False, 0.0, 0.0

    current = candles[-1]
    current_close = float(current["close"])
    current_open = float(current["open"])
    previous_close = float(candles[-2]["close"])

    peak = max(float(x["high"]) for x in candles)
    gain_pct = (peak / float(entry_price) - 1.0) * 100.0
    if gain_pct < abs(float(min_profit_pct or 0.0)):
        return False, peak, gain_pct

    retreat_pct = (current_close / peak - 1.0) * 100.0 if peak > 0 else 0.0
    rolling_over = bool(
        current_close < current_open
        or current_close < previous_close
    )
    if rolling_over and retreat_pct <= -abs(float(peak_retreat_pct or 0.0)):
        return True, peak, gain_pct

    return False, peak, gain_pct


def _gaboja_stage3_exit_from_rows(
    rows,
    *,
    current_bar_key: str,
    timeframe: int,
    entry_price: float,
    opened_at: str = "",
) -> tuple[bool, float]:
    """Detect the next completed/live thrust after a post-entry pullback ("3").

    차 진입 뒤 상승이 나온 후 최소 한 번의 1~3봉 눌림이 있고, 현재 봉이 그 눌림 전 고점을
    다시 넘으며 몸통을 회복할 때 3파동으로 본다. 미래 봉은 보지 않는다.
    """
    candles = normalize_candles(rows or [])
    if len(candles) < 4:
        return False, 0.0

    entry_stamp = ""
    try:
        dt = datetime.fromisoformat(str(opened_at or ""))
        entry_stamp = dt.strftime("%Y%m%d%H%M")
    except Exception:
        entry_stamp = ""

    if entry_stamp:
        post = []
        for row in candles:
            digits = "".join(ch for ch in str(row.get("date") or "") if ch.isdigit())
            if len(digits) >= 12 and digits[:12] >= entry_stamp:
                post.append(row)
        if len(post) >= 3:
            candles = post
        else:
            candles = candles[-8:]
    else:
        candles = candles[-8:]

    if len(candles) < 3:
        return False, 0.0

    current = candles[-1]
    current_close = float(current["close"])
    current_high = float(current["high"])
    if current_close <= float(entry_price or 0):
        return False, 0.0

    # 2영 이후 바로 한 봉 더 오르는 것은 아직 3으로 보지 않는다.
    # 중간에 실제 눌림(음봉 또는 전봉 대비 종가 하락)이 있어야 한다.
    end = len(candles) - 1
    for span in (1, 2, 3):
        pb_start = end - span
        if pb_start < 1:
            continue
        pullback = candles[pb_start:end]
        before = candles[max(0, pb_start - 4):pb_start]
        if not before or not pullback:
            continue

        has_retreat = False
        prev_close = float(before[-1]["close"])
        for bar in pullback:
            if float(bar["close"]) < float(bar["open"]) or float(bar["close"]) < prev_close:
                has_retreat = True
            prev_close = float(bar["close"])
        if not has_retreat:
            continue

        pre_high = max(float(x["high"]) for x in before)
        pull_body_high = max(max(float(x["open"]), float(x["close"])) for x in pullback)
        pull_low = min(float(x["low"]) for x in pullback)
        if pull_low <= 0:
            continue

        # 3: 눌림 뒤 재상승이 이전 파동 고점을 다시 갱신.
        if (
            current_close > float(current["open"])
            and current_high > pre_high
            and current_close > pull_body_high
        ):
            return True, current_high

    return False, 0.0


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
        self.seed_capital = float(getattr(settings, "seed_initial_capital", INITIAL_SEED_CAPITAL) or INITIAL_SEED_CAPITAL)
        self.daily_start_seed = float(self.seed_capital)
        self.daily_realized_pnl = 0.0
        self.daily_loss_locked = False
        self.managed_qty: Dict[str, int] = {}
        self.managed_meta: Dict[str, dict] = {}
        self._gaboja_daily_cache: Dict[str, dict] = {}

    def _persist_runtime(self):
        # 실제 계좌용 상태만 영구 저장한다. 모의투자가 실전 관리상태를 덮어쓰지 않게 한다.
        if not self.live_mode:
            return
        save_runtime({
            "daily_order_date": self.daily_order_date.isoformat(),
            "daily_order_count": self.daily_order_count,
            "managed_qty": self.managed_qty,
            "managed_meta": self.managed_meta,
            "pending_orders": self.pending_orders,
            "seed_capital": self.seed_capital,
            "daily_start_seed": self.daily_start_seed,
            "daily_realized_pnl": self.daily_realized_pnl,
            "daily_loss_locked": self.daily_loss_locked,
        })

    def set_broker(self, broker):
        self.broker = broker
        self.positions.clear()
        self.account_held_codes.clear()
        self.account_qty.clear()
        self.pending_orders.clear()
        self.managed_meta.clear()
        self._gaboja_daily_cache.clear()
        self.last_account_sync = None
        self.daily_order_date = datetime.now().date()
        if self.live_mode:
            runtime = load_runtime()
            today = self.daily_order_date.isoformat()
            self.daily_order_count = int(runtime.get("daily_order_count", 0)) if runtime.get("daily_order_date") == today else 0
            self.managed_qty = {
                str(k): int(v) for k, v in dict(runtime.get("managed_qty", {})).items() if int(v) > 0
            }
            self.managed_meta = {
                str(k): dict(v) for k, v in dict(runtime.get("managed_meta", {})).items() if isinstance(v, dict)
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
            same_day = runtime.get("daily_order_date") == today
            self.seed_capital = max(
                0.0,
                float(runtime.get("seed_capital", getattr(self.settings, "seed_initial_capital", INITIAL_SEED_CAPITAL)) or INITIAL_SEED_CAPITAL),
            )
            self.daily_start_seed = (
                max(0.0, float(runtime.get("daily_start_seed", self.seed_capital) or self.seed_capital))
                if same_day else self.seed_capital
            )
            self.daily_realized_pnl = float(runtime.get("daily_realized_pnl", 0) or 0) if same_day else 0.0
            self.daily_loss_locked = bool(runtime.get("daily_loss_locked", False)) if same_day else False
        else:
            self.daily_order_count = 0
            self.managed_qty = {}
            self.managed_meta = {}
            self.seed_capital = float(getattr(self.settings, "seed_initial_capital", INITIAL_SEED_CAPITAL) or INITIAL_SEED_CAPITAL)
            self.daily_start_seed = self.seed_capital
            self.daily_realized_pnl = 0.0
            self.daily_loss_locked = False

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
            # 전일 손익이 반영된 현재 시드가 다음 거래일 시작 시드가 된다.
            self.daily_start_seed = float(self.seed_capital)
            self.daily_realized_pnl = 0.0
            self.daily_loss_locked = False
            self._persist_runtime()

    def current_trade_budget(self) -> int:
        """1차 목표 300만원 전까지 현재 PUMA 시드를 다음 거래에 전액 재투입."""
        if not bool(getattr(self.settings, "compound_seed_enabled", True)):
            return max(0, int(getattr(self.settings, "order_budget", INITIAL_SEED_CAPITAL) or 0))
        return max(0, int(self.seed_capital))

    def phase1_complete(self) -> bool:
        target = float(getattr(self.settings, "seed_phase1_target", PHASE1_TARGET_CAPITAL) or PHASE1_TARGET_CAPITAL)
        return float(self.seed_capital) >= target

    def daily_loss_pct(self) -> float:
        if self.daily_start_seed <= 0:
            return 0.0
        return (float(self.seed_capital) / float(self.daily_start_seed) - 1.0) * 100.0

    def _record_realized_delta(self, pnl_delta: float):
        delta = float(pnl_delta or 0.0)
        self.seed_capital = max(0.0, float(self.seed_capital) + delta)
        self.daily_realized_pnl += delta
        limit = float(getattr(self.settings, "daily_loss_limit_pct", -4.0) or -4.0)
        if self.daily_loss_pct() <= limit:
            self.daily_loss_locked = True
        self._persist_runtime()

    def _gaboja_daily_rows(self, code: str) -> list[dict]:
        """Daily history is static intraday; cache it so 5-minute auto-trading stays fast.

        Today's OHLCV is rebuilt from live 5-minute bars inside evaluate_gaboja(),
        so a 10-minute daily-history cache does not delay intraday volume/breakout checks.
        """
        now = datetime.now()
        day = now.strftime("%Y%m%d")
        cached = self._gaboja_daily_cache.get(code)
        if cached and cached.get("day") == day:
            age = (now - cached.get("at", now)).total_seconds()
            if age < 600:
                return list(cached.get("rows") or [])

        getter = getattr(self.broker, "get_daily_candles", None)
        if not getter:
            return []
        rows = getter(code, max_pages=6)
        self._gaboja_daily_cache[code] = {"day": day, "at": now, "rows": list(rows or [])}
        return list(rows or [])

    def can_open(self, code):
        self._roll_daily_counter()
        if self.daily_loss_locked or self.phase1_complete():
            return False
        # 1차 복리 구간은 현재 시드 전액을 가장 좋은 단타 한 종목에만 사용한다.
        # 한 포지션/매수주문이 끝나기 전에는 두 번째 종목 신규진입을 절대 허용하지 않는다.
        if bool(getattr(self.settings, "compound_seed_enabled", True)):
            if self.positions or any(x.get("side") == "BUY" for x in self.pending_orders.values()):
                return False
        # 계좌에 사용자가 이미 보유한 같은 종목도 중복매수하지 않는다.
        if code in self.account_held_codes or code in self.positions or code in self.pending_orders:
            return False
        if not bool(getattr(self.settings, "compound_seed_enabled", True)) and len(self.positions) + sum(1 for x in self.pending_orders.values() if x.get("side") == "BUY") >= self.settings.max_positions:
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
            target_qty = max(1, int(pending.get("target_qty", pending.get("qty", 0)) or 0))
            base_qty = max(0, int(pending.get("account_qty_before", 0) or 0))
            if item["qty"] >= base_qty + target_qty:
                self.managed_qty[code] = target_qty
                self.managed_meta[code] = {
                    "stop_price": float(pending.get("stop_price", 0) or 0),
                    "entry_kind": str(pending.get("entry_kind", "")),
                    "partial_taken": False,
                    "partial_price": 0.0,
                    "partial_time": "",
                }
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
                self.managed_meta.pop(code, None)
                continue

            seen_managed.add(code)
            qty = min(max(1, int(managed)), item["qty"])
            entry = item["entry"] or item["current"]
            current = item["current"] or entry
            old = self.positions.get(code)
            meta = dict(self.managed_meta.get(code) or {})
            high = max(current, entry, old.highest_price if old else 0)
            self.positions[code] = Position(
                code=code,
                name=item["name"],
                qty=qty,
                entry_price=entry or current,
                highest_price=high,
                opened_at=old.opened_at if old else now.isoformat(timespec="seconds"),
                broker_order_no=old.broker_order_no if old else "ACCOUNT",
                stop_price=float(meta.get("stop_price", getattr(old, "stop_price", 0)) or 0),
                entry_kind=str(meta.get("entry_kind", getattr(old, "entry_kind", "")) or ""),
                partial_taken=bool(meta.get("partial_taken", getattr(old, "partial_taken", False))),
                partial_price=float(meta.get("partial_price", getattr(old, "partial_price", 0)) or 0),
                partial_time=str(meta.get("partial_time", getattr(old, "partial_time", "")) or ""),
                remainder_down_trigger_bar=str(meta.get("remainder_down_trigger_bar", getattr(old, "remainder_down_trigger_bar", "")) or ""),
                remainder_down_wait_bar=str(meta.get("remainder_down_wait_bar", getattr(old, "remainder_down_wait_bar", "")) or ""),
            )

        # 매도 주문 확인. +4% 1차 익절은 50%를 줄이고, 손절/3파동/종가청산은 잔량 전량 정리한다.
        for code, pending in list(self.pending_orders.items()):
            if pending.get("side") != "SELL":
                continue
            before = int(pending.get("account_qty_before", self.account_qty.get(code, 0)) or 0)
            sold_qty = int(pending.get("qty", 0) or 0)
            now_qty = int(self.account_qty.get(code, 0) or 0)
            desired_remaining = max(0, int(pending.get("remaining_qty", max(0, before - sold_qty)) or 0))
            if now_qty <= desired_remaining:
                self.pending_orders.pop(code, None)
                self._record_realized_delta(float(pending.get("seed_pnl_delta", 0) or 0))
                full_exit = bool(pending.get("full_exit", True))
                remaining = max(0, int(pending.get("remaining_qty", 0) or 0))
                if full_exit or remaining <= 0:
                    self.positions.pop(code, None)
                    self.managed_qty.pop(code, None)
                    self.managed_meta.pop(code, None)
                    self.cooldowns[code] = now + timedelta(minutes=self.settings.cooldown_min)
                else:
                    self.managed_qty[code] = remaining
                    meta = dict(self.managed_meta.get(code) or {})
                    meta.update({
                        "stop_price": float(pending.get("stop_price", meta.get("stop_price", 0)) or 0),
                        "entry_kind": str(pending.get("entry_kind", meta.get("entry_kind", "")) or ""),
                        "partial_taken": bool(pending.get("partial_taken_after", True)),
                        "partial_price": float(pending.get("partial_price_after", meta.get("partial_price", 0)) or 0),
                        "partial_time": str(pending.get("partial_time_after", meta.get("partial_time", "")) or ""),
                        "remainder_down_trigger_bar": "",
                        "remainder_down_wait_bar": "",
                    })
                    self.managed_meta[code] = meta
                    pos = self.positions.get(code)
                    if pos:
                        pos.qty = remaining
                        pos.partial_taken = True
                        pos.partial_price = float(pending.get("partial_price_after", 0) or 0)
                        pos.partial_time = str(pending.get("partial_time_after", now.isoformat(timespec="seconds")) or "")
                        pos.remainder_down_trigger_bar = ""
                        pos.remainder_down_wait_bar = ""

        # 계좌에 일부만 들어온 매수는 포지션 표시만 하되 pending을 유지해 추가 주문을 막는다.
        for code, pending in self.pending_orders.items():
            if pending.get("side") != "BUY" or code in self.positions:
                continue
            item = account.get(code)
            if not item:
                continue
            target_qty = max(1, int(pending.get("target_qty", pending.get("qty", 0)) or 0))
            base_qty = max(0, int(pending.get("account_qty_before", 0) or 0))
            qty = min(target_qty, max(0, item["qty"] - base_qty))
            entry = item["entry"] or item["current"]
            current = item["current"] or entry
            self.positions[code] = Position(
                code, item["name"], qty, entry, max(entry, current), now.isoformat(timespec="seconds"),
                str(pending.get("ord_no", "")),
                float(pending.get("stop_price", 0) or 0),
                str(pending.get("entry_kind", "") or ""),
                False,
            )

        self._persist_runtime()
        return {
            "synced": True,
            "account_positions": len(account),
            "managed_positions": len(self.positions),
        }

    def _session_order_exchange(self) -> str:
        """Return an automatic venue override for the currently open session.

        08:00~08:50 is NXT-only for PUMA live auto trading. From 09:00 onward
        the user's configured KRX/NXT/SOR order venue is used again.
        """
        hm = datetime.now().strftime("%H:%M")
        start = str(getattr(self.settings, "trade_start", "08:00") or "08:00")
        nxt_end = str(getattr(self.settings, "nxt_premarket_end", "08:50") or "08:50")
        if start <= hm < nxt_end:
            return "NXT"
        return ""

    def _buy_session_order(self, code: str, qty: int):
        exchange = self._session_order_exchange()
        if exchange == "NXT" and self.broker.__class__.__name__ != "SimBroker":
            quote_getter = getattr(self.broker, "get_best_quote", None)
            limit_order = getattr(self.broker, "buy_limit_on", None)
            if not callable(quote_getter) or not callable(limit_order):
                raise RuntimeError("NXT 프리마켓 자동 지정가 주문 기능이 없습니다.")
            quote = quote_getter(code, "NXT") or {}
            price = int(quote.get("best_ask", 0) or 0)
            if price <= 0:
                raise RuntimeError("NXT 최우선 매도호가를 조회하지 못했습니다.")
            try:
                resp = dict(limit_order(code, qty, price, "NXT") or {})
            except OrderStateUnknown as exc:
                raise AutoOrderError(f"NXT 매수주문 상태 확인 필요: {exc}") from exc
            except BrokerError as exc:
                allowed = _max_buyable_qty_from_error(exc)
                if 0 < allowed < int(qty):
                    try:
                        resp = dict(limit_order(code, int(allowed), price, "NXT") or {})
                        resp["_puma_order_qty"] = int(allowed)
                        resp["_puma_qty_adjusted_from"] = int(qty)
                        resp["_puma_qty_adjust_reason"] = str(exc)
                    except OrderStateUnknown as retry_exc:
                        raise AutoOrderError(f"NXT 매수 재주문 상태 확인 필요: {retry_exc}") from retry_exc
                    except BrokerError:
                        self.cooldowns[code] = datetime.now() + timedelta(seconds=15)
                        raise
                    except Exception as retry_exc:
                        raise AutoOrderError(f"NXT 매수 재주문 상태 확인 필요: {retry_exc}") from retry_exc
                else:
                    # 명시적 주문거절은 미체결이 확정이므로 자동매매를 끄지 않는다.
                    self.cooldowns[code] = datetime.now() + timedelta(seconds=15)
                    raise
            except Exception as exc:
                # 서드파티/테스트 브로커의 원시 통신 예외는 체결여부를 확정할 수 없다.
                raise AutoOrderError(f"NXT 매수주문 상태 확인 필요: {exc}") from exc
            resp["_puma_exchange"] = "NXT"
            resp["_puma_order_type"] = "limit"
            resp["_puma_limit_price"] = price
            resp.setdefault("_puma_order_qty", int(qty))
            return resp

        routed = getattr(self.broker, "buy_market_on", None)
        try:
            if exchange and callable(routed):
                resp = routed(code, qty, exchange)
            else:
                resp = self.broker.buy_market(code, qty)
            if isinstance(resp, dict):
                resp.setdefault("_puma_order_qty", int(qty))
            return resp
        except OrderStateUnknown as exc:
            raise AutoOrderError(f"매수주문 상태 확인 필요: {exc}") from exc
        except BrokerError as exc:
            # 키움이 'N주 매수가능'이라고 명시적으로 거절하면 주문 상태는 확정적으로 미체결이다.
            # 자동매매를 끄지 말고 그 수량으로 즉시 한 번만 재주문한다.
            allowed = _max_buyable_qty_from_error(exc)
            if 0 < allowed < int(qty):
                retry_qty = int(allowed)
                try:
                    if exchange and callable(routed):
                        resp = routed(code, retry_qty, exchange)
                    else:
                        resp = self.broker.buy_market(code, retry_qty)
                    if isinstance(resp, dict):
                        resp["_puma_order_qty"] = retry_qty
                        resp["_puma_qty_adjusted_from"] = int(qty)
                        resp["_puma_qty_adjust_reason"] = str(exc)
                    return resp
                except OrderStateUnknown as retry_exc:
                    raise AutoOrderError(f"매수 재주문 상태 확인 필요: {retry_exc}") from retry_exc
                except BrokerError:
                    self.cooldowns[code] = datetime.now() + timedelta(seconds=15)
                    raise
                except Exception as retry_exc:
                    raise AutoOrderError(f"매수 재주문 상태 확인 필요: {retry_exc}") from retry_exc
            self.cooldowns[code] = datetime.now() + timedelta(seconds=15)
            raise
        except Exception as exc:
            raise AutoOrderError(f"매수주문 상태 확인 필요: {exc}") from exc

    def _sell_session_order(self, code: str, qty: int):
        exchange = self._session_order_exchange()
        if exchange == "NXT" and self.broker.__class__.__name__ != "SimBroker":
            quote_getter = getattr(self.broker, "get_best_quote", None)
            limit_order = getattr(self.broker, "sell_limit_on", None)
            if not callable(quote_getter) or not callable(limit_order):
                raise RuntimeError("NXT 프리마켓 자동 지정가 주문 기능이 없습니다.")
            quote = quote_getter(code, "NXT") or {}
            price = int(quote.get("best_bid", 0) or 0)
            if price <= 0:
                raise RuntimeError("NXT 최우선 매수호가를 조회하지 못했습니다.")
            try:
                resp = dict(limit_order(code, qty, price, "NXT") or {})
            except OrderStateUnknown as exc:
                raise AutoOrderError(f"NXT 매도주문 상태 확인 필요: {exc}") from exc
            except BrokerError:
                raise
            except Exception as exc:
                raise AutoOrderError(f"NXT 매도주문 상태 확인 필요: {exc}") from exc
            resp["_puma_exchange"] = "NXT"
            resp["_puma_order_type"] = "limit"
            resp["_puma_limit_price"] = price
            return resp

        routed = getattr(self.broker, "sell_market_on", None)
        try:
            if exchange and callable(routed):
                return routed(code, qty, exchange)
            return self.broker.sell_market(code, qty)
        except OrderStateUnknown as exc:
            raise AutoOrderError(f"매도주문 상태 확인 필요: {exc}") from exc
        except BrokerError:
            raise
        except Exception as exc:
            raise AutoOrderError(f"매도주문 상태 확인 필요: {exc}") from exc

    @staticmethod
    def _pending_age_seconds(pending: dict) -> float:
        raw = pending.get("created_at")
        if isinstance(raw, datetime):
            stamp = raw
        else:
            try:
                stamp = datetime.fromisoformat(str(raw or ""))
            except Exception:
                return 0.0
        return max(0.0, (datetime.now() - stamp).total_seconds())

    def _manage_nxt_limit_pending(self, code: str, name: str, current: float):
        """Reprice an unfilled NXT premarket limit order against the best quote.

        The old remainder is cancelled before every reprice, then the account is
        synchronized and only the truly unfilled remainder is resubmitted. This
        avoids over-ordering even when a partial fill races with cancellation.
        Buy chasing is capped from the first submitted ask; sells may keep
        following the best bid because they are position-risk exits.
        """
        pending = self.pending_orders.get(code)
        if not pending:
            return None
        if str(pending.get("exchange", "")).upper() != "NXT" or str(pending.get("order_type", "")).lower() != "limit":
            return None

        hm = datetime.now().strftime("%H:%M")
        start = str(getattr(self.settings, "trade_start", "08:00") or "08:00")
        end = str(getattr(self.settings, "nxt_premarket_end", "08:50") or "08:50")
        if not (start <= hm < end):
            return None

        side = str(pending.get("side", "")).upper()
        before = int(pending.get("account_qty_before", 0) or 0)

        wait_sec = max(1.0, float(getattr(self.settings, "nxt_limit_reprice_sec", 2.0) or 2.0))
        if self._pending_age_seconds(pending) < wait_sec:
            return None

        max_reprices = max(0, int(getattr(self.settings, "nxt_limit_max_reprices", 3) or 0))
        count = max(0, int(pending.get("reprice_count", 0) or 0))
        if count >= max_reprices:
            return {
                "code": code, "name": self.positions.get(code).name if code in self.positions else name,
                "status": f"{side}_PENDING", "price": current,
                "signal": f"NXT 지정가 유지 · 재정정 {count}/{max_reprices} 완료",
            }

        quote_getter = getattr(self.broker, "get_best_quote", None)
        cancel = getattr(self.broker, "cancel_order_on", None)
        limit_order = getattr(self.broker, "buy_limit_on" if side == "BUY" else "sell_limit_on", None)
        if not callable(quote_getter) or not callable(cancel) or not callable(limit_order):
            return None

        quote = quote_getter(code, "NXT") or {}
        new_price = int(quote.get("best_ask" if side == "BUY" else "best_bid", 0) or 0)
        old_price = int(pending.get("limit_price", 0) or 0)
        if new_price <= 0 or new_price == old_price:
            pending["created_at"] = datetime.now()
            self._persist_runtime()
            return None

        first_price = int(pending.get("first_limit_price", old_price) or old_price or new_price)
        if side == "BUY":
            chase_pct = max(0.0, float(getattr(self.settings, "nxt_limit_buy_chase_pct", 0.50) or 0.50))
            ceiling = first_price * (1.0 + chase_pct / 100.0)
            if first_price > 0 and new_price > ceiling:
                try:
                    cancel(code, str(pending.get("ord_no", "")), "NXT", 0)
                    self.pending_orders.pop(code, None)
                    self.sync_account(force=True)
                except OrderStateUnknown as exc:
                    raise AutoOrderError(f"NXT 매수취소 상태 확인 필요: {exc}") from exc
                except BrokerError:
                    self.sync_account(force=True)
                    raise
                held = int(self.account_qty.get(code, 0) or 0)
                if held <= before:
                    self.managed_qty.pop(code, None)
                    self.managed_meta.pop(code, None)
                    self.positions.pop(code, None)
                    self.cooldowns[code] = datetime.now() + timedelta(minutes=1)
                else:
                    self.managed_qty[code] = held
                self._persist_runtime()
                return {
                    "code": code, "name": name, "status": "BUY_CANCELLED_CHASE",
                    "price": current,
                    "signal": f"NXT 추격매수 중단 · 최우선매도 {new_price:,.0f} > 허용 {ceiling:,.0f}",
                }

        # Cancel the old remainder first, then synchronize once to avoid duplicating
        # shares if a fill raced with the cancel request.
        try:
            cancel(code, str(pending.get("ord_no", "")), "NXT", 0)
            self.sync_account(force=True)
        except OrderStateUnknown as exc:
            raise AutoOrderError(f"NXT 주문취소/동기화 상태 확인 필요: {exc}") from exc
        except BrokerError:
            self.sync_account(force=True)
            raise
        latest = self.pending_orders.get(code)
        if latest is None:
            return {
                "code": code, "name": name, "status": f"{side}_FILLED",
                "price": current, "signal": "NXT 지정가 체결 확인",
            }

        now_qty = int(self.account_qty.get(code, 0) or 0)
        if side == "BUY":
            base_qty = int(latest.get("account_qty_before", before) or 0)
            target_qty = max(1, int(latest.get("target_qty", latest.get("qty", 0)) or 0))
            filled_qty = max(0, now_qty - base_qty)
            qty = max(0, target_qty - filled_qty)
        else:
            desired_remaining = max(0, int(latest.get("remaining_qty", 0) or 0))
            qty = max(0, now_qty - desired_remaining)
            latest["account_qty_before"] = now_qty

        if qty <= 0:
            self.sync_account(force=True)
            return {
                "code": code, "name": self.positions.get(code).name if code in self.positions else name,
                "status": f"{side}_FILLED", "price": current,
                "signal": "NXT 지정가 목표수량 체결 확인",
            }

        try:
            resp = dict(limit_order(code, qty, new_price, "NXT") or {})
        except OrderStateUnknown as exc:
            raise AutoOrderError(f"NXT 재주문 상태 확인 필요: {exc}") from exc
        except BrokerError:
            # 기존 주문은 이미 정상 취소됐고 새 주문은 명시적으로 거절됨.
            # stale pending을 제거해 다음 스캔에서 같은 취소를 무한 반복하지 않는다.
            self.pending_orders.pop(code, None)
            if side == "BUY":
                self.cooldowns[code] = datetime.now() + timedelta(seconds=15)
            self._persist_runtime()
            raise
        latest["qty"] = qty
        self.daily_order_count += 1
        latest["ord_no"] = str(resp.get("ord_no", ""))
        latest["limit_price"] = new_price
        latest["first_limit_price"] = first_price
        latest["reprice_count"] = count + 1
        latest["created_at"] = datetime.now()
        self._persist_runtime()
        return {
            "code": code, "name": name, "status": f"{side}_REPRICED",
            "price": current,
            "signal": f"NXT 최우선 {'매도' if side == 'BUY' else '매수'}호가 {new_price:,.0f}원으로 재정정 {count + 1}/{max_reprices}",
            "order": resp,
        }

    def _submit_buy(self, code: str, name: str, current: float, reason: str, *, stop_price: float = 0.0, entry_kind: str = "", require_enabled: bool = False):
        if require_enabled and not self.enabled:
            return {"code": code, "name": name, "status": "STOPPED", "price": current, "signal": "자동매매 중지 · 신규주문 차단"}
        budget = self.current_trade_budget()
        qty = int(budget // current)
        if qty < 1:
            return {
                "code": code, "name": name, "status": "WAIT", "price": current,
                "signal": f"현재 복리 시드 {budget:,.0f}원보다 주가가 높아 자동매수 불가",
            }
        requested_qty = int(qty)
        resp = self._buy_session_order(code, qty)
        actual_qty = int((resp or {}).get("_puma_order_qty", requested_qty) or requested_qty) if isinstance(resp, dict) else requested_qty
        qty = max(1, actual_qty)
        if isinstance(resp, dict) and int(resp.get("_puma_qty_adjusted_from", 0) or 0) > qty:
            reason = (
                f"{reason} · 주문가능 수량 자동조정 "
                f"{int(resp.get('_puma_qty_adjusted_from', requested_qty))}→{qty}주"
            )
        self.daily_order_count += 1
        if self.broker.__class__.__name__ != "SimBroker":
            # 앱이 재시작되어도 체결된 종목을 PUMA 포지션으로 복구할 수 있도록 주문수량을 먼저 기록.
            self.managed_qty[code] = qty
            self.managed_meta[code] = {
                "stop_price": float(stop_price or 0),
                "entry_kind": str(entry_kind or ""),
                "partial_taken": False,
                "partial_price": 0.0,
                "partial_time": "",
                "remainder_down_trigger_bar": "",
                "remainder_down_wait_bar": "",
            }
            self.pending_orders[code] = {
                "side": "BUY",
                "qty": qty,
                "ord_no": str(resp.get("ord_no", "")),
                "created_at": datetime.now(),
                "stop_price": float(stop_price or 0),
                "entry_kind": str(entry_kind or ""),
                "seed_budget": float(budget),
                "target_qty": qty,
                "account_qty_before": int(self.account_qty.get(code, 0) or 0),
                "exchange": str(resp.get("_puma_exchange", "") or ""),
                "order_type": str(resp.get("_puma_order_type", "market") or "market"),
                "limit_price": int(resp.get("_puma_limit_price", 0) or 0),
                "first_limit_price": int(resp.get("_puma_limit_price", 0) or 0),
                "reprice_count": 0,
            }
            self._persist_runtime()
            return {"code": code, "name": name, "status": "BUY_SENT", "price": current, "signal": reason, "order": resp}

        pos = Position(
            code, name, qty, current, current, datetime.now().isoformat(timespec="seconds"),
            str(resp.get("ord_no", "")), float(stop_price or 0), str(entry_kind or ""), False
        )
        self.positions[code] = pos
        self._persist_runtime()
        return {"code": code, "name": name, "status": "BUY", "price": current, "signal": reason, "order": resp}

    def _submit_sell(self, code: str, pos: Position, current: float, reason: str, *, require_enabled: bool = False):
        if require_enabled and not self.enabled:
            return {"code": code, "name": pos.name, "status": "STOPPED", "price": current, "signal": "자동매매 중지 · 자동주문 차단"}
        resp = self._sell_session_order(code, pos.qty)
        self.daily_order_count += 1
        if self.broker.__class__.__name__ != "SimBroker":
            self.pending_orders[code] = {
                "side": "SELL",
                "qty": pos.qty,
                "ord_no": str(resp.get("ord_no", "")),
                "created_at": datetime.now(),
                "account_qty_before": int(self.account_qty.get(code, pos.qty)),
                "remaining_qty": 0,
                "full_exit": True,
                "stop_price": float(getattr(pos, "stop_price", 0) or 0),
                "entry_kind": str(getattr(pos, "entry_kind", "") or ""),
                "partial_taken_after": bool(getattr(pos, "partial_taken", False)),
                "seed_pnl_delta": (float(current) - float(pos.entry_price)) * int(pos.qty),
                "exchange": str(resp.get("_puma_exchange", "") or ""),
                "order_type": str(resp.get("_puma_order_type", "market") or "market"),
                "limit_price": int(resp.get("_puma_limit_price", 0) or 0),
                "first_limit_price": int(resp.get("_puma_limit_price", 0) or 0),
                "reprice_count": 0,
            }
            self._persist_runtime()
            return {"code": code, "name": pos.name, "status": "SELL_SENT", "price": current, "signal": reason, "order": resp}

        realized = (float(current) - float(pos.entry_price)) * int(pos.qty)
        del self.positions[code]
        self.cooldowns[code] = datetime.now() + timedelta(minutes=self.settings.cooldown_min)
        self._record_realized_delta(realized)
        return {"code": code, "name": pos.name, "status": "SELL", "price": current, "signal": reason, "order": resp}

    def _submit_partial_sell(
        self, code: str, pos: Position, current: float, reason: str, *,
        require_enabled: bool = False, sell_ratio: float = 0.5,
    ):
        if require_enabled and not self.enabled:
            return {"code": code, "name": pos.name, "status": "STOPPED", "price": current, "signal": "자동매매 중지 · 자동주문 차단"}
        ratio = min(1.0, max(0.01, float(sell_ratio or 0.5)))
        sell_qty = max(1, int(int(pos.qty) * ratio))
        if sell_qty >= int(pos.qty):
            return self._submit_sell(code, pos, current, reason + " · 1주라 전량", require_enabled=require_enabled)

        remaining = int(pos.qty) - sell_qty
        resp = self._sell_session_order(code, sell_qty)
        self.daily_order_count += 1

        if self.broker.__class__.__name__ != "SimBroker":
            self.pending_orders[code] = {
                "side": "SELL",
                "qty": sell_qty,
                "ord_no": str(resp.get("ord_no", "")),
                "created_at": datetime.now(),
                "account_qty_before": int(self.account_qty.get(code, pos.qty)),
                "remaining_qty": remaining,
                "full_exit": False,
                "stop_price": float(getattr(pos, "stop_price", 0) or 0),
                "entry_kind": str(getattr(pos, "entry_kind", "") or ""),
                "partial_taken_after": True,
                "partial_price_after": float(current),
                "partial_time_after": datetime.now().isoformat(timespec="seconds"),
                "remainder_down_trigger_bar_after": "",
                "remainder_down_wait_bar_after": "",
                "seed_pnl_delta": (float(current) - float(pos.entry_price)) * int(sell_qty),
                "exchange": str(resp.get("_puma_exchange", "") or ""),
                "order_type": str(resp.get("_puma_order_type", "market") or "market"),
                "limit_price": int(resp.get("_puma_limit_price", 0) or 0),
                "first_limit_price": int(resp.get("_puma_limit_price", 0) or 0),
                "reprice_count": 0,
            }
            self._persist_runtime()
            return {
                "code": code, "name": pos.name, "status": "PARTIAL_SELL_SENT",
                "price": current, "signal": reason, "order": resp,
            }

        self._record_realized_delta((float(current) - float(pos.entry_price)) * int(sell_qty))
        pos.qty = remaining
        pos.partial_taken = True
        pos.partial_price = float(current)
        pos.partial_time = datetime.now().isoformat(timespec="seconds")
        pos.remainder_down_trigger_bar = ""
        pos.remainder_down_wait_bar = ""
        self.managed_qty[code] = remaining
        self.managed_meta[code] = {
            "stop_price": float(getattr(pos, "stop_price", 0) or 0),
            "entry_kind": str(getattr(pos, "entry_kind", "") or ""),
            "partial_taken": True,
            "partial_price": float(current),
            "partial_time": pos.partial_time,
            "remainder_down_trigger_bar": "",
            "remainder_down_wait_bar": "",
        }
        self._persist_runtime()
        return {
            "code": code, "name": pos.name, "status": "PARTIAL_SELL",
            "price": current, "signal": reason, "order": resp,
        }

    def process(
        self,
        code,
        name,
        require_buy_filter: bool = True,
        allow_buy: bool = True,
        market_context: str = "",
    ):
        self._roll_daily_counter()
        if self.broker.__class__.__name__ != "SimBroker":
            self.sync_account(force=False)

        hm_now = datetime.now().strftime("%H:%M")
        nxt_end = str(getattr(self.settings, "nxt_premarket_end", "08:50") or "08:50")
        chart_exchange = ""
        exchange_getter = getattr(self.broker, "get_minute_candles_for_exchange", None)
        if callable(exchange_getter) and self.broker.__class__.__name__ != "SimBroker":
            if str(getattr(self.settings, "trade_start", "08:00") or "08:00") <= hm_now < nxt_end:
                # NXT premarket bars require the documented _NX chart code.
                chart_exchange = "NXT"
            elif str(market_context or "").upper() == "NXT" and hm_now >= "09:00":
                # Keep the 08:00 NXT hill connected to the regular session with SOR/integrated bars.
                chart_exchange = "SOR"

        if chart_exchange:
            candles = exchange_getter(code, self.settings.timeframe_min, chart_exchange)
        else:
            candles = self.broker.get_minute_candles(code, self.settings.timeframe_min)
        if not candles:
            return {"code": code, "name": name, "status": "NO DATA", "price": 0, "signal": "데이터 없음"}

        try:
            current = abs(float(str(candles[0].get("cur_prc", "0")).replace(",", "")))
        except Exception:
            current = 0

        bar_key = _minute_bucket_key(candles[0], self.settings.timeframe_min)
        try:
            previous_bar_close = abs(float(str(candles[1].get("cur_prc", "0")).replace(",", ""))) if len(candles) > 1 else 0.0
        except Exception:
            previous_bar_close = 0.0

        pending = self.pending_orders.get(code)
        if pending:
            managed = self._manage_nxt_limit_pending(code, name, current)
            if managed is not None:
                return managed
            pending = self.pending_orders.get(code)
            if pending:
                return {
                    "code": code,
                    "name": self.positions.get(code).name if code in self.positions else name,
                    "status": f"{pending.get('side')}_PENDING",
                    "price": current,
                    "signal": (
                        f"NXT 지정가 주문 확인 중 · {pending.get('limit_price', 0):,.0f}원 · {pending.get('ord_no', '')}"
                        if str(pending.get("exchange", "")).upper() == "NXT"
                        else f"주문 확인 중 · {pending.get('ord_no', '')}"
                    ),
                }

        # NXT 프리마켓 종료(08:50)와 KRX 정규장 시작(09:00) 사이에는
        # 신규 주문/자동청산을 보내지 않는다. 보유종목은 09:00부터 즉시 다시 관리한다.
        if nxt_end <= hm_now < "09:00":
            return {
                "code": code,
                "name": self.positions.get(code).name if code in self.positions else name,
                "status": "HOLD" if code in self.positions else "WAIT",
                "price": current,
                "signal": f"NXT {nxt_end} 종료 · KRX 09:00 재개 대기",
            }

        if code in self.positions:
            pos = self.positions[code]
            pnl = pos.pnl_pct(current)

            # 가보자 추세추적: 새로 확정된 높은 차 저점이 생기면 손절선을 위로만 올린다.
            if bool(getattr(self.settings, "gabojago_trend_tracking_enabled", True)):
                old_stop = float(getattr(pos, "stop_price", 0) or 0)
                new_stop = _gaboja_trend_stop_from_rows(
                    candles,
                    current_bar_key=bar_key,
                    timeframe=self.settings.timeframe_min,
                    current_stop=old_stop,
                    entry_price=float(pos.entry_price or 0),
                )
                if new_stop > old_stop:
                    pos.stop_price = float(new_stop)
                    meta = dict(self.managed_meta.get(code) or {})
                    meta.update({
                        "stop_price": float(new_stop),
                        "entry_kind": str(getattr(pos, "entry_kind", "") or ""),
                        "partial_taken": bool(getattr(pos, "partial_taken", False)),
                        "partial_price": float(getattr(pos, "partial_price", 0) or 0),
                        "partial_time": str(getattr(pos, "partial_time", "") or ""),
                    })
                    self.managed_meta[code] = meta
                    self._persist_runtime()

            # 당일 단타 최종 안전청산. 새 추세추적 모드는 레거시 13:00 설정과 분리.
            trend_tracking = bool(getattr(self.settings, "gabojago_trend_tracking_enabled", True))
            day_exit = (
                str(getattr(self.settings, "gabojago_trend_force_exit_time", "15:00") or "15:00")
                if trend_tracking
                else str(getattr(self.settings, "gabojago_force_exit_time", "13:00") or "13:00")
            )
            if self.enabled and float(getattr(pos, "stop_price", 0) or 0) > 0 and datetime.now().strftime("%H:%M") >= day_exit:
                return self._submit_sell(code, pos, current, f"가보자 당일 단타 {day_exit} 전량청산", require_enabled=True)

            # 영차 단타 빠른 익절: 유효 진입 뒤 고점을 만들고 되밀리기 시작하면
            # +4%를 기다리지 않고 먼저 수익을 확보한다.
            if (
                self.enabled
                and bool(getattr(self.settings, "gabojago_quick_profit_enabled", True))
                and str(getattr(pos, "entry_kind", "") or "") in {"PULLBACK", "YOUNG2"}
            ):
                quick_exit, quick_peak, quick_gain = _gaboja_quick_profit_exit_from_rows(
                    candles,
                    current_bar_key=bar_key,
                    timeframe=self.settings.timeframe_min,
                    entry_price=float(pos.entry_price or 0),
                    opened_at=str(getattr(pos, "opened_at", "") or ""),
                    min_profit_pct=float(getattr(self.settings, "gabojago_quick_profit_min_pct", 1.0) or 1.0),
                    peak_retreat_pct=float(getattr(self.settings, "gabojago_quick_profit_peak_retreat_pct", 0.35) or 0.35),
                )
                if quick_exit:
                    return self._submit_sell(
                        code, pos, current,
                        f"가보자 빠른 익절 · 고점 {quick_peak:,.0f} 형성 후 되밀림 · 고점기준 {quick_gain:+.2f}%",
                        require_enabled=True,
                    )

            # 가보자 추세추적: +4% 최초 도달 시 50% 확보, 나머지 50%는 차 저점/3파동 추적.
            partial_target = float(getattr(self.settings, "gabojago_partial_profit_pct", self.settings.take_profit_pct) or self.settings.take_profit_pct)
            partial_ratio = float(getattr(self.settings, "gabojago_partial_sell_ratio", 0.50) or 0.50)
            if self.enabled and not bool(getattr(pos, "partial_taken", False)) and pnl >= partial_target:
                pct = max(1, int(round(partial_ratio * 100)))
                return self._submit_partial_sell(
                    code, pos, current,
                    f"가보자 +{partial_target:.1f}% 1차 {pct}% 익절 · 잔량 추세추적 · {pnl:+.2f}%",
                    require_enabled=True,
                    sell_ratio=partial_ratio,
                )

            # 차 매수 뒤 상승·눌림을 거쳐 다음 재상승 파동(3)이 확인되면 잔량 전량 매도.
            stage3, stage3_high = _gaboja_stage3_exit_from_rows(
                candles,
                current_bar_key=bar_key,
                timeframe=self.settings.timeframe_min,
                entry_price=float(pos.entry_price or 0),
                opened_at=str(getattr(pos, "opened_at", "") or ""),
            )
            if self.enabled and stage3:
                return self._submit_sell(
                    code, pos, current,
                    f"가보자 3파동 매도 · 재상승 고점 {stage3_high:,.0f} 확인",
                    require_enabled=True,
                )

            state_before = (
                str(getattr(pos, "remainder_down_trigger_bar", "") or ""),
                str(getattr(pos, "remainder_down_wait_bar", "") or ""),
            )
            should_sell, reason = evaluate_sell(
                pos,
                current,
                self.settings,
                bar_key=bar_key,
                previous_bar_close=previous_bar_close,
            )
            state_after = (
                str(getattr(pos, "remainder_down_trigger_bar", "") or ""),
                str(getattr(pos, "remainder_down_wait_bar", "") or ""),
            )
            if state_after != state_before:
                meta = dict(self.managed_meta.get(code) or {})
                meta.update({
                    "stop_price": float(getattr(pos, "stop_price", 0) or 0),
                    "entry_kind": str(getattr(pos, "entry_kind", "") or ""),
                    "partial_taken": bool(getattr(pos, "partial_taken", False)),
                    "partial_price": float(getattr(pos, "partial_price", 0) or 0),
                    "partial_time": str(getattr(pos, "partial_time", "") or ""),
                    "remainder_down_trigger_bar": state_after[0],
                    "remainder_down_wait_bar": state_after[1],
                })
                self.managed_meta[code] = meta
                self._persist_runtime()

            if self.enabled and should_sell:
                return self._submit_sell(code, pos, current, reason, require_enabled=True)
            return {"code": code, "name": pos.name, "status": "HOLD", "price": current, "signal": f"{reason} / {pnl:+.2f}%"}

        # 신규매수는 후보 공급원이 무엇이든 '가보자' 두 타점만 허용한다.
        # 영웅문 조건검색은 종목을 공급할 뿐, 편입 자체가 매수 신호가 되지 않는다.
        daily_rows = self._gaboja_daily_rows(code)
        sig = evaluate_gaboja(
            candles,
            daily_rows,
            scan_start=self.settings.scan_start,
            trade_start=str(getattr(self.settings, "trade_start", "08:00") or "08:00"),
            scan_end=self.settings.scan_end,
            apply_secondary_filter=bool(require_buy_filter),
            secondary_min_score=int(getattr(self.settings, "puma_secondary_min_score", 3) or 3),
            cha_max_ratio=float(getattr(self.settings, "gabojago_cha_max_ratio", 0.35) or 0.35),
            cha_volume_pace_ratio=float(getattr(self.settings, "gabojago_cha_volume_pace_ratio", 1.00) or 1.00),
            cha_min_live_seconds=int(getattr(self.settings, "gabojago_cha_min_live_seconds", 20) or 20),
        )

        if self.daily_loss_locked:
            return {
                "code": code, "name": name, "status": "DAILY_STOP", "price": current,
                "signal": f"하루 손실 한도 도달 · {self.daily_loss_pct():+.2f}% · 다음 거래일 현재 시드 {self.seed_capital:,.0f}원으로 재개",
            }
        if self.phase1_complete():
            return {
                "code": code, "name": name, "status": "TARGET", "price": current,
                "signal": f"1차 목표 300만원 달성 · 현재 시드 {self.seed_capital:,.0f}원 · 신규매수 중지",
            }

        if self.enabled and allow_buy and sig.passed and self.can_open(code) and current > 0:
            # 차 진입은 진행봉 저점이 아직 확정되지 않았으므로 기준봉 시가를 최초 손절선으로 사용.
            # 차 타점을 놓친 뒤 전고 몸통돌파 보조진입이면 이미 확인된 직전 차 저점을 쓴다.
            if str(sig.entry_kind or "") == "PULLBACK":
                stop_price = float(sig.basis_open or 0)
            else:
                stop_price = float(sig.pullback_low or sig.basis_open or 0)
            return self._submit_buy(
                code, name, current, sig.reason,
                stop_price=stop_price,
                entry_kind=sig.entry_kind,
                require_enabled=True,
            )

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
            "change": 0.0,
            "volume_ratio": float(getattr(sig, "day_volume_ratio", 0) or 0),
            "rsi": None,
            "entry_kind": str(getattr(sig, "entry_kind", "") or ""),
            "basis_open": float(getattr(sig, "basis_open", 0) or 0),
            "puma_score": int((getattr(sig, "details", {}) or {}).get("puma_score", 0) or 0),
            "premarket_available": bool((getattr(sig, "details", {}) or {}).get("premarket_available", False)),
            "premarket_change_pct": float((getattr(sig, "details", {}) or {}).get("premarket_change_pct", 0) or 0),
            "premarket_high_retention_pct": float((getattr(sig, "details", {}) or {}).get("premarket_high_retention_pct", 0) or 0),
            "premarket_volume": float((getattr(sig, "details", {}) or {}).get("premarket_volume", 0) or 0),
        }
