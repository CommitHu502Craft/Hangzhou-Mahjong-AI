from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


REQUIRED_ROOT_KEYS = {"profile_name", "version", "rules", "top10_disputes"}
REQUIRED_RULE_KEYS = {"wealth_god", "qiaoxiang", "special_hu_types", "scoring", "reaction"}
SUPPORTED_SPECIAL_HU_TYPES = {"qidui", "shisanyao"}


def _load_yaml_or_json(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    raise ValueError(
        f"failed to parse rule profile: {path}. "
        "Use JSON-compatible YAML or install PyYAML for full YAML parsing."
    )


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_rule_profile(profile: Dict[str, Any]) -> None:
    missing_root = REQUIRED_ROOT_KEYS.difference(profile.keys())
    _assert(not missing_root, f"profile missing root keys: {sorted(missing_root)}")

    rules = profile.get("rules")
    _assert(isinstance(rules, dict), "profile.rules must be an object")
    missing_rules = REQUIRED_RULE_KEYS.difference(rules.keys())
    _assert(not missing_rules, f"profile.rules missing keys: {sorted(missing_rules)}")

    top10 = profile.get("top10_disputes")
    _assert(isinstance(top10, list), "profile.top10_disputes must be a list")
    _assert(len(top10) >= 10, "profile.top10_disputes must contain at least 10 entries")

    special_hu_types = rules.get("special_hu_types")
    _assert(isinstance(special_hu_types, list), "profile.rules.special_hu_types must be a list")
    for idx, item in enumerate(special_hu_types):
        _assert(isinstance(item, str), f"profile.rules.special_hu_types[{idx}] must be a string")
        name = item.strip().lower()
        _assert(name in SUPPORTED_SPECIAL_HU_TYPES, f"unsupported special_hu_type: {item}")

    qx = rules.get("qiaoxiang", {})
    _assert(isinstance(qx, dict), "profile.rules.qiaoxiang must be an object")
    # Current engine models a single hand and does not implement dealer streak multiplier.
    lianzhuang = qx.get("lianzhuang_multiplier", 1.0)
    _assert(float(lianzhuang) == 1.0, "unsupported qiaoxiang.lianzhuang_multiplier (only 1.0 supported)")

    scoring = rules.get("scoring", {})
    _assert(isinstance(scoring, dict), "profile.rules.scoring must be an object")
    _assert(str(scoring.get("package_liability", "none")) == "none", "unsupported scoring.package_liability")
    _assert(str(scoring.get("flow_scoring_mode", "zero")) == "zero", "unsupported scoring.flow_scoring_mode")

    reaction = rules.get("reaction", {})
    _assert(isinstance(reaction, dict), "profile.rules.reaction must be an object")
    _assert(str(reaction.get("priority", "hu>gang_pon>chi")) == "hu>gang_pon>chi", "unsupported reaction.priority")
    _assert(
        str(reaction.get("tie_break", "clockwise_from_discarder_next")) == "clockwise_from_discarder_next",
        "unsupported reaction.tie_break",
    )
    _assert(bool(reaction.get("qiangganghu", False)) is False, "unsupported reaction.qiangganghu=true")

    ids = set()
    for idx, item in enumerate(top10):
        _assert(isinstance(item, dict), f"top10_disputes[{idx}] must be an object")
        rid = item.get("id")
        _assert(isinstance(rid, str) and rid, f"top10_disputes[{idx}].id must be a non-empty string")
        _assert(rid not in ids, f"duplicate dispute id: {rid}")
        ids.add(rid)



def load_rule_profile(path: Path) -> Dict[str, Any]:
    profile = _load_yaml_or_json(path)
    validate_rule_profile(profile)
    return profile



def engine_kwargs_from_profile(profile: Dict[str, Any]) -> Dict[str, Any]:
    rules = profile["rules"]
    wg = rules["wealth_god"]
    qx = rules["qiaoxiang"]
    scoring = rules["scoring"]

    return {
        "enable_wealth_god": bool(wg.get("enabled", True)),
        "protect_wealth_god_discard": not bool(wg.get("discardable", False)),
        "wealth_god_can_meld": bool(wg.get("can_meld", True)),
        "special_hu_types": [str(x).strip().lower() for x in rules.get("special_hu_types", [])],
        "enable_qiaoxiang": bool(qx.get("enabled", False)),
        "qiaoxiang_fan_bonus": int(qx.get("fan_bonus", 1)),
        "base_score_unit": int(scoring.get("base_score_unit", 10)),
        "score_cap": scoring.get("score_cap", None),
        "draw_scoring_mode": str(scoring.get("draw_scoring_mode", "zero")),
    }



def env_kwargs_from_profile(profile: Dict[str, Any]) -> Dict[str, Any]:
    return engine_kwargs_from_profile(profile)
