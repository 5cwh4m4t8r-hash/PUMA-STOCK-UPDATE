from puma_trader.classification import source_display_buckets


def test_danta_source_never_leaks_to_swing_or_bowl_filters():
    buckets = source_display_buckets(
        {"danta": 10, "swing": 95, "bowl": 92},
        danta_source=True,
        threshold=55,
    )
    assert buckets == {"danta": 10}


def test_non_danta_candidate_can_use_swing_and_bowl_scores():
    buckets = source_display_buckets(
        {"danta": 99, "swing": 70, "bowl": 68},
        danta_source=False,
        threshold=55,
    )
    assert "danta" not in buckets
    assert buckets == {"swing": 70, "bowl": 68}
