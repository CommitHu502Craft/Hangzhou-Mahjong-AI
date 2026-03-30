import json
from pathlib import Path

import pytest

from rl.eval_duplicate import REPORT_SCHEMA_VERSION, PolicyRunner, build_policy_runner, evaluate, resolve_seed_list


def test_policy_runner_fallback_when_model_missing():
    runner = PolicyRunner("models/definitely_missing_model_for_test")
    assert runner.backend == "fallback"
    assert runner.load_status.startswith("fallback")


def test_policy_runner_strict_load_raises_on_missing_model():
    with pytest.raises(RuntimeError):
        PolicyRunner("models/definitely_missing_model_for_test", strict_load=True)


def test_evaluate_fail_on_fallback_raises(tmp_path: Path):
    out = tmp_path / "dup_report.json"
    with pytest.raises(RuntimeError):
        evaluate(
            model="models/definitely_missing_model_for_test",
            seeds=[1001],
            seats=[0],
            out=out,
            strict_load=False,
            fail_on_fallback=True,
            policy_mode="model",
            seed=2026,
            rulebot_epsilon=0.0,
            enable_wealth_god=True,
            protect_wealth_god_discard=True,
            enable_qiaoxiang=False,
        )


def test_build_policy_runner_supports_rule_and_random_modes():
    rule_runner = build_policy_runner(
        policy_mode="rule",
        model="models/unused",
        strict_load=False,
        fail_on_fallback=False,
        seed=99,
        rulebot_epsilon=0.0,
    )
    random_runner = build_policy_runner(
        policy_mode="random",
        model="models/unused",
        strict_load=False,
        fail_on_fallback=False,
        seed=99,
        rulebot_epsilon=0.0,
    )
    assert rule_runner.backend == "rulebot"
    assert random_runner.backend == "randombot"


def test_resolve_seed_list_from_range():
    seeds = resolve_seed_list(None, 1001, 1003)
    assert seeds == [1001, 1002, 1003]


def test_resolve_seed_list_rejects_mixed_inputs():
    with pytest.raises(ValueError):
        resolve_seed_list([1, 2], 1, 2)


def test_resolve_seed_list_from_seed_set_dev():
    seeds = resolve_seed_list(None, None, None, "dev")
    assert seeds[0] == 1001
    assert seeds[-1] == 1500
    assert len(seeds) == 500


def test_resolve_seed_list_rejects_seed_set_mixed_with_explicit():
    with pytest.raises(ValueError):
        resolve_seed_list([1001], None, None, "dev")


def test_evaluate_report_includes_opponent_epsilon(tmp_path: Path):
    out = tmp_path / "dup_report.json"
    evaluate(
        model="models/unused",
        seeds=[1001],
        seats=[0],
        out=out,
        strict_load=False,
        fail_on_fallback=False,
        policy_mode="minlegal",
        seed=2026,
        rulebot_epsilon=0.0,
        enable_wealth_god=True,
        protect_wealth_god_discard=True,
        enable_qiaoxiang=False,
        opponent_epsilon=0.23,
    )
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["report_schema_version"] == REPORT_SCHEMA_VERSION
    assert report["opponent_epsilon"] == pytest.approx(0.23)
    assert report["opponent_mix"] == "rule:1.0"
    assert report["seed_set_id"] != ""
    assert report["spec_version"] != ""
    assert report["opponent_suite_id"] != ""
    assert report["rule_profile_id"] != ""
