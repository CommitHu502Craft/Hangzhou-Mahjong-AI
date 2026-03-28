import json
from pathlib import Path

import numpy as np
import pytest

from datasets import gen_data


class _FakeEngine:
    def __init__(self) -> None:
        self.terminated = False


class _FakeEnv:
    def __init__(self, bot_epsilon: float = 0.08, **kwargs) -> None:
        self.engine = _FakeEngine()
        self._mask = np.zeros(47, dtype=bool)
        self._mask[0] = True
        self._obs = np.zeros((40, 4, 9), dtype=np.float32)

    def reset(self, seed: int | None = None):
        self.engine.terminated = False
        return self._obs.copy(), {"action_mask": self._mask.copy()}

    def step(self, action: int):
        self.engine.terminated = True
        return self._obs.copy(), 1.0, True, False, {"action_mask": self._mask.copy()}


class _FakeRuleBot:
    def __init__(self, epsilon: float = 0.08, seed: int = 0) -> None:
        self.epsilon = epsilon
        self.seed = seed

    def select_action(self, obs: np.ndarray, mask: np.ndarray, env=None) -> int:
        return int(np.flatnonzero(mask)[0])


def _load_meta(npz_path: Path) -> dict:
    arr = np.load(npz_path, allow_pickle=True)
    try:
        return json.loads(str(arr["meta"][0]))
    finally:
        arr.close()


def test_generate_data_target_decisions_stops_early(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(gen_data, "HangzhouMahjongEnv", _FakeEnv)
    monkeypatch.setattr(gen_data, "RuleBot", _FakeRuleBot)

    out = tmp_path / "data_target.npz"
    gen_data.generate_data(
        episodes=50,
        out_path=out,
        seed_start=10,
        epsilon=0.1,
        target_decisions=3,
        min_samples=1,
        max_episodes=50,
        bootstrap_if_empty=False,
        enable_wealth_god=True,
        protect_wealth_god_discard=True,
        enable_qiaoxiang=False,
        gate_min_myturn_ratio=0.0,
        gate_min_reaction_ratio=0.0,
        gate_max_action_share=1.0,
        gate_min_avg_legal_actions=1.0,
        gate_max_truncated_rate=1.0,
        enforce_distribution_gates=False,
    )

    meta = _load_meta(out)
    assert meta["actual_samples"] == 3
    assert meta["episodes_used"] == 3
    assert meta["stop_reason"] == "target_decisions_reached"
    assert meta["phase_counts"]["reaction"] == 3
    assert meta["phase_counts"]["myturn"] == 0
    assert meta["action_hist"]["0"] == 3
    assert "distribution_gates" in meta
    assert meta["distribution_gates"]["status"] == "PASS"


def test_generate_data_raises_when_min_samples_not_met(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(gen_data, "HangzhouMahjongEnv", _FakeEnv)
    monkeypatch.setattr(gen_data, "RuleBot", _FakeRuleBot)

    with pytest.raises(RuntimeError):
        gen_data.generate_data(
            episodes=1,
            out_path=tmp_path / "too_few.npz",
            seed_start=22,
            epsilon=0.1,
            target_decisions=0,
            min_samples=5,
            max_episodes=1,
            bootstrap_if_empty=False,
            enable_wealth_god=True,
            protect_wealth_god_discard=True,
            enable_qiaoxiang=False,
            gate_min_myturn_ratio=0.0,
            gate_min_reaction_ratio=0.0,
            gate_max_action_share=1.0,
            gate_min_avg_legal_actions=1.0,
            gate_max_truncated_rate=1.0,
            enforce_distribution_gates=False,
        )


def test_generate_data_distribution_gate_can_fail_when_enforced(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(gen_data, "HangzhouMahjongEnv", _FakeEnv)
    monkeypatch.setattr(gen_data, "RuleBot", _FakeRuleBot)

    with pytest.raises(RuntimeError):
        gen_data.generate_data(
            episodes=3,
            out_path=tmp_path / "gate_fail.npz",
            seed_start=33,
            epsilon=0.1,
            target_decisions=3,
            min_samples=1,
            max_episodes=3,
            bootstrap_if_empty=False,
            enable_wealth_god=True,
            protect_wealth_god_discard=True,
            enable_qiaoxiang=False,
            gate_min_myturn_ratio=0.5,
            gate_min_reaction_ratio=0.0,
            gate_max_action_share=1.0,
            gate_min_avg_legal_actions=1.0,
            gate_max_truncated_rate=1.0,
            enforce_distribution_gates=True,
        )
