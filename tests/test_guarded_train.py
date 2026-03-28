import json
import time
import argparse
import subprocess
import sys
from pathlib import Path

import pytest

from tools.guarded_train import (
    _heartbeat_age_seconds,
    _read_model_timesteps,
    _read_total_steps,
    _terminate_process_tree,
    _validate_args,
)


def test_read_model_timesteps_from_meta(tmp_path: Path):
    base = tmp_path / "ppo_x"
    base.with_suffix(".json").write_text(
        json.dumps({"num_timesteps_total": 12345}, ensure_ascii=True),
        encoding="utf-8",
    )
    assert _read_model_timesteps(base) == 12345


def test_heartbeat_age_seconds(tmp_path: Path):
    hb = tmp_path / "hb.json"
    now = time.time()
    hb.write_text(
        json.dumps({"updated_at_unix": now - 5}, ensure_ascii=True),
        encoding="utf-8",
    )
    age = _heartbeat_age_seconds(hb)
    assert age >= 4.0


def test_read_total_steps_prefers_checkpoint_when_meta_lags(tmp_path: Path):
    base = tmp_path / "ppo_main"
    base.with_suffix(".json").write_text(
        json.dumps({"num_timesteps_total": 1000}, ensure_ascii=True),
        encoding="utf-8",
    )
    ckpt_dir = tmp_path / "checkpoints"
    ckpt_dir.mkdir(parents=True)
    (ckpt_dir / "ppo_main_ckpt_2500_steps.zip").write_text("x", encoding="utf-8")
    assert _read_total_steps(base, ckpt_dir, "ppo_main_ckpt") == 2500


def test_validate_args_checks_core_bounds():
    args = argparse.Namespace(
        target_total_timesteps=1,
        chunk_timesteps=1,
        max_attempts=1,
        max_no_progress_attempts=1,
        stale_timeout_minutes=1.0,
        poll_seconds=1.0,
        checkpoint_every=1,
        heartbeat_every=1,
    )
    _validate_args(args)

    args_bad = argparse.Namespace(
        target_total_timesteps=0,
        chunk_timesteps=1,
        max_attempts=1,
        max_no_progress_attempts=1,
        stale_timeout_minutes=1.0,
        poll_seconds=1.0,
        checkpoint_every=1,
        heartbeat_every=1,
    )
    with pytest.raises(ValueError):
        _validate_args(args_bad)


def test_terminate_process_tree_noop_on_exited_process():
    proc = subprocess.Popen([sys.executable, "-c", "print('ok')"])
    proc.wait(timeout=5)
    _terminate_process_tree(proc)
