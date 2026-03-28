from __future__ import annotations

from typing import Dict, List, Optional

DEFAULT_SEED_SPLITS: Dict[str, Dict[str, int]] = {
    "dev": {"start": 1001, "end": 1500},
    "test": {"start": 1501, "end": 2000},
}


def resolve_seed_set(name: str) -> List[int]:
    key = str(name).strip().lower()
    if key not in DEFAULT_SEED_SPLITS:
        raise ValueError(f"unknown seed_set: {name}")
    start = int(DEFAULT_SEED_SPLITS[key]["start"])
    end = int(DEFAULT_SEED_SPLITS[key]["end"])
    if start > end:
        raise ValueError(f"invalid seed split range for {name}: {start}>{end}")
    return list(range(start, end + 1))


def classify_seed_set(seeds: List[int]) -> Optional[str]:
    for name in sorted(DEFAULT_SEED_SPLITS.keys()):
        if seeds == resolve_seed_set(name):
            return name
    return None
