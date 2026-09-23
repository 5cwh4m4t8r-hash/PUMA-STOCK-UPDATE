from puma_trader.classification import bucket_scores, classify_scores


def test_condition_result_buckets_are_independent():
    out = bucket_scores({"danta": 71, "swing": 62, "bowl": 20})
    assert out == {"danta": 71, "swing": 62}


def test_bowl3_bucket_is_separate():
    out = bucket_scores({"danta": 10, "swing": 30, "bowl": 88})
    assert out == {"bowl": 88}
    label, detail = classify_scores(10, 30, 88)
    assert "중장기(밥3)" in label
    assert "밥3 88" in detail


def test_subthreshold_candidate_is_not_forced_into_any_bucket():
    assert bucket_scores({"danta": 54, "swing": 54, "bowl": 54}) == {}
