import pickle

from env import HangzhouMahjongEnv


def test_action_masks_bound_method_pickles_with_unpicklable_runtime_bot():
    env = HangzhouMahjongEnv()

    class _UnpicklableBot:
        def __init__(self):
            self.bad = lambda x: x

    env._bots = {1: _UnpicklableBot()}  # noqa: SLF001
    data = pickle.dumps(getattr(env, "action_masks"))
    assert isinstance(data, (bytes, bytearray))
