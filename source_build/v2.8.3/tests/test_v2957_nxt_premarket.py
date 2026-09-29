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


def test_defaults_search_and_trade_from_0800():
    settings = StrategySettings()
    assert settings.scan_start == "08:00"
    assert settings.trade_start == "08:00"
    assert settings.nxt_premarket_end == "08:50"


def test_premarket_snapshot_keeps_08xx_context():
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


def test_0800_session_is_live_and_uses_08xx_bars():
    rows = [
        _row("20260929080000", 100, 102, 99, 101, 1000),
        _row("20260929080500", 101, 106, 100.5, 105.5, 1200),
        _row("20260929081000", 105.5, 113, 105, 112.5, 1800),
        _row("20260929081500", 112.0, 112.3, 109.5, 111.5, 700),
    ]
    sig = evaluate_gaboja(
        rows, [], now=datetime(2026, 9, 29, 8, 15),
        scan_start="08:00", trade_start="08:00", apply_secondary_filter=False,
    )
    assert sig.basis_open == 100
    assert sig.passed is True
    assert sig.entry_kind == "PULLBACK"
    assert sig.details["premarket_available"] is True


def test_hill_shaped_young_can_trigger_without_single_volume_impulse():
    # 거래량이 봉마다 줄어 단일 장대양봉 impulse 조건은 충족하지 않지만,
    # 여러 봉이 이어져 상승 언덕 전체를 영으로 만드는 사례.
    rows = [
        _row("20260929080000", 100, 102, 99, 101, 1000),
        _row("20260929080500", 101, 106, 100.5, 105, 900),
        _row("20260929081000", 105, 110, 104.5, 109.5, 800),
        _row("20260929081500", 109, 109.2, 107, 108.5, 700),
    ]
    sig = evaluate_gaboja(
        rows, [], now=datetime(2026, 9, 29, 8, 15),
        scan_start="08:00", trade_start="08:00", apply_secondary_filter=False,
    )
    assert sig.passed is True
    assert sig.entry_kind == "PULLBACK"
    assert sig.details["young_kind"] == "hill"
    assert sig.details["young_start_index"] == 0
    assert sig.young1_high == 110


def test_0900_keeps_0800_young_context():
    rows = [
        _row("20260929080000", 100, 102, 99, 101, 1000),
        _row("20260929080500", 101, 106, 100.5, 105, 900),
        _row("20260929081000", 105, 110, 104.5, 109.5, 800),
        _row("20260929081500", 109, 109.2, 107, 108.5, 700),
        _row("20260929090000", 108.5, 111.5, 108.2, 111.2, 900),
    ]
    sig = evaluate_gaboja(
        rows, [], now=datetime(2026, 9, 29, 9, 0),
        scan_start="08:00", trade_start="08:00", apply_secondary_filter=False,
    )
    assert sig.basis_open == 100
    assert sig.details["premarket_available"] is True


def test_nxt_chart_suffix_and_sor_integrated_suffix():
    broker = KiwoomRestBroker("key", "secret", real=True)
    seen = []

    def fake_minute(code, timeframe, max_pages=1, base_dt=None):
        seen.append((code, timeframe, max_pages, base_dt))
        return []

    broker.get_minute_candles = fake_minute
    broker.get_minute_candles_for_exchange("338220", 5, "NXT")
    broker.get_minute_candles_for_exchange("338220", 5, "SOR")

    assert seen[0][0] == "338220_NX"
    assert seen[1][0] == "338220_AL"


def test_nxt_market_order_override_restores_configured_exchange():
    broker = KiwoomRestBroker("key", "secret", real=True, order_exchange="KRX")
    seen = []

    def fake_place(side, code, qty, order_type="market", price=0, cond_price=0):
        seen.append((side, code, qty, broker.order_exchange))
        return {"ord_no": "TEST"}

    broker.place_order = fake_place
    broker.buy_market_on("338220", 10, "NXT")

    assert seen == [("BUY", "338220", 10, "NXT")]
    assert broker.order_exchange == "KRX"


def test_account_sync_queries_both_krx_and_nxt_and_deduplicates():
    broker = KiwoomRestBroker("key", "secret", real=True)
    seen = []

    def fake_post_page(path, api_id, body, cont_yn="", next_key=""):
        seen.append(body["dmst_stex_tp"])
        qty = "10" if body["dmst_stex_tp"] == "KRX" else "12"
        return {
            "acnt_evlt_remn_indv_tot": [
                {"stk_cd": "338220", "stk_nm": "뷰노", "rmnd_qty": qty, "pur_pric": "6000", "cur_prc": "6500"}
            ]
        }, "N", ""

    broker._post_page = fake_post_page
    rows = broker.get_account_positions()

    assert seen == ["KRX", "NXT"]
    assert len(rows) == 1
    assert rows[0]["rmnd_qty"] == "12"
    assert rows[0]["_puma_exchange"] == "NXT"


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
