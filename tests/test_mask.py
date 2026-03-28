import numpy as np

from env import HangzhouMahjongEnv


def test_mask_shape_and_myturn_pass_rule():
    env = HangzhouMahjongEnv()
    _, info = env.reset(seed=11)
    mask = np.asarray(info["action_mask"], dtype=bool)
    assert mask.shape == (47,)
    if env.engine.phase == "myturn" and env.engine.actor == env.hero_seat:
        assert bool(mask[42]) is False
    assert mask.any()


def test_reaction_pass_always_true_when_hero_awaiting():
    env = HangzhouMahjongEnv()
    env.reset(seed=12)
    env.engine.phase = "reaction"
    env.engine.last_discarder = 3
    env.engine.last_discard = 5
    env._awaiting_hero_reaction = True  # noqa: SLF001
    env._hero_reaction_claims = {  # noqa: SLF001
        "hu": [],
        "ming_kong": [],
        "pon": [],
        "chi_l": [],
        "chi_m": [],
        "chi_r": [],
    }
    mask = env.action_masks()
    assert bool(mask[42]) is True
    assert mask.any()


def test_myturn_all_false_fallback_enables_safe_action():
    env = HangzhouMahjongEnv()
    env.reset(seed=13)
    env.engine.phase = "myturn"
    env.engine.actor = env.hero_seat
    env.engine.hands[env.hero_seat][:] = 0
    mask = env.action_masks()
    assert mask.any()
    assert bool(mask[0]) is True
    assert bool(mask[42]) is False


def test_qiaoxiang_reaction_mask_blocks_chi_pon_kong():
    env = HangzhouMahjongEnv(enable_qiaoxiang=True)
    env.reset(seed=21)
    hero = env.hero_seat

    env.engine._activate_qiaoxiang(hero, "test_hook")  # noqa: SLF001
    env.engine.phase = "reaction"
    env.engine.last_discarder = (hero - 1) % 4
    env.engine.last_discard = 5
    env.engine.hands[hero][:] = 0
    env.engine.hands[hero][5] = 3
    env.engine.hands[hero][4] = 1
    env.engine.hands[hero][6] = 1

    env._awaiting_hero_reaction = True  # noqa: SLF001
    env._hero_reaction_claims = env.engine.legal_reaction_candidates(hero)  # noqa: SLF001
    mask = env.action_masks()

    assert bool(mask[42]) is True
    for blocked in (34, 35, 36, 37, 38):
        assert bool(mask[blocked]) is False
