from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@dataclass(frozen=True)
class ExperimentSpec:
    id: str
    variable: str
    description: str
    ppo_changes: Dict[str, object]


def default_matrix_experiments() -> List[ExperimentSpec]:
    return [
        ExperimentSpec(
            id="baseline",
            variable="baseline",
            description="Baseline: reward_mode=log1p, opponent_mix=rule:1.0",
            ppo_changes={},
        ),
        ExperimentSpec(
            id="reward_raw_vecnorm",
            variable="reward_strategy",
            description="Single-variable change: reward strategy -> raw + vecnormalize reward",
            ppo_changes={
                "reward_mode": "raw",
                "use_vec_normalize_reward": True,
            },
        ),
        ExperimentSpec(
            id="opponent_mix_diverse",
            variable="opponent_suite",
            description="Single-variable change: diversified opponent mix",
            ppo_changes={
                "opponent_mix": "rule:0.4,defensive:0.2,aggressive:0.2,random:0.1,minlegal:0.1",
            },
        ),
    ]


def validate_matrix_experiments(experiments: Sequence[ExperimentSpec]) -> None:
    if not experiments:
        raise ValueError("matrix experiments cannot be empty")

    ids = set()
    baseline_found = False
    for exp in experiments:
        if not exp.id or not exp.variable:
            raise ValueError(f"invalid experiment id/variable: {exp}")
        if exp.id in ids:
            raise ValueError(f"duplicate experiment id: {exp.id}")
        ids.add(exp.id)
        if exp.id == "baseline":
            baseline_found = True
        elif not exp.ppo_changes:
            raise ValueError(f"non-baseline experiment requires ppo_changes: {exp.id}")
    if not baseline_found:
        raise ValueError("matrix experiments must include id='baseline'")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sanitize(s: str) -> str:
    out = []
    for ch in s:
        if ch.isalnum() or ch in ("-", "_"):
            out.append(ch)
        else:
            out.append("_")
    return "".join(out).strip("_")


def _run_cmd(cmd: List[str], cwd: Path) -> str:
    print("[RUN]", " ".join(cmd))
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    output = proc.stdout or ""
    if output:
        print(output.rstrip())
    if proc.returncode != 0:
        raise RuntimeError(f"command failed ({proc.returncode}): {' '.join(cmd)}")
    return output


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _bool_flag(name: str, value: bool) -> List[str]:
    return [f"--{name}"] if value else []


def _select_experiments(all_exps: Sequence[ExperimentSpec], selected_ids: Sequence[str]) -> List[ExperimentSpec]:
    if not selected_ids:
        return list(all_exps)
    wanted = {x.strip() for x in selected_ids if x.strip()}
    out = [e for e in all_exps if e.id in wanted]
    missing = sorted(wanted.difference({e.id for e in out}))
    if missing:
        raise ValueError(f"unknown experiment ids: {missing}")
    if "baseline" not in {e.id for e in out}:
        out = [e for e in all_exps if e.id == "baseline"] + out
    return out


def run_matrix(args: argparse.Namespace) -> None:
    experiments = _select_experiments(default_matrix_experiments(), args.experiments)
    validate_matrix_experiments(experiments)

    matrix_tag = _sanitize(args.matrix_id)
    profile_id = _sanitize(args.rule_profile_id)
    seed_set_id = _sanitize(args.seed_set_id)
    run_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    reports_dir = ROOT / "reports"
    models_dir = ROOT / "models"
    datasets_dir = ROOT / "datasets" / "artifacts"
    reports_dir.mkdir(parents=True, exist_ok=True)
    models_dir.mkdir(parents=True, exist_ok=True)
    datasets_dir.mkdir(parents=True, exist_ok=True)

    matrix_manifest_path = reports_dir / f"matrix_{matrix_tag}_{profile_id}_{seed_set_id}.json"
    matrix_markdown_path = reports_dir / f"matrix_{matrix_tag}_{profile_id}_{seed_set_id}.md"

    dataset_path = datasets_dir / f"train_data_{matrix_tag}_{profile_id}_{run_stamp}.npz"
    bc_path = models_dir / f"bc_{matrix_tag}_{profile_id}_{run_stamp}.pt"

    # 1) Data generation (shared across all single-variable PPO runs).
    gen_cmd = [
        "uv",
        "run",
        "python",
        "datasets/gen_data.py",
        "--episodes",
        str(args.data_episodes),
        "--target_decisions",
        str(args.data_target_decisions),
        "--min_samples",
        str(args.data_min_samples),
        "--max_episodes",
        str(args.data_max_episodes),
        "--seed_start",
        str(args.seed_start),
        "--epsilon",
        str(args.data_epsilon),
        "--out",
        str(dataset_path),
        "--enforce_distribution_gates",
        "--gate_min_myturn_ratio",
        str(args.gate_min_myturn_ratio),
        "--gate_min_reaction_ratio",
        str(args.gate_min_reaction_ratio),
        "--gate_max_action_share",
        str(args.gate_max_action_share),
        "--gate_min_avg_legal_actions",
        str(args.gate_min_avg_legal_actions),
        "--gate_max_truncated_rate",
        str(args.gate_max_truncated_rate),
    ]
    if args.enable_qiaoxiang:
        gen_cmd.append("--enable_qiaoxiang")
    _run_cmd(gen_cmd, cwd=ROOT)

    # 2) BC preheat (shared baseline).
    bc_cmd = [
        "uv",
        "run",
        "python",
        "datasets/bc_train.py",
        "--data",
        str(dataset_path),
        "--epochs",
        str(args.bc_epochs),
        "--batch_size",
        str(args.bc_batch_size),
        "--lr",
        str(args.bc_lr),
        "--out",
        str(bc_path),
    ]
    _run_cmd(bc_cmd, cwd=ROOT)

    baseline_ppo = {
        "timesteps": int(args.ppo_timesteps),
        "num_envs": int(args.ppo_num_envs),
        "seed": int(args.seed_start + 2026),
        "vec_backend": str(args.vec_backend),
        "reward_mode": "log1p",
        "bot_epsilon": float(args.bot_epsilon),
        "opponent_mix": str(args.opponent_mix_baseline),
        "use_vec_normalize_reward": False,
        "use_opponent_pool": bool(args.use_opponent_pool),
        "pool_dir": str(args.pool_dir),
        "opponent_replace_count": int(args.opponent_replace_count),
        "monitor_episodes": int(args.monitor_episodes),
        "enforce_monitor_gates": True,
    }

    results: List[dict] = []
    rule_cache: Dict[str, Path] = {}

    for idx, exp in enumerate(experiments):
        exp_cfg = dict(baseline_ppo)
        exp_cfg.update(exp.ppo_changes)

        exp_tag = _sanitize(exp.id)
        model_base = models_dir / f"ppo_{matrix_tag}_{profile_id}_{exp_tag}"
        model_zip = model_base.with_suffix(".zip")
        model_meta = model_base.with_suffix(".json")

        # 3) PPO train.
        train_cmd = [
            "uv",
            "run",
            "python",
            "rl/train_ppo.py",
            "--timesteps",
            str(exp_cfg["timesteps"]),
            "--num-envs",
            str(exp_cfg["num_envs"]),
            "--seed",
            str(exp_cfg["seed"]),
            "--vec_backend",
            str(exp_cfg["vec_backend"]),
            "--reward_mode",
            str(exp_cfg["reward_mode"]),
            "--bot_epsilon",
            str(exp_cfg["bot_epsilon"]),
            "--opponent_mix",
            str(exp_cfg["opponent_mix"]),
            "--monitor_episodes",
            str(exp_cfg["monitor_episodes"]),
            "--out",
            str(model_base),
            "--run_tag",
            f"{matrix_tag}:{exp_tag}",
        ]
        if bool(exp_cfg.get("use_vec_normalize_reward", False)):
            train_cmd.append("--use_vec_normalize_reward")
        if bool(exp_cfg.get("use_opponent_pool", False)):
            train_cmd.extend(
                [
                    "--use_opponent_pool",
                    "--pool_dir",
                    str(exp_cfg["pool_dir"]),
                    "--opponent_replace_count",
                    str(exp_cfg["opponent_replace_count"]),
                ]
            )
        if args.enable_qiaoxiang:
            train_cmd.append("--enable_qiaoxiang")
        if not bool(exp_cfg.get("enforce_monitor_gates", True)):
            train_cmd.append("--no_enforce_monitor_gates")

        _run_cmd(train_cmd, cwd=ROOT)

        # 4) Evaluate model under fixed versioned context.
        opp_suite_id = f"{exp_tag}_eps{int(round(float(args.eval_opponent_epsilon) * 100)):02d}"
        dup_model_report = reports_dir / f"dup_{matrix_tag}_{profile_id}_{exp_tag}_{seed_set_id}.json"
        eval_model_cmd = [
            "uv",
            "run",
            "python",
            "rl/eval_duplicate.py",
            "--model",
            str(model_base),
            "--policy_mode",
            "model",
            "--seed_set",
            str(args.seed_set),
            "--strict_load",
            "--fail_on_fallback",
            "--opponent_epsilon",
            str(args.eval_opponent_epsilon),
            "--opponent_mix",
            str(exp_cfg["opponent_mix"]),
            "--rule_profile",
            str(args.rule_profile),
            "--rule_profile_id",
            str(args.rule_profile_id),
            "--spec_version",
            str(args.spec_version),
            "--seed_set_id",
            str(args.seed_set_id),
            "--opponent_suite_id",
            opp_suite_id,
            "--out",
            str(dup_model_report),
        ]
        if args.enable_qiaoxiang:
            eval_model_cmd.append("--enable_qiaoxiang")
        _run_cmd(eval_model_cmd, cwd=ROOT)

        # 5) Evaluate Rule baseline for the same opponent suite (cache by suite+seed-set).
        rule_key = f"{seed_set_id}:{opp_suite_id}:{exp_cfg['opponent_mix']}"
        if rule_key in rule_cache:
            dup_rule_report = rule_cache[rule_key]
        else:
            dup_rule_report = reports_dir / f"dup_rule_{matrix_tag}_{profile_id}_{opp_suite_id}_{seed_set_id}.json"
            eval_rule_cmd = [
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
                str(args.seed_set),
                "--opponent_epsilon",
                str(args.eval_opponent_epsilon),
                "--opponent_mix",
                str(exp_cfg["opponent_mix"]),
                "--rule_profile",
                str(args.rule_profile),
                "--rule_profile_id",
                str(args.rule_profile_id),
                "--spec_version",
                str(args.spec_version),
                "--seed_set_id",
                str(args.seed_set_id),
                "--opponent_suite_id",
                opp_suite_id,
                "--out",
                str(dup_rule_report),
            ]
            if args.enable_qiaoxiang:
                eval_rule_cmd.append("--enable_qiaoxiang")
            _run_cmd(eval_rule_cmd, cwd=ROOT)
            rule_cache[rule_key] = dup_rule_report

        # 6) Readiness (L1-style) for this experiment.
        readiness_report = reports_dir / f"readiness_{matrix_tag}_{profile_id}_{exp_tag}_{seed_set_id}.json"
        readiness_cmd = [
            "uv",
            "run",
            "python",
            "rl/assess_model_readiness.py",
            "--model_report",
            str(dup_model_report),
            "--rule_report",
            str(dup_rule_report),
            "--expected_rule_profile_id",
            str(args.rule_profile_id),
            "--expected_spec_version",
            str(args.spec_version),
            "--expected_seed_set_id",
            str(args.seed_set_id),
            "--expected_opponent_suite_id",
            opp_suite_id,
            "--min_games",
            str(args.readiness_min_games),
            "--min_advantage",
            str(args.readiness_min_advantage),
            "--out",
            str(readiness_report),
        ]
        _run_cmd(readiness_cmd, cwd=ROOT)

        dup_payload = _read_json(dup_model_report)
        ready_payload = _read_json(readiness_report)
        result = {
            "order": idx,
            "experiment": asdict(exp),
            "model_base": str(model_base),
            "model_zip": str(model_zip),
            "model_meta": str(model_meta),
            "duplicate_report": str(dup_model_report),
            "rule_report": str(dup_rule_report),
            "readiness_report": str(readiness_report),
            "opponent_suite_id": opp_suite_id,
            "summary": {
                "n_games": int(dup_payload.get("n_games", 0)),
                "mean_diff": float(dup_payload.get("mean_diff", 0.0)),
                "ci95": float(dup_payload.get("ci95", 0.0)),
                "readiness_status": str(ready_payload.get("status", "UNKNOWN")),
                "advantage_vs_rule": float(ready_payload.get("metrics", {}).get("advantage_vs_rule", 0.0)),
            },
            "ppo_config": exp_cfg,
        }
        results.append(result)

    matrix_payload = {
        "matrix_id": matrix_tag,
        "profile_id": str(args.rule_profile_id),
        "spec_version": str(args.spec_version),
        "seed_set": str(args.seed_set),
        "seed_set_id": str(args.seed_set_id),
        "rule_profile": str(args.rule_profile),
        "created_at_utc": _utc_now(),
        "dataset_artifact": str(dataset_path),
        "bc_artifact": str(bc_path),
        "baseline_ppo": baseline_ppo,
        "experiments": results,
    }
    matrix_manifest_path.write_text(json.dumps(matrix_payload, ensure_ascii=True, indent=2), encoding="utf-8")

    md_lines = [
        f"# Single-Variable Matrix: {matrix_tag}",
        "",
        f"- Profile: `{args.rule_profile_id}`",
        f"- Spec: `{args.spec_version}`",
        f"- Seed set: `{args.seed_set}` / `{args.seed_set_id}`",
        f"- Dataset: `{dataset_path}`",
        f"- BC: `{bc_path}`",
        "",
        "| Experiment | Variable | Mean Diff | CI95 | Readiness | Dup Report | Readiness Report |",
        "|---|---:|---:|---:|---|---|---|",
    ]
    for item in results:
        exp = item["experiment"]
        s = item["summary"]
        md_lines.append(
            f"| `{exp['id']}` | `{exp['variable']}` | {s['mean_diff']:.4f} | {s['ci95']:.4f} | "
            f"{s['readiness_status']} | `{item['duplicate_report']}` | `{item['readiness_report']}` |"
        )
    matrix_markdown_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    print(f"saved_matrix_manifest={matrix_manifest_path}")
    print(f"saved_matrix_markdown={matrix_markdown_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix_id", type=str, default="hzvA_singlevar_start")
    parser.add_argument("--rule_profile", type=Path, default=Path("rules/hz_local_v2026_02_A.yaml"))
    parser.add_argument("--rule_profile_id", type=str, default="hz_local_v2026_02_A")
    parser.add_argument("--spec_version", type=str, default="v1.1")
    parser.add_argument("--seed_set", type=str, default="dev", choices=["dev", "test"])
    parser.add_argument("--seed_set_id", type=str, default="dev")
    parser.add_argument("--seed_start", type=int, default=4100)
    parser.add_argument("--enable_qiaoxiang", action="store_true")

    parser.add_argument("--data_episodes", type=int, default=120)
    parser.add_argument("--data_max_episodes", type=int, default=200)
    parser.add_argument("--data_target_decisions", type=int, default=2000)
    parser.add_argument("--data_min_samples", type=int, default=500)
    parser.add_argument("--data_epsilon", type=float, default=0.08)
    parser.add_argument("--gate_min_myturn_ratio", type=float, default=0.0)
    parser.add_argument("--gate_min_reaction_ratio", type=float, default=0.0)
    parser.add_argument("--gate_max_action_share", type=float, default=1.0)
    parser.add_argument("--gate_min_avg_legal_actions", type=float, default=1.0)
    parser.add_argument("--gate_max_truncated_rate", type=float, default=1.0)

    parser.add_argument("--bc_epochs", type=int, default=2)
    parser.add_argument("--bc_batch_size", type=int, default=256)
    parser.add_argument("--bc_lr", type=float, default=1e-3)

    parser.add_argument("--ppo_timesteps", type=int, default=8000)
    parser.add_argument("--ppo_num_envs", type=int, default=4)
    parser.add_argument("--vec_backend", type=str, default="dummy", choices=["dummy", "subproc"])
    parser.add_argument("--bot_epsilon", type=float, default=0.08)
    parser.add_argument("--opponent_mix_baseline", type=str, default="rule:1.0")
    parser.add_argument("--use_opponent_pool", action="store_true")
    parser.add_argument("--pool_dir", type=str, default="models/pool")
    parser.add_argument("--opponent_replace_count", type=int, default=1)
    parser.add_argument("--monitor_episodes", type=int, default=10)

    parser.add_argument("--eval_opponent_epsilon", type=float, default=0.08)
    parser.add_argument("--readiness_min_games", type=int, default=2000)
    parser.add_argument("--readiness_min_advantage", type=float, default=2.0)

    parser.add_argument(
        "--experiments",
        type=str,
        nargs="*",
        default=[],
        help="subset of experiment ids, e.g. baseline reward_raw_vecnorm",
    )

    args = parser.parse_args()
    run_matrix(args)


if __name__ == "__main__":
    main()
