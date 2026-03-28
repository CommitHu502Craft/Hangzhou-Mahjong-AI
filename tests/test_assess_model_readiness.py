import json
from pathlib import Path

from rl.assess_model_readiness import assess


def _write_report(
    path: Path,
    mean_diff: float,
    ci95: float,
    n_games: int,
    *,
    rule_profile_id: str = "hz_local_v2026_02_A",
    spec_version: str = "v1.1",
    seed_set_id: str = "test",
    opponent_suite_id: str = "mix=rule:1.0|eps=0.080",
):
    payload = {
        "mean_diff": mean_diff,
        "ci95": ci95,
        "n_games": n_games,
        "rule_profile_id": rule_profile_id,
        "spec_version": spec_version,
        "seed_set_id": seed_set_id,
        "opponent_suite_id": opponent_suite_id,
    }
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")


def test_assess_pass(tmp_path: Path):
    model = tmp_path / "model.json"
    rule = tmp_path / "rule.json"
    out = tmp_path / "out.json"
    _write_report(model, mean_diff=10.0, ci95=1.0, n_games=300)
    _write_report(rule, mean_diff=2.0, ci95=1.0, n_games=300)

    result = assess(model, rule, out, min_games=200, min_advantage=2.0)
    assert result["status"] == "PASS"
    assert result["checks"]["model_lower_ci95_positive"] is True
    assert result["context"]["rule_profile_id"] == "hz_local_v2026_02_A"


def test_assess_fail_when_not_enough_advantage(tmp_path: Path):
    model = tmp_path / "model.json"
    rule = tmp_path / "rule.json"
    out = tmp_path / "out.json"
    _write_report(model, mean_diff=2.5, ci95=1.0, n_games=300)
    _write_report(rule, mean_diff=2.0, ci95=1.0, n_games=300)

    result = assess(model, rule, out, min_games=200, min_advantage=2.0)
    assert result["status"] == "FAIL"
    assert result["checks"]["advantage_vs_rule_ok"] is False


def test_assess_raises_when_context_mismatch(tmp_path: Path):
    model = tmp_path / "model.json"
    rule = tmp_path / "rule.json"
    out = tmp_path / "out.json"
    _write_report(model, mean_diff=10.0, ci95=1.0, n_games=300, rule_profile_id="hz_local_vA")
    _write_report(rule, mean_diff=2.0, ci95=1.0, n_games=300, rule_profile_id="hz_local_vB")

    import pytest

    with pytest.raises(ValueError):
        assess(model, rule, out, min_games=200, min_advantage=2.0)
