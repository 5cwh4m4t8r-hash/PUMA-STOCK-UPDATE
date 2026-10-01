from pathlib import Path

from puma_trader.broker import KiwoomRestBroker


def test_account_overview_combines_account_cash_and_balance():
    broker = KiwoomRestBroker("app", "secret", real=True)

    def fake_post(path, api_id, body):
        assert path == "/api/dostk/acnt"
        if api_id == "ka00001":
            return {"acctNo": "1234567890", "return_code": 0}
        if api_id == "kt00001":
            assert body["qry_tp"] == "2"
            return {
                "entr": "1500000",
                "ord_alow_amt": "1400000",
                "pymn_alow_amt": "1300000",
                "d2_entra": "1450000",
                "ch_uncla": "0",
                "return_code": 0,
            }
        if api_id == "kt00018":
            return {
                "tot_pur_amt": "1000000",
                "tot_evlt_amt": "1100000",
                "tot_evlt_pl": "100000",
                "tot_prft_rt": "10.00",
                "prsm_dpst_aset_amt": "2600000",
                "acnt_evlt_remn_indv_tot": [
                    {
                        "stk_cd": "A005930",
                        "stk_nm": "삼성전자",
                        "rmnd_qty": "10",
                        "cur_prc": "110000",
                        "evltv_prft": "100000",
                        "prft_rt": "10.00",
                    }
                ],
                "return_code": 0,
            }
        raise AssertionError(api_id)

    broker._post = fake_post
    out = broker.get_account_overview()

    assert out["account_no"] == "1234567890"
    assert out["deposit"] == 1_500_000
    assert out["order_available"] == 1_400_000
    assert out["withdrawable"] == 1_300_000
    assert out["holding_count"] == 1
    assert out["total_evaluation"] == 1_100_000
    assert out["total_profit_loss"] == 100_000
    assert out["total_profit_rate"] == 10.0
    assert out["holdings"][0]["name"] == "삼성전자"


def test_header_places_compact_account_summary_beside_version_and_refreshes_async():
    src = Path("puma_trader/ui.py").read_text(encoding="utf-8")
    assert 'QLabel(f"🐆  PUMA STOCK PRO  v{CURRENT_VERSION}")' in src
    assert 'self.header_account_summary = QLabel(' in src
    assert "계좌 미연결 · 예수금 -" in src
    assert "AccountSummaryThread" in src
    assert "self.account_summary_timer.setInterval(15_000)" in src
    assert "예수금" in src
    assert "주문가능" in src
    assert "보유" in src
    assert "평가" in src
    assert "손익" in src
