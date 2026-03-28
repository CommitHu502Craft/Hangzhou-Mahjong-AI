from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


ROOT = Path(__file__).resolve().parents[1]


@dataclass
class AttemptRecord:
    index: int
    started_at: str
    ended_at: str
    exit_code: int
    reason: str
    num_timesteps_total: int
    progress_delta: int
    heartbeat_age_seconds: float


def _read_json(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _read_model_timesteps(model_base: Path) -> int:
    meta = _read_json(model_base.with_suffix(".json"))
    if not isinstance(meta, dict):
        return 0
    try:
        return int(meta.get("num_timesteps_total", meta.get("timesteps", 0)))
    except Exception:
        return 0


def _extract_steps_from_checkpoint_name(path: Path) -> int:
    name = path.name
    if not name.endswith("_steps.zip"):
        return -1
    parts = name.split("_")
    if len(parts) < 3:
        return -1
    try:
        return int(parts[-2])
    except Exception:
        return -1


def _latest_checkpoint_steps(checkpoint_dir: Path, checkpoint_prefix: str) -> int:
    if not checkpoint_dir.exists():
        return 0
    best = 0
    for p in checkpoint_dir.glob(f"{checkpoint_prefix}_*_steps.zip"):
        if not p.is_file():
            continue
        steps = _extract_steps_from_checkpoint_name(p)
        if steps > best:
            best = steps
    return best


def _read_total_steps(model_base: Path, checkpoint_dir: Path, checkpoint_prefix: str) -> int:
    meta_steps = _read_model_timesteps(model_base)
    ckpt_steps = _latest_checkpoint_steps(checkpoint_dir, checkpoint_prefix)
    return max(int(meta_steps), int(ckpt_steps))


def _heartbeat_age_seconds(heartbeat_path: Path) -> Optional[float]:
    payload = _read_json(heartbeat_path)
    if not isinstance(payload, dict):
        return None
    ts = payload.get("updated_at_unix", None)
    if ts is None:
        return None
    try:
        return max(0.0, time.time() - float(ts))
    except Exception:
        return None


def _heartbeat_snapshot(heartbeat_path: Path) -> Dict[str, object]:
    payload = _read_json(heartbeat_path)
    if not isinstance(payload, dict):
        return {"available": False}
    status = str(payload.get("status", ""))
    steps = 0
    target = 0
    try:
        steps = int(payload.get("num_timesteps", payload.get("num_timesteps_total", 0)))
    except Exception:
        steps = 0
    try:
        target = int(payload.get("target_total_timesteps", 0))
    except Exception:
        target = 0
    return {
        "available": True,
        "status": status,
        "steps": int(steps),
        "target": int(target),
        "elapsed_seconds": payload.get("elapsed_seconds"),
    }


def _terminate_process_tree(proc: subprocess.Popen, timeout_seconds: float = 30.0) -> None:
    if proc.poll() is not None:
        return

    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except Exception:
            proc.terminate()
    else:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except Exception:
            proc.terminate()

    try:
        proc.wait(timeout=timeout_seconds)
        return
    except subprocess.TimeoutExpired:
        pass

    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except Exception:
            proc.kill()
    else:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:
            proc.kill()

    proc.wait(timeout=timeout_seconds)


def _run_attempt(
    cmd: List[str],
    *,
    stale_timeout_seconds: float,
    heartbeat_path: Path,
    poll_seconds: float,
    model_base: Path,
    checkpoint_dir: Path,
    checkpoint_prefix: str,
    target_total_timesteps: int,
    attempt_index: int,
) -> tuple[int, str, float]:
    popen_kwargs: Dict[str, object] = {"cwd": str(ROOT)}
    if os.name == "nt":
        create_new_group = int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        if create_new_group:
            popen_kwargs["creationflags"] = create_new_group
    else:
        popen_kwargs["start_new_session"] = True
    proc = subprocess.Popen(cmd, **popen_kwargs)
    reason = "process_exit"
    start_ts = time.time()
    last_age_for_report = -1.0
    last_print_steps = -1
    last_print_status = ""
    while proc.poll() is None:
        time.sleep(max(1.0, poll_seconds))
        age = _heartbeat_age_seconds(heartbeat_path)
        hb = _heartbeat_snapshot(heartbeat_path)
        total_steps = _read_total_steps(model_base, checkpoint_dir, checkpoint_prefix)
        hb_steps = int(hb.get("steps", 0)) if bool(hb.get("available", False)) else 0
        shown_steps = max(int(total_steps), int(hb_steps))
        hb_status = str(hb.get("status", "")) if bool(hb.get("available", False)) else "booting"
        if shown_steps != last_print_steps or hb_status != last_print_status:
            if int(target_total_timesteps) > 0:
                pct = 100.0 * float(shown_steps) / float(target_total_timesteps)
                pct_text = f"{pct:.1f}%"
                target_text = str(int(target_total_timesteps))
            else:
                pct_text = "-"
                target_text = "-"
            age_text = f"{age:.0f}s" if age is not None else "missing"
            print(
                f"[WATCH a{attempt_index}] status={hb_status or '-'} "
                f"steps={shown_steps}/{target_text} ({pct_text}) hb_age={age_text}",
                flush=True,
            )
            last_print_steps = shown_steps
            last_print_status = hb_status
        if age is None:
            if (time.time() - start_ts) <= stale_timeout_seconds:
                continue
            reason = "heartbeat_missing_timeout"
            print(f"[WATCH a{attempt_index}] heartbeat missing timeout, terminating attempt", flush=True)
            _terminate_process_tree(proc)
            break
        last_age_for_report = float(age)
        if age > stale_timeout_seconds:
            reason = "heartbeat_stale_timeout"
            print(
                f"[WATCH a{attempt_index}] heartbeat stale ({age:.0f}s > {stale_timeout_seconds:.0f}s), terminating attempt",
                flush=True,
            )
            _terminate_process_tree(proc)
            break
    exit_code = int(proc.returncode if proc.returncode is not None else 1)
    age = _heartbeat_age_seconds(heartbeat_path)
    if age is not None:
        last_age_for_report = float(age)
    return exit_code, reason, float(last_age_for_report)


def _build_train_cmd(args: argparse.Namespace) -> List[str]:
    cmd = [
        "uv",
        "run",
        "python",
        "-u",
        "rl/train_ppo.py",
        "--timesteps",
        str(args.chunk_timesteps),
        "--target_total_timesteps",
        str(args.target_total_timesteps),
        "--num-envs",
        str(args.num_envs),
        "--seed",
        str(args.seed),
        "--vec_backend",
        str(args.vec_backend),
        "--reward_mode",
        str(args.reward_mode),
        "--bot_epsilon",
        str(args.bot_epsilon),
        "--opponent_mix",
        str(args.opponent_mix),
        "--enable_qiaoxiang",
        "--monitor_episodes",
        str(args.monitor_episodes),
        "--checkpoint_every",
        str(args.checkpoint_every),
        "--checkpoint_dir",
        str(args.checkpoint_dir),
        "--checkpoint_prefix",
        str(args.checkpoint_prefix),
        "--resume_latest_checkpoint",
        "--heartbeat_every",
        str(args.heartbeat_every),
        "--heartbeat_path",
        str(args.heartbeat_path),
        "--min_free_disk_gb",
        str(args.min_free_disk_gb),
        "--out",
        str(args.out),
        "--run_tag",
        str(args.run_tag),
    ]
    if args.use_opponent_pool:
        cmd.extend(
            [
                "--use_opponent_pool",
                "--pool_dir",
                str(args.pool_dir),
                "--opponent_replace_count",
                str(args.opponent_replace_count),
            ]
        )
    if args.use_vec_normalize_reward:
        cmd.append("--use_vec_normalize_reward")
    if args.allow_fallback:
        cmd.append("--allow_fallback")
    return cmd


def _validate_args(args: argparse.Namespace) -> None:
    if int(args.target_total_timesteps) <= 0:
        raise ValueError("target_total_timesteps must be > 0")
    if int(args.chunk_timesteps) <= 0:
        raise ValueError("chunk_timesteps must be > 0")
    if int(args.max_attempts) < 1:
        raise ValueError("max_attempts must be >= 1")
    if int(args.max_no_progress_attempts) < 1:
        raise ValueError("max_no_progress_attempts must be >= 1")
    if float(args.stale_timeout_minutes) <= 0:
        raise ValueError("stale_timeout_minutes must be > 0")
    if float(args.poll_seconds) <= 0:
        raise ValueError("poll_seconds must be > 0")
    if int(args.checkpoint_every) <= 0:
        raise ValueError("checkpoint_every must be > 0")
    if int(args.heartbeat_every) <= 0:
        raise ValueError("heartbeat_every must be > 0")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run_id", type=str, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--report_out", type=Path, required=True)
    parser.add_argument("--chunk_timesteps", type=int, default=200_000)
    parser.add_argument("--target_total_timesteps", type=int, default=2_000_000)
    parser.add_argument("--num_envs", type=int, default=8)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--vec_backend", type=str, default="subproc", choices=["dummy", "subproc"])
    parser.add_argument("--reward_mode", type=str, default="log1p", choices=["log1p", "raw"])
    parser.add_argument("--bot_epsilon", type=float, default=0.08)
    parser.add_argument("--opponent_mix", type=str, default="rule:1.0")
    parser.add_argument("--monitor_episodes", type=int, default=24)
    parser.add_argument("--checkpoint_every", type=int, default=50_000)
    parser.add_argument("--checkpoint_dir", type=Path, default=Path("models/checkpoints"))
    parser.add_argument("--checkpoint_prefix", type=str, default="")
    parser.add_argument("--heartbeat_every", type=int, default=10_000)
    parser.add_argument("--heartbeat_path", type=Path, default=Path(""))
    parser.add_argument("--stale_timeout_minutes", type=float, default=20.0)
    parser.add_argument("--poll_seconds", type=float, default=20.0)
    parser.add_argument("--max_attempts", type=int, default=100)
    parser.add_argument("--max_no_progress_attempts", type=int, default=5)
    parser.add_argument("--min_free_disk_gb", type=float, default=2.0)
    parser.add_argument("--run_tag", type=str, default="")
    parser.add_argument("--allow_fallback", action="store_true")
    parser.add_argument("--use_opponent_pool", action="store_true")
    parser.add_argument("--pool_dir", type=str, default="models/pool")
    parser.add_argument("--opponent_replace_count", type=int, default=1)
    parser.add_argument("--use_vec_normalize_reward", action="store_true")
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.report_out.parent.mkdir(parents=True, exist_ok=True)
    args.checkpoint_dir.mkdir(parents=True, exist_ok=True)
    if not str(args.checkpoint_prefix).strip():
        args.checkpoint_prefix = f"{args.out.name}_ckpt"
    if not str(args.run_tag).strip():
        args.run_tag = f"guarded:{args.run_id}"
    if not str(args.heartbeat_path).strip():
        args.heartbeat_path = Path("reports") / f"heartbeat_{args.run_id}.json"
    else:
        args.heartbeat_path = Path(args.heartbeat_path)
    try:
        _validate_args(args)
    except ValueError as exc:
        parser.error(str(exc))

    attempts: List[AttemptRecord] = []
    no_progress_attempts = 0
    last_steps = _read_total_steps(args.out, args.checkpoint_dir, args.checkpoint_prefix)
    status = "FAIL"
    fail_reason = ""
    target = int(args.target_total_timesteps)
    for i in range(1, int(args.max_attempts) + 1):
        if last_steps >= target > 0:
            status = "PASS"
            fail_reason = ""
            break
        started = datetime.now().isoformat(timespec="seconds")
        cmd = _build_train_cmd(args)
        print(f"[ATTEMPT {i}] run_id={args.run_id} steps={last_steps}/{target}", flush=True)
        print(" ".join(cmd), flush=True)
        exit_code, reason, hb_age = _run_attempt(
            cmd,
            stale_timeout_seconds=float(args.stale_timeout_minutes) * 60.0,
            heartbeat_path=args.heartbeat_path,
            poll_seconds=float(args.poll_seconds),
            model_base=args.out,
            checkpoint_dir=args.checkpoint_dir,
            checkpoint_prefix=str(args.checkpoint_prefix),
            target_total_timesteps=int(target),
            attempt_index=int(i),
        )
        now_steps = _read_total_steps(args.out, args.checkpoint_dir, args.checkpoint_prefix)
        delta = int(now_steps - last_steps)
        ended = datetime.now().isoformat(timespec="seconds")
        attempts.append(
            AttemptRecord(
                index=i,
                started_at=started,
                ended_at=ended,
                exit_code=int(exit_code),
                reason=reason,
                num_timesteps_total=int(now_steps),
                progress_delta=int(delta),
                heartbeat_age_seconds=float(hb_age),
            )
        )
        if delta <= 0:
            no_progress_attempts += 1
        else:
            no_progress_attempts = 0
        last_steps = now_steps

        if last_steps >= target > 0:
            status = "PASS"
            fail_reason = ""
            break
        if no_progress_attempts >= int(args.max_no_progress_attempts):
            status = "FAIL"
            fail_reason = "no_progress_limit_reached"
            break

    if status != "PASS" and not fail_reason:
        fail_reason = "max_attempts_reached"

    report = {
        "status": status,
        "run_id": args.run_id,
        "out": str(args.out),
        "report_out": str(args.report_out),
        "checkpoint_dir": str(args.checkpoint_dir),
        "checkpoint_prefix": str(args.checkpoint_prefix),
        "heartbeat_path": str(args.heartbeat_path),
        "target_total_timesteps": int(target),
        "num_timesteps_total": int(last_steps),
        "attempts": [asdict(x) for x in attempts],
        "attempt_count": int(len(attempts)),
        "fail_reason": fail_reason,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    args.report_out.write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")
    print(
        f"saved_report={args.report_out} status={status} steps={last_steps}/{target} attempts={len(attempts)}",
        flush=True,
    )
    if status != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
