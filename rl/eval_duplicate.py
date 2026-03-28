from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import List, Optional

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bots import RandomBot, RuleBot
from env import HangzhouMahjongEnv
from rl.report_context import build_report_context, read_spec_version
from rl.seed_splits import DEFAULT_SEED_SPLITS, classify_seed_set, resolve_seed_set


class PolicyRunner:
    def __init__(self, model_path: str, strict_load: bool = False):
        self.model_path = Path(model_path)
        self.strict_load = strict_load
        self.model = None
        self.backend = "fallback"
        self.load_status = "fallback"
        self.load_error: Optional[str] = None
        self.resolved_model_path: Optional[str] = None
        self._load()

    def _load(self) -> None:
        candidates: List[Path] = []
        if self.model_path.exists() and self.model_path.is_file():
            candidates.append(self.model_path)
        if self.model_path.suffix != ".zip":
            candidates.append(self.model_path.with_suffix(".zip"))
        elif not candidates:
            candidates.append(self.model_path)

        seen = set()
        deduped_candidates: List[Path] = []
        for c in candidates:
            key = str(c.resolve()) if c.exists() else str(c)
            if key in seen:
                continue
            seen.add(key)
            deduped_candidates.append(c)

        load_errors: List[str] = []
        try:
            from sb3_contrib import MaskablePPO
        except Exception as exc:
            self.model = None
            self.load_error = f"MaskablePPO import failed: {exc}"
            if self.strict_load:
                raise RuntimeError(self.load_error) from exc
            self.backend = "fallback"
            self.load_status = "fallback_import_error"
            return

        for path in deduped_candidates:
            if not path.exists():
                load_errors.append(f"{path}: not found")
                continue
            if path.suffix != ".zip":
                load_errors.append(f"{path}: unsupported suffix '{path.suffix}'")
                continue
            try:
                self.model = MaskablePPO.load(str(path))
                self.backend = "sb3"
                self.load_status = "loaded"
                self.resolved_model_path = str(path)
                self.load_error = None
                return
            except Exception as exc:
                load_errors.append(f"{path}: {exc}")

        self.model = None
        self.backend = "fallback"
        self.load_status = "fallback_no_model"
        self.load_error = "; ".join(load_errors) if load_errors else "no loadable checkpoint"
        if self.strict_load:
            raise RuntimeError(f"strict load failed for '{self.model_path}': {self.load_error}")

    def act(self, obs: np.ndarray, action_mask: np.ndarray) -> int:
        legal = np.flatnonzero(action_mask)
        if legal.size == 0:
            return 42
        if self.model is None:
            return int(legal.min())
        try:
            action, _ = self.model.predict(obs, deterministic=True, action_masks=action_mask)
            action = int(action)
            if action_mask[action]:
                return action
        except Exception:
            pass
        return int(legal.min())


def resolve_seed_list(
    seeds: Optional[List[int]],
    seed_start: Optional[int],
    seed_end: Optional[int],
    seed_set: Optional[str] = None,
) -> List[int]:
    if seed_set is not None and (seeds or seed_start is not None or seed_end is not None):
        raise ValueError("use either --seed_set or (--seeds / --seed_start --seed_end), not both")
    if seed_set is not None:
        return resolve_seed_set(seed_set)
    if seeds and (seed_start is not None or seed_end is not None):
        raise ValueError("use either --seeds or --seed_start/--seed_end, not both")
    if seed_start is not None or seed_end is not None:
        if seed_start is None or seed_end is None:
            raise ValueError("--seed_start and --seed_end must be provided together")
        if seed_start > seed_end:
            raise ValueError("--seed_start must be <= --seed_end")
        out = list(range(seed_start, seed_end + 1))
    else:
        out = seeds or []
    if not out:
        raise ValueError("must provide seeds via --seeds or --seed_start/--seed_end")
    return out

class RulePolicyRunner:
    def __init__(self, seed: int = 2026, epsilon: float = 0.0):
        self.backend = "rulebot"
        self.load_status = "n/a"
        self.load_error: Optional[str] = None
        self.resolved_model_path: Optional[str] = None
        self.bot = RuleBot(epsilon=epsilon, seed=seed)

    def act(self, obs: np.ndarray, action_mask: np.ndarray) -> int:
        return int(self.bot.select_action(obs, action_mask))


class RandomPolicyRunner:
    def __init__(self, seed: int = 2026):
        self.backend = "randombot"
        self.load_status = "n/a"
        self.load_error: Optional[str] = None
        self.resolved_model_path: Optional[str] = None
        self.bot = RandomBot(seed=seed)

    def act(self, obs: np.ndarray, action_mask: np.ndarray) -> int:
        return int(self.bot.select_action(obs, action_mask))


class MinLegalPolicyRunner:
    def __init__(self):
        self.backend = "fallback"
        self.load_status = "n/a"
        self.load_error: Optional[str] = None
        self.resolved_model_path: Optional[str] = None

    def act(self, obs: np.ndarray, action_mask: np.ndarray) -> int:
        legal = np.flatnonzero(action_mask)
        if legal.size == 0:
            return 42
        return int(legal.min())


def build_policy_runner(
    policy_mode: str,
    model: str,
    strict_load: bool,
    fail_on_fallback: bool,
    seed: int,
    rulebot_epsilon: float,
):
    mode = policy_mode.lower()
    if mode == "model":
        runner = PolicyRunner(model, strict_load=strict_load)
        if fail_on_fallback and runner.backend != "sb3":
            raise RuntimeError(
                f"policy backend is '{runner.backend}' (load_status={runner.load_status}); "
                "--fail_on_fallback requested hard failure"
            )
        return runner
    if mode == "rule":
        return RulePolicyRunner(seed=seed, epsilon=rulebot_epsilon)
    if mode == "random":
        return RandomPolicyRunner(seed=seed)
    if mode == "minlegal":
        return MinLegalPolicyRunner()
    raise ValueError(f"unsupported --policy_mode: {policy_mode}")


def run_one_game(
    seed: int,
    hero_seat: int,
    policy,
    enable_wealth_god: bool,
    protect_wealth_god_discard: bool,
    enable_qiaoxiang: bool,
    opponent_epsilon: float = 0.08,
    opponent_mix: str = "rule:1.0",
) -> float:
    env = HangzhouMahjongEnv(
        hero_seat=hero_seat,
        reward_mode="raw",
        bot_epsilon=float(opponent_epsilon),
        enable_wealth_god=enable_wealth_god,
        protect_wealth_god_discard=protect_wealth_god_discard,
        enable_qiaoxiang=enable_qiaoxiang,
        opponent_mix=opponent_mix,
    )
    obs, info = env.reset(seed=seed)
    terminated = env.engine.terminated
    truncated = False
    while not (terminated or truncated):
        mask = np.asarray(info["action_mask"], dtype=bool)
        action = policy.act(obs, mask)
        obs, reward, terminated, truncated, info = env.step(action)
    hero = env.engine.scores[hero_seat]
    others = [env.engine.scores[s] for s in range(4) if s != hero_seat]
    return float(hero - sum(others) / 3.0)


def evaluate(
    model: str,
    seeds: List[int],
    seats: List[int],
    out: Path,
    strict_load: bool,
    fail_on_fallback: bool,
    policy_mode: str,
    seed: int,
    rulebot_epsilon: float,
    enable_wealth_god: bool,
    protect_wealth_god_discard: bool,
    enable_qiaoxiang: bool,
    opponent_epsilon: float = 0.08,
    opponent_mix: str = "rule:1.0",
    seed_set_name: Optional[str] = None,
    rule_profile: Optional[Path] = None,
    rule_profile_id: Optional[str] = None,
    spec_version: Optional[str] = None,
    seed_set_id: Optional[str] = None,
    opponent_suite_id: Optional[str] = None,
) -> None:
    policy = build_policy_runner(
        policy_mode=policy_mode,
        model=model,
        strict_load=strict_load,
        fail_on_fallback=fail_on_fallback,
        seed=seed,
        rulebot_epsilon=rulebot_epsilon,
    )
    diffs: List[float] = []
    game_records = []
    for seed in seeds:
        for hero_seat in seats:
            diff = run_one_game(
                seed,
                hero_seat,
                policy,
                opponent_epsilon=float(opponent_epsilon),
                opponent_mix=opponent_mix,
                enable_wealth_god=enable_wealth_god,
                protect_wealth_god_discard=protect_wealth_god_discard,
                enable_qiaoxiang=enable_qiaoxiang,
            )
            diffs.append(diff)
            game_records.append({"seed": seed, "hero_seat": hero_seat, "score_diff": diff})

    arr = np.asarray(diffs, dtype=np.float64)
    mean = float(arr.mean()) if arr.size else 0.0
    std = float(arr.std(ddof=1)) if arr.size > 1 else 0.0
    ci95 = float(1.96 * std / math.sqrt(arr.size)) if arr.size > 1 else 0.0

    resolved_seed_set = seed_set_name or classify_seed_set(seeds)
    context = build_report_context(
        rule_profile_path=rule_profile,
        rule_profile_id=rule_profile_id,
        spec_version=spec_version or read_spec_version(),
        seed_set_name=resolved_seed_set,
        seeds=seeds,
        seed_set_id=seed_set_id,
        opponent_mix=opponent_mix,
        opponent_epsilon=float(opponent_epsilon),
        opponent_suite_id=opponent_suite_id,
    )

    report = {
        "model": model,
        "resolved_model_path": policy.resolved_model_path,
        "backend": policy.backend,
        "load_status": policy.load_status,
        "load_error": policy.load_error,
        "policy_mode": policy_mode,
        "n_games": int(arr.size),
        "mean_diff": mean,
        "std_diff": std,
        "ci95": ci95,
        "seeds": seeds,
        "seed_set": resolved_seed_set,
        "rule_profile": str(rule_profile) if rule_profile is not None else None,
        "rule_profile_id": context["rule_profile_id"],
        "spec_version": context["spec_version"],
        "seed_set_id": context["seed_set_id"],
        "opponent_suite_id": context["opponent_suite_id"],
        "seats": seats,
        "opponent_epsilon": float(opponent_epsilon),
        "opponent_mix": opponent_mix,
        "enable_wealth_god": bool(enable_wealth_god),
        "protect_wealth_god_discard": bool(protect_wealth_god_discard),
        "enable_qiaoxiang": bool(enable_qiaoxiang),
        "games": game_records,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")
    print(f"saved={out} n_games={arr.size} mean_diff={mean:.4f}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, required=True)
    parser.add_argument("--policy_mode", type=str, default="model", choices=["model", "rule", "random", "minlegal"])
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--rulebot_epsilon", type=float, default=0.0)
    parser.add_argument("--opponent_epsilon", type=float, default=0.08)
    parser.add_argument("--opponent_mix", type=str, default="rule:1.0")
    parser.add_argument("--seed_set", type=str, default=None, choices=sorted(DEFAULT_SEED_SPLITS.keys()))
    parser.add_argument("--seeds", type=int, nargs="*", default=None)
    parser.add_argument("--seed_start", type=int, default=None)
    parser.add_argument("--seed_end", type=int, default=None)
    parser.add_argument("--seats", type=int, nargs="+", default=[0, 1, 2, 3])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--strict_load", action="store_true")
    parser.add_argument("--fail_on_fallback", action="store_true")
    parser.add_argument("--rule_profile", type=Path, default=None)
    parser.add_argument("--rule_profile_id", type=str, default=None)
    parser.add_argument("--spec_version", type=str, default=None)
    parser.add_argument("--seed_set_id", type=str, default=None)
    parser.add_argument("--opponent_suite_id", type=str, default=None)
    parser.add_argument("--disable_wealth_god", action="store_true")
    parser.add_argument("--allow_discard_wealth_god", action="store_true")
    parser.add_argument("--enable_qiaoxiang", action="store_true")
    args = parser.parse_args()

    seeds = resolve_seed_list(args.seeds, args.seed_start, args.seed_end, args.seed_set)

    valid_seats = [s for s in args.seats if 0 <= s <= 3]
    if len(valid_seats) != len(args.seats) or not valid_seats:
        raise ValueError("--seats must be a non-empty list of values in [0,1,2,3]")
    evaluate(
        model=args.model,
        seeds=seeds,
        seats=valid_seats,
        out=args.out,
        strict_load=args.strict_load,
        fail_on_fallback=args.fail_on_fallback,
        policy_mode=args.policy_mode,
        seed=args.seed,
        rulebot_epsilon=args.rulebot_epsilon,
        opponent_epsilon=args.opponent_epsilon,
        opponent_mix=args.opponent_mix,
        seed_set_name=args.seed_set,
        rule_profile=args.rule_profile,
        rule_profile_id=args.rule_profile_id,
        spec_version=args.spec_version,
        seed_set_id=args.seed_set_id,
        opponent_suite_id=args.opponent_suite_id,
        enable_wealth_god=not args.disable_wealth_god,
        protect_wealth_god_discard=not args.allow_discard_wealth_god,
        enable_qiaoxiang=args.enable_qiaoxiang,
    )


if __name__ == "__main__":
    main()
