from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rl.real_ab_utils import canonicalize_records, load_ab_records, summarize_diffs


def build_replay_offline(
    *,
    input_paths: Sequence[Path],
    out_dir: Path,
    tag: str,
    rule_profile_id: str,
    spec_version: str,
    seed_set_id: str,
    opponent_suite_id: str,
) -> Dict[str, object]:
    raw, parse_errors = load_ab_records(list(input_paths))
    rows, row_errors = canonicalize_records(raw)
    stats = summarize_diffs([float(x["diff"]) for x in rows])

    out_dir.mkdir(parents=True, exist_ok=True)
    safe_tag = "".join(ch if (ch.isalnum() or ch in ("-", "_")) else "_" for ch in tag).strip("_")
    if not safe_tag:
        safe_tag = datetime.now().strftime("%Y%m%d_%H%M%S")

    records_path = out_dir / f"records_{safe_tag}.ndjson"
    summary_path = out_dir / f"summary_{safe_tag}.json"

    with records_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=True))
            f.write("\n")

    summary: Dict[str, object] = {
        "status": "OK",
        "tag": safe_tag,
        "n_games": int(stats["n_games"]),
        "mean_diff": float(stats["mean_diff"]),
        "std_diff": float(stats["std_diff"]),
        "ci95": float(stats["ci95"]),
        "lower_ci95": float(stats["lower_ci95"]),
        "context": {
            "rule_profile_id": str(rule_profile_id),
            "spec_version": str(spec_version),
            "seed_set_id": str(seed_set_id),
            "opponent_suite_id": str(opponent_suite_id),
        },
        "input_files": [str(Path(p)) for p in input_paths],
        "records_file": str(records_path),
        "parse_errors": parse_errors,
        "row_errors": row_errors,
        "parsed_rows": int(len(rows)),
        "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }

    summary_path.write_text(json.dumps(summary, ensure_ascii=True, indent=2), encoding="utf-8")
    print(f"saved_records={records_path}")
    print(f"saved_summary={summary_path}")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", type=Path, nargs="+", required=True)
    parser.add_argument("--out_dir", type=Path, default=Path("datasets/replay_offline"))
    parser.add_argument("--tag", type=str, default="")
    parser.add_argument("--rule_profile_id", type=str, default="unknown")
    parser.add_argument("--spec_version", type=str, default="unknown")
    parser.add_argument("--seed_set_id", type=str, default="human_live")
    parser.add_argument("--opponent_suite_id", type=str, default="human_table_v1")
    args = parser.parse_args()

    build_replay_offline(
        input_paths=args.inputs,
        out_dir=args.out_dir,
        tag=args.tag,
        rule_profile_id=args.rule_profile_id,
        spec_version=args.spec_version,
        seed_set_id=args.seed_set_id,
        opponent_suite_id=args.opponent_suite_id,
    )


if __name__ == "__main__":
    main()
