import pytest

from rl.run_single_variable_matrix import (
    ExperimentSpec,
    default_matrix_experiments,
    validate_matrix_experiments,
)


def test_default_matrix_experiments_valid():
    exps = default_matrix_experiments()
    validate_matrix_experiments(exps)
    assert exps[0].id == "baseline"


def test_validate_requires_baseline():
    exps = [
        ExperimentSpec(
            id="reward_only",
            variable="reward_strategy",
            description="x",
            ppo_changes={"reward_mode": "raw", "use_vec_normalize_reward": True},
        )
    ]
    with pytest.raises(ValueError):
        validate_matrix_experiments(exps)


def test_validate_non_baseline_requires_changes():
    exps = [
        ExperimentSpec(id="baseline", variable="baseline", description="x", ppo_changes={}),
        ExperimentSpec(id="noop", variable="noop", description="x", ppo_changes={}),
    ]
    with pytest.raises(ValueError):
        validate_matrix_experiments(exps)
