from puma_trader.strategy import sma, rsi


def test_sma():
    assert sma([1,2,3,4,5], 3) == 4


def test_rsi_runs():
    v = list(range(1, 30))
    assert 99 <= rsi(v) <= 100
