import numpy as np

from engine import MahjongEngine
from env import HangzhouMahjongEnv


def test_engine_reset_same_seed_identical():
    e1 = MahjongEngine()
    e2 = MahjongEngine()
    assert e1.reset(seed=77) == e2.reset(seed=77)


def test_env_replay_same_seed_same_outcome_for_fixed_actions():
    env1 = HangzhouMahjongEnv()
    env2 = HangzhouMahjongEnv()

    obs1, info1 = env1.reset(seed=88)
    obs2, info2 = env2.reset(seed=88)
    assert np.array_equal(obs1, obs2)
    assert np.array_equal(info1["action_mask"], info2["action_mask"])

    for _ in range(8):
        m1 = np.asarray(info1["action_mask"], dtype=bool)
        m2 = np.asarray(info2["action_mask"], dtype=bool)
        a1 = int(np.flatnonzero(m1)[0])
        a2 = int(np.flatnonzero(m2)[0])
        assert a1 == a2

        obs1, r1, t1, tr1, info1 = env1.step(a1)
        obs2, r2, t2, tr2, info2 = env2.step(a2)

        assert float(r1) == float(r2)
        assert t1 == t2
        assert tr1 == tr2
        assert np.array_equal(obs1, obs2)
        if t1 or tr1:
            break
