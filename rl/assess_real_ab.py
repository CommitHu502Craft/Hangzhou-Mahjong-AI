from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rl.real_ab_utils import canonicalize_records, load_ab_records, summarize_diffs


def assess_real_ab(
    *,
    input_paths: Sequence[Path],
    out: Path,
    min_games: int = 200,
    min_advantage: float = 0.0,
    require_lower_ci_positive: bool = False,
    rule_profile_id: str = "unknown",
    spec_version: str = "unknown",
    seed_set_id: str = "human_live",
    opponent_suite_id: str = "human_table_v1",
    notes: str = "",
) -> Dict[str, object]:
    raw, parse_errors = load_ab_records(list(input_paths))
    rows, row_errors = canonicalize_records(raw)
    stats = summarize_diffs([float(x["diff"]) for x in rows])
    checks = {
        "enough_games": int(stats["n_games"]) >= int(min_games),
        "advantage_ok": float(stats["mean_diff"]) >= float(min_advantage),
        "lower_ci95_positive": float(stats["lower_ci95"]) > 0.0,
    }

    passed = checks["enough_games"] and checks["advantage_ok"]
    if require_lower_ci_positive:
        passed = passed and checks["lower_ci95_positive"]

    payload: Dict[str, object] = {
        "status": "PASS" if passed else "FAIL",
        "n_games": int(stats["n_games"]),
        "mean_diff": float(stats["mean_diff"]),
        "std_diff": float(stats["std_diff"]),
        "ci95": float(stats["ci95"]),
        "lower_ci95": float(stats["lower_ci95"]),
        "criteria": {
            "min_games": int(min_games),
            "min_advantage": float(min_advantage),
            "require_lower_ci95_positive": bool(require_lower_ci_positive),
        },
        "checks": checks,
        "context": {
            "rule_profile_id": str(rule_profile_id),
            "spec_version": str(spec_version),
            "seed_set_id": str(seed_set_id),
            "opponent_suite_id": str(opponent_suite_id),
        },
        "inputs": [str(Path(p)) for p in input_paths],
        "parse_errors": parse_errors,
        "row_errors": row_errors,
        "parsed_rows": int(len(rows)),
        "notes": str(notes),
    }

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    print(
        f"saved={out} status={payload['status']} n_games={payload['n_games']} "
        f"mean_diff={payload['mean_diff']:.4f}"
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", type=Path, nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--min_games", type=int, default=200)
    parser.add_argument("--min_advantage", type=float, default=0.0)
    parser.add_argument("--require_lower_ci_positive", action="store_true")
    parser.add_argument("--rule_profile_id", type=str, default="unknown")
    parser.add_argument("--spec_version", type=str, default="unknown")
    parser.add_argument("--seed_set_id", type=str, default="human_live")
    parser.add_argument("--opponent_suite_id", type=str, default="human_table_v1")
    parser.add_argument("--notes", type=str, default="")
    args = parser.parse_args()

    assess_real_ab(
        input_paths=args.inputs,
        out=args.out,
        min_games=args.min_games,
        min_advantage=args.min_advantage,
        require_lower_ci_positive=args.require_lower_ci_positive,
        rule_profile_id=args.rule_profile_id,
        spec_version=args.spec_version,
        seed_set_id=args.seed_set_id,
        opponent_suite_id=args.opponent_suite_id,
        notes=args.notes,
    )


if __name__ == "__main__":
    main()
