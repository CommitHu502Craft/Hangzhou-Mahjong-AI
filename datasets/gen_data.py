from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bots import RuleBot
from env import HangzhouMahjongEnv


def _bootstrap_one_decision(
    env: HangzhouMahjongEnv,
    bot: RuleBot,
    seed_start: int,
    max_tries: int = 256,
) -> Optional[tuple[np.ndarray, int, np.ndarray, int]]:
    for offset in range(max_tries):
        obs, info = env.reset(seed=seed_start + 100_000 + offset)
        terminated = env.engine.terminated
        truncated = False
        if terminated or truncated:
            continue
        mask = np.asarray(info["action_mask"], dtype=bool)
        legal = np.flatnonzero(mask)
        if legal.size == 0:
            continue
        action = bot.select_action(obs, mask, env=env)
        if not mask[action]:
            action = int(legal.min())
        phase = int(obs[6, 0, 0] > 0.5)
        return obs.astype(np.float32).copy(), int(action), mask.copy(), phase
    return None


def _check_distribution_gates(
    *,
    phase_myturn: int,
    phase_reaction: int,
    action_hist_pct: np.ndarray,
    legal_mask_counts: np.ndarray,
    truncated_episodes: int,
    episodes_used: int,
    min_myturn_ratio: float,
    min_reaction_ratio: float,
    max_action_share: float,
    min_avg_legal_actions: float,
    max_truncated_rate: float,
) -> Dict[str, object]:
    total = max(1, phase_myturn + phase_reaction)
    myturn_ratio = float(phase_myturn / total)
    reaction_ratio = float(phase_reaction / total)
    dominant_action_share = float(action_hist_pct.max()) if action_hist_pct.size > 0 else 0.0
    avg_legal_actions = float(np.mean(legal_mask_counts)) if legal_mask_counts.size > 0 else 0.0
    truncated_rate = float(truncated_episodes / max(1, episodes_used))

    checks = {
        "myturn_ratio_ok": myturn_ratio >= float(min_myturn_ratio),
        "reaction_ratio_ok": reaction_ratio >= float(min_reaction_ratio),
        "dominant_action_share_ok": dominant_action_share <= float(max_action_share),
        "avg_legal_actions_ok": avg_legal_actions >= float(min_avg_legal_actions),
        "truncated_rate_ok": truncated_rate <= float(max_truncated_rate),
    }
    return {
        "metrics": {
            "myturn_ratio": myturn_ratio,
            "reaction_ratio": reaction_ratio,
            "dominant_action_share": dominant_action_share,
            "avg_legal_actions": avg_legal_actions,
            "truncated_rate": truncated_rate,
        },
        "thresholds": {
            "min_myturn_ratio": float(min_myturn_ratio),
            "min_reaction_ratio": float(min_reaction_ratio),
            "max_action_share": float(max_action_share),
            "min_avg_legal_actions": float(min_avg_legal_actions),
            "max_truncated_rate": float(max_truncated_rate),
        },
        "checks": checks,
        "status": "PASS" if all(bool(v) for v in checks.values()) else "FAIL",
    }


def generate_data(
    episodes: int,
    out_path: Path,
    seed_start: int,
    epsilon: float,
    target_decisions: int,
    min_samples: int,
    max_episodes: Optional[int],
    bootstrap_if_empty: bool,
    enable_wealth_god: bool,
    protect_wealth_god_discard: bool,
    enable_qiaoxiang: bool,
    gate_min_myturn_ratio: float,
    gate_min_reaction_ratio: float,
    gate_max_action_share: float,
    gate_min_avg_legal_actions: float,
    gate_max_truncated_rate: float,
    enforce_distribution_gates: bool,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    env = HangzhouMahjongEnv(
        bot_epsilon=epsilon,
        enable_wealth_god=enable_wealth_god,
        protect_wealth_god_discard=protect_wealth_god_discard,
        enable_qiaoxiang=enable_qiaoxiang,
    )
    hero_bot = RuleBot(epsilon=epsilon, seed=seed_start + 9_999)

    obs_buf: List[np.ndarray] = []
    action_buf: List[int] = []
    mask_buf: List[np.ndarray] = []
    phase_buf: List[int] = []
    returns: List[float] = []
    decisions_per_episode: List[int] = []
    truncated_episodes = 0
    early_terminal_episodes = 0

    target = max(0, int(target_decisions))
    if max_episodes is not None and max_episodes <= 0:
        raise ValueError("--max_episodes must be > 0 when provided")
    if episodes <= 0:
        raise ValueError("--episodes must be > 0")
    episode_budget = int(max_episodes) if max_episodes is not None else int(episodes)
    if episode_budget <= 0:
        raise ValueError("episode budget must be > 0")

    ep = 0
    while ep < episode_budget and (target == 0 or len(action_buf) < target):
        sample_before = len(action_buf)
        obs, info = env.reset(seed=seed_start + ep)
        terminated = env.engine.terminated
        truncated = False
        total_reward = 0.0

        while not (terminated or truncated):
            mask = np.asarray(info["action_mask"], dtype=bool)
            action = hero_bot.select_action(obs, mask, env=env)
            if not mask[action]:
                raise RuntimeError("sampled illegal action during data generation")

            obs_buf.append(obs.astype(np.float32).copy())
            action_buf.append(int(action))
            mask_buf.append(mask.copy())
            phase_buf.append(int(obs[6, 0, 0] > 0.5))

            obs, reward, terminated, truncated, info = env.step(int(action))
            total_reward += float(reward)

        returns.append(total_reward)
        if truncated:
            truncated_episodes += 1
        decisions_this_episode = len(action_buf) - sample_before
        decisions_per_episode.append(decisions_this_episode)
        if decisions_this_episode == 0:
            early_terminal_episodes += 1
        ep += 1

    if len(action_buf) == 0 and bootstrap_if_empty:
        bootstrap = _bootstrap_one_decision(env, hero_bot, seed_start=seed_start)
        if bootstrap is not None:
            b_obs, b_action, b_mask, b_phase = bootstrap
            obs_buf.append(b_obs)
            action_buf.append(b_action)
            mask_buf.append(b_mask)
            phase_buf.append(b_phase)

    if len(action_buf) < int(min_samples):
        raise RuntimeError(
            f"generated samples {len(action_buf)} < min_samples {min_samples}; "
            "increase --episodes/--max_episodes or lower --min_samples"
        )

    obs_arr = np.asarray(obs_buf, dtype=np.float32)
    action_arr = np.asarray(action_buf, dtype=np.int64)
    mask_arr = np.asarray(mask_buf, dtype=bool)
    phase_arr = np.asarray(phase_buf, dtype=np.uint8)
    action_hist = np.bincount(action_arr, minlength=47) if action_arr.size > 0 else np.zeros(47, dtype=np.int64)
    action_hist_pct = (action_hist / max(1, int(action_arr.size))).astype(np.float64)
    legal_mask_counts = mask_arr.sum(axis=1).astype(np.int64) if mask_arr.size > 0 else np.zeros(0, dtype=np.int64)
    phase_myturn = int(np.sum(phase_arr == 1))
    phase_reaction = int(np.sum(phase_arr == 0))
    stop_reason = "target_decisions_reached" if target > 0 and len(action_buf) >= target else "episode_budget_exhausted"
    gate_result = _check_distribution_gates(
        phase_myturn=phase_myturn,
        phase_reaction=phase_reaction,
        action_hist_pct=action_hist_pct,
        legal_mask_counts=legal_mask_counts,
        truncated_episodes=truncated_episodes,
        episodes_used=ep,
        min_myturn_ratio=gate_min_myturn_ratio,
        min_reaction_ratio=gate_min_reaction_ratio,
        max_action_share=gate_max_action_share,
        min_avg_legal_actions=gate_min_avg_legal_actions,
        max_truncated_rate=gate_max_truncated_rate,
    )
    meta = {
        "episodes_requested": int(episodes),
        "max_episodes": int(episode_budget),
        "episodes_used": int(ep),
        "seed_start": seed_start,
        "bot": "RuleBot",
        "epsilon": epsilon,
        "target_decisions": int(target),
        "actual_samples": int(len(action_arr)),
        "min_samples": int(min_samples),
        "bootstrap_if_empty": bool(bootstrap_if_empty),
        "enable_wealth_god": bool(enable_wealth_god),
        "protect_wealth_god_discard": bool(protect_wealth_god_discard),
        "enable_qiaoxiang": bool(enable_qiaoxiang),
        "stop_reason": stop_reason,
        "truncated_episodes": int(truncated_episodes),
        "early_terminal_episodes": int(early_terminal_episodes),
        "early_terminal_rate": float(early_terminal_episodes / ep) if ep > 0 else 0.0,
        "decision_mean_per_episode": float(np.mean(decisions_per_episode) if decisions_per_episode else 0.0),
        "reward_mean": float(np.mean(returns) if returns else 0.0),
        "phase_counts": {"myturn": phase_myturn, "reaction": phase_reaction},
        "action_hist": {str(i): int(v) for i, v in enumerate(action_hist.tolist()) if v > 0},
        "action_hist_pct": {str(i): float(v) for i, v in enumerate(action_hist_pct.tolist()) if action_hist[i] > 0},
        "legal_mask_stats": {
            "avg_legal_actions": float(np.mean(legal_mask_counts) if legal_mask_counts.size > 0 else 0.0),
            "min_legal_actions": int(np.min(legal_mask_counts) if legal_mask_counts.size > 0 else 0),
            "max_legal_actions": int(np.max(legal_mask_counts) if legal_mask_counts.size > 0 else 0),
        },
        "distribution_gates": gate_result,
        "distribution_gates_enforced": bool(enforce_distribution_gates),
    }
    meta_arr = np.asarray([json.dumps(meta)], dtype=object)

    np.savez_compressed(
        out_path,
        obs=obs_arr,
        action=action_arr,
        legal_mask=mask_arr,
        phase=phase_arr,
        meta=meta_arr,
    )
    print(
        f"saved={out_path} samples={len(action_arr)} episodes_used={ep} "
        f"target_decisions={target} stop_reason={stop_reason}"
    )
    if enforce_distribution_gates and str(gate_result["status"]).upper() != "PASS":
        checks = gate_result["checks"]  # type: ignore[index]
        failed = [name for name, ok in checks.items() if not bool(ok)]  # type: ignore[union-attr]
        raise RuntimeError(
            "dataset distribution gates failed: "
            + ",".join(failed)
            + f" | artifact={out_path}"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--episodes", type=int, default=100)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed_start", type=int, default=1000)
    parser.add_argument("--epsilon", type=float, default=0.08)
    parser.add_argument("--target_decisions", type=int, default=0)
    parser.add_argument("--min_samples", type=int, default=1)
    parser.add_argument("--max_episodes", type=int, default=None)
    parser.add_argument("--bootstrap_if_empty", action="store_true")
    parser.add_argument("--disable_wealth_god", action="store_true")
    parser.add_argument("--allow_discard_wealth_god", action="store_true")
    parser.add_argument("--enable_qiaoxiang", action="store_true")
    parser.add_argument("--gate_min_myturn_ratio", type=float, default=0.0)
    parser.add_argument("--gate_min_reaction_ratio", type=float, default=0.0)
    parser.add_argument("--gate_max_action_share", type=float, default=1.0)
    parser.add_argument("--gate_min_avg_legal_actions", type=float, default=1.0)
    parser.add_argument("--gate_max_truncated_rate", type=float, default=1.0)
    parser.add_argument("--enforce_distribution_gates", action="store_true")
    args = parser.parse_args()
    generate_data(
        episodes=args.episodes,
        out_path=args.out,
        seed_start=args.seed_start,
        epsilon=args.epsilon,
        target_decisions=args.target_decisions,
        min_samples=args.min_samples,
        max_episodes=args.max_episodes,
        bootstrap_if_empty=args.bootstrap_if_empty,
        enable_wealth_god=not args.disable_wealth_god,
        protect_wealth_god_discard=not args.allow_discard_wealth_god,
        enable_qiaoxiang=args.enable_qiaoxiang,
        gate_min_myturn_ratio=args.gate_min_myturn_ratio,
        gate_min_reaction_ratio=args.gate_min_reaction_ratio,
        gate_max_action_share=args.gate_max_action_share,
        gate_min_avg_legal_actions=args.gate_min_avg_legal_actions,
        gate_max_truncated_rate=args.gate_max_truncated_rate,
        enforce_distribution_gates=args.enforce_distribution_gates,
    )


if __name__ == "__main__":
    main()
