from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# Allow direct script execution: `python rl/assess_readiness_levels.py ...`
# where repository root may not be on sys.path.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rules.profiles import load_rule_profile
from rl.report_context import (
    assert_context_match,
    assert_expected_context,
    build_rule_profile_id,
    extract_report_context,
)


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def assess_levels(
    l1_model_report: Path,
    l1_rule_report: Path,
    l2_suite_report: Path,
    rule_profile_path: Path,
    out: Path,
    pytest_passed: bool,
    min_games: int = 800,
    min_advantage: float = 2.0,
    real_ab_report: Optional[Path] = None,
    min_real_ab_games: int = 200,
    min_real_ab_advantage: float = 0.0,
    require_real_ab_for_l3: bool = True,
    expected_rule_profile_id: Optional[str] = None,
    expected_spec_version: Optional[str] = None,
    expected_seed_set_id: Optional[str] = None,
) -> Dict[str, Any]:
    l1_model = _load_json(l1_model_report)
    l1_rule = _load_json(l1_rule_report)
    l2_suite = _load_json(l2_suite_report)
    l1_context = assert_context_match(
        left=l1_model,
        right=l1_rule,
        left_name="l1_model_report",
        right_name="l1_rule_report",
    )
    l2_context = (
        extract_report_context(l2_suite["context"])
        if isinstance(l2_suite.get("context"), dict)
        else extract_report_context(l2_suite)
    )
    for key in ("rule_profile_id", "spec_version", "seed_set_id"):
        if l1_context.get(key) != l2_context.get(key):
            raise ValueError(
                f"context mismatch between L1 and L2 suite on '{key}': "
                f"{l1_context.get(key)} vs {l2_context.get(key)}"
            )
    assert_expected_context(
        l1_context,
        expected_rule_profile_id=expected_rule_profile_id,
        expected_spec_version=expected_spec_version,
        expected_seed_set_id=expected_seed_set_id,
    )

    model_n = int(l1_model.get("n_games", 0))
    rule_n = int(l1_rule.get("n_games", 0))
    model_mean = float(l1_model.get("mean_diff", 0.0))
    model_ci = float(l1_model.get("ci95", 0.0))
    rule_mean = float(l1_rule.get("mean_diff", 0.0))

    l1_lower_ci = model_mean - model_ci
    l1_advantage = model_mean - rule_mean
    l1_checks = {
        "pytest_passed": bool(pytest_passed),
        "enough_games": model_n >= min_games and rule_n >= min_games,
        "model_lower_ci95_positive": l1_lower_ci > 0.0,
        "advantage_vs_rule_ok": l1_advantage >= float(min_advantage),
    }
    l1_pass = all(l1_checks.values())

    l2_checks = {
        "suite_status_pass": str(l2_suite.get("status", "FAIL")).upper() == "PASS",
    }
    l2_pass = l1_pass and all(l2_checks.values())

    profile = load_rule_profile(rule_profile_path)
    profile_id_from_file = build_rule_profile_id(rule_profile_path, override=None)
    profile_id_locked = (
        str(expected_rule_profile_id).strip()
        if expected_rule_profile_id is not None and str(expected_rule_profile_id).strip()
        else profile_id_from_file
    )
    explicit_profile_lock = expected_rule_profile_id is not None and str(expected_rule_profile_id).strip() != ""
    profile_id_match = l1_context.get("rule_profile_id") == profile_id_locked
    profile_file_id_match = l1_context.get("rule_profile_id") == profile_id_from_file
    profile_lock_ok = profile_id_match and (profile_file_id_match or explicit_profile_lock)
    profile_lock = {
        "path": str(rule_profile_path),
        "sha256": _sha256(rule_profile_path),
        "profile_name": profile.get("profile_name", ""),
        "version": profile.get("version", ""),
        "valid": True,
        "rule_profile_id_locked": profile_id_locked,
        "rule_profile_id_from_file": profile_id_from_file,
        "explicit_profile_lock": bool(explicit_profile_lock),
        "report_rule_profile_id_match": bool(profile_id_match),
        "report_rule_profile_id_match_file_id": bool(profile_file_id_match),
        "profile_lock_ok": bool(profile_lock_ok),
    }

    real_ab_payload: Dict[str, Any] = {
        "provided": real_ab_report is not None,
        "status": "MISSING",
        "n_games": 0,
        "mean_diff": 0.0,
        "checks": {
            "enough_games": False,
            "advantage_ok": False,
        },
    }
    real_ab_pass = False
    if real_ab_report is not None:
        ab = _load_json(real_ab_report)
        ab_status = str(ab.get("status", "")).upper()
        ab_n = int(ab.get("n_games", ab.get("metrics", {}).get("n_games", 0)))
        ab_adv = float(ab.get("mean_diff", ab.get("metrics", {}).get("mean_diff", 0.0)))
        check_n = ab_n >= int(min_real_ab_games)
        check_adv = ab_adv >= float(min_real_ab_advantage)
        real_ab_pass = (ab_status == "PASS") or (check_n and check_adv)
        real_ab_payload = {
            "provided": True,
            "path": str(real_ab_report),
            "status": "PASS" if real_ab_pass else "FAIL",
            "n_games": ab_n,
            "mean_diff": ab_adv,
            "checks": {
                "enough_games": check_n,
                "advantage_ok": check_adv,
            },
        }

    if require_real_ab_for_l3:
        l3_pass = l2_pass and real_ab_pass and profile_lock["valid"] and profile_lock_ok
    else:
        l3_pass = (
            l2_pass
            and profile_lock["valid"]
            and profile_lock_ok
            and (real_ab_pass or not real_ab_payload["provided"])
        )

    highest_level = "L0"
    if l1_pass:
        highest_level = "L1"
    if l2_pass:
        highest_level = "L2"
    if l3_pass:
        highest_level = "L3"

    result = {
        "status": "PASS" if l1_pass else "FAIL",
        "highest_level": highest_level,
        "level_definitions": {
            "L1": "可训练稳定：pytest通过 + duplicate优于RuleBot",
            "L2": "仿真稳健：多场景human_readiness门禁通过",
            "L3": "真人可宣称：L2通过 + 规则画像锁定 + 真人A/B达标",
        },
        "criteria": {
            "l1_min_games": int(min_games),
            "l1_min_advantage": float(min_advantage),
            "real_ab_min_games": int(min_real_ab_games),
            "real_ab_min_advantage": float(min_real_ab_advantage),
            "require_real_ab_for_l3": bool(require_real_ab_for_l3),
        },
        "context": l1_context,
        "levels": {
            "L1": {
                "status": "PASS" if l1_pass else "FAIL",
                "checks": l1_checks,
                "metrics": {
                    "model_n_games": model_n,
                    "rule_n_games": rule_n,
                    "model_mean_diff": model_mean,
                    "model_ci95": model_ci,
                    "model_lower_ci95": l1_lower_ci,
                    "rule_mean_diff": rule_mean,
                    "advantage_vs_rule": l1_advantage,
                },
            },
            "L2": {
                "status": "PASS" if l2_pass else "FAIL",
                "checks": l2_checks,
                "suite_report": str(l2_suite_report),
            },
            "L3": {
                "status": "PASS" if l3_pass else "FAIL",
                "profile_lock": profile_lock,
                "real_ab": real_ab_payload,
            },
        },
    }

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=True, indent=2), encoding="utf-8")
    print(f"saved={out} highest_level={highest_level} l1={result['levels']['L1']['status']} l2={result['levels']['L2']['status']} l3={result['levels']['L3']['status']}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--l1_model_report", type=Path, required=True)
    parser.add_argument("--l1_rule_report", type=Path, required=True)
    parser.add_argument("--l2_suite_report", type=Path, required=True)
    parser.add_argument("--rule_profile", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--pytest_passed", action="store_true")
    parser.add_argument("--min_games", type=int, default=800)
    parser.add_argument("--min_advantage", type=float, default=2.0)
    parser.add_argument("--real_ab_report", type=Path, default=None)
    parser.add_argument("--min_real_ab_games", type=int, default=200)
    parser.add_argument("--min_real_ab_advantage", type=float, default=0.0)
    parser.add_argument("--no_require_real_ab_for_l3", action="store_true")
    parser.add_argument("--expected_rule_profile_id", type=str, default=None)
    parser.add_argument("--expected_spec_version", type=str, default=None)
    parser.add_argument("--expected_seed_set_id", type=str, default=None)
    args = parser.parse_args()

    assess_levels(
        l1_model_report=args.l1_model_report,
        l1_rule_report=args.l1_rule_report,
        l2_suite_report=args.l2_suite_report,
        rule_profile_path=args.rule_profile,
        out=args.out,
        pytest_passed=args.pytest_passed,
        min_games=args.min_games,
        min_advantage=args.min_advantage,
        real_ab_report=args.real_ab_report,
        min_real_ab_games=args.min_real_ab_games,
        min_real_ab_advantage=args.min_real_ab_advantage,
        require_real_ab_for_l3=not args.no_require_real_ab_for_l3,
        expected_rule_profile_id=args.expected_rule_profile_id,
        expected_spec_version=args.expected_spec_version,
        expected_seed_set_id=args.expected_seed_set_id,
    )


if __name__ == "__main__":
    main()
