from puma_trader.bowl import analyze_bowl
from puma_trader.swing import demo_candles


def test_bowl_runs_on_demo():
    a, s = analyze_bowl(demo_candles(620))
    assert len(s['candles']) >= 600
    assert 0 <= a.score <= 100
    assert '224EMA 돌파' in a.details
