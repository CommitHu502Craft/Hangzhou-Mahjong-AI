import pytest

from bots import MinLegalBot, RandomBot, RuleBot
from env import HangzhouMahjongEnv


def test_opponent_mix_defensive_only():
    env = HangzhouMahjongEnv(opponent_mix="defensive:1.0")
    env.reset(seed=99)
    assert len(env._bots) == 3  # noqa: SLF001
    for bot in env._bots.values():  # noqa: SLF001
        assert isinstance(bot, RuleBot)
        assert bot.style == "defensive"


def test_opponent_mix_random_and_minlegal_only():
    env = HangzhouMahjongEnv(opponent_mix="random:1.0,minlegal:1.0")
    env.reset(seed=100)
    assert len(env._bots) == 3  # noqa: SLF001
    for bot in env._bots.values():  # noqa: SLF001
        assert isinstance(bot, (RandomBot, MinLegalBot))


def test_opponent_mix_rejects_unknown_entry():
    with pytest.raises(ValueError):
        HangzhouMahjongEnv(opponent_mix="unknown:1.0")

