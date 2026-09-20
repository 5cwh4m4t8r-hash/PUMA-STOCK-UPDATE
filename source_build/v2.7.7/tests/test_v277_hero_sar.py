from puma_trader.signals import _sar


def test_hero_style_sar_state_machine_with_user_params():
    candles=[
        {"high":101.0,"low":99.0,"close":100.0},
        {"high":103.0,"low":100.0,"close":102.0},
        {"high":105.0,"low":101.0,"close":104.0},
        {"high":106.0,"low":102.0,"close":105.0},
        {"high":104.0,"low":98.0,"close":99.0},
        {"high":100.0,"low":96.0,"close":97.0},
    ]
    out=_sar(candles,0.066,0.016)
    expected=[100.0,100.0,100.198,100.274832,106.0,105.472]
    assert len(out)==len(expected)
    for got,want in zip(out,expected):
        assert abs(float(got)-want) < 1e-6
