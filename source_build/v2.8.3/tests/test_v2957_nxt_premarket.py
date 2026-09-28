from datetime import datetime

from puma_trader.broker import KiwoomRestBroker
from puma_trader.gaboja import _premarket_snapshot, evaluate_gaboja
from puma_trader.models import StrategySettings


def _row(ts, op, hi, lo, cl, vol=1000):
    return {
        "cntr_tm": ts,
        "open_pric": str(op),
        "high_pric": str(hi),
        "low_pric": str(lo),
        "cur_prc": str(cl),
        "trde_qty": str(vol),
    }


def test_defaults_search_0800_but_trade_0900():
    settings = StrategySettings()
    assert settings.scan_start == "08:00"
    assert settings.trade_start == "09:00"


def test_premarket_snapshot_is_metadata_only():
    rows = [
        _row("20260929080000", 100, 106, 99, 105, 1000),
        _row("20260929080500", 105, 110, 104, 108, 2000),
    ]
    snap = _premarket_snapshot(rows, "20260929")
    assert snap["premarket_available"] is True
    assert snap["premarket_bars"] == 2
    assert snap["premarket_open"] == 100
    assert snap["premarket_close"] == 108
    assert round(snap["premarket_change_pct"], 2) == 8.00

    sig = evaluate_gaboja(
        rows, [], now=datetime(2026, 9, 29, 8, 10),
        scan_start="08:00", trade_start="09:00", apply_secondary_filter=False,
    )
    assert sig.passed is False
    assert "09:00" in sig.reason
    assert sig.details["premarket_available"] is True


def test_0900_session_excludes_08xx_bars():
    rows = [
        _row("20260929080000", 500, 550, 490, 540, 9000),
        _row("20260929080500", 540, 560, 530, 550, 8000),
        _row("20260929090000", 1000, 1020, 995, 1010, 1000),
        _row("20260929090500", 1010, 1030, 1005, 1020, 1200),
        _row("20260929091000", 1020, 1040, 1015, 1030, 1300),
        _row("20260929091500", 1030, 1045, 1025, 1035, 900),
    ]
    sig = evaluate_gaboja(
        rows, [], now=datetime(2026, 9, 29, 9, 16),
        scan_start="08:00", trade_start="09:00", apply_secondary_filter=False,
    )
    assert sig.basis_open == 1000


def test_nxt_candidate_api_uses_supported_nxt_exchange_and_merges_sources():
    broker = KiwoomRestBroker("key", "secret", real=True)
    seen = []

    def fake_post(path, api_id, body):
        seen.append((path, api_id, dict(body)))
        if api_id == "ka10027":
            return {
                "pred_pre_flu_rt_upper": [
                    {"stk_cd": "338220_NX", "stk_nm": "뷰노", "cur_prc": "+6340", "flu_rt": "+11.03", "now_trde_qty": "100000"},
                    {"stk_cd": "000001", "stk_nm": "A", "cur_prc": "+2000", "flu_rt": "+5.0", "now_trde_qty": "50000"},
                ]
            }
        if api_id == "ka10023":
            return {
                "trde_qty_sdnin": [
                    {"stk_cd": "338220_NX", "stk_nm": "뷰노", "cur_prc": "+6340", "flu_rt": "+11.03", "now_trde_qty": "100000", "sdnin_rt": "+320.0"},
                ]
            }
        raise AssertionError(api_id)

    broker._post = fake_post
    rows = broker.get_nxt_premarket_candidates(limit=30)

    assert {api for _, api, _ in seen} == {"ka10027", "ka10023"}
    assert all(body["stex_tp"] == "2" for _, _, body in seen)
    vuno = next(x for x in rows if x["code"] == "338220")
    assert set(vuno["sources"]) == {"NXT상승", "NXT거래량"}
    assert vuno["change_pct"] == 11.03
    assert vuno["surge_pct"] == 320.0
