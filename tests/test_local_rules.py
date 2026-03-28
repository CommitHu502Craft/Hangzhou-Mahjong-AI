import numpy as np

from engine import MahjongEngine, ReactionClaim
from env import HangzhouMahjongEnv


def _blank_hand() -> np.ndarray:
    return np.zeros(34, dtype=np.int8)


def test_wealth_god_wildcard_can_complete_hu():
    eng = MahjongEngine(enable_wealth_god=True)
    eng.hands = [_blank_hand() for _ in range(4)]
    eng.wealth_god = 33

    # 123m, 123p, 123s, 34m + [wealth-god], pair 66m.
    hand = _blank_hand()
    hand[0] = 1
    hand[1] = 1
    hand[2] = 1
    hand[9] = 1
    hand[10] = 1
    hand[11] = 1
    hand[18] = 1
    hand[19] = 1
    hand[20] = 1
    hand[3] = 1
    hand[4] = 1
    hand[5] = 2
    hand[33] = 1
    eng.hands[0] = hand

    assert eng._can_self_hu(0) is True  # noqa: SLF001


def test_same_hand_not_hu_when_wealth_god_disabled():
    eng = MahjongEngine(enable_wealth_god=False)
    eng.hands = [_blank_hand() for _ in range(4)]
    eng.wealth_god = -1

    hand = _blank_hand()
    hand[0] = 1
    hand[1] = 1
    hand[2] = 1
    hand[9] = 1
    hand[10] = 1
    hand[11] = 1
    hand[18] = 1
    hand[19] = 1
    hand[20] = 1
    hand[3] = 1
    hand[4] = 1
    hand[5] = 2
    hand[33] = 1
    eng.hands[0] = hand

    assert eng._can_self_hu(0) is False  # noqa: SLF001


def test_legal_discards_protect_wealth_god_when_possible():
    eng = MahjongEngine(enable_wealth_god=True, protect_wealth_god_discard=True)
    eng.hands = [_blank_hand() for _ in range(4)]
    eng.wealth_god = 5
    eng.hands[0][5] = 1
    eng.hands[0][7] = 1

    assert eng.legal_discards(0) == [7]

    eng.hands[0][7] = 0
    assert eng.legal_discards(0) == [5]


def test_env_can_disable_wealth_god_observation_channel():
    env = HangzhouMahjongEnv(enable_wealth_god=False)
    obs, _ = env.reset(seed=123)
    assert float(obs[4].sum()) == 0.0


def test_qiaoxiang_activates_on_kong_and_restricts_reaction_actions():
    eng = MahjongEngine(enable_qiaoxiang=True, enable_wealth_god=False)
    eng.reset(seed=7)
    eng.hands = [_blank_hand() for _ in range(4)]
    eng.wall = [1, 2, 3, 4]
    eng.phase = "myturn"
    eng.actor = 0
    eng.hands[0][3] = 4

    eng.apply_an_kong(0, 3)
    assert eng.is_qiaoxiang_active(0) is True

    eng.phase = "reaction"
    eng.last_discarder = 3
    eng.last_discard = 5
    eng.hands[0][5] = 3
    eng.hands[0][4] = 1
    eng.hands[0][6] = 1

    claims = eng.legal_reaction_candidates(0)
    assert claims["ming_kong"] == []
    assert claims["pon"] == []
    assert claims["chi_l"] == []
    assert claims["chi_m"] == []
    assert claims["chi_r"] == []


def test_qiaoxiang_adds_local_fan_and_score():
    base = _blank_hand()
    base[0] = 3
    base[1] = 3
    base[2] = 3
    base[3] = 1
    base[4] = 1
    base[5] = 1
    base[6] = 2

    plain = MahjongEngine(enable_qiaoxiang=False, enable_wealth_god=False)
    plain.hands = [_blank_hand() for _ in range(4)]
    plain.hands[0] = base.copy()
    plain.phase = "myturn"
    plain.actor = 0
    plain.apply_self_hu(0)

    qx = MahjongEngine(enable_qiaoxiang=True, enable_wealth_god=False)
    qx.hands = [_blank_hand() for _ in range(4)]
    qx.hands[0] = base.copy()
    qx.phase = "myturn"
    qx.actor = 0
    qx._activate_qiaoxiang(0, "test_hook")  # noqa: SLF001
    qx.apply_self_hu(0)

    assert plain.win_details is not None
    assert qx.win_details is not None
    assert qx.win_details["fan_total"] == plain.win_details["fan_total"] + 1
    assert "qiaoxiang" in qx.win_details["fan_types"]
    assert qx.scores[0] > plain.scores[0]


def test_qingyise_fan_detected_in_win_details():
    eng = MahjongEngine(enable_wealth_god=False)
    eng.hands = [_blank_hand() for _ in range(4)]

    hand = _blank_hand()
    hand[0] = 3
    hand[1] = 3
    hand[2] = 3
    hand[3] = 3
    hand[4] = 2
    eng.hands[0] = hand
    eng.phase = "myturn"
    eng.actor = 0
    eng.apply_self_hu(0)

    assert eng.win_details is not None
    assert "qingyise" in eng.win_details["fan_types"]


def test_chi_can_use_wealth_god_substitution_when_enabled():
    eng = MahjongEngine(enable_wealth_god=True, wealth_god_can_meld=True)
    eng.hands = [_blank_hand() for _ in range(4)]
    eng.wealth_god = 33
    eng.phase = "reaction"
    eng.last_discarder = 3
    eng.last_discard = 10  # tong 2

    # Need chi_m sequence (9,10,11): hand has only 11 + wealth-god.
    eng.hands[0][11] = 1
    eng.hands[0][33] = 1
    claims = eng.legal_reaction_candidates(0)
    assert (9, 10, 11) in claims["chi_m"]

    eng.apply_reaction(ReactionClaim(seat=0, action="chi_m", candidate=(9, 10, 11)))
    assert int(eng.hands[0][11]) == 0
    assert int(eng.hands[0][33]) == 0
    assert int(eng.melds[0][9]) == 1
    assert int(eng.melds[0][10]) == 1
    assert int(eng.melds[0][11]) == 1


def test_chi_wealth_god_substitution_blocked_when_meld_disabled():
    eng = MahjongEngine(enable_wealth_god=True, wealth_god_can_meld=False)
    eng.hands = [_blank_hand() for _ in range(4)]
    eng.wealth_god = 33
    eng.phase = "reaction"
    eng.last_discarder = 3
    eng.last_discard = 10

    eng.hands[0][11] = 1
    eng.hands[0][33] = 1
    claims = eng.legal_reaction_candidates(0)
    assert claims["chi_m"] == []
