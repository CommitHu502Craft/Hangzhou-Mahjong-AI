import argparse
import json
from pathlib import Path

import pytest

from rl.train_ppo import _collect_pool_paths, _fallback_train, _validate_reward_normalization_args, _write_json_atomic


def test_collect_pool_paths_only_zip_files(tmp_path: Path):
    (tmp_path / "a.zip").write_text("x", encoding="utf-8")
    (tmp_path / "b.json").write_text("x", encoding="utf-8")
    (tmp_path / "c").write_text("x", encoding="utf-8")
    (tmp_path / "nested").mkdir()

    got = _collect_pool_paths(tmp_path)
    assert got == [str(tmp_path / "a.zip")]


def test_fallback_train_meta_contains_seed_and_vec_backend(tmp_path: Path):
    out = tmp_path / "fallback_unit"
    args = argparse.Namespace(
        reward_mode="log1p",
        use_opponent_pool=False,
        pool_dir=str(tmp_path),
        opponent_replace_count=1,
        timesteps=16,
        num_envs=1,
        out=str(out),
        seed=12345,
        vec_backend="dummy",
        policy="MlpPolicy",
        run_tag="unit-test",
        disable_wealth_god=False,
        allow_discard_wealth_god=False,
        enable_qiaoxiang=False,
        opponent_mix="rule:1.0",
        use_vec_normalize_reward=False,
        monitor_episodes=1,
        enforce_monitor_gates=False,
    )

    _fallback_train(args, RuntimeError("forced fallback for test"))
    meta = json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))
    assert meta["backend"] == "fallback"
    assert meta["seed"] == 12345
    assert meta["vec_backend"] == "dummy"
    assert meta["run_tag"] == "unit-test"
    assert "monitor_gate" in meta


def test_reward_guard_blocks_log1p_plus_vecnormalize():
    args = argparse.Namespace(reward_mode="log1p", use_vec_normalize_reward=True)
    with pytest.raises(ValueError):
        _validate_reward_normalization_args(args)


def test_write_json_atomic_retries_permission_error(tmp_path: Path, monkeypatch):
    out = tmp_path / "hb.json"
    calls = {"n": 0}
    real_replace = Path.replace

    def flaky_replace(self: Path, target: Path):  # type: ignore[override]
        if calls["n"] == 0:
            calls["n"] += 1
            raise PermissionError("locked")
        return real_replace(self, target)

    monkeypatch.setattr(Path, "replace", flaky_replace)
    _write_json_atomic(out, {"status": "ok"})
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == "ok"
    assert calls["n"] == 1
