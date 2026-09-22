import json
from pathlib import Path
from .models import StrategySettings
from .swing import SwingSettings

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
STRATEGY_PATH = CONFIG_DIR / "strategy.json"
WATCHLIST_PATH = CONFIG_DIR / "watchlist.json"
RUNTIME_PATH = CONFIG_DIR / "runtime.json"
SWING_PATH = CONFIG_DIR / "swing.json"


def load_strategy() -> StrategySettings:
    CONFIG_DIR.mkdir(exist_ok=True)
    if not STRATEGY_PATH.exists():
        s = StrategySettings()
        save_strategy(s)
        return s
    try:
        return StrategySettings.from_dict(json.loads(STRATEGY_PATH.read_text(encoding="utf-8")))
    except Exception:
        return StrategySettings()


def save_strategy(settings: StrategySettings):
    CONFIG_DIR.mkdir(exist_ok=True)
    STRATEGY_PATH.write_text(
        json.dumps(settings.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_watchlist():
    CONFIG_DIR.mkdir(exist_ok=True)
    if not WATCHLIST_PATH.exists():
        return []
    try:
        data = json.loads(WATCHLIST_PATH.read_text(encoding="utf-8"))
        return [x for x in data if isinstance(x, dict) and x.get("code")]
    except Exception:
        return []


def save_watchlist(items):
    CONFIG_DIR.mkdir(exist_ok=True)
    WATCHLIST_PATH.write_text(
        json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_runtime() -> dict:
    """주문 안전상 필요한 최소 런타임 상태만 저장. 인증키/시크릿은 절대 저장하지 않음."""
    CONFIG_DIR.mkdir(exist_ok=True)
    default = {"daily_order_date": "", "daily_order_count": 0, "managed_qty": {}, "managed_meta": {}, "pending_orders": {}}
    if not RUNTIME_PATH.exists():
        return default
    try:
        raw = json.loads(RUNTIME_PATH.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return default
        managed = raw.get("managed_qty", {})
        if not isinstance(managed, dict):
            managed = {}
        managed_meta = raw.get("managed_meta", {})
        if not isinstance(managed_meta, dict):
            managed_meta = {}
        safe_meta = {}
        for code, item in managed_meta.items():
            if not isinstance(item, dict):
                continue
            safe_meta[str(code)] = {
                "stop_price": float(item.get("stop_price", 0) or 0),
                "entry_kind": str(item.get("entry_kind", "")),
                "partial_taken": bool(item.get("partial_taken", False)),
            }

        managed_meta = raw.get("managed_meta", {})
        if not isinstance(managed_meta, dict):
            managed_meta = {}
        pending = raw.get("pending_orders", {})
        if not isinstance(pending, dict):
            pending = {}
        safe_pending = {}
        for code, item in pending.items():
            if not isinstance(item, dict):
                continue
            side = str(item.get("side", "")).upper()
            if side not in ("BUY", "SELL"):
                continue
            safe_pending[str(code)] = {
                "side": side,
                "qty": max(0, int(item.get("qty", 0) or 0)),
                "ord_no": str(item.get("ord_no", "")),
                "created_at": str(item.get("created_at", "")),
                "account_qty_before": max(0, int(item.get("account_qty_before", 0) or 0)),
                "remaining_qty": max(0, int(item.get("remaining_qty", 0) or 0)),
                "full_exit": bool(item.get("full_exit", True)),
                "stop_price": float(item.get("stop_price", 0) or 0),
                "entry_kind": str(item.get("entry_kind", "")),
                "partial_taken_after": bool(item.get("partial_taken_after", False)),
            }
        return {
            "daily_order_date": str(raw.get("daily_order_date", "")),
            "daily_order_count": int(raw.get("daily_order_count", 0) or 0),
            "managed_qty": {str(k): max(0, int(v)) for k, v in managed.items() if str(k)},
            "managed_meta": safe_meta,
            "pending_orders": safe_pending,
        }
    except Exception:
        return default


def save_runtime(data: dict):
    CONFIG_DIR.mkdir(exist_ok=True)
    managed_meta = {}
    for code, item in dict(data.get("managed_meta", {})).items():
        if not isinstance(item, dict):
            continue
        managed_meta[str(code)] = {
            "stop_price": float(item.get("stop_price", 0) or 0),
            "entry_kind": str(item.get("entry_kind", "")),
            "partial_taken": bool(item.get("partial_taken", False)),
        }

    pending = {}
    for code, item in dict(data.get("pending_orders", {})).items():
        if not isinstance(item, dict):
            continue
        created = item.get("created_at", "")
        if hasattr(created, "isoformat"):
            created = created.isoformat(timespec="seconds")
        pending[str(code)] = {
            "side": str(item.get("side", "")).upper(),
            "qty": max(0, int(item.get("qty", 0) or 0)),
            "ord_no": str(item.get("ord_no", "")),
            "created_at": str(created),
            "account_qty_before": max(0, int(item.get("account_qty_before", 0) or 0)),
            "remaining_qty": max(0, int(item.get("remaining_qty", 0) or 0)),
            "full_exit": bool(item.get("full_exit", True)),
            "stop_price": float(item.get("stop_price", 0) or 0),
            "entry_kind": str(item.get("entry_kind", "")),
            "partial_taken_after": bool(item.get("partial_taken_after", False)),
        }
    safe = {
        "daily_order_date": str(data.get("daily_order_date", "")),
        "daily_order_count": int(data.get("daily_order_count", 0) or 0),
        "managed_qty": {str(k): max(0, int(v)) for k, v in dict(data.get("managed_qty", {})).items()},
        "managed_meta": managed_meta,
        "pending_orders": pending,
    }
    RUNTIME_PATH.write_text(json.dumps(safe, ensure_ascii=False, indent=2), encoding="utf-8")


def load_swing_settings() -> SwingSettings:
    CONFIG_DIR.mkdir(exist_ok=True)
    if not SWING_PATH.exists():
        return SwingSettings()
    try:
        raw = json.loads(SWING_PATH.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return SwingSettings()
        allowed = SwingSettings().__dict__.keys()
        clean = {k: raw[k] for k in allowed if k in raw}
        return SwingSettings(**clean)
    except Exception:
        return SwingSettings()


def save_swing_settings(settings: SwingSettings):
    CONFIG_DIR.mkdir(exist_ok=True)
    SWING_PATH.write_text(
        json.dumps(settings.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
