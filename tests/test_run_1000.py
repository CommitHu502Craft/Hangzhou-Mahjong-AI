import numpy as np

from env import HangzhouMahjongEnv


def test_run_1000_games_no_crash():
    env = HangzhouMahjongEnv(max_internal_steps=10_000)
    for game_id in range(1000):
        _, info = env.reset(seed=3000 + game_id)
        terminated = env.engine.terminated
        truncated = False
        steps = 0

        while not (terminated or truncated):
            mask = np.asarray(info["action_mask"], dtype=bool)
            assert mask.shape == (47,)
            assert mask.any()
            action = int(np.flatnonzero(mask)[0])
            _, _, terminated, truncated, info = env.step(action)
            steps += 1
            assert steps <= 1000

        if truncated:
            assert "phase" in info
            assert "actor" in info
        assert terminated or truncated
