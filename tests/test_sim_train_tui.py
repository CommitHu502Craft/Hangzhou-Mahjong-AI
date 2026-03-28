import json
from pathlib import Path

from tools.sim_train_tui import (
    _collect_guard_report_summary,
    _collect_long_progress,
    _collect_model_insights,
    _fmt_duration,
    _latest_file,
    _normalize_model_base,
    _pick_best_model_from_matrix,
    _sanitize_long_run_cfg,
    _wants_help,
    main,
)


def test_normalize_model_base_zip():
    p = Path("models/ppo_demo.zip")
    assert _normalize_model_base(p) == Path("models/ppo_demo")


def test_latest_file_by_mtime(tmp_path: Path):
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("a", encoding="utf-8")
    b.write_text("b", encoding="utf-8")
    a.touch()
    b.touch()
    latest = _latest_file([a, b])
    assert latest is not None
    assert latest.name in {"a.txt", "b.txt"}


def test_pick_best_model_from_matrix(tmp_path: Path):
    p = tmp_path / "matrix.json"
    payload = {
        "experiments": [
            {"model_base": "models/ppo_a", "summary": {"mean_diff": 1.0}},
            {"model_base": "models/ppo_b", "summary": {"mean_diff": 5.0}},
        ]
    }
    p.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
    best = _pick_best_model_from_matrix(p)
    assert best == Path("models/ppo_b")


def test_collect_long_progress_reads_checkpoint_and_meta(tmp_path: Path):
    model_base = tmp_path / "models" / "ppo_long_main"
    model_base.parent.mkdir(parents=True)
    model_base.with_suffix(".json").write_text(
        json.dumps({"num_timesteps_total": 120000}, ensure_ascii=True),
        encoding="utf-8",
    )
    ckpt_dir = tmp_path / "models" / "checkpoints"
    ckpt_dir.mkdir(parents=True)
    (ckpt_dir / "ppo_long_main_ckpt_150000_steps.zip").write_text("x", encoding="utf-8")

    state = {
        "long_run": {
            "run_id": "long_main",
            "out": str(model_base),
            "checkpoint_dir": str(ckpt_dir),
            "checkpoint_prefix": "ppo_long_main_ckpt",
            "target_total_timesteps": 500000,
            "chunk_timesteps": 200000,
        }
    }
    prog = _collect_long_progress(state)
    assert prog["available"] is True
    assert prog["current_steps"] == 150000
    assert prog["target_steps"] == 500000


def test_wants_help_flags():
    assert _wants_help(["--help"]) is True
    assert _wants_help(["-h"]) is True
    assert _wants_help(["help"]) is True
    assert _wants_help(["--unknown"]) is False


def test_main_handles_eof_and_exits(monkeypatch):
    monkeypatch.setattr("tools.sim_train_tui._clear_screen", lambda: None)
    monkeypatch.setattr("tools.sim_train_tui._print_dashboard", lambda: None)

    def _raise_eof(_prompt: str = "") -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", _raise_eof)
    assert main() is None


def test_collect_model_insights_reads_meta(tmp_path: Path):
    model_base = tmp_path / "models" / "ppo_demo"
    model_base.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "backend": "sb3_maskableppo",
        "reward_mode": "log1p",
        "num_envs": 8,
        "resumed": True,
        "num_timesteps_total": 2000,
        "target_total_timesteps": 5000,
        "monitor_gate": {
            "status": "PASS",
            "metrics": {
                "myturn_ratio": 0.8,
                "reaction_ratio": 0.2,
                "illegal_action_rate": 0.0,
                "truncation_rate": 0.01,
            },
        },
    }
    model_base.with_suffix(".json").write_text(
        json.dumps(payload, ensure_ascii=True),
        encoding="utf-8",
    )
    insights = _collect_model_insights(model_base)
    assert insights["available"] is True
    assert insights["backend"] == "sb3_maskableppo"
    assert insights["total_steps"] == 2000
    assert insights["target_steps"] == 5000
    assert insights["monitor_status"] == "PASS"


def test_collect_guard_report_summary(tmp_path: Path):
    report = tmp_path / "guarded.json"
    payload = {
        "status": "FAIL",
        "attempt_count": 2,
        "num_timesteps_total": 1200,
        "target_total_timesteps": 5000,
        "fail_reason": "no_progress_limit_reached",
        "attempts": [
            {
                "index": 1,
                "started_at": "2026-02-22T10:00:00",
                "ended_at": "2026-02-22T10:01:00",
                "exit_code": 0,
                "reason": "process_exit",
                "progress_delta": 600,
            },
            {
                "index": 2,
                "started_at": "2026-02-22T10:01:00",
                "ended_at": "2026-02-22T10:02:30",
                "exit_code": 1,
                "reason": "heartbeat_stale_timeout",
                "progress_delta": 600,
            },
        ],
    }
    report.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
    summary = _collect_guard_report_summary(report)
    assert summary["available"] is True
    assert summary["attempt_count"] == 2
    assert summary["last_reason"] == "heartbeat_stale_timeout"
    assert summary["total_progress"] == 1200
    assert summary["speed_sps"] > 0


def test_fmt_duration():
    assert _fmt_duration(None) == "-"
    assert _fmt_duration(59) == "59s"
    assert _fmt_duration(125) == "2m05s"


def test_sanitize_long_run_cfg_adjusts_bad_intervals():
    cfg = {
        "chunk_timesteps": 20_000,
        "target_total_timesteps": 200_000,
        "num_envs": 4,
        "checkpoint_every": 500_000,
        "heartbeat_every": 100_000,
        "stale_timeout_minutes": 20.0,
        "max_attempts": 50,
        "max_no_progress_attempts": 5,
    }
    out = _sanitize_long_run_cfg(cfg)
    assert out["checkpoint_every"] <= out["chunk_timesteps"]
    assert out["heartbeat_every"] < out["checkpoint_every"]
