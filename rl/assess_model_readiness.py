from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rl.report_context import assert_context_match, assert_expected_context


def _load_report(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def assess(
    model_report_path: Path,
    rule_report_path: Path,
    out: Path,
    min_games: int = 200,
    min_advantage: float = 2.0,
    expected_rule_profile_id: str | None = None,
    expected_spec_version: str | None = None,
    expected_seed_set_id: str | None = None,
    expected_opponent_suite_id: str | None = None,
) -> dict:
    model = _load_report(model_report_path)
    rule = _load_report(rule_report_path)
    context = assert_context_match(
        left=model,
        right=rule,
        left_name="model_report",
        right_name="rule_report",
    )
    assert_expected_context(
        context,
        expected_rule_profile_id=expected_rule_profile_id,
        expected_spec_version=expected_spec_version,
        expected_seed_set_id=expected_seed_set_id,
        expected_opponent_suite_id=expected_opponent_suite_id,
    )

    model_n = int(model.get("n_games", 0))
    rule_n = int(rule.get("n_games", 0))
    model_mean = float(model.get("mean_diff", 0.0))
    rule_mean = float(rule.get("mean_diff", 0.0))
    model_ci = float(model.get("ci95", 0.0))

    lower_ci = model_mean - model_ci
    advantage_vs_rule = model_mean - rule_mean

    pass_n = model_n >= min_games and rule_n >= min_games
    pass_positive = lower_ci > 0.0
    pass_advantage = advantage_vs_rule >= float(min_advantage)
    overall_pass = pass_n and pass_positive and pass_advantage

    result = {
        "status": "PASS" if overall_pass else "FAIL",
        "criteria": {
            "min_games": int(min_games),
            "min_advantage_vs_rule": float(min_advantage),
        },
        "model_report": str(model_report_path),
        "rule_report": str(rule_report_path),
        "context": context,
        "metrics": {
            "model_n_games": model_n,
            "rule_n_games": rule_n,
            "model_mean_diff": model_mean,
            "model_ci95": model_ci,
            "model_lower_ci95": lower_ci,
            "rule_mean_diff": rule_mean,
            "advantage_vs_rule": advantage_vs_rule,
        },
        "checks": {
            "enough_games": pass_n,
            "model_lower_ci95_positive": pass_positive,
            "advantage_vs_rule_ok": pass_advantage,
        },
    }

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=True, indent=2), encoding="utf-8")
    print(f"saved={out} status={result['status']} lower_ci95={lower_ci:.4f} advantage_vs_rule={advantage_vs_rule:.4f}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model_report", type=Path, required=True)
    parser.add_argument("--rule_report", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--min_games", type=int, default=200)
    parser.add_argument("--min_advantage", type=float, default=2.0)
    parser.add_argument("--expected_rule_profile_id", type=str, default=None)
    parser.add_argument("--expected_spec_version", type=str, default=None)
    parser.add_argument("--expected_seed_set_id", type=str, default=None)
    parser.add_argument("--expected_opponent_suite_id", type=str, default=None)
    args = parser.parse_args()

    assess(
        model_report_path=args.model_report,
        rule_report_path=args.rule_report,
        out=args.out,
        min_games=args.min_games,
        min_advantage=args.min_advantage,
        expected_rule_profile_id=args.expected_rule_profile_id,
        expected_spec_version=args.expected_spec_version,
        expected_seed_set_id=args.expected_seed_set_id,
        expected_opponent_suite_id=args.expected_opponent_suite_id,
    )


if __name__ == "__main__":
    main()
