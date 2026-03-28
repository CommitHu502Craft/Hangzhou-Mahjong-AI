from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import Iterable

VALID_SUFFIXES = {".zip", ".json", ".pt"}


def _iter_move_candidates(models_dir: Path) -> Iterable[Path]:
    for p in sorted(models_dir.iterdir()):
        if p.is_dir():
            continue
        if p.suffix.lower() in VALID_SUFFIXES:
            continue
        yield p


def cleanup_models(models_dir: Path, archive_dir: Path, apply: bool) -> int:
    models_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)
    moved = 0

    for src in _iter_move_candidates(models_dir):
        dst = archive_dir / src.name
        if dst.exists():
            stem = src.stem or src.name
            suffix = src.suffix
            idx = 1
            while True:
                candidate = archive_dir / f"{stem}_{idx}{suffix}"
                if not candidate.exists():
                    dst = candidate
                    break
                idx += 1
        if apply:
            shutil.move(str(src), str(dst))
            print(f"moved {src} -> {dst}")
        else:
            print(f"would_move {src} -> {dst}")
        moved += 1
    print(f"done moved={moved} apply={apply}")
    return moved


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models_dir", type=Path, default=Path("models"))
    parser.add_argument("--archive_dir", type=Path, default=Path("models/archive"))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    cleanup_models(args.models_dir, args.archive_dir, args.apply)


if __name__ == "__main__":
    main()

