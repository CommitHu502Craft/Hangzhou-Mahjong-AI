from __future__ import annotations

import numpy as np

from bots import RuleBot
from engine import MahjongEngine, ReactionClaim
from env import HangzhouMahjongEnv


def test_no_all_false_mask_under_random_rollout():
    env = HangzhouMahjongEnv(max_internal_steps=10_000, bot_epsilon=0.08)
    rng = np.random.default_rng(20260222)

    for game_idx in range(80):
        obs, info = env.reset(seed=80_000 + game_idx)
        terminated = env.engine.terminated
        truncated = False
        steps = 0

        while not (terminated or truncated):
            mask = np.asarray(info["action_mask"], dtype=bool)
            assert mask.shape == (47,)
            assert mask.any()
            legal = np.flatnonzero(mask)
            action = int(rng.choice(legal))
            obs, _, terminated, truncated, info = env.step(action)
            steps += 1
            assert steps <= 1200


def test_no_priority_deadlock_on_multi_reaction():
    eng = MahjongEngine(enable_wealth_god=False)
    eng.reset(seed=90210)
    eng.phase = "reaction"
    eng.last_discarder = 0
    eng.last_discard = 11
    eng.actor = 1
    for seat in range(4):
        eng.hands[seat][:] = 0
    eng.hands[1][11] = 2
    eng.hands[1][10] = 1
    eng.hands[1][12] = 1
    eng.hands[2][11] = 2

    claims = [
        ReactionClaim(seat=1, action="pon", candidate=11),
        ReactionClaim(seat=1, action="chi_m", candidate=(10, 11, 12)),
        ReactionClaim(seat=2, action="pon", candidate=11),
    ]
    winner = eng.resolve_reaction_priority(claims, discarder=0)
    assert winner is not None
    assert winner.action == "pon"
    assert winner.seat == 1

    eng.apply_reaction(winner)
    assert eng.phase == "myturn"
    assert eng.actor == 1
    assert eng.last_discard is None
    assert eng.last_discarder is None


def test_truncation_rate_under_rulebot_selfplay_below_threshold():
    env = HangzhouMahjongEnv(max_internal_steps=10_000, bot_epsilon=0.08)
    hero_bot = RuleBot(epsilon=0.08, seed=1234, style="balanced")

    episodes = 200
    truncated_count = 0
    for game_idx in range(episodes):
        obs, info = env.reset(seed=100_000 + game_idx)
        terminated = env.engine.terminated
        truncated = False
        steps = 0

        while not (terminated or truncated):
            mask = np.asarray(info["action_mask"], dtype=bool)
            legal = np.flatnonzero(mask)
            assert legal.size > 0
            action = int(hero_bot.select_action(obs, mask, env=env))
            if action < 0 or action >= 47 or not mask[action]:
                action = int(legal[0])
            obs, _, terminated, truncated, info = env.step(action)
            steps += 1
            assert steps <= 1500

        if truncated:
            truncated_count += 1

    truncation_rate = truncated_count / episodes
    assert truncation_rate <= 0.02
