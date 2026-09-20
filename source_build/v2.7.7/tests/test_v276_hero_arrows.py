from puma_trader.signals import _ema


def test_hero_style_eavg_starts_from_first_value():
    values=[100.0,110.0,120.0,130.0]
    out=_ema(values,3)
    # alpha=0.5, first value is the first EAVG
    assert out == [100.0,105.0,112.5,121.25]


def test_long_eavg_is_available_before_period_count():
    values=[100.0]*20
    out=_ema(values,448)
    assert len(out)==20
    assert all(v == 100.0 for v in out)
