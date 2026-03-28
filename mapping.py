from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence, Tuple, Union

TileCandidate = Union[int, Tuple[int, ...]]
SlotCandidate = Tuple[int, TileCandidate]

ROWS = 4
COLS = 9
GRID_SIZE = ROWS * COLS

PLAYABLE_TILE_COUNT = 34
PAD_TILES = (34, 35)

ACTION_DISCARD_START = 0
ACTION_DISCARD_END = 33
ACTION_CHI_L = 34
ACTION_CHI_M = 35
ACTION_CHI_R = 36
ACTION_PON = 37
ACTION_MING_KONG = 38
ACTION_ADD_KONG = 39
ACTION_AN_KONG = 40
ACTION_HU = 41
ACTION_PASS = 42
ACTION_SLOT_START = 43
ACTION_SLOT_END = 46
ACTION_DIM = 47


def tile_to_row_col(tile_idx: int) -> Tuple[int, int]:
    if not 0 <= tile_idx < GRID_SIZE:
        raise ValueError(f"tile out of range: {tile_idx}")
    return tile_idx // COLS, tile_idx % COLS


def row_col_to_tile(row: int, col: int) -> int:
    if not 0 <= row < ROWS or not 0 <= col < COLS:
        raise ValueError(f"row/col out of range: ({row},{col})")
    return row * COLS + col


def tile_to_discard_action(tile_idx: int) -> int:
    if not 0 <= tile_idx <= ACTION_DISCARD_END:
        raise ValueError(f"tile is not discardable: {tile_idx}")
    return tile_idx


def discard_action_to_tile(action: int) -> int:
    if not ACTION_DISCARD_START <= action <= ACTION_DISCARD_END:
        raise ValueError(f"action is not a discard action: {action}")
    return action


def _candidate_key(cand: TileCandidate) -> Tuple[int, Tuple[int, ...]]:
    if isinstance(cand, int):
        return cand, (cand,)
    if not cand:
        return 10_000, ()
    minimum = min(cand)
    return minimum, tuple(cand)


def sort_candidates(candidates: Iterable[TileCandidate]) -> List[TileCandidate]:
    return sorted(candidates, key=_candidate_key)


@dataclass(frozen=True)
class SlotAssignment:
    primary_action: int
    primary_candidate: TileCandidate | None
    extra_slots: Dict[int, SlotCandidate]


def assign_candidates_to_slots(
    primary_action: int,
    candidates: Sequence[TileCandidate],
) -> SlotAssignment:
    if not (0 <= primary_action < ACTION_DIM):
        raise ValueError(f"invalid primary action: {primary_action}")

    sorted_candidates = sort_candidates(candidates)
    if not sorted_candidates:
        return SlotAssignment(primary_action=primary_action, primary_candidate=None, extra_slots={})

    extras: Dict[int, SlotCandidate] = {}
    for idx, cand in enumerate(sorted_candidates[1:5], start=ACTION_SLOT_START):
        extras[idx] = (primary_action, cand)

    return SlotAssignment(
        primary_action=primary_action,
        primary_candidate=sorted_candidates[0],
        extra_slots=extras,
    )


def assign_multi_action_candidates(
    primary_to_candidates: Dict[int, Sequence[TileCandidate]],
) -> Tuple[Dict[int, TileCandidate], Dict[int, SlotCandidate]]:
    primary_selected: Dict[int, TileCandidate] = {}
    extras: List[SlotCandidate] = []

    for action in sorted(primary_to_candidates.keys()):
        assigned = assign_candidates_to_slots(action, primary_to_candidates[action])
        if assigned.primary_candidate is not None:
            primary_selected[action] = assigned.primary_candidate
        extras.extend(assigned.extra_slots.values())

    extras = sorted(extras, key=lambda x: (_candidate_key(x[1]), x[0]))
    slot_map: Dict[int, SlotCandidate] = {}
    for action_slot, slot_content in zip(range(ACTION_SLOT_START, ACTION_SLOT_END + 1), extras):
        slot_map[action_slot] = slot_content
    return primary_selected, slot_map


def candidate_to_tile_index(candidate: TileCandidate) -> int:
    if isinstance(candidate, int):
        return candidate
    return min(candidate)
