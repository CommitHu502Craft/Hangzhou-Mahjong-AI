import json
from pathlib import Path

from rl.assess_real_ab import assess_real_ab


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=True))
            f.write("\n")


def test_assess_real_ab_pass_with_model_baseline_scores(tmp_path: Path):
    src = tmp_path / "ab.jsonl"
    out = tmp_path / "real_ab.json"
    _write_jsonl(
        src,
        [
            {"game_id": "g1", "model_score": 120, "baseline_score": 100},
            {"game_id": "g2", "model_score": 110, "baseline_score": 101},
            {"game_id": "g3", "model_score": 130, "baseline_score": 119},
        ],
    )
    res = assess_real_ab(
        input_paths=[src],
        out=out,
        min_games=3,
        min_advantage=5.0,
        rule_profile_id="hz_local_v2026_02_A",
        spec_version="v1.1",
    )
    assert res["status"] == "PASS"
    assert int(res["n_games"]) == 3
    assert float(res["mean_diff"]) > 5.0
    assert res["context"]["rule_profile_id"] == "hz_local_v2026_02_A"


def test_assess_real_ab_fail_when_not_enough_games(tmp_path: Path):
    src = tmp_path / "ab.json"
    out = tmp_path / "real_ab.json"
    src.write_text(json.dumps([{"diff": 2.0}], ensure_ascii=True), encoding="utf-8")
    res = assess_real_ab(
        input_paths=[src],
        out=out,
        min_games=2,
        min_advantage=0.0,
    )
    assert res["status"] == "FAIL"
    assert res["checks"]["enough_games"] is False

