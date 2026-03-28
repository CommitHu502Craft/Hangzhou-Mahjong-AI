from rl.seed_splits import classify_seed_set, resolve_seed_set


def test_resolve_seed_set_test_range():
    seeds = resolve_seed_set("test")
    assert seeds[0] == 1501
    assert seeds[-1] == 2000
    assert len(seeds) == 500


def test_classify_seed_set_custom_is_none():
    assert classify_seed_set([1001, 1002, 1003]) is None
