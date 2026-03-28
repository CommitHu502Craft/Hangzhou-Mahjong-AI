import numpy as np

from env import HangzhouMahjongEnv


def test_an_kong_multi_candidates_use_stable_slots():
    env = HangzhouMahjongEnv(enable_wealth_god=False)
    env.reset(seed=2026)
    hero = env.hero_seat

    env.engine.phase = "myturn"
    env.engine.actor = hero
    env.engine.hands[hero][:] = 0
    env.engine.hands[hero][1] = 4
    env.engine.hands[hero][7] = 4
    env.engine.hands[hero][11] = 1

    mask1 = np.asarray(env.action_masks(), dtype=bool)
    ctx1 = dict(env._action_context)  # noqa: SLF001
    assert bool(mask1[40]) is True
    assert bool(mask1[43]) is True
    assert ctx1[40] == ("an_kong", 1)
    assert ctx1[43] == ("an_kong", 7)

    mask2 = np.asarray(env.action_masks(), dtype=bool)
    ctx2 = dict(env._action_context)  # noqa: SLF001
    assert bool(mask2[40]) is True
    assert bool(mask2[43]) is True
    assert ctx2[40] == ("an_kong", 1)
    assert ctx2[43] == ("an_kong", 7)


def test_reaction_chi_with_wealth_god_substitution_is_exposed_in_mask():
    env = HangzhouMahjongEnv(enable_wealth_god=True, wealth_god_can_meld=True)
    env.reset(seed=17)
    hero = env.hero_seat

    env.engine.wealth_god = 33
    env.engine.phase = "reaction"
    env.engine.last_discarder = (hero - 1) % 4
    env.engine.last_discard = 10
    env.engine.hands[hero][:] = 0
    env.engine.hands[hero][11] = 1
    env.engine.hands[hero][33] = 1

    env._awaiting_hero_reaction = True  # noqa: SLF001
    env._hero_reaction_claims = env.engine.legal_reaction_candidates(hero)  # noqa: SLF001
    env._pending_bot_claims = []  # noqa: SLF001

    mask = np.asarray(env.action_masks(), dtype=bool)
    assert bool(mask[35]) is True  # chi_m

