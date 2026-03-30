from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List

REPORT_SCHEMA_VERSION = "duplicate_trend.v1"


def _load_report(path: Path) -> Dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _default_version_name(path: Path) -> str:
    name = path.stem
    if name.startswith("dup_"):
        return name[len("dup_") :]
    return name


def build_trend(reports: List[Path], out_md: Path, out_json: Path | None = None) -> None:
    rows = []
    for path in reports:
        report = _load_report(path)
        mean = float(report.get("mean_diff", 0.0))
        ci95 = float(report.get("ci95", 0.0))
        rows.append(
            {
                "version": _default_version_name(path),
                "report": str(path),
                "policy_mode": str(report.get("policy_mode", "model")),
                "backend": str(report.get("backend", "")),
                "n_games": int(report.get("n_games", 0)),
                "mean_diff": mean,
                "std_diff": float(report.get("std_diff", 0.0)),
                "ci95": ci95,
                "lower_ci95": mean - ci95,
                "rule_profile_id": str(report.get("rule_profile_id", "")),
                "spec_version": str(report.get("spec_version", "")),
                "seed_set_id": str(report.get("seed_set_id", "")),
                "opponent_suite_id": str(report.get("opponent_suite_id", "")),
            }
        )

    rows.sort(key=lambda r: (r["policy_mode"], r["version"]))

    out_md.parent.mkdir(parents=True, exist_ok=True)
    with out_md.open("w", encoding="utf-8") as f:
        f.write("# Duplicate Trend\n\n")
        f.write(
            "| Version | Policy | Backend | Games | Mean Diff | CI95 | Lower CI95 | Rule Profile | Spec | Seed Set | Opponent Suite | Report |\n"
        )
        f.write("|---|---|---:|---:|---:|---:|---:|---|---|---|---|---|\n")
        for row in rows:
            f.write(
                f"| {row['version']} | {row['policy_mode']} | {row['backend']} | {row['n_games']} | "
                f"{row['mean_diff']:.4f} | {row['ci95']:.4f} | {row['lower_ci95']:.4f} | "
                f"{row['rule_profile_id']} | {row['spec_version']} | {row['seed_set_id']} | "
                f"{row['opponent_suite_id']} | `{row['report']}` |\n"
            )

    if out_json is not None:
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(
            json.dumps(
                {
                    "report_schema_version": REPORT_SCHEMA_VERSION,
                    "rows": rows,
                },
                ensure_ascii=True,
                indent=2,
            ),
            encoding="utf-8",
        )

    print(f"saved_md={out_md} rows={len(rows)}")
    if out_json is not None:
        print(f"saved_json={out_json}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reports", type=Path, nargs="+", required=True)
    parser.add_argument("--out_md", type=Path, required=True)
    parser.add_argument("--out_json", type=Path, default=None)
    args = parser.parse_args()
    build_trend(args.reports, args.out_md, args.out_json)


if __name__ == "__main__":
    main()
