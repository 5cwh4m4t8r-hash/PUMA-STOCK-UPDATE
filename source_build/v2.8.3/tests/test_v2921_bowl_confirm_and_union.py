from puma_trader.bowl import is_bowl3_confirmed_state
from puma_trader.classification import classify_scores


def test_bowl3_requires_breakout_and_pullback_support():
    assert is_bowl3_confirmed_state(250, True, True, False) is True
    assert is_bowl3_confirmed_state(250, False, True, False) is False
    assert is_bowl3_confirmed_state(250, True, False, False) is False
    assert is_bowl3_confirmed_state(-1, True, True, False) is False
    assert is_bowl3_confirmed_state(250, True, True, True) is False


def test_unconfirmed_long_term_observation_is_not_named_bowl3():
    label, detail = classify_scores(0, 20, 49)
    assert "밥3" not in label
    assert "중장기관찰" in label
    assert "밥3 49" in detail
