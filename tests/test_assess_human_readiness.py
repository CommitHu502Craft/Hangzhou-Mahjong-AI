import json
from pathlib import Path

from rl.assess_human_readiness import assess_suite


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


def test_assess_suite_all_pass(tmp_path: Path):
    m1 = tmp_path / "m1.json"
    r1 = tmp_path / "r1.json"
    m2 = tmp_path / "m2.json"
    r2 = tmp_path / "r2.json"
    out = tmp_path / "out.json"

    _write_report(m1, mean_diff=10.0, ci95=1.0, n_games=500)
    _write_report(r1, mean_diff=1.0, ci95=1.0, n_games=500)
    _write_report(m2, mean_diff=8.0, ci95=1.0, n_games=500)
    _write_report(r2, mean_diff=0.5, ci95=1.0, n_games=500)

    res = assess_suite(
        model_reports=[m1, m2],
        rule_reports=[r1, r2],
        out=out,
        scenario_names=["s1", "s2"],
        min_games=200,
        min_advantage=2.0,
        min_pass_ratio=1.0,
    )

    assert res["status"] == "PASS"
    assert res["summary"]["pass_count"] == 2
    assert res["context"]["rule_profile_id"] == "hz_local_v2026_02_A"


def test_assess_suite_ratio_gate(tmp_path: Path):
    m1 = tmp_path / "m1.json"
    r1 = tmp_path / "r1.json"
    m2 = tmp_path / "m2.json"
    r2 = tmp_path / "r2.json"
    out = tmp_path / "out.json"

    _write_report(m1, mean_diff=10.0, ci95=1.0, n_games=500)
    _write_report(r1, mean_diff=1.0, ci95=1.0, n_games=500)
    _write_report(m2, mean_diff=2.0, ci95=1.5, n_games=500)
    _write_report(r2, mean_diff=1.5, ci95=1.0, n_games=500)

    res = assess_suite(
        model_reports=[m1, m2],
        rule_reports=[r1, r2],
        out=out,
        scenario_names=["s1", "s2"],
        min_games=200,
        min_advantage=2.0,
        min_pass_ratio=0.5,
    )

    assert res["status"] == "PASS"
    assert res["summary"]["pass_count"] == 1
    assert res["summary"]["fail_count"] == 1


def test_assess_suite_raises_when_context_mismatch(tmp_path: Path):
    m1 = tmp_path / "m1.json"
    r1 = tmp_path / "r1.json"
    out = tmp_path / "out.json"

    _write_report(m1, mean_diff=10.0, ci95=1.0, n_games=500, rule_profile_id="hz_local_vA")
    _write_report(r1, mean_diff=1.0, ci95=1.0, n_games=500, rule_profile_id="hz_local_vB")

    import pytest

    with pytest.raises(ValueError):
        assess_suite(
            model_reports=[m1],
            rule_reports=[r1],
            out=out,
            scenario_names=["s1"],
            min_games=200,
            min_advantage=2.0,
            min_pass_ratio=1.0,
        )
