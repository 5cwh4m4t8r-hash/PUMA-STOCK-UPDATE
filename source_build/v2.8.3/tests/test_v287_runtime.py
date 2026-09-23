import json

from puma_trader import storage


def _patch_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(storage, "RUNTIME_PATH", tmp_path / "runtime.json")


def test_runtime_preserves_gaboja_partial_state(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    storage.save_runtime({
        "daily_order_date": "2026-09-23",
        "daily_order_count": 3,
        "managed_qty": {"005930": 5},
        "managed_meta": {
            "005930": {
                "stop_price": 70000,
                "entry_kind": "PULLBACK",
                "partial_taken": True,
                "partial_price": 73950,
                "partial_time": "2026-09-23T10:41:07",
            }
        },
        "pending_orders": {},
    })

    loaded = storage.load_runtime()
    meta = loaded["managed_meta"]["005930"]
    assert meta["partial_taken"] is True
    assert meta["partial_price"] == 73950
    assert meta["partial_time"] == "2026-09-23T10:41:07"


def test_runtime_preserves_pending_partial_sell_reference(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    storage.save_runtime({
        "managed_qty": {"005930": 10},
        "managed_meta": {},
        "pending_orders": {
            "005930": {
                "side": "SELL",
                "qty": 5,
                "ord_no": "12345",
                "created_at": "2026-09-23T10:41:07",
                "account_qty_before": 10,
                "remaining_qty": 5,
                "full_exit": False,
                "stop_price": 70000,
                "entry_kind": "BODY_REBREAK",
                "partial_taken_after": True,
                "partial_price_after": 73950,
                "partial_time_after": "2026-09-23T10:41:07",
            }
        },
    })

    loaded = storage.load_runtime()
    pending = loaded["pending_orders"]["005930"]
    assert pending["partial_price_after"] == 73950
    assert pending["partial_time_after"] == "2026-09-23T10:41:07"


def test_runtime_write_is_valid_json_and_leaves_no_tmp(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    storage.save_runtime({"managed_qty": {}, "managed_meta": {}, "pending_orders": {}})
    raw = json.loads((tmp_path / "runtime.json").read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    assert not (tmp_path / "runtime.json.tmp").exists()
