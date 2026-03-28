import json
from pathlib import Path

from rl.assess_readiness_levels import assess_levels


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")


def test_levels_reach_l2_without_real_ab(tmp_path: Path):
    model = tmp_path / "model.json"
    rule = tmp_path / "rule.json"
    suite = tmp_path / "suite.json"
    out = tmp_path / "out.json"

    ctx = {
        "rule_profile_id": "hangzhou_local_table_v1@2026-02-22",
        "spec_version": "v1.1",
        "seed_set_id": "test",
        "opponent_suite_id": "mix=rule:1.0|eps=0.080",
    }
    _write(model, {"n_games": 1000, "mean_diff": 10.0, "ci95": 1.0, **ctx})
    _write(rule, {"n_games": 1000, "mean_diff": 1.0, "ci95": 1.0, **ctx})
    _write(suite, {"status": "PASS", "context": ctx})

    profile = Path("rules/profile_hangzhou_mvp.yaml")
    res = assess_levels(
        l1_model_report=model,
        l1_rule_report=rule,
        l2_suite_report=suite,
        rule_profile_path=profile,
        out=out,
        pytest_passed=True,
        min_games=800,
        min_advantage=2.0,
        real_ab_report=None,
        require_real_ab_for_l3=True,
    )

    assert res["levels"]["L1"]["status"] == "PASS"
    assert res["levels"]["L2"]["status"] == "PASS"
    assert res["levels"]["L3"]["status"] == "FAIL"
    assert res["highest_level"] == "L2"


def test_levels_reach_l3_with_real_ab(tmp_path: Path):
    model = tmp_path / "model.json"
    rule = tmp_path / "rule.json"
    suite = tmp_path / "suite.json"
    real_ab = tmp_path / "real_ab.json"
    out = tmp_path / "out.json"

    ctx = {
        "rule_profile_id": "hangzhou_local_table_v1@2026-02-22",
        "spec_version": "v1.1",
        "seed_set_id": "test",
        "opponent_suite_id": "mix=rule:1.0|eps=0.080",
    }
    _write(model, {"n_games": 1000, "mean_diff": 12.0, "ci95": 1.5, **ctx})
    _write(rule, {"n_games": 1000, "mean_diff": 1.0, "ci95": 1.0, **ctx})
    _write(suite, {"status": "PASS", "context": ctx})
    _write(real_ab, {"status": "PASS", "n_games": 260, "mean_diff": 2.1})

    profile = Path("rules/profile_hangzhou_mvp.yaml")
    res = assess_levels(
        l1_model_report=model,
        l1_rule_report=rule,
        l2_suite_report=suite,
        rule_profile_path=profile,
        out=out,
        pytest_passed=True,
        min_games=800,
        min_advantage=2.0,
        real_ab_report=real_ab,
        min_real_ab_games=200,
        min_real_ab_advantage=0.0,
        require_real_ab_for_l3=True,
    )

    assert res["levels"]["L3"]["status"] == "PASS"
    assert res["highest_level"] == "L3"


def test_levels_l3_pass_with_explicit_profile_id_alias(tmp_path: Path):
    model = tmp_path / "model.json"
    rule = tmp_path / "rule.json"
    suite = tmp_path / "suite.json"
    real_ab = tmp_path / "real_ab.json"
    out = tmp_path / "out.json"

    ctx = {
        "rule_profile_id": "hz_local_v2026_02_A",
        "spec_version": "v1.1",
        "seed_set_id": "test",
        "opponent_suite_id": "opp_suite_eps08_rule",
    }
    _write(model, {"n_games": 1200, "mean_diff": 12.0, "ci95": 1.5, **ctx})
    _write(rule, {"n_games": 1200, "mean_diff": 1.0, "ci95": 1.0, **ctx})
    _write(suite, {"status": "PASS", "context": ctx})
    _write(real_ab, {"status": "PASS", "n_games": 260, "mean_diff": 2.1})

    profile = Path("rules/hz_local_v2026_02_A.yaml")
    res = assess_levels(
        l1_model_report=model,
        l1_rule_report=rule,
        l2_suite_report=suite,
        rule_profile_path=profile,
        out=out,
        pytest_passed=True,
        min_games=800,
        min_advantage=2.0,
        real_ab_report=real_ab,
        min_real_ab_games=200,
        min_real_ab_advantage=0.0,
        require_real_ab_for_l3=True,
        expected_rule_profile_id="hz_local_v2026_02_A",
    )

    assert res["levels"]["L3"]["status"] == "PASS"
    assert res["highest_level"] == "L3"


def test_levels_raise_on_l1_l2_context_mismatch(tmp_path: Path):
    model = tmp_path / "model.json"
    rule = tmp_path / "rule.json"
    suite = tmp_path / "suite.json"
    out = tmp_path / "out.json"

    _write(
        model,
        {
            "n_games": 1000,
            "mean_diff": 10.0,
            "ci95": 1.0,
            "rule_profile_id": "hangzhou_local_table_v1@2026-02-22",
            "spec_version": "v1.1",
            "seed_set_id": "test",
            "opponent_suite_id": "mix=rule:1.0|eps=0.080",
        },
    )
    _write(
        rule,
        {
            "n_games": 1000,
            "mean_diff": 1.0,
            "ci95": 1.0,
            "rule_profile_id": "hangzhou_local_table_v1@2026-02-22",
            "spec_version": "v1.1",
            "seed_set_id": "test",
            "opponent_suite_id": "mix=rule:1.0|eps=0.080",
        },
    )
    _write(
        suite,
        {
            "status": "PASS",
            "context": {
                "rule_profile_id": "hangzhou_local_table_v1@2026-02-22",
                "spec_version": "v1.1",
                "seed_set_id": "dev",
                "opponent_suite_id": ["mix=rule:1.0|eps=0.080"],
            },
        },
    )

    import pytest

    with pytest.raises(ValueError):
        assess_levels(
            l1_model_report=model,
            l1_rule_report=rule,
            l2_suite_report=suite,
            rule_profile_path=Path("rules/profile_hangzhou_mvp.yaml"),
            out=out,
            pytest_passed=True,
        )
