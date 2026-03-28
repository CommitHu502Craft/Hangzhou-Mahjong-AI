from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = ROOT / "reports"
MODELS_DIR = ROOT / "models"
LOGS_DIR = ROOT / "logs"
STATE_PATH = REPORTS_DIR / "tui_state.json"

RULE_PROFILE = "rules/hz_local_v2026_02_A.yaml"
RULE_PROFILE_ID = "hz_local_v2026_02_A"
SPEC_VERSION = "v1.1"
DEFAULT_OPP_MIX = "rule:1.0"
DEFAULT_LONG_CHUNK = 200_000
DEFAULT_LONG_TARGET = 2_000_000
DEFAULT_HEARTBEAT_EVERY = 10_000
DEFAULT_STALE_TIMEOUT_MIN = 20


def _recommended_num_envs() -> int:
    logical = int(os.cpu_count() or 8)
    # Keep 1-2 threads for OS/UI, avoid full oversubscription by default.
    return max(4, min(16, logical - 2))


@dataclass(frozen=True)
class CmdSpec:
    label: str
    cmd: List[str]


def _clear_screen() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def _wants_help(argv: Sequence[str]) -> bool:
    for arg in argv:
        if arg in {"-h", "--help", "help"}:
            return True
    return False


def _print_cli_help() -> None:
    print("Usage: uv run python tools/sim_train_tui.py")
    print("Interactive CMD-style dashboard for simulation training and evaluation.")
    print("")
    print("Menu includes:")
    print("  1) Quick baseline train")
    print("  2) Single-variable matrix train")
    print("  3) Evaluate latest model on test seed set")
    print("  4) Inspect long-run progress (checkpoint/meta/heartbeat)")
    print("  5) Run pytest gate (uv)")
    print("  6) Start guarded long run")
    print("  7) Resume last guarded long run")
    print("  8) Tail latest log")


def _now_tag() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _safe_read_json(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _fmt_duration(seconds: Optional[float]) -> str:
    if seconds is None:
        return "-"
    total = max(0, int(seconds))
    hours = total // 3600
    minutes = (total % 3600) // 60
    sec = total % 60
    if hours > 0:
        return f"{hours}h{minutes:02d}m"
    if minutes > 0:
        return f"{minutes}m{sec:02d}s"
    return f"{sec}s"


def _fmt_steps_per_sec(value: Optional[float]) -> str:
    if value is None or value <= 0:
        return "-"
    return f"{value:.1f}/s"


def _collect_model_insights(model_base: Optional[Path]) -> Dict[str, object]:
    if model_base is None:
        return {"available": False}
    model_meta = model_base.with_suffix(".json")
    payload = _safe_read_json(model_meta)
    if not isinstance(payload, dict):
        return {"available": False, "model_base": str(model_base)}

    total_steps = _safe_int(payload.get("num_timesteps_total", payload.get("timesteps", 0)))
    target_steps = _safe_int(payload.get("target_total_timesteps", 0))
    ratio = float(total_steps / target_steps) if target_steps > 0 else 0.0
    monitor = payload.get("monitor_gate", {})
    monitor_status = "unknown"
    myturn_ratio = None
    reaction_ratio = None
    illegal_rate = None
    trunc_rate = None
    if isinstance(monitor, dict):
        monitor_status = str(monitor.get("status", "unknown"))
        metrics = monitor.get("metrics", {})
        if isinstance(metrics, dict):
            myturn_ratio = _safe_float(metrics.get("myturn_ratio"), -1.0)
            reaction_ratio = _safe_float(metrics.get("reaction_ratio"), -1.0)
            illegal_rate = _safe_float(metrics.get("illegal_action_rate"), -1.0)
            trunc_rate = _safe_float(metrics.get("truncation_rate"), -1.0)
    try:
        updated_at = datetime.fromtimestamp(model_meta.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        updated_at = "-"
    return {
        "available": True,
        "model_base": str(model_base),
        "total_steps": int(total_steps),
        "target_steps": int(target_steps),
        "progress_ratio": float(ratio),
        "backend": str(payload.get("backend", "unknown")),
        "reward_mode": str(payload.get("reward_mode", "unknown")),
        "num_envs": _safe_int(payload.get("num_envs", 0)),
        "resumed": bool(payload.get("resumed", False)),
        "target_reached": bool(payload.get("target_reached", False)),
        "run_tag": str(payload.get("run_tag", "")),
        "monitor_status": monitor_status,
        "myturn_ratio": float(myturn_ratio) if myturn_ratio is not None else None,
        "reaction_ratio": float(reaction_ratio) if reaction_ratio is not None else None,
        "illegal_rate": float(illegal_rate) if illegal_rate is not None else None,
        "trunc_rate": float(trunc_rate) if trunc_rate is not None else None,
        "meta_path": str(model_meta),
        "updated_at": updated_at,
    }


def _collect_guard_report_summary(report_path: Path) -> Dict[str, object]:
    payload = _safe_read_json(report_path)
    if not isinstance(payload, dict):
        return {"available": False}
    attempts = payload.get("attempts", [])
    if not isinstance(attempts, list):
        attempts = []
    latest = attempts[-1] if attempts else {}
    if not isinstance(latest, dict):
        latest = {}

    total_progress = 0
    total_wall_seconds = 0.0
    for item in attempts:
        if not isinstance(item, dict):
            continue
        total_progress += max(0, _safe_int(item.get("progress_delta", 0)))
        started = str(item.get("started_at", "")).strip()
        ended = str(item.get("ended_at", "")).strip()
        if not started or not ended:
            continue
        try:
            delta = (datetime.fromisoformat(ended) - datetime.fromisoformat(started)).total_seconds()
            if delta > 0:
                total_wall_seconds += float(delta)
        except Exception:
            continue
    speed_sps = float(total_progress / total_wall_seconds) if total_wall_seconds > 0 else 0.0
    return {
        "available": True,
        "path": str(report_path),
        "status": str(payload.get("status", "unknown")),
        "attempt_count": _safe_int(payload.get("attempt_count", len(attempts))),
        "fail_reason": str(payload.get("fail_reason", "")),
        "num_timesteps_total": _safe_int(payload.get("num_timesteps_total", 0)),
        "target_total_timesteps": _safe_int(payload.get("target_total_timesteps", 0)),
        "last_reason": str(latest.get("reason", "-")),
        "last_exit_code": _safe_int(latest.get("exit_code", -1)),
        "last_progress_delta": _safe_int(latest.get("progress_delta", 0)),
        "total_progress": int(total_progress),
        "total_wall_seconds": float(total_wall_seconds),
        "speed_sps": float(speed_sps),
    }


def _collect_log_insights(log_path: Optional[str]) -> Dict[str, object]:
    if not log_path:
        return {"available": False}
    p = Path(log_path)
    if not p.exists():
        return {"available": False, "path": str(p)}
    try:
        stat = p.stat()
        size_kb = float(stat.st_size / 1024.0)
        updated_at = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        return {
            "available": True,
            "path": str(p),
            "size_kb": float(size_kb),
            "updated_at": updated_at,
        }
    except Exception:
        return {"available": False, "path": str(p)}


def _collect_runtime_insights() -> Dict[str, object]:
    try:
        _total, _used, free = shutil.disk_usage(str(ROOT))
        free_gb = float(free / (1024**3))
    except Exception:
        free_gb = -1.0
    return {"free_disk_gb": float(free_gb)}


def _load_state() -> Dict[str, object]:
    payload = _safe_read_json(STATE_PATH)
    if isinstance(payload, dict):
        return payload
    return {}


def _latest_file(paths: Iterable[Path]) -> Optional[Path]:
    existing = [p for p in paths if p.exists()]
    if not existing:
        return None
    return max(existing, key=lambda p: p.stat().st_mtime)


def _latest_glob(folder: Path, pattern: str) -> Optional[Path]:
    return _latest_file(folder.glob(pattern))


def _normalize_model_base(model_path: Path) -> Path:
    if model_path.suffix == ".zip":
        return model_path.with_suffix("")
    if model_path.suffix == ".json":
        return model_path.with_suffix("")
    return model_path


def _collect_latest_model() -> Optional[Path]:
    candidates: List[Path] = []
    for p in MODELS_DIR.glob("*.zip"):
        if p.name.startswith("ppo_"):
            candidates.append(p)
    latest = _latest_file(candidates)
    if latest is None:
        return None
    return _normalize_model_base(latest)


def _extract_steps_from_checkpoint(path: Path) -> int:
    match = re.search(r"_(\d+)_steps\.zip$", path.name)
    if not match:
        return -1
    try:
        return int(match.group(1))
    except ValueError:
        return -1


def _latest_checkpoint(checkpoint_dir: Path, checkpoint_prefix: str) -> Optional[Path]:
    if not checkpoint_dir.exists():
        return None
    candidates = [
        p
        for p in checkpoint_dir.glob(f"{checkpoint_prefix}_*_steps.zip")
        if p.is_file() and _extract_steps_from_checkpoint(p) >= 0
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: (_extract_steps_from_checkpoint(p), p.stat().st_mtime))


def _read_total_timesteps_from_meta(model_base: Path) -> int:
    meta = _safe_read_json(model_base.with_suffix(".json"))
    if not isinstance(meta, dict):
        return 0
    try:
        return int(meta.get("num_timesteps_total", meta.get("timesteps", 0)))
    except Exception:
        return 0


def _collect_long_progress(state: Dict[str, object]) -> Dict[str, object]:
    long_run = state.get("long_run", {})
    if not isinstance(long_run, dict):
        return {"available": False}
    out = str(long_run.get("out", "")).strip()
    if not out:
        return {"available": False}

    model_base = Path(out)
    checkpoint_dir = Path(str(long_run.get("checkpoint_dir", "models/checkpoints")))
    checkpoint_prefix = str(long_run.get("checkpoint_prefix", f"{model_base.name}_ckpt"))
    heartbeat_path = Path(str(long_run.get("heartbeat_path", f"reports/heartbeat_{long_run.get('run_id', 'long')}.json")))
    latest_ckpt = _latest_checkpoint(checkpoint_dir, checkpoint_prefix)
    ckpt_steps = _extract_steps_from_checkpoint(latest_ckpt) if latest_ckpt else -1
    meta_steps = _read_total_timesteps_from_meta(model_base)
    current_steps = max(meta_steps, ckpt_steps if ckpt_steps > 0 else 0)
    target_steps = int(long_run.get("target_total_timesteps", 0) or 0)
    progress_ratio = float(current_steps / target_steps) if target_steps > 0 else 0.0
    hb_payload = _safe_read_json(heartbeat_path)
    hb_age = None
    hb_status = ""
    hb_elapsed_seconds = None
    hb_num_timesteps = 0
    hb_target_timesteps = 0
    if isinstance(hb_payload, dict):
        hb_status = str(hb_payload.get("status", ""))
        ts = hb_payload.get("updated_at_unix")
        hb_elapsed_seconds = _safe_float(hb_payload.get("elapsed_seconds"), -1.0)
        if hb_elapsed_seconds < 0:
            hb_elapsed_seconds = None
        hb_num_timesteps = _safe_int(hb_payload.get("num_timesteps", hb_payload.get("num_timesteps_total", 0)))
        hb_target_timesteps = _safe_int(hb_payload.get("target_total_timesteps", 0))
        try:
            hb_age = max(0.0, time.time() - float(ts)) if ts is not None else None
        except Exception:
            hb_age = None
    speed_sps = None
    if hb_elapsed_seconds is not None and hb_elapsed_seconds > 0 and hb_num_timesteps > 0:
        speed_sps = float(hb_num_timesteps / hb_elapsed_seconds)
    eta_seconds = None
    if target_steps > current_steps and speed_sps is not None and speed_sps > 0:
        eta_seconds = float((target_steps - current_steps) / speed_sps)

    guard_summary = {"available": False}
    guard_report_out = str(long_run.get("guard_report_out", "")).strip()
    if guard_report_out:
        guard_summary = _collect_guard_report_summary(Path(guard_report_out))

    return {
        "available": True,
        "run_id": str(long_run.get("run_id", "")),
        "model_base": str(model_base),
        "checkpoint_dir": str(checkpoint_dir),
        "checkpoint_prefix": checkpoint_prefix,
        "latest_checkpoint": str(latest_ckpt) if latest_ckpt else "",
        "meta_steps": int(meta_steps),
        "checkpoint_steps": int(max(0, ckpt_steps)),
        "current_steps": int(current_steps),
        "target_steps": int(target_steps),
        "progress_ratio": float(progress_ratio),
        "chunk_timesteps": int(long_run.get("chunk_timesteps", DEFAULT_LONG_CHUNK) or DEFAULT_LONG_CHUNK),
        "heartbeat_path": str(heartbeat_path),
        "heartbeat_status": hb_status,
        "heartbeat_age_seconds": hb_age,
        "heartbeat_elapsed_seconds": hb_elapsed_seconds,
        "heartbeat_num_timesteps": int(hb_num_timesteps),
        "heartbeat_target_timesteps": int(hb_target_timesteps),
        "speed_sps": speed_sps,
        "eta_seconds": eta_seconds,
        "guard_report_out": str(long_run.get("guard_report_out", "")),
        "guard_summary": guard_summary,
        "stale_timeout_minutes": float(long_run.get("stale_timeout_minutes", DEFAULT_STALE_TIMEOUT_MIN)),
    }


def _collect_dashboard() -> Dict[str, object]:
    state = _load_state()
    latest_model = _collect_latest_model()
    latest_readiness = _latest_glob(REPORTS_DIR, "readiness_levels_*_sim_only*.json")
    latest_matrix = _latest_glob(REPORTS_DIR, "matrix_*_*.json")
    latest_human = _latest_glob(REPORTS_DIR, "human_readiness_*_test.json")
    latest_model_ready = _latest_glob(REPORTS_DIR, "readiness_*_test.json")

    out: Dict[str, object] = {
        "state": state,
        "latest_model": str(latest_model) if latest_model else "",
        "latest_readiness_levels": str(latest_readiness) if latest_readiness else "",
        "latest_matrix": str(latest_matrix) if latest_matrix else "",
        "latest_human_readiness": str(latest_human) if latest_human else "",
        "latest_model_readiness": str(latest_model_ready) if latest_model_ready else "",
    }
    out["runtime"] = _collect_runtime_insights()
    out["model_insights"] = _collect_model_insights(latest_model)
    out["log_insights"] = _collect_log_insights(str(state.get("log", "")).strip() if isinstance(state, dict) else "")
    if latest_readiness:
        payload = _safe_read_json(latest_readiness)
        if isinstance(payload, dict):
            out["latest_readiness_level"] = payload.get("highest_level", "unknown")
            out["latest_readiness_status"] = payload.get("status", "unknown")
    if latest_matrix:
        payload = _safe_read_json(latest_matrix)
        if isinstance(payload, dict):
            exps = payload.get("experiments", [])
            if isinstance(exps, list) and exps:
                top = sorted(
                    exps,
                    key=lambda x: float(x.get("summary", {}).get("mean_diff", -1e9)),
                    reverse=True,
                )[0]
                out["matrix_top"] = {
                    "id": str(top.get("experiment", {}).get("id", "unknown")),
                    "mean_diff": float(top.get("summary", {}).get("mean_diff", 0.0)),
                    "readiness": str(top.get("summary", {}).get("readiness_status", "unknown")),
                }
    long_prog = _collect_long_progress(state)
    if long_prog.get("available"):
        out["long_progress"] = long_prog
    return out


def _print_dashboard() -> None:
    dash = _collect_dashboard()
    logical = int(os.cpu_count() or 0)
    print("=" * 72)
    print(" Hangzhou Mahjong AI | Simulation TUI (CMD)")
    print("=" * 72)
    print(f" Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    runtime = dash.get("runtime", {})
    free_disk_gb = _safe_float(runtime.get("free_disk_gb"), -1.0) if isinstance(runtime, dict) else -1.0
    free_disk_text = f"{free_disk_gb:.1f}GB" if free_disk_gb >= 0 else "-"
    print(
        f" CPU Threads(logical): {logical} | Recommended num_envs: {_recommended_num_envs()} | "
        f"FreeDisk: {free_disk_text}"
    )
    print(f" Latest Model: {dash.get('latest_model') or '-'}")
    model_insights = dash.get("model_insights", {})
    if isinstance(model_insights, dict) and model_insights.get("available"):
        total_steps = _safe_int(model_insights.get("total_steps", 0))
        target_steps = _safe_int(model_insights.get("target_steps", 0))
        ratio = _safe_float(model_insights.get("progress_ratio", 0.0))
        target_text = str(target_steps) if target_steps > 0 else "-"
        ratio_text = f"{ratio * 100:.1f}%" if target_steps > 0 else "-"
        monitor_status = str(model_insights.get("monitor_status", "unknown"))
        myturn_ratio = _safe_float(model_insights.get("myturn_ratio"), -1.0)
        reaction_ratio = _safe_float(model_insights.get("reaction_ratio"), -1.0)
        illegal_rate = _safe_float(model_insights.get("illegal_rate"), -1.0)
        trunc_rate = _safe_float(model_insights.get("trunc_rate"), -1.0)
        myturn_text = f"{myturn_ratio * 100:.1f}%" if myturn_ratio >= 0 else "-"
        reaction_text = f"{reaction_ratio * 100:.1f}%" if reaction_ratio >= 0 else "-"
        illegal_text = f"{illegal_rate * 100:.2f}%" if illegal_rate >= 0 else "-"
        trunc_text = f"{trunc_rate * 100:.2f}%" if trunc_rate >= 0 else "-"
        print(
            " Model Meta: "
            f"backend={model_insights.get('backend', '-')} | reward={model_insights.get('reward_mode', '-')} | "
            f"envs={model_insights.get('num_envs', '-')} | resumed={model_insights.get('resumed', False)}"
        )
        print(
            " Model Step: "
            f"{total_steps}/{target_text} ({ratio_text}) | monitor={monitor_status} | "
            f"updated={model_insights.get('updated_at', '-')}"
        )
        print(
            " Model Gate: "
            f"myturn={myturn_text} | reaction={reaction_text} | illegal={illegal_text} | trunc={trunc_text}"
        )
    print(f" Latest Lvl Report: {dash.get('latest_readiness_levels') or '-'}")
    print(
        " Latest Lvl: "
        f"{dash.get('latest_readiness_level', '-')} "
        f"({dash.get('latest_readiness_status', '-')})"
    )
    print(f" Latest Matrix: {dash.get('latest_matrix') or '-'}")
    top = dash.get("matrix_top")
    if isinstance(top, dict):
        print(
            " Matrix Top: "
            f"{top.get('id')} | mean_diff={float(top.get('mean_diff', 0.0)):.4f} | "
            f"readiness={top.get('readiness')}"
        )
    print(f" Latest L1 Report: {dash.get('latest_model_readiness') or '-'}")
    print(f" Latest L2 Report: {dash.get('latest_human_readiness') or '-'}")
    state = dash.get("state", {})
    if isinstance(state, dict) and state:
        print(
            " Last Action: "
            f"{state.get('last_action', '-')} | exit={state.get('last_exit', '-')} | "
            f"run_id={state.get('last_run_id', '-')}"
        )
    log_insights = dash.get("log_insights", {})
    if isinstance(log_insights, dict) and log_insights.get("available"):
        print(
            " Last Log: "
            f"{log_insights.get('path', '-')} | size={_safe_float(log_insights.get('size_kb'), 0.0):.1f}KB | "
            f"updated={log_insights.get('updated_at', '-')}"
        )
    long_prog = dash.get("long_progress")
    if isinstance(long_prog, dict) and long_prog.get("available"):
        target = int(long_prog.get("target_steps", 0))
        current = int(long_prog.get("current_steps", 0))
        ratio = float(long_prog.get("progress_ratio", 0.0))
        latest_ckpt = str(long_prog.get("latest_checkpoint", "")) or "-"
        hb_status = str(long_prog.get("heartbeat_status", "")) or "-"
        hb_age = long_prog.get("heartbeat_age_seconds", None)
        hb_text = f"{float(hb_age):.0f}s" if hb_age is not None else "-"
        stale_timeout_sec = float(long_prog.get("stale_timeout_minutes", DEFAULT_STALE_TIMEOUT_MIN)) * 60.0
        stale_tag = " STALE!" if (hb_age is not None and float(hb_age) > stale_timeout_sec) else ""
        print(
            " LongRun: "
            f"{long_prog.get('run_id', '-')} | {current}/{target} "
            f"({ratio * 100:.1f}%) | ckpt={latest_ckpt} | hb={hb_status}/{hb_text}{stale_tag}"
        )
        print(
            " LongRun Detail: "
            f"elapsed={_fmt_duration(long_prog.get('heartbeat_elapsed_seconds'))} | "
            f"speed={_fmt_steps_per_sec(_safe_float(long_prog.get('speed_sps'), 0.0))} | "
            f"eta={_fmt_duration(long_prog.get('eta_seconds'))}"
        )
        guard_summary = long_prog.get("guard_summary", {})
        if isinstance(guard_summary, dict) and guard_summary.get("available"):
            print(
                " Guard: "
                f"status={guard_summary.get('status', '-')} | attempts={guard_summary.get('attempt_count', '-')} | "
                f"last_reason={guard_summary.get('last_reason', '-')} | "
                f"last_delta={guard_summary.get('last_progress_delta', 0)}"
            )
    print("-" * 72)
    print(" 1) 短训（Quick Baseline）")
    print(" 2) 短训矩阵（Baseline + OpponentMix）")
    print(" 3) 评测最新模型（test + sim-only readiness）")
    print(" 4) 查看长训进度（checkpoint/meta）")
    print(" 5) 跑测试门禁（uv pytest）")
    print(" 6) 启动长训（可断点，创建/覆盖长训配置）")
    print(" 7) 继续上次长训（自动从最新checkpoint续训）")
    print(" 8) 查看最近日志（tail）")
    print(" 0) 退出")
    print("-" * 72)


def _save_state(last_action: str, last_run_id: str, last_exit: int, extra: Optional[Dict[str, object]] = None) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    payload: Dict[str, object] = dict(_load_state())
    payload.update(
        {
        "last_action": last_action,
        "last_run_id": last_run_id,
        "last_exit": int(last_exit),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    })
    if extra:
        payload.update(extra)
    STATE_PATH.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")


def _run_cmd(spec: CmdSpec, log_path: Path) -> int:
    print(f"[RUN] {spec.label}")
    print("      " + " ".join(spec.cmd))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as logf:
        logf.write(f"\n=== {datetime.now().isoformat(timespec='seconds')} | {spec.label} ===\n")
        logf.write("CMD: " + " ".join(spec.cmd) + "\n")
        proc = subprocess.Popen(
            spec.cmd,
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            print(line, end="")
            logf.write(line)
        proc.wait()
        logf.write(f"EXIT: {proc.returncode}\n")
        return int(proc.returncode)


def _run_pipeline(action_name: str, run_id: str, commands: Sequence[CmdSpec]) -> int:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / f"tui_{action_name}_{run_id}.log"
    print(f"\n[INFO] run_id={run_id}")
    print(f"[INFO] log={log_path}\n")
    for spec in commands:
        rc = _run_cmd(spec, log_path)
        if rc != 0:
            print(f"\n[FAIL] {spec.label} exit={rc}")
            _save_state(action_name, run_id, rc, {"log": str(log_path)})
            return rc
        print(f"[OK] {spec.label}\n")
    _save_state(action_name, run_id, 0, {"log": str(log_path)})
    print("[DONE] pipeline completed.\n")
    return 0


def _quick_train_commands(run_id: str) -> List[CmdSpec]:
    data_path = f"datasets/artifacts/train_data_tui_{run_id}.npz"
    bc_path = f"models/bc_tui_{run_id}.pt"
    model_base = f"models/ppo_tui_{run_id}"
    dup_model = f"reports/dup_tui_{run_id}_model_dev.json"
    dup_rule = f"reports/dup_tui_{run_id}_rule_dev.json"
    read_l1 = f"reports/readiness_tui_{run_id}_dev.json"

    return [
        CmdSpec(
            "Generate Data",
            [
                "uv",
                "run",
                "python",
                "datasets/gen_data.py",
                "--episodes",
                "200",
                "--max_episodes",
                "300",
                "--target_decisions",
                "4000",
                "--min_samples",
                "1200",
                "--seed_start",
                "7001",
                "--epsilon",
                "0.08",
                "--out",
                data_path,
                "--enable_qiaoxiang",
                "--enforce_distribution_gates",
                "--gate_min_myturn_ratio",
                "0.05",
                "--gate_min_reaction_ratio",
                "0.05",
                "--gate_max_action_share",
                "0.98",
                "--gate_min_avg_legal_actions",
                "1.1",
                "--gate_max_truncated_rate",
                "0.08",
            ],
        ),
        CmdSpec(
            "BC Train",
            [
                "uv",
                "run",
                "python",
                "datasets/bc_train.py",
                "--data",
                data_path,
                "--epochs",
                "2",
                "--batch_size",
                "256",
                "--lr",
                "0.001",
                "--out",
                bc_path,
            ],
        ),
        CmdSpec(
            "PPO Train",
            [
                "uv",
                "run",
                "python",
                "rl/train_ppo.py",
                "--timesteps",
                "50000",
                "--num-envs",
                "8",
                "--seed",
                "8026",
                "--vec_backend",
                "subproc",
                "--reward_mode",
                "log1p",
                "--bot_epsilon",
                "0.08",
                "--opponent_mix",
                DEFAULT_OPP_MIX,
                "--enable_qiaoxiang",
                "--monitor_episodes",
                "16",
                "--out",
                model_base,
                "--run_tag",
                f"tui-quick:{run_id}",
            ],
        ),
        CmdSpec(
            "Eval Model (dev)",
            [
                "uv",
                "run",
                "python",
                "rl/eval_duplicate.py",
                "--model",
                model_base,
                "--policy_mode",
                "model",
                "--seed_set",
                "dev",
                "--strict_load",
                "--fail_on_fallback",
                "--opponent_epsilon",
                "0.08",
                "--opponent_mix",
                DEFAULT_OPP_MIX,
                "--rule_profile",
                RULE_PROFILE,
                "--rule_profile_id",
                RULE_PROFILE_ID,
                "--spec_version",
                SPEC_VERSION,
                "--seed_set_id",
                "dev",
                "--opponent_suite_id",
                "opp_suite_eps08_rule",
                "--enable_qiaoxiang",
                "--out",
                dup_model,
            ],
        ),
        CmdSpec(
            "Eval Rule (dev)",
            [
                "uv",
                "run",
                "python",
                "rl/eval_duplicate.py",
                "--model",
                "models/unused",
                "--policy_mode",
                "rule",
                "--rulebot_epsilon",
                "0.0",
                "--seed_set",
                "dev",
                "--opponent_epsilon",
                "0.08",
                "--opponent_mix",
                DEFAULT_OPP_MIX,
                "--rule_profile",
                RULE_PROFILE,
                "--rule_profile_id",
                RULE_PROFILE_ID,
                "--spec_version",
                SPEC_VERSION,
                "--seed_set_id",
                "dev",
                "--opponent_suite_id",
                "opp_suite_eps08_rule",
                "--enable_qiaoxiang",
                "--out",
                dup_rule,
            ],
        ),
        CmdSpec(
            "Assess L1 (dev)",
            [
                "uv",
                "run",
                "python",
                "rl/assess_model_readiness.py",
                "--model_report",
                dup_model,
                "--rule_report",
                dup_rule,
                "--expected_rule_profile_id",
                RULE_PROFILE_ID,
                "--expected_spec_version",
                SPEC_VERSION,
                "--expected_seed_set_id",
                "dev",
                "--expected_opponent_suite_id",
                "opp_suite_eps08_rule",
                "--min_games",
                "2000",
                "--min_advantage",
                "2.0",
                "--out",
                read_l1,
            ],
        ),
    ]


def _matrix_train_commands(run_id: str) -> List[CmdSpec]:
    return [
        CmdSpec(
            "Single-Variable Matrix (dev)",
            [
                "uv",
                "run",
                "python",
                "rl/run_single_variable_matrix.py",
                "--matrix_id",
                f"tui_{run_id}",
                "--rule_profile",
                RULE_PROFILE,
                "--rule_profile_id",
                RULE_PROFILE_ID,
                "--spec_version",
                SPEC_VERSION,
                "--seed_set",
                "dev",
                "--seed_set_id",
                "dev",
                "--seed_start",
                "9001",
                "--enable_qiaoxiang",
                "--data_episodes",
                "800",
                "--data_max_episodes",
                "1200",
                "--data_target_decisions",
                "35000",
                "--data_min_samples",
                "9000",
                "--bc_epochs",
                "3",
                "--bc_batch_size",
                "512",
                "--bc_lr",
                "0.001",
                "--ppo_timesteps",
                "300000",
                "--ppo_num_envs",
                "8",
                "--vec_backend",
                "subproc",
                "--bot_epsilon",
                "0.08",
                "--opponent_mix_baseline",
                DEFAULT_OPP_MIX,
                "--use_opponent_pool",
                "--pool_dir",
                "models/pool",
                "--opponent_replace_count",
                "1",
                "--monitor_episodes",
                "24",
                "--eval_opponent_epsilon",
                "0.08",
                "--readiness_min_games",
                "2000",
                "--readiness_min_advantage",
                "2.0",
                "--experiments",
                "baseline",
                "opponent_mix_diverse",
            ],
        ),
    ]


def _test_eval_commands(model_base: Path, run_id: str) -> List[CmdSpec]:
    model_base_str = str(model_base)
    commands: List[CmdSpec] = []
    scenarios: List[Tuple[str, str, str]] = [
        ("eps08", "0.08", "opp_suite_eps08_rule"),
        ("opp0", "0.0", "opp_suite_eps00_rule"),
        ("opp16", "0.16", "opp_suite_eps16_rule"),
    ]
    for name, eps, suite_id in scenarios:
        commands.append(
            CmdSpec(
                f"Eval Model test ({name})",
                [
                    "uv",
                    "run",
                    "python",
                    "rl/eval_duplicate.py",
                    "--model",
                    model_base_str,
                    "--policy_mode",
                    "model",
                    "--seed_set",
                    "test",
                    "--strict_load",
                    "--fail_on_fallback",
                    "--opponent_epsilon",
                    eps,
                    "--opponent_mix",
                    DEFAULT_OPP_MIX,
                    "--rule_profile",
                    RULE_PROFILE,
                    "--rule_profile_id",
                    RULE_PROFILE_ID,
                    "--spec_version",
                    SPEC_VERSION,
                    "--seed_set_id",
                    "test",
                    "--opponent_suite_id",
                    suite_id,
                    "--enable_qiaoxiang",
                    "--out",
                    f"reports/dup_tui_{run_id}_model_{name}_test.json",
                ],
            )
        )
        commands.append(
            CmdSpec(
                f"Eval Rule test ({name})",
                [
                    "uv",
                    "run",
                    "python",
                    "rl/eval_duplicate.py",
                    "--model",
                    "models/unused",
                    "--policy_mode",
                    "rule",
                    "--rulebot_epsilon",
                    "0.0",
                    "--seed_set",
                    "test",
                    "--opponent_epsilon",
                    eps,
                    "--opponent_mix",
                    DEFAULT_OPP_MIX,
                    "--rule_profile",
                    RULE_PROFILE,
                    "--rule_profile_id",
                    RULE_PROFILE_ID,
                    "--spec_version",
                    SPEC_VERSION,
                    "--seed_set_id",
                    "test",
                    "--opponent_suite_id",
                    suite_id,
                    "--enable_qiaoxiang",
                    "--out",
                    f"reports/dup_tui_{run_id}_rule_{name}_test.json",
                ],
            )
        )
    commands.extend(
        [
            CmdSpec(
                "Assess L1 (test)",
                [
                    "uv",
                    "run",
                    "python",
                    "rl/assess_model_readiness.py",
                    "--model_report",
                    f"reports/dup_tui_{run_id}_model_eps08_test.json",
                    "--rule_report",
                    f"reports/dup_tui_{run_id}_rule_eps08_test.json",
                    "--expected_rule_profile_id",
                    RULE_PROFILE_ID,
                    "--expected_spec_version",
                    SPEC_VERSION,
                    "--expected_seed_set_id",
                    "test",
                    "--expected_opponent_suite_id",
                    "opp_suite_eps08_rule",
                    "--min_games",
                    "2000",
                    "--min_advantage",
                    "2.0",
                    "--out",
                    f"reports/readiness_tui_{run_id}_test.json",
                ],
            ),
            CmdSpec(
                "Assess L2 (test suite)",
                [
                    "uv",
                    "run",
                    "python",
                    "rl/assess_human_readiness.py",
                    "--model_reports",
                    f"reports/dup_tui_{run_id}_model_eps08_test.json",
                    f"reports/dup_tui_{run_id}_model_opp0_test.json",
                    f"reports/dup_tui_{run_id}_model_opp16_test.json",
                    "--rule_reports",
                    f"reports/dup_tui_{run_id}_rule_eps08_test.json",
                    f"reports/dup_tui_{run_id}_rule_opp0_test.json",
                    f"reports/dup_tui_{run_id}_rule_opp16_test.json",
                    "--scenario_names",
                    "test_eps08",
                    "test_opp0",
                    "test_opp16",
                    "--min_games",
                    "2000",
                    "--min_advantage",
                    "2.0",
                    "--min_pass_ratio",
                    "1.0",
                    "--expected_rule_profile_id",
                    RULE_PROFILE_ID,
                    "--expected_spec_version",
                    SPEC_VERSION,
                    "--expected_seed_set_id",
                    "test",
                    "--out",
                    f"reports/human_readiness_tui_{run_id}_test.json",
                ],
            ),
            CmdSpec(
                "Assess Sim-Only Levels",
                [
                    "uv",
                    "run",
                    "python",
                    "rl/assess_readiness_levels.py",
                    "--l1_model_report",
                    f"reports/dup_tui_{run_id}_model_eps08_test.json",
                    "--l1_rule_report",
                    f"reports/dup_tui_{run_id}_rule_eps08_test.json",
                    "--l2_suite_report",
                    f"reports/human_readiness_tui_{run_id}_test.json",
                    "--rule_profile",
                    RULE_PROFILE,
                    "--expected_rule_profile_id",
                    RULE_PROFILE_ID,
                    "--expected_spec_version",
                    SPEC_VERSION,
                    "--expected_seed_set_id",
                    "test",
                    "--pytest_passed",
                    "--no_require_real_ab_for_l3",
                    "--out",
                    f"reports/readiness_levels_tui_{run_id}_sim_only_test.json",
                ],
            ),
        ]
    )
    return commands


def _ask_text(prompt: str, default: str) -> str:
    raw = input(f"{prompt} [{default}]: ").strip()
    return raw if raw else default


def _ask_int(prompt: str, default: int) -> int:
    raw = input(f"{prompt} [{default}]: ").strip()
    if not raw:
        return int(default)
    try:
        return int(raw)
    except ValueError:
        print(f"[WARN] invalid int '{raw}', use default={default}")
        return int(default)


def _sanitize_long_run_cfg(cfg: Dict[str, object]) -> Dict[str, object]:
    out = dict(cfg)
    chunk = max(1_000, int(out.get("chunk_timesteps", DEFAULT_LONG_CHUNK) or DEFAULT_LONG_CHUNK))
    target = max(chunk, int(out.get("target_total_timesteps", DEFAULT_LONG_TARGET) or DEFAULT_LONG_TARGET))
    num_envs = max(1, int(out.get("num_envs", _recommended_num_envs()) or _recommended_num_envs()))
    checkpoint_every = max(1_000, int(out.get("checkpoint_every", 50_000) or 50_000))
    heartbeat_every = max(1_000, int(out.get("heartbeat_every", DEFAULT_HEARTBEAT_EVERY) or DEFAULT_HEARTBEAT_EVERY))
    stale_timeout = float(out.get("stale_timeout_minutes", DEFAULT_STALE_TIMEOUT_MIN) or DEFAULT_STALE_TIMEOUT_MIN)
    max_attempts = max(1, int(out.get("max_attempts", 100) or 100))
    max_no_progress = max(1, int(out.get("max_no_progress_attempts", 5) or 5))

    # Keep checkpoint cadence meaningful within each chunk.
    if checkpoint_every > chunk:
        new_val = max(1_000, chunk // 2)
        print(f"[WARN] checkpoint_every={checkpoint_every} > chunk={chunk}, auto-adjust to {new_val}")
        checkpoint_every = new_val
    # Heartbeat should be more frequent than checkpoint to avoid stale false alarms.
    if heartbeat_every >= checkpoint_every:
        new_val = max(1_000, checkpoint_every // 2)
        print(f"[WARN] heartbeat_every={heartbeat_every} >= checkpoint_every={checkpoint_every}, auto-adjust to {new_val}")
        heartbeat_every = new_val
    if stale_timeout <= 1.0:
        print(f"[WARN] stale_timeout_minutes={stale_timeout} too small, auto-adjust to 5.0")
        stale_timeout = 5.0

    out["chunk_timesteps"] = int(chunk)
    out["target_total_timesteps"] = int(target)
    out["num_envs"] = int(num_envs)
    out["checkpoint_every"] = int(checkpoint_every)
    out["heartbeat_every"] = int(heartbeat_every)
    out["stale_timeout_minutes"] = float(stale_timeout)
    out["max_attempts"] = int(max_attempts)
    out["max_no_progress_attempts"] = int(max_no_progress)
    return out


def _build_long_train_command(long_cfg: Dict[str, object], *, resume_mode: bool) -> CmdSpec:
    out = str(long_cfg["out"])
    checkpoint_dir = str(long_cfg["checkpoint_dir"])
    checkpoint_prefix = str(long_cfg["checkpoint_prefix"])
    chunk_timesteps = int(long_cfg["chunk_timesteps"])
    target_total_timesteps = int(long_cfg["target_total_timesteps"])
    num_envs = int(long_cfg["num_envs"])
    seed = int(long_cfg["seed"])
    checkpoint_every = int(long_cfg["checkpoint_every"])
    bot_epsilon = float(long_cfg.get("bot_epsilon", 0.08))
    opponent_mix = str(long_cfg.get("opponent_mix", DEFAULT_OPP_MIX))
    heartbeat_every = int(long_cfg.get("heartbeat_every", DEFAULT_HEARTBEAT_EVERY))
    stale_timeout_minutes = float(long_cfg.get("stale_timeout_minutes", DEFAULT_STALE_TIMEOUT_MIN))
    max_attempts = int(long_cfg.get("max_attempts", 100))
    max_no_progress_attempts = int(long_cfg.get("max_no_progress_attempts", 5))
    heartbeat_path = str(long_cfg.get("heartbeat_path", f"reports/heartbeat_{long_cfg['run_id']}.json"))
    report_out = str(long_cfg.get("guard_report_out", f"reports/guarded_train_{long_cfg['run_id']}.json"))

    cmd = [
        "uv",
        "run",
        "python",
        "tools/guarded_train.py",
        "--run_id",
        str(long_cfg["run_id"]),
        "--out",
        out,
        "--report_out",
        report_out,
        "--chunk_timesteps",
        str(chunk_timesteps),
        "--target_total_timesteps",
        str(target_total_timesteps),
        "--num_envs",
        str(num_envs),
        "--seed",
        str(seed),
        "--vec_backend",
        "subproc",
        "--reward_mode",
        "log1p",
        "--bot_epsilon",
        str(bot_epsilon),
        "--opponent_mix",
        opponent_mix,
        "--monitor_episodes",
        "24",
        "--checkpoint_every",
        str(checkpoint_every),
        "--checkpoint_dir",
        checkpoint_dir,
        "--checkpoint_prefix",
        checkpoint_prefix,
        "--heartbeat_every",
        str(heartbeat_every),
        "--heartbeat_path",
        heartbeat_path,
        "--stale_timeout_minutes",
        str(stale_timeout_minutes),
        "--poll_seconds",
        "10",
        "--max_attempts",
        str(max_attempts),
        "--max_no_progress_attempts",
        str(max_no_progress_attempts),
        "--min_free_disk_gb",
        "2.0",
        "--run_tag",
        f"tui-long:{long_cfg['run_id']}",
        "--use_opponent_pool",
        "--pool_dir",
        "models/pool",
        "--opponent_replace_count",
        "1",
    ]
    return CmdSpec("Long Train (guarded resumable)", cmd)


def _show_long_progress() -> None:
    state = _load_state()
    prog = _collect_long_progress(state)
    if not prog.get("available"):
        print("[INFO] no long-run config in reports/tui_state.json")
        return
    print("\n[Long Progress]")
    print(f" run_id: {prog.get('run_id')}")
    print(f" model_base: {prog.get('model_base')}")
    print(f" checkpoint_dir: {prog.get('checkpoint_dir')}")
    print(f" checkpoint_prefix: {prog.get('checkpoint_prefix')}")
    print(f" latest_checkpoint: {prog.get('latest_checkpoint') or '-'}")
    print(f" meta_steps: {prog.get('meta_steps')}")
    print(f" checkpoint_steps: {prog.get('checkpoint_steps')}")
    print(f" current_steps: {prog.get('current_steps')}")
    print(f" target_steps: {prog.get('target_steps')}")
    print(f" progress: {float(prog.get('progress_ratio', 0.0)) * 100:.2f}%")
    hb_path = str(prog.get("heartbeat_path", "")) or "-"
    print(f" heartbeat_path: {hb_path}")
    print(f" heartbeat_status: {prog.get('heartbeat_status', '-')}, age={prog.get('heartbeat_age_seconds', '-')}")
    guard_report = str(prog.get("guard_report_out", "")).strip()
    if guard_report:
        gp = _safe_read_json(Path(guard_report))
        if isinstance(gp, dict):
            print(
                " guard_report: "
                f"{guard_report} | status={gp.get('status', '-')} | "
                f"attempts={gp.get('attempt_count', '-')} | fail_reason={gp.get('fail_reason', '')}"
            )
        else:
            print(f" guard_report: {guard_report} (not ready)")


def _show_last_log_tail(lines: int = 60) -> None:
    state = _load_state()
    log_path = str(state.get("log", "")).strip()
    if not log_path:
        print("[INFO] no log path in state.")
        return
    p = Path(log_path)
    if not p.exists():
        print(f"[WARN] log not found: {p}")
        return
    content = p.read_text(encoding="utf-8", errors="replace").splitlines()
    tail = content[-max(1, int(lines)) :]
    print(f"\n[Last Log Tail] {p}")
    print("-" * 72)
    for ln in tail:
        print(ln)
    print("-" * 72)


def _run_long_train_new() -> None:
    alias = _ask_text("long run alias", "main")
    run_id = f"long_{alias}"
    out = f"models/ppo_{run_id}"
    checkpoint_dir = "models/checkpoints"
    checkpoint_prefix = f"ppo_{run_id}_ckpt"
    chunk = _ask_int("chunk timesteps per run", DEFAULT_LONG_CHUNK)
    target = _ask_int("target total timesteps", DEFAULT_LONG_TARGET)
    num_envs = _ask_int("num envs", _recommended_num_envs())
    seed = _ask_int("seed", 2026)
    checkpoint_every = _ask_int("checkpoint every timesteps", 50_000)
    bot_epsilon = float(_ask_text("bot epsilon", "0.08"))
    heartbeat_every = _ask_int("heartbeat every timesteps", DEFAULT_HEARTBEAT_EVERY)
    stale_timeout_minutes = float(_ask_text("stale timeout minutes", str(DEFAULT_STALE_TIMEOUT_MIN)))
    max_attempts = _ask_int("max retry attempts", 100)
    max_no_progress_attempts = _ask_int("max no-progress attempts", 5)
    heartbeat_path = f"reports/heartbeat_{run_id}.json"
    guard_report_out = f"reports/guarded_train_{run_id}.json"

    long_cfg: Dict[str, object] = {
        "run_id": run_id,
        "out": out,
        "checkpoint_dir": checkpoint_dir,
        "checkpoint_prefix": checkpoint_prefix,
        "chunk_timesteps": int(chunk),
        "target_total_timesteps": int(target),
        "num_envs": int(num_envs),
        "seed": int(seed),
        "checkpoint_every": int(checkpoint_every),
        "bot_epsilon": float(bot_epsilon),
        "opponent_mix": DEFAULT_OPP_MIX,
        "heartbeat_every": int(heartbeat_every),
        "stale_timeout_minutes": float(stale_timeout_minutes),
        "max_attempts": int(max_attempts),
        "max_no_progress_attempts": int(max_no_progress_attempts),
        "heartbeat_path": heartbeat_path,
        "guard_report_out": guard_report_out,
    }
    long_cfg = _sanitize_long_run_cfg(long_cfg)
    state = _load_state()
    state["long_run"] = long_cfg
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=True, indent=2), encoding="utf-8")

    rc = _run_pipeline(
        "long_train",
        f"{run_id}_{_now_tag()}",
        [_build_long_train_command(long_cfg, resume_mode=True)],
    )
    _save_state("long_train_new", run_id, rc, {"long_run": long_cfg, "last_model_base": out})


def _run_long_train_resume() -> None:
    state = _load_state()
    long_cfg = state.get("long_run")
    if not isinstance(long_cfg, dict):
        print("[WARN] no long_run config. run option 6 first.")
        return
    long_cfg = _sanitize_long_run_cfg(long_cfg)
    state["long_run"] = long_cfg
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=True, indent=2), encoding="utf-8")
    run_id = str(long_cfg.get("run_id", "long_unknown"))
    rc = _run_pipeline(
        "long_resume",
        f"{run_id}_{_now_tag()}",
        [_build_long_train_command(long_cfg, resume_mode=True)],
    )
    _save_state("long_train_resume", run_id, rc, {"long_run": long_cfg, "last_model_base": str(long_cfg.get("out", ""))})


def _run_quick_train() -> None:
    run_id = f"quick_{_now_tag()}"
    rc = _run_pipeline("quick_train", run_id, _quick_train_commands(run_id))
    if rc == 0:
        model_base = Path(f"models/ppo_tui_{run_id}")
        _save_state("quick_train", run_id, 0, {"last_model_base": str(model_base)})


def _run_matrix_train() -> None:
    run_id = f"matrix_{_now_tag()}"
    rc = _run_pipeline("matrix_train", run_id, _matrix_train_commands(run_id))
    if rc != 0:
        return
    matrix_json = REPORTS_DIR / f"matrix_tui_{run_id}_{RULE_PROFILE_ID}_dev.json"
    best_model_base = _pick_best_model_from_matrix(matrix_json)
    extra: Dict[str, object] = {"matrix_json": str(matrix_json)}
    if best_model_base is not None:
        extra["last_model_base"] = str(best_model_base)
    _save_state("matrix_train", run_id, 0, extra)


def _pick_best_model_from_matrix(matrix_json_path: Path) -> Optional[Path]:
    payload = _safe_read_json(matrix_json_path)
    if not isinstance(payload, dict):
        return None
    exps = payload.get("experiments")
    if not isinstance(exps, list) or not exps:
        return None
    best = sorted(
        exps,
        key=lambda x: float(x.get("summary", {}).get("mean_diff", -1e9)),
        reverse=True,
    )[0]
    model_base = best.get("model_base")
    if not isinstance(model_base, str):
        return None
    return Path(model_base)


def _run_eval_latest_model() -> None:
    run_id = f"eval_{_now_tag()}"
    state = _load_state()
    model_base = None
    if isinstance(state, dict):
        maybe = state.get("last_model_base")
        if isinstance(maybe, str) and maybe.strip():
            candidate = Path(maybe.strip())
            if candidate.with_suffix(".zip").exists():
                model_base = candidate
    if model_base is None:
        model_base = _collect_latest_model()
    if model_base is None:
        print("[WARN] no model found under models/*.zip")
        _save_state("eval_latest", run_id, 1, {"reason": "no_model"})
        return
    print(f"[INFO] evaluate model: {model_base}")
    rc = _run_pipeline("eval_latest", run_id, _test_eval_commands(model_base, run_id))
    if rc == 0:
        _save_state("eval_latest", run_id, 0, {"last_model_base": str(model_base)})


def _run_pytest_gate() -> None:
    run_id = f"gate_{_now_tag()}"
    rc = _run_pipeline(
        "pytest_gate",
        run_id,
        [CmdSpec("Pytest Full", ["uv", "run", "pytest", "tests", "-q"])],
    )
    _save_state("pytest_gate", run_id, rc)


def main() -> None:
    if _wants_help(sys.argv[1:]):
        _print_cli_help()
        return

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    while True:
        _clear_screen()
        _print_dashboard()
        try:
            choice = input("Select> ").strip()
        except EOFError:
            print("\n[INFO] EOF received, exit TUI.")
            return
        if choice == "0":
            print("Bye.")
            return
        if choice == "1":
            _run_quick_train()
        elif choice == "2":
            _run_matrix_train()
        elif choice == "3":
            _run_eval_latest_model()
        elif choice == "4":
            _show_long_progress()
        elif choice == "5":
            _run_pytest_gate()
        elif choice == "6":
            _run_long_train_new()
        elif choice == "7":
            _run_long_train_resume()
        elif choice == "8":
            _show_last_log_tail()
        else:
            print("Unknown option.")
        try:
            input("\nPress Enter to continue...")
        except EOFError:
            print("\n[INFO] EOF received, exit TUI.")
            return


if __name__ == "__main__":
    main()
