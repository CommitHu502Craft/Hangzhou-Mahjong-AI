from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable

import numpy as np
import pytest

from engine import MahjongEngine, ReactionClaim
from env import HangzhouMahjongEnv
from rules.profiles import engine_kwargs_from_profile, env_kwargs_from_profile, load_rule_profile, validate_rule_profile

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "local_rules"


def _fixture_paths() -> list[Path]:
    return sorted(FIXTURE_DIR.glob("*.json"))


def _load_fixture(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _set_counts(target: np.ndarray, payload: Dict[str, int]) -> None:
    target[:] = 0
    for tile_str, count in payload.items():
        tile = int(tile_str)
        target[tile] = int(count)


def _apply_setup_to_engine(engine: MahjongEngine, setup: Dict[str, Any]) -> None:
    if "phase" in setup:
        engine.phase = str(setup["phase"])
    if "actor" in setup:
        engine.actor = int(setup["actor"])
    if "wealth_god" in setup:
        engine.wealth_god = int(setup["wealth_god"])
    if "last_discard" in setup:
        value = setup["last_discard"]
        engine.last_discard = None if value is None else int(value)
    if "last_discarder" in setup:
        value = setup["last_discarder"]
        engine.last_discarder = None if value is None else int(value)

    for key, banks in (("hands", engine.hands), ("melds", engine.melds), ("discards", engine.discards)):
        if key not in setup:
            continue
        for seat_str, payload in setup[key].items():
            seat = int(seat_str)
            _set_counts(banks[seat], payload)

    for seat in setup.get("activate_qiaoxiang_seats", []):
        engine._activate_qiaoxiang(int(seat), "fixture")  # noqa: SLF001

    if "wall" in setup:
        engine.wall = [int(x) for x in setup["wall"]]


def _assert_mask(mask: np.ndarray, expect: Dict[str, Any]) -> None:
    for action in expect.get("mask_true", []):
        assert bool(mask[int(action)]) is True
    for action in expect.get("mask_false", []):
        assert bool(mask[int(action)]) is False


def _to_candidate(raw: Any) -> int | tuple[int, ...]:
    if isinstance(raw, list):
        return tuple(int(x) for x in raw)
    return int(raw)


def test_rule_profile_schema_has_top10_disputes() -> None:
    profile = load_rule_profile(ROOT / "rules" / "profile_hangzhou_mvp.yaml")
    top10 = profile["top10_disputes"]
    assert len(top10) >= 10
    assert all("id" in x and "rule" in x and "expected" in x for x in top10)


def test_engine_kwargs_include_special_hu_types_from_profile() -> None:
    profile = load_rule_profile(ROOT / "rules" / "profile_hangzhou_mvp.yaml")
    kwargs = engine_kwargs_from_profile(profile)
    assert kwargs["special_hu_types"] == ["qidui", "shisanyao"]


def test_validate_rule_profile_rejects_unknown_special_hu_type() -> None:
    profile = load_rule_profile(ROOT / "rules" / "profile_hangzhou_mvp.yaml")
    profile["rules"]["special_hu_types"] = ["qidui", "unknown_hu_type"]
    with pytest.raises(ValueError):
        validate_rule_profile(profile)


def test_validate_rule_profile_rejects_unsupported_lianzhuang_multiplier() -> None:
    profile = load_rule_profile(ROOT / "rules" / "profile_hangzhou_mvp.yaml")
    profile["rules"]["qiaoxiang"]["lianzhuang_multiplier"] = 2.0
    with pytest.raises(ValueError):
        validate_rule_profile(profile)


def test_validate_rule_profile_rejects_unsupported_qiangganghu() -> None:
    profile = load_rule_profile(ROOT / "rules" / "profile_hangzhou_mvp.yaml")
    profile["rules"]["reaction"]["qiangganghu"] = True
    with pytest.raises(ValueError):
        validate_rule_profile(profile)


@pytest.mark.parametrize("fixture_path", _fixture_paths(), ids=lambda p: p.stem)
def test_local_rule_fixture_suite(fixture_path: Path) -> None:
    fixture = _load_fixture(fixture_path)
    profile_path = ROOT / fixture["profile_path"]
    profile = load_rule_profile(profile_path)
    scenario = fixture["scenario"]
    setup = fixture.get("setup", {})
    expect = fixture.get("expect", {})

    if scenario == "env_mask":
        hero_seat = int(setup.get("hero_seat", 0))
        env = HangzhouMahjongEnv(hero_seat=hero_seat, **env_kwargs_from_profile(profile))
        env.reset(seed=int(setup.get("seed", 123)))
        _apply_setup_to_engine(env.engine, setup)

        if bool(setup.get("prepare_hero_reaction_claims", False)):
            env._awaiting_hero_reaction = True  # noqa: SLF001
            env._hero_reaction_claims = env.engine.legal_reaction_candidates(hero_seat)  # noqa: SLF001

        mask = env.action_masks()
        _assert_mask(mask, expect)
        return

    engine = MahjongEngine(**engine_kwargs_from_profile(profile))
    _apply_setup_to_engine(engine, setup)

    if scenario == "priority":
        claims = [
            ReactionClaim(
                seat=int(item["seat"]),
                action=str(item["action"]),
                candidate=_to_candidate(item["candidate"]),
            )
            for item in fixture["claims"]
        ]
        winner = engine.resolve_reaction_priority(claims, int(setup["discarder"]))
        assert winner is not None
        assert winner.seat == int(expect["winner_seat"])
        assert winner.action == str(expect["winner_action"])
        if "winner_candidate" in expect:
            assert winner.candidate == _to_candidate(expect["winner_candidate"])
        return

    if scenario == "scoring":
        op = fixture["operation"]
        op_type = op["type"]
        if op_type == "self_hu":
            engine.phase = "myturn"
            engine.actor = int(op["seat"])
            engine.apply_self_hu(int(op["seat"]))
        elif op_type == "reaction_hu":
            discarder = int(op["discarder"])
            seat = int(op["seat"])
            tile = int(op["tile"])
            engine.phase = "reaction"
            engine.last_discarder = discarder
            engine.last_discard = tile
            engine.apply_reaction(ReactionClaim(seat=seat, action="hu", candidate=tile))
        elif op_type == "force_draw":
            draw_seat = int(op.get("seat", 0))
            engine.wall = []
            engine.draw_tile(draw_seat)
        else:
            raise ValueError(f"unsupported operation type: {op_type}")

        if "fan_types_contains" in expect:
            assert engine.win_details is not None
            fan_types = set(str(x) for x in engine.win_details["fan_types"])
            for fan in expect["fan_types_contains"]:
                assert str(fan) in fan_types
        if "fan_total_min" in expect:
            assert engine.win_details is not None
            assert int(engine.win_details["fan_total"]) >= int(expect["fan_total_min"])
        if bool(expect.get("score_sum_zero", False)):
            assert sum(int(x) for x in engine.scores) == 0
        if "winner_score_min" in expect:
            winner = int(expect.get("winner_seat", 0))
            assert int(engine.scores[winner]) >= int(expect["winner_score_min"])
        if "qiaoxiang_state" in expect:
            seat = int(expect.get("qiaoxiang_seat", 0))
            state = str(engine.qiaoxiang_states[seat]["state"])
            assert state == str(expect["qiaoxiang_state"])
        return

    raise ValueError(f"unsupported scenario: {scenario}")
