import argparse
from pathlib import Path

from rl.train_ppo import (
    _compute_learn_timesteps,
    _extract_steps_from_checkpoint_name,
    _find_latest_checkpoint,
    _resolve_resume_source,
)


def test_extract_steps_from_checkpoint_name():
    assert _extract_steps_from_checkpoint_name(Path("ppo_main_ckpt_12345_steps.zip")) == 12345
    assert _extract_steps_from_checkpoint_name(Path("ppo_main.zip")) is None


def test_find_latest_checkpoint_by_steps(tmp_path: Path):
    a = tmp_path / "ppo_main_ckpt_1000_steps.zip"
    b = tmp_path / "ppo_main_ckpt_5000_steps.zip"
    c = tmp_path / "ppo_main_ckpt_2000_steps.zip"
    a.write_text("x", encoding="utf-8")
    b.write_text("x", encoding="utf-8")
    c.write_text("x", encoding="utf-8")
    latest = _find_latest_checkpoint(tmp_path, "ppo_main_ckpt")
    assert latest == b


def test_compute_learn_timesteps_with_target():
    assert _compute_learn_timesteps(current_timesteps=0, chunk_timesteps=1000, target_total_timesteps=0) == 1000
    assert _compute_learn_timesteps(current_timesteps=800, chunk_timesteps=500, target_total_timesteps=1000) == 200
    assert _compute_learn_timesteps(current_timesteps=1000, chunk_timesteps=500, target_total_timesteps=1000) == 0


def test_resolve_resume_source_prefers_latest_checkpoint(tmp_path: Path):
    ckpt_dir = tmp_path / "ckpts"
    ckpt_dir.mkdir()
    newest = ckpt_dir / "ppo_main_ckpt_3000_steps.zip"
    older = ckpt_dir / "ppo_main_ckpt_1000_steps.zip"
    older.write_text("x", encoding="utf-8")
    newest.write_text("x", encoding="utf-8")

    out_base = tmp_path / "ppo_main"
    args = argparse.Namespace(
        resume_latest_checkpoint=True,
        checkpoint_dir=str(ckpt_dir),
        checkpoint_prefix="ppo_main_ckpt",
        resume_from="",
    )
    got = _resolve_resume_source(args, out_base)
    assert got == newest

