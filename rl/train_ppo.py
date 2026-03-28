from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from env import HangzhouMahjongEnv
from mapping import ACTION_PASS


def _write_json_atomic(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # On Windows, heartbeat target may be momentarily locked by AV/indexing or a watcher.
    # Use a pid-specific temp file and retry replace a few times to avoid spurious training aborts.
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    attempts = 6
    for i in range(attempts):
        try:
            tmp.replace(path)
            return
        except PermissionError:
            if i >= attempts - 1:
                raise
            time.sleep(0.05 * (i + 1))


def _assert_min_free_disk(path: Path, min_free_gb: float) -> None:
    parent = path if path.exists() else path.parent
    parent.mkdir(parents=True, exist_ok=True)
    total, used, free = shutil.disk_usage(str(parent))
    free_gb = float(free) / (1024**3)
    if free_gb < float(min_free_gb):
        raise RuntimeError(
            f"low disk space at {parent}: free={free_gb:.2f}GB < required={float(min_free_gb):.2f}GB"
        )


def _collect_pool_paths(pool_dir: Path) -> List[str]:
    if not pool_dir.exists():
        return []
    paths: List[str] = []
    for p in sorted(pool_dir.glob("*")):
        # Opponent pool only supports MaskablePPO checkpoints.
        if p.is_file() and p.suffix == ".zip":
            paths.append(str(p))
    return paths


def _resolve_model_base(path_like: str) -> Path:
    p = Path(path_like)
    if p.suffix in (".zip", ".json", ".pkl"):
        return p.with_suffix("")
    return p


def _extract_steps_from_checkpoint_name(path: Path) -> Optional[int]:
    # Example: ppo_main_ckpt_200000_steps.zip
    match = re.search(r"_(\d+)_steps\.zip$", path.name)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _find_latest_checkpoint(checkpoint_dir: Path, prefix: str) -> Optional[Path]:
    if not checkpoint_dir.exists():
        return None
    candidates: List[Path] = []
    for p in checkpoint_dir.glob(f"{prefix}_*_steps.zip"):
        if p.is_file() and _extract_steps_from_checkpoint_name(p) is not None:
            candidates.append(p)
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda x: (_extract_steps_from_checkpoint_name(x) or -1, x.stat().st_mtime),
    )


def _guess_vecnormalize_path(
    resume_model_zip: Optional[Path],
    out_base: Path,
    explicit_vec_path: Optional[str],
) -> Optional[Path]:
    if explicit_vec_path:
        p = Path(explicit_vec_path)
        if p.exists():
            return p

    if resume_model_zip is not None:
        # If resuming from checkpoint callback artifact:
        # <prefix>_<N>_steps.zip -> <prefix>_vecnormalize_<N>_steps.pkl
        steps = _extract_steps_from_checkpoint_name(resume_model_zip)
        stem = resume_model_zip.stem
        if steps is not None and stem.endswith(f"_{steps}_steps"):
            prefix = stem[: -len(f"_{steps}_steps")]
            ckpt_vec = resume_model_zip.parent / f"{prefix}_vecnormalize_{steps}_steps.pkl"
            if ckpt_vec.exists():
                return ckpt_vec

        # Standard sidecar beside resumed model base.
        sidecar = resume_model_zip.with_suffix(".vecnormalize.pkl")
        if sidecar.exists():
            return sidecar

    # Fallback to out sidecar.
    out_sidecar = out_base.with_suffix(".vecnormalize.pkl")
    if out_sidecar.exists():
        return out_sidecar
    return None


def _compute_learn_timesteps(
    *,
    current_timesteps: int,
    chunk_timesteps: int,
    target_total_timesteps: int,
) -> int:
    if target_total_timesteps <= 0:
        return max(0, int(chunk_timesteps))
    remaining = int(target_total_timesteps) - int(current_timesteps)
    if remaining <= 0:
        return 0
    return max(0, min(int(chunk_timesteps), int(remaining)))


def _resolve_resume_source(args: argparse.Namespace, out_base: Path) -> Optional[Path]:
    if bool(getattr(args, "resume_latest_checkpoint", False)):
        ckpt_dir = Path(getattr(args, "checkpoint_dir", "")) if getattr(args, "checkpoint_dir", "") else out_base.parent / "checkpoints"
        prefix = str(getattr(args, "checkpoint_prefix", "")).strip() or f"{out_base.name}_ckpt"
        latest = _find_latest_checkpoint(ckpt_dir, prefix)
        if latest is not None:
            return latest

    resume_from = str(getattr(args, "resume_from", "")).strip()
    if resume_from:
        resume_base = _resolve_model_base(resume_from)
        resume_zip = resume_base.with_suffix(".zip")
        if resume_zip.exists():
            return resume_zip
        # Allow explicit .zip path in resume_from as-is.
        p = Path(resume_from)
        if p.exists() and p.suffix == ".zip":
            return p
        raise FileNotFoundError(f"resume model not found: {resume_from}")
    return None


def _default_heartbeat_path(out_base: Path) -> Path:
    return Path("reports") / f"heartbeat_{out_base.name}.json"


def _validate_reward_normalization_args(args: argparse.Namespace) -> None:
    use_vec_norm = bool(getattr(args, "use_vec_normalize_reward", False))
    reward_mode = str(getattr(args, "reward_mode", "log1p"))
    if use_vec_norm and reward_mode != "raw":
        raise ValueError(
            "VecNormalize reward normalization requires --reward_mode raw. "
            "Do not combine log1p with VecNormalize reward normalization."
        )


def _monitor_thresholds_from_args(args: argparse.Namespace) -> Dict[str, float]:
    return {
        "min_myturn_ratio": float(getattr(args, "gate_min_myturn_ratio", 0.0)),
        "min_reaction_ratio": float(getattr(args, "gate_min_reaction_ratio", 0.0)),
        "max_reaction_pass_rate": float(getattr(args, "gate_max_reaction_pass_rate", 1.0)),
        "max_illegal_action_rate": float(getattr(args, "gate_max_illegal_action_rate", 0.0)),
        "max_truncation_rate": float(getattr(args, "gate_max_truncation_rate", 0.05)),
    }


def _evaluate_monitor_gates(metrics: Dict[str, float], thresholds: Dict[str, float]) -> Dict[str, Any]:
    checks = {
        "myturn_ratio_ok": metrics["myturn_ratio"] >= thresholds["min_myturn_ratio"],
        "reaction_ratio_ok": metrics["reaction_ratio"] >= thresholds["min_reaction_ratio"],
        "reaction_pass_rate_ok": metrics["reaction_pass_rate"] <= thresholds["max_reaction_pass_rate"],
        "illegal_action_rate_ok": metrics["illegal_action_rate"] <= thresholds["max_illegal_action_rate"],
        "truncation_rate_ok": metrics["truncation_rate"] <= thresholds["max_truncation_rate"],
    }
    return {
        "status": "PASS" if all(bool(v) for v in checks.values()) else "FAIL",
        "metrics": metrics,
        "thresholds": thresholds,
        "checks": checks,
    }


def _run_policy_monitor(
    args: argparse.Namespace,
    pool_paths: List[str],
    action_selector: Callable[[np.ndarray, np.ndarray, HangzhouMahjongEnv], int],
) -> Dict[str, float]:
    monitor_episodes = max(1, int(getattr(args, "monitor_episodes", 12)))
    env = HangzhouMahjongEnv(
        reward_mode=args.reward_mode,
        bot_epsilon=float(getattr(args, "bot_epsilon", 0.08)),
        enable_wealth_god=not args.disable_wealth_god,
        protect_wealth_god_discard=not args.allow_discard_wealth_god,
        enable_qiaoxiang=args.enable_qiaoxiang,
        use_opponent_pool=args.use_opponent_pool,
        opponent_pool_paths=pool_paths,
        opponent_replace_count=args.opponent_replace_count,
        opponent_mix=str(getattr(args, "opponent_mix", "rule:1.0")),
    )

    decision_myturn = 0
    decision_reaction = 0
    reaction_pass = 0
    illegal_actions = 0
    truncated_episodes = 0
    total_steps = 0

    for ep in range(monitor_episodes):
        obs, info = env.reset(seed=args.seed + 800_000 + ep)
        terminated = env.engine.terminated
        truncated = False

        while not (terminated or truncated):
            mask = np.asarray(info["action_mask"], dtype=bool)
            legal = np.flatnonzero(mask)
            if legal.size == 0:
                illegal_actions += 1
                break

            phase = "reaction" if (env.engine.phase == "reaction" and env._awaiting_hero_reaction) else "myturn"  # noqa: SLF001
            if phase == "reaction":
                decision_reaction += 1
            else:
                decision_myturn += 1

            action = int(action_selector(obs, mask, env))
            if action < 0 or action >= len(mask) or not mask[action]:
                illegal_actions += 1
                action = int(legal[0])

            if phase == "reaction" and action == ACTION_PASS:
                reaction_pass += 1

            obs, _, terminated, truncated, info = env.step(action)
            total_steps += 1

        if truncated:
            truncated_episodes += 1

    total_decisions = max(1, decision_myturn + decision_reaction)
    reaction_decisions = max(1, decision_reaction)
    return {
        "episodes": float(monitor_episodes),
        "total_steps": float(total_steps),
        "myturn_decisions": float(decision_myturn),
        "reaction_decisions": float(decision_reaction),
        "myturn_ratio": float(decision_myturn / total_decisions),
        "reaction_ratio": float(decision_reaction / total_decisions),
        "reaction_pass_rate": float(reaction_pass / reaction_decisions),
        "illegal_action_rate": float(illegal_actions / total_decisions),
        "truncation_rate": float(truncated_episodes / monitor_episodes),
    }


def _fallback_train(args: argparse.Namespace, error: Exception) -> None:
    _validate_reward_normalization_args(args)
    out_base = Path(args.out)
    _assert_min_free_disk(out_base.parent, float(getattr(args, "min_free_disk_gb", 2.0)))
    resume_source = _resolve_resume_source(args, out_base)
    heartbeat_path = Path(args.heartbeat_path) if str(getattr(args, "heartbeat_path", "")).strip() else _default_heartbeat_path(out_base)
    resume_info = {}
    current_timesteps = 0
    if resume_source is not None:
        resume_meta = _resolve_model_base(str(resume_source)).with_suffix(".json")
        if resume_meta.exists():
            try:
                payload = json.loads(resume_meta.read_text(encoding="utf-8"))
                current_timesteps = int(payload.get("num_timesteps_total", payload.get("timesteps", 0)))
            except Exception:
                current_timesteps = 0
        resume_info = {
            "resumed": True,
            "resume_source": str(resume_source),
            "resume_current_timesteps": int(current_timesteps),
        }
    learn_timesteps = _compute_learn_timesteps(
        current_timesteps=int(current_timesteps),
        chunk_timesteps=int(args.timesteps),
        target_total_timesteps=int(getattr(args, "target_total_timesteps", 0)),
    )
    if learn_timesteps <= 0:
        out_base.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "backend": "fallback",
            "timesteps": int(args.timesteps),
            "num_timesteps_total": int(current_timesteps),
            "target_total_timesteps": int(getattr(args, "target_total_timesteps", 0)),
            "target_reached": bool(
                int(getattr(args, "target_total_timesteps", 0)) > 0
                and int(current_timesteps) >= int(getattr(args, "target_total_timesteps", 0))
            ),
            "skipped_training": True,
            "reason": "target_total_timesteps_reached",
            "error": str(error),
            **resume_info,
        }
        out_base.with_suffix(".json").write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
        _write_json_atomic(
            heartbeat_path,
            {
                "status": "skipped",
                "reason": "target_total_timesteps_reached",
                "updated_at_unix": time.time(),
                "num_timesteps_total": int(current_timesteps),
                "target_total_timesteps": int(getattr(args, "target_total_timesteps", 0)),
                "out": str(out_base),
                "run_tag": str(getattr(args, "run_tag", "")),
            },
        )
        print(
            f"saved={out_base.with_suffix('.json')} backend=fallback skipped=true "
            f"num_timesteps_total={current_timesteps}"
        )
        return

    pool_paths = _collect_pool_paths(Path(args.pool_dir))
    env = HangzhouMahjongEnv(
        reward_mode=args.reward_mode,
        enable_wealth_god=not args.disable_wealth_god,
        protect_wealth_god_discard=not args.allow_discard_wealth_god,
        enable_qiaoxiang=args.enable_qiaoxiang,
        use_opponent_pool=args.use_opponent_pool,
        opponent_pool_paths=pool_paths,
        opponent_replace_count=args.opponent_replace_count,
        opponent_mix=str(getattr(args, "opponent_mix", "rule:1.0")),
    )
    total_reward = 0.0
    episodes = max(4, args.num_envs)
    for i in range(episodes):
        obs, info = env.reset(seed=args.seed + i)
        terminated = env.engine.terminated
        truncated = False
        while not (terminated or truncated):
            mask = info["action_mask"]
            legal = [a for a, ok in enumerate(mask) if ok]
            action = legal[0]
            obs, reward, terminated, truncated, info = env.step(action)
            total_reward += float(reward)

    monitor_metrics = _run_policy_monitor(
        args,
        pool_paths,
        action_selector=lambda _obs, mask, _env: int(np.flatnonzero(mask)[0]),
    )
    monitor_gate = _evaluate_monitor_gates(monitor_metrics, _monitor_thresholds_from_args(args))
    if bool(getattr(args, "enforce_monitor_gates", True)) and monitor_gate["status"] != "PASS":
        raise RuntimeError(f"training monitor gates failed: {monitor_gate['checks']}")

    out_base.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "backend": "fallback",
        "timesteps": int(args.timesteps),
        "learn_timesteps": int(learn_timesteps),
        "target_total_timesteps": int(getattr(args, "target_total_timesteps", 0)),
        "num_timesteps_total": int(current_timesteps + learn_timesteps),
        "target_reached": bool(
            int(getattr(args, "target_total_timesteps", 0)) > 0
            and int(current_timesteps + learn_timesteps) >= int(getattr(args, "target_total_timesteps", 0))
        ),
        "num_envs": int(args.num_envs),
        "seed": int(args.seed),
        "vec_backend": args.vec_backend,
        "reward_mode": args.reward_mode,
        "use_opponent_pool": bool(args.use_opponent_pool),
        "pool_size": len(pool_paths),
        "policy": args.policy,
        "run_tag": args.run_tag,
        "opponent_mix": str(getattr(args, "opponent_mix", "rule:1.0")),
        "enable_wealth_god": bool(not args.disable_wealth_god),
        "protect_wealth_god_discard": bool(not args.allow_discard_wealth_god),
        "enable_qiaoxiang": bool(args.enable_qiaoxiang),
        "use_vec_normalize_reward": bool(getattr(args, "use_vec_normalize_reward", False)),
        "episodes": episodes,
        "total_reward": total_reward,
        "monitor_gate": monitor_gate,
        "error": str(error),
        **resume_info,
    }
    out_base.write_text("fallback_policy\n", encoding="utf-8")
    out_json = out_base.with_suffix(".json")
    out_json.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    _write_json_atomic(
        heartbeat_path,
        {
            "status": "fallback_done",
            "updated_at_unix": time.time(),
            "num_timesteps_total": int(payload["num_timesteps_total"]),
            "target_total_timesteps": int(payload["target_total_timesteps"]),
            "out": str(out_base),
            "run_tag": str(getattr(args, "run_tag", "")),
        },
    )
    print(
        f"saved={out_base} meta={out_json} backend=fallback "
        f"use_opponent_pool={args.use_opponent_pool} pool_size={len(pool_paths)}"
    )


def _ppo_train(args: argparse.Namespace) -> None:
    _validate_reward_normalization_args(args)
    try:
        from stable_baselines3.common.callbacks import BaseCallback, CheckpointCallback
        from sb3_contrib import MaskablePPO
        from stable_baselines3.common.utils import set_random_seed
        from stable_baselines3.common.vec_env import DummyVecEnv, SubprocVecEnv, VecNormalize
    except Exception as exc:
        if args.allow_fallback:
            _fallback_train(args, exc)
            return
        raise RuntimeError(
            "MaskablePPO dependencies unavailable. Re-run with --allow_fallback to use fallback trainer."
        ) from exc

    pool_paths = _collect_pool_paths(Path(args.pool_dir))
    set_random_seed(args.seed)
    out_base = Path(args.out)
    out_base.parent.mkdir(parents=True, exist_ok=True)
    _assert_min_free_disk(out_base.parent, float(getattr(args, "min_free_disk_gb", 2.0)))
    heartbeat_path = Path(args.heartbeat_path) if str(getattr(args, "heartbeat_path", "")).strip() else _default_heartbeat_path(out_base)

    class HeartbeatCallback(BaseCallback):
        def __init__(self, path: Path, save_freq: int, run_tag: str, out_base_path: Path):
            super().__init__(verbose=0)
            self.path = path
            self.save_freq = max(1, int(save_freq))
            self.run_tag = run_tag
            self.out_base_path = out_base_path
            self.start_time = time.time()

        def _write(self, status: str) -> None:
            payload = {
                "status": status,
                "updated_at_unix": time.time(),
                "elapsed_seconds": float(time.time() - self.start_time),
                "pid": int(os.getpid()),
                "num_timesteps": int(self.num_timesteps),
                "n_calls": int(self.n_calls),
                "run_tag": self.run_tag,
                "out": str(self.out_base_path),
                "target_total_timesteps": int(getattr(args, "target_total_timesteps", 0)),
            }
            _write_json_atomic(self.path, payload)

        def _on_training_start(self) -> None:
            self._write("running")

        def _on_step(self) -> bool:
            if self.n_calls % self.save_freq == 0:
                self._write("running")
            return True

        def _on_training_end(self) -> None:
            self._write("finished")

    resume_source = _resolve_resume_source(args, out_base)
    resumed = resume_source is not None
    resume_current_timesteps = 0
    resume_vec_path: Optional[Path] = None
    if resume_source is not None:
        resume_vec_path = _guess_vecnormalize_path(
            resume_model_zip=Path(resume_source),
            out_base=out_base,
            explicit_vec_path=getattr(args, "resume_vecnormalize", None),
        )

    def make_env(seed_offset: int):
        def _factory():
            env = HangzhouMahjongEnv(
                reward_mode=args.reward_mode,
                bot_epsilon=args.bot_epsilon,
                enable_wealth_god=not args.disable_wealth_god,
                protect_wealth_god_discard=not args.allow_discard_wealth_god,
                enable_qiaoxiang=args.enable_qiaoxiang,
                use_opponent_pool=args.use_opponent_pool,
                opponent_pool_paths=pool_paths,
                opponent_replace_count=args.opponent_replace_count,
                opponent_mix=args.opponent_mix,
            )
            env.reset(seed=args.seed + seed_offset)
            return env

        return _factory

    vec_env = None
    try:
        env_fns = [make_env(i) for i in range(max(1, args.num_envs))]
        if args.vec_backend == "subproc":
            vec_env = SubprocVecEnv(env_fns, start_method="spawn")
        else:
            vec_env = DummyVecEnv(env_fns)
        if args.use_vec_normalize_reward:
            if resume_vec_path is not None and resume_vec_path.exists():
                vec_env = VecNormalize.load(str(resume_vec_path), vec_env)
                vec_env.training = True
                vec_env.norm_reward = True
            else:
                vec_env = VecNormalize(vec_env, norm_obs=False, norm_reward=True)
        vec_env.seed(args.seed)
        if resume_source is not None:
            model = MaskablePPO.load(str(resume_source), env=vec_env, seed=args.seed)
            resume_current_timesteps = int(getattr(model, "num_timesteps", 0))
        else:
            model = MaskablePPO(
                args.policy,
                vec_env,
                verbose=0,
                n_steps=128,
                batch_size=128,
                learning_rate=3e-4,
                gamma=0.99,
                seed=args.seed,
            )

        learn_timesteps = _compute_learn_timesteps(
            current_timesteps=resume_current_timesteps,
            chunk_timesteps=int(args.timesteps),
            target_total_timesteps=int(getattr(args, "target_total_timesteps", 0)),
        )
        if learn_timesteps <= 0:
            meta = {
                "backend": "sb3_maskableppo",
                "timesteps": int(args.timesteps),
                "learn_timesteps": 0,
                "num_timesteps_total": int(resume_current_timesteps),
                "target_total_timesteps": int(getattr(args, "target_total_timesteps", 0)),
                "target_reached": bool(
                    int(getattr(args, "target_total_timesteps", 0)) > 0
                    and int(resume_current_timesteps) >= int(getattr(args, "target_total_timesteps", 0))
                ),
                "skipped_training": True,
                "reason": "target_total_timesteps_reached",
                "num_envs": int(args.num_envs),
                "seed": int(args.seed),
                "vec_backend": args.vec_backend,
                "reward_mode": args.reward_mode,
                "use_vec_normalize_reward": bool(args.use_vec_normalize_reward),
                "use_opponent_pool": bool(args.use_opponent_pool),
                "pool_size": len(pool_paths),
                "opponent_mix": args.opponent_mix,
                "policy": args.policy,
                "run_tag": args.run_tag,
                "enable_wealth_god": bool(not args.disable_wealth_god),
                "protect_wealth_god_discard": bool(not args.allow_discard_wealth_god),
                "enable_qiaoxiang": bool(args.enable_qiaoxiang),
                "resumed": bool(resumed),
                "resume_source": str(resume_source) if resume_source is not None else "",
                "resume_current_timesteps": int(resume_current_timesteps),
            }
            out_base.with_suffix(".json").write_text(json.dumps(meta, ensure_ascii=True, indent=2), encoding="utf-8")
            _write_json_atomic(
                heartbeat_path,
                {
                    "status": "skipped",
                    "reason": "target_total_timesteps_reached",
                    "updated_at_unix": time.time(),
                    "num_timesteps_total": int(resume_current_timesteps),
                    "target_total_timesteps": int(getattr(args, "target_total_timesteps", 0)),
                    "run_tag": str(args.run_tag),
                    "out": str(out_base),
                },
            )
            print(
                f"saved={out_base.with_suffix('.json')} skipped=true "
                f"num_timesteps_total={resume_current_timesteps}"
            )
            return

        callbacks = []
        checkpoint_dir = Path(args.checkpoint_dir) if str(args.checkpoint_dir).strip() else out_base.parent / "checkpoints"
        checkpoint_prefix = str(args.checkpoint_prefix).strip() or f"{out_base.name}_ckpt"
        checkpoint_every = int(getattr(args, "checkpoint_every", 0))
        if checkpoint_every > 0:
            checkpoint_dir.mkdir(parents=True, exist_ok=True)
            _assert_min_free_disk(checkpoint_dir, float(getattr(args, "min_free_disk_gb", 2.0)))
            save_freq = max(1, int(checkpoint_every) // max(1, int(args.num_envs)))
            callbacks.append(
                CheckpointCallback(
                    save_freq=save_freq,
                    save_path=str(checkpoint_dir),
                    name_prefix=checkpoint_prefix,
                    save_replay_buffer=False,
                    save_vecnormalize=bool(args.use_vec_normalize_reward),
                    verbose=0,
                )
            )
        heartbeat_every = max(1000, int(getattr(args, "heartbeat_every", 10_000)))
        heartbeat_freq = max(1, int(heartbeat_every) // max(1, int(args.num_envs)))
        callbacks.append(HeartbeatCallback(heartbeat_path, heartbeat_freq, str(args.run_tag), out_base))

        model.learn(
            total_timesteps=int(learn_timesteps),
            progress_bar=False,
            reset_num_timesteps=False,
            callback=callbacks if callbacks else None,
        )
        model.save(str(out_base))
        if args.use_vec_normalize_reward:
            vec_norm_path = out_base.with_suffix(".vecnormalize.pkl")
            vec_env.save(str(vec_norm_path))

        monitor_metrics = _run_policy_monitor(
            args,
            pool_paths,
            action_selector=lambda obs, mask, _env: int(model.predict(obs, deterministic=True, action_masks=mask)[0]),
        )
        monitor_gate = _evaluate_monitor_gates(monitor_metrics, _monitor_thresholds_from_args(args))
        if bool(getattr(args, "enforce_monitor_gates", True)) and monitor_gate["status"] != "PASS":
            raise RuntimeError(f"training monitor gates failed: {monitor_gate['checks']}")

        meta = {
            "backend": "sb3_maskableppo",
            "timesteps": int(args.timesteps),
            "learn_timesteps": int(learn_timesteps),
            "num_timesteps_total": int(getattr(model, "num_timesteps", 0)),
            "target_total_timesteps": int(getattr(args, "target_total_timesteps", 0)),
            "target_reached": bool(
                int(getattr(args, "target_total_timesteps", 0)) > 0
                and int(getattr(model, "num_timesteps", 0)) >= int(getattr(args, "target_total_timesteps", 0))
            ),
            "num_envs": int(args.num_envs),
            "seed": int(args.seed),
            "vec_backend": args.vec_backend,
            "reward_mode": args.reward_mode,
            "use_vec_normalize_reward": bool(args.use_vec_normalize_reward),
            "checkpoint_every": int(checkpoint_every),
            "checkpoint_dir": str(checkpoint_dir),
            "checkpoint_prefix": checkpoint_prefix,
            "use_opponent_pool": bool(args.use_opponent_pool),
            "pool_size": len(pool_paths),
            "opponent_mix": args.opponent_mix,
            "policy": args.policy,
            "run_tag": args.run_tag,
            "enable_wealth_god": bool(not args.disable_wealth_god),
            "protect_wealth_god_discard": bool(not args.allow_discard_wealth_god),
            "enable_qiaoxiang": bool(args.enable_qiaoxiang),
            "resumed": bool(resumed),
            "resume_source": str(resume_source) if resume_source is not None else "",
            "resume_current_timesteps": int(resume_current_timesteps),
            "resume_vecnormalize_path": str(resume_vec_path) if resume_vec_path is not None else "",
            "monitor_gate": monitor_gate,
        }
        out_base.with_suffix(".json").write_text(json.dumps(meta, ensure_ascii=True, indent=2), encoding="utf-8")
        _write_json_atomic(
            heartbeat_path,
            {
                "status": "done",
                "updated_at_unix": time.time(),
                "num_timesteps_total": int(meta["num_timesteps_total"]),
                "target_total_timesteps": int(meta["target_total_timesteps"]),
                "target_reached": bool(meta["target_reached"]),
                "run_tag": str(args.run_tag),
                "out": str(out_base),
            },
        )
        print(f"saved={out_base}.zip meta={out_base.with_suffix('.json')}")
    except KeyboardInterrupt:
        try:
            if "model" in locals():
                interrupt_base = out_base.with_name(out_base.name + "_interrupt")
                model.save(str(interrupt_base))
                if args.use_vec_normalize_reward and vec_env is not None:
                    try:
                        vec_env.save(str(interrupt_base.with_suffix(".vecnormalize.pkl")))
                    except Exception:
                        pass
                _write_json_atomic(
                    heartbeat_path,
                    {
                        "status": "interrupted",
                        "updated_at_unix": time.time(),
                        "num_timesteps_total": int(getattr(model, "num_timesteps", 0)),
                        "target_total_timesteps": int(getattr(args, "target_total_timesteps", 0)),
                        "run_tag": str(args.run_tag),
                        "out": str(out_base),
                        "interrupt_model": str(interrupt_base.with_suffix(".zip")),
                    },
                )
        finally:
            raise
    except Exception as exc:
        _write_json_atomic(
            heartbeat_path,
            {
                "status": "error",
                "updated_at_unix": time.time(),
                "error": str(exc),
                "run_tag": str(args.run_tag),
                "out": str(out_base),
            },
        )
        if args.allow_fallback:
            _fallback_train(args, exc)
            return
        raise
    finally:
        try:
            if vec_env is not None:
                vec_env.close()
        except Exception:
            pass


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timesteps", type=int, default=50_000)
    parser.add_argument("--num-envs", type=int, default=4)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--vec_backend", type=str, default="dummy", choices=["dummy", "subproc"])
    parser.add_argument("--reward_mode", type=str, default="log1p", choices=["log1p", "raw"])
    parser.add_argument("--out", type=str, required=True)
    parser.add_argument("--bot_epsilon", type=float, default=0.08)
    parser.add_argument("--policy", type=str, default="MlpPolicy")
    parser.add_argument("--run_tag", type=str, default="")
    parser.add_argument("--resume_from", type=str, default="")
    parser.add_argument("--resume_vecnormalize", type=str, default="")
    parser.add_argument("--resume_latest_checkpoint", action="store_true")
    parser.add_argument("--target_total_timesteps", type=int, default=0)
    parser.add_argument("--checkpoint_every", type=int, default=0)
    parser.add_argument("--checkpoint_dir", type=str, default="models/checkpoints")
    parser.add_argument("--checkpoint_prefix", type=str, default="")
    parser.add_argument("--heartbeat_every", type=int, default=10_000)
    parser.add_argument("--heartbeat_path", type=str, default="")
    parser.add_argument("--min_free_disk_gb", type=float, default=2.0)
    parser.add_argument("--disable_wealth_god", action="store_true")
    parser.add_argument("--allow_discard_wealth_god", action="store_true")
    parser.add_argument("--enable_qiaoxiang", action="store_true")
    parser.add_argument("--allow_fallback", action="store_true")
    parser.add_argument("--use_opponent_pool", action="store_true")
    parser.add_argument("--pool_dir", type=str, default="models/pool")
    parser.add_argument("--opponent_replace_count", type=int, default=1)
    parser.add_argument("--opponent_mix", type=str, default="rule:1.0")
    parser.add_argument("--use_vec_normalize_reward", action="store_true")
    parser.add_argument("--monitor_episodes", type=int, default=12)
    parser.add_argument("--gate_min_myturn_ratio", type=float, default=0.0)
    parser.add_argument("--gate_min_reaction_ratio", type=float, default=0.0)
    parser.add_argument("--gate_max_reaction_pass_rate", type=float, default=1.0)
    parser.add_argument("--gate_max_illegal_action_rate", type=float, default=0.0)
    parser.add_argument("--gate_max_truncation_rate", type=float, default=0.05)
    parser.add_argument("--enforce_monitor_gates", dest="enforce_monitor_gates", action="store_true")
    parser.add_argument("--no_enforce_monitor_gates", dest="enforce_monitor_gates", action="store_false")
    parser.set_defaults(enforce_monitor_gates=True)
    args = parser.parse_args()
    _ppo_train(args)


if __name__ == "__main__":
    main()
