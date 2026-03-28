from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence

from rules.profiles import load_rule_profile


CONTEXT_KEYS: Sequence[str] = (
    "rule_profile_id",
    "spec_version",
    "seed_set_id",
    "opponent_suite_id",
)


def read_spec_version(spec_path: Optional[Path] = None) -> str:
    path = spec_path or Path("SPEC.md")
    if not path.exists():
        return "unknown"
    text = path.read_text(encoding="utf-8")
    for line in text.splitlines():
        match = re.match(r"^\s*Version:\s*(.+?)\s*$", line)
        if match:
            return match.group(1).strip()
    return "unknown"


def build_rule_profile_id(
    rule_profile_path: Optional[Path],
    override: Optional[str] = None,
) -> str:
    if override:
        return str(override).strip()
    if rule_profile_path is None:
        return "unknown"
    path = Path(rule_profile_path)
    if not path.exists():
        return f"{path.stem}@missing"
    try:
        profile = load_rule_profile(path)
        name = str(profile.get("profile_name", path.stem)).strip() or path.stem
        version = str(profile.get("version", "unknown")).strip() or "unknown"
        return f"{name}@{version}"
    except Exception:
        return f"{path.stem}@unparsed"


def build_seed_set_id(
    seed_set_name: Optional[str],
    seeds: Optional[Iterable[int]],
    override: Optional[str] = None,
) -> str:
    if override:
        return str(override).strip()
    if seed_set_name:
        return str(seed_set_name).strip()
    if seeds is None:
        return "unknown"
    seed_list = [int(s) for s in seeds]
    if not seed_list:
        return "unknown"
    return f"custom:{min(seed_list)}-{max(seed_list)}:{len(seed_list)}"


def build_opponent_suite_id(
    opponent_mix: str,
    opponent_epsilon: float,
    override: Optional[str] = None,
) -> str:
    if override:
        return str(override).strip()
    return f"mix={str(opponent_mix).strip()}|eps={float(opponent_epsilon):.3f}"


def build_report_context(
    *,
    rule_profile_path: Optional[Path],
    rule_profile_id: Optional[str],
    spec_version: Optional[str],
    seed_set_name: Optional[str],
    seeds: Optional[Iterable[int]],
    seed_set_id: Optional[str],
    opponent_mix: str,
    opponent_epsilon: float,
    opponent_suite_id: Optional[str],
) -> Dict[str, str]:
    return {
        "rule_profile_id": build_rule_profile_id(rule_profile_path, override=rule_profile_id),
        "spec_version": str(spec_version).strip() if spec_version else read_spec_version(),
        "seed_set_id": build_seed_set_id(seed_set_name=seed_set_name, seeds=seeds, override=seed_set_id),
        "opponent_suite_id": build_opponent_suite_id(
            opponent_mix=opponent_mix,
            opponent_epsilon=opponent_epsilon,
            override=opponent_suite_id,
        ),
    }


def extract_report_context(report: Mapping[str, Any]) -> Dict[str, str]:
    seed_set_fallback = report.get("seed_set", "unknown")
    opp_mix = str(report.get("opponent_mix", "unknown"))
    opp_eps = float(report.get("opponent_epsilon", 0.0))
    out = {
        "rule_profile_id": str(report.get("rule_profile_id", "unknown")),
        "spec_version": str(report.get("spec_version", "unknown")),
        "seed_set_id": str(report.get("seed_set_id", seed_set_fallback)),
        "opponent_suite_id": str(
            report.get(
                "opponent_suite_id",
                build_opponent_suite_id(opponent_mix=opp_mix, opponent_epsilon=opp_eps),
            )
        ),
    }
    for key in CONTEXT_KEYS:
        if not out.get(key):
            out[key] = "unknown"
    return out


def assert_context_match(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    left_name: str,
    right_name: str,
    keys: Sequence[str] = CONTEXT_KEYS,
) -> Dict[str, str]:
    lctx = extract_report_context(left)
    rctx = extract_report_context(right)
    mismatch: Dict[str, Dict[str, str]] = {}
    for key in keys:
        if lctx.get(key) != rctx.get(key):
            mismatch[key] = {"left": str(lctx.get(key)), "right": str(rctx.get(key))}
    if mismatch:
        raise ValueError(
            f"context mismatch between {left_name} and {right_name}: {mismatch}"
        )
    return lctx


def assert_expected_context(
    context: Mapping[str, Any],
    *,
    expected_rule_profile_id: Optional[str] = None,
    expected_spec_version: Optional[str] = None,
    expected_seed_set_id: Optional[str] = None,
    expected_opponent_suite_id: Optional[str] = None,
) -> None:
    expected = {
        "rule_profile_id": expected_rule_profile_id,
        "spec_version": expected_spec_version,
        "seed_set_id": expected_seed_set_id,
        "opponent_suite_id": expected_opponent_suite_id,
    }
    for key, exp in expected.items():
        if exp is None:
            continue
        if str(context.get(key, "")) != str(exp):
            raise ValueError(
                f"context field '{key}' mismatch: expected '{exp}', got '{context.get(key)}'"
            )
