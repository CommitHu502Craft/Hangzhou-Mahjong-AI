from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rl.report_context import assert_context_match, assert_expected_context, extract_report_context


def _load_report(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _assess_one(
    name: str,
    model_report_path: Path,
    rule_report_path: Path,
    min_games: int,
    min_advantage: float,
) -> dict:
    model = _load_report(model_report_path)
    rule = _load_report(rule_report_path)
    context = assert_context_match(
        left=model,
        right=rule,
        left_name=f"model_report({name})",
        right_name=f"rule_report({name})",
    )

    model_n = int(model.get("n_games", 0))
    rule_n = int(rule.get("n_games", 0))
    model_mean = float(model.get("mean_diff", 0.0))
    rule_mean = float(rule.get("mean_diff", 0.0))
    model_ci = float(model.get("ci95", 0.0))

    lower_ci = model_mean - model_ci
    advantage_vs_rule = model_mean - rule_mean

    check_n = model_n >= min_games and rule_n >= min_games
    check_positive = lower_ci > 0.0
    check_advantage = advantage_vs_rule >= float(min_advantage)
    passed = check_n and check_positive and check_advantage

    return {
        "name": name,
        "status": "PASS" if passed else "FAIL",
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
            "enough_games": check_n,
            "model_lower_ci95_positive": check_positive,
            "advantage_vs_rule_ok": check_advantage,
        },
    }


def assess_suite(
    model_reports: List[Path],
    rule_reports: List[Path],
    out: Path,
    scenario_names: Optional[List[str]] = None,
    min_games: int = 4000,
    min_advantage: float = 2.0,
    min_pass_ratio: float = 1.0,
    expected_rule_profile_id: Optional[str] = None,
    expected_spec_version: Optional[str] = None,
    expected_seed_set_id: Optional[str] = None,
) -> dict:
    if not model_reports or not rule_reports:
        raise ValueError("model_reports and rule_reports must be non-empty")
    if len(model_reports) != len(rule_reports):
        raise ValueError("model_reports and rule_reports must have same length")

    total = len(model_reports)
    if scenario_names is None or len(scenario_names) == 0:
        names = [f"scenario_{i+1}" for i in range(total)]
    else:
        if len(scenario_names) != total:
            raise ValueError("scenario_names length must match report pair count")
        names = scenario_names

    ratio = float(min_pass_ratio)
    if ratio <= 0.0 or ratio > 1.0:
        raise ValueError("min_pass_ratio must be in (0, 1]")

    scenarios: List[dict] = []
    for i in range(total):
        scenarios.append(
            _assess_one(
                name=names[i],
                model_report_path=model_reports[i],
                rule_report_path=rule_reports[i],
                min_games=min_games,
                min_advantage=min_advantage,
            )
        )

    if scenarios:
        base_context = extract_report_context(scenarios[0]["context"])
        for key in ("rule_profile_id", "spec_version", "seed_set_id"):
            values = {extract_report_context(s["context"])[key] for s in scenarios}
            if len(values) != 1:
                raise ValueError(f"context key '{key}' mismatch across scenarios: {sorted(values)}")
        suite_context = {
            "rule_profile_id": base_context["rule_profile_id"],
            "spec_version": base_context["spec_version"],
            "seed_set_id": base_context["seed_set_id"],
            "opponent_suite_id": sorted({extract_report_context(s["context"])["opponent_suite_id"] for s in scenarios}),
        }
    else:
        suite_context = {
            "rule_profile_id": "unknown",
            "spec_version": "unknown",
            "seed_set_id": "unknown",
            "opponent_suite_id": [],
        }
    assert_expected_context(
        suite_context,
        expected_rule_profile_id=expected_rule_profile_id,
        expected_spec_version=expected_spec_version,
        expected_seed_set_id=expected_seed_set_id,
        expected_opponent_suite_id=None,
    )

    pass_count = sum(1 for s in scenarios if s["status"] == "PASS")
    required_pass = int(math.ceil(total * ratio))
    overall_pass = pass_count >= required_pass

    result = {
        "status": "PASS" if overall_pass else "FAIL",
        "criteria": {
            "min_games": int(min_games),
            "min_advantage_vs_rule": float(min_advantage),
            "min_pass_ratio": ratio,
            "required_pass_count": required_pass,
            "total_scenarios": total,
        },
        "summary": {
            "pass_count": pass_count,
            "fail_count": total - pass_count,
        },
        "context": suite_context,
        "scenarios": scenarios,
    }

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=True, indent=2), encoding="utf-8")
    print(
        f"saved={out} status={result['status']} pass_count={pass_count}/{total} "
        f"required={required_pass}"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model_reports", type=Path, nargs="+", required=True)
    parser.add_argument("--rule_reports", type=Path, nargs="+", required=True)
    parser.add_argument("--scenario_names", type=str, nargs="*", default=None)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--min_games", type=int, default=4000)
    parser.add_argument("--min_advantage", type=float, default=2.0)
    parser.add_argument("--min_pass_ratio", type=float, default=1.0)
    parser.add_argument("--expected_rule_profile_id", type=str, default=None)
    parser.add_argument("--expected_spec_version", type=str, default=None)
    parser.add_argument("--expected_seed_set_id", type=str, default=None)
    args = parser.parse_args()

    assess_suite(
        model_reports=args.model_reports,
        rule_reports=args.rule_reports,
        out=args.out,
        scenario_names=args.scenario_names,
        min_games=args.min_games,
        min_advantage=args.min_advantage,
        min_pass_ratio=args.min_pass_ratio,
        expected_rule_profile_id=args.expected_rule_profile_id,
        expected_spec_version=args.expected_spec_version,
        expected_seed_set_id=args.expected_seed_set_id,
    )


if __name__ == "__main__":
    main()
