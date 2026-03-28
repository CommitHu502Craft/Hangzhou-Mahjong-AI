import json
from pathlib import Path

from datasets.build_replay_offline import build_replay_offline


def test_build_replay_offline_outputs_files(tmp_path: Path):
    src = tmp_path / "raw.jsonl"
    src.write_text(
        "\n".join(
            [
                json.dumps({"game_id": "g1", "diff": 3.0}, ensure_ascii=True),
                json.dumps({"game_id": "g2", "model_score": 118, "baseline_score": 110}, ensure_ascii=True),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    out_dir = tmp_path / "offline"
    summary = build_replay_offline(
        input_paths=[src],
        out_dir=out_dir,
        tag="hzvA_batch1",
        rule_profile_id="hz_local_v2026_02_A",
        spec_version="v1.1",
        seed_set_id="human_live",
        opponent_suite_id="human_table_v1",
    )

    records_path = out_dir / "records_hzvA_batch1.ndjson"
    summary_path = out_dir / "summary_hzvA_batch1.json"
    assert records_path.exists()
    assert summary_path.exists()
    assert summary["n_games"] == 2
    assert summary["context"]["rule_profile_id"] == "hz_local_v2026_02_A"


def test_build_replay_offline_handles_invalid_rows(tmp_path: Path):
    src = tmp_path / "raw2.jsonl"
    src.write_text(
        "\n".join(
            [
                json.dumps({"game_id": "g1", "diff": 1.0}, ensure_ascii=True),
                json.dumps({"game_id": "g2", "foo": "bar"}, ensure_ascii=True),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    out_dir = tmp_path / "offline2"
    summary = build_replay_offline(
        input_paths=[src],
        out_dir=out_dir,
        tag="",
        rule_profile_id="hz_local_v2026_02_A",
        spec_version="v1.1",
        seed_set_id="human_live",
        opponent_suite_id="human_table_v1",
    )
    assert summary["n_games"] == 1
    assert len(summary["row_errors"]) == 1

