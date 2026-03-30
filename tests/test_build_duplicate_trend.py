import json
from pathlib import Path

from rl.build_duplicate_trend import REPORT_SCHEMA_VERSION, build_trend


def _write_report(path: Path, *, mean_diff: float, policy_mode: str) -> None:
    payload = {
        "report_schema_version": "duplicate_eval.v1",
        "policy_mode": policy_mode,
        "backend": "sb3",
        "n_games": 200,
        "mean_diff": mean_diff,
        "std_diff": 3.0,
        "ci95": 0.5,
        "rule_profile_id": "hz_local_v2026_02_A",
        "spec_version": "v1.1",
        "seed_set_id": "test",
        "opponent_suite_id": "mix=rule:1.0|eps=0.080",
    }
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")


def test_build_trend_writes_schema_and_context_fields(tmp_path: Path):
    report_a = tmp_path / "dup_model_a.json"
    report_b = tmp_path / "dup_model_b.json"
    out_md = tmp_path / "duplicate_trend.md"
    out_json = tmp_path / "duplicate_trend.json"

    _write_report(report_a, mean_diff=10.0, policy_mode="model")
    _write_report(report_b, mean_diff=8.0, policy_mode="rule")

    build_trend([report_a, report_b], out_md=out_md, out_json=out_json)

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["report_schema_version"] == REPORT_SCHEMA_VERSION
    assert len(payload["rows"]) == 2
    assert payload["rows"][0]["rule_profile_id"] == "hz_local_v2026_02_A"
    assert payload["rows"][0]["spec_version"] == "v1.1"
    assert payload["rows"][0]["seed_set_id"] == "test"
    assert payload["rows"][0]["opponent_suite_id"] == "mix=rule:1.0|eps=0.080"

    markdown = out_md.read_text(encoding="utf-8")
    assert "Rule Profile" in markdown
    assert "Opponent Suite" in markdown

