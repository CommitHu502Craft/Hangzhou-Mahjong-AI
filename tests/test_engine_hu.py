import numpy as np

from engine import MahjongEngine


def _blank_hand() -> np.ndarray:
    return np.zeros(34, dtype=np.int8)


def test_self_hu_requires_real_structure():
    eng = MahjongEngine(enable_wealth_god=False)
    eng.hands = [_blank_hand() for _ in range(4)]

    # Winning hand: 123/123/123/345 + 66.
    hand = _blank_hand()
    hand[0] = 3
    hand[1] = 3
    hand[2] = 3
    hand[3] = 1
    hand[4] = 1
    hand[5] = 1
    hand[6] = 2
    eng.hands[0] = hand

    assert eng._can_self_hu(0) is True  # noqa: SLF001


def test_self_hu_rejects_old_false_positive_shape():
    eng = MahjongEngine(enable_wealth_god=False)
    eng.hands = [_blank_hand() for _ in range(4)]

    # Non-winning hand with pair + scattered tiles:
    # 111/222/333 + 4,6,8 + EE.
    hand = _blank_hand()
    hand[0] = 3
    hand[1] = 3
    hand[2] = 3
    hand[3] = 1
    hand[5] = 1
    hand[7] = 1
    hand[27] = 2
    eng.hands[0] = hand

    assert eng._can_self_hu(0) is False  # noqa: SLF001


def test_reaction_hu_uses_discarded_tile_even_if_not_in_hand():
    eng = MahjongEngine(enable_wealth_god=False)
    eng.hands = [_blank_hand() for _ in range(4)]

    # Seat 1 waits on tile 5 to complete 345:
    # 123/123/123 + 34 + 66. Discard 5 should enable hu.
    hand = _blank_hand()
    hand[0] = 3
    hand[1] = 3
    hand[2] = 3
    hand[3] = 1
    hand[4] = 1
    hand[6] = 2
    eng.hands[1] = hand
    eng.last_discard = 5
    eng.last_discarder = 0

    claims = eng.legal_reaction_candidates(1)
    assert claims["hu"] == [5]


def test_self_hu_supports_seven_pairs_without_wildcard():
    eng = MahjongEngine(enable_wealth_god=False)
    eng.hands = [_blank_hand() for _ in range(4)]

    # 11223344556677
    hand = _blank_hand()
    for tile in range(7):
        hand[tile] = 2
    eng.hands[0] = hand

    assert eng._can_self_hu(0) is True  # noqa: SLF001


def test_self_hu_supports_seven_pairs_with_wildcard():
    eng = MahjongEngine(enable_wealth_god=True)
    eng.hands = [_blank_hand() for _ in range(4)]
    eng.wealth_god = 33

    # 1122334455667 + 财神(33), wildcard completes the last pair.
    hand = _blank_hand()
    for tile in range(6):
        hand[tile] = 2
    hand[6] = 1
    hand[33] = 1
    eng.hands[0] = hand

    assert eng._can_self_hu(0) is True  # noqa: SLF001


def test_self_hu_supports_thirteen_orphans():
    eng = MahjongEngine(enable_wealth_god=False)
    eng.hands = [_blank_hand() for _ in range(4)]

    hand = _blank_hand()
    orphans = [0, 8, 9, 17, 18, 26, 27, 28, 29, 30, 31, 32, 33]
    for tile in orphans:
        hand[tile] += 1
    hand[0] += 1
    eng.hands[0] = hand

    assert eng._can_self_hu(0) is True  # noqa: SLF001


def test_win_details_include_qidui_fan_type():
    eng = MahjongEngine(enable_wealth_god=False)
    eng.hands = [_blank_hand() for _ in range(4)]

    hand = _blank_hand()
    for tile in range(7):
        hand[tile] = 2
    eng.hands[0] = hand
    eng.phase = "myturn"
    eng.actor = 0
    eng.apply_self_hu(0)

    assert eng.win_details is not None
    assert "qidui" in eng.win_details["fan_types"]


def test_qidui_can_be_disabled_by_special_hu_types():
    eng = MahjongEngine(enable_wealth_god=False, special_hu_types=[])
    eng.hands = [_blank_hand() for _ in range(4)]

    hand = _blank_hand()
    # Seven pairs on honors only: cannot be reduced to standard meld+pair hand.
    for tile in [27, 28, 29, 30, 31, 32, 33]:
        hand[tile] = 2
    eng.hands[0] = hand

    assert eng._can_self_hu(0) is False  # noqa: SLF001


def test_shisanyao_can_be_disabled_by_special_hu_types():
    eng = MahjongEngine(enable_wealth_god=False, special_hu_types=["qidui"])
    eng.hands = [_blank_hand() for _ in range(4)]

    hand = _blank_hand()
    orphans = [0, 8, 9, 17, 18, 26, 27, 28, 29, 30, 31, 32, 33]
    for tile in orphans:
        hand[tile] += 1
    hand[0] += 1
    eng.hands[0] = hand

    assert eng._can_self_hu(0) is False  # noqa: SLF001
