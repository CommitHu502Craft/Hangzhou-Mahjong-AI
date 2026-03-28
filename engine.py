from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Deque, Dict, List, Optional, Sequence, Tuple

import numpy as np

from mapping import PLAYABLE_TILE_COUNT


@dataclass(frozen=True)
class ReactionClaim:
    seat: int
    action: str
    candidate: int | Tuple[int, ...]


class MahjongEngine:
    ACTION_PRIORITY = {
        "hu": 3,
        "ming_kong": 2,
        "pon": 2,
        "chi_l": 1,
        "chi_m": 1,
        "chi_r": 1,
    }

    ORPHAN_TILES: Tuple[int, ...] = (0, 8, 9, 17, 18, 26, 27, 28, 29, 30, 31, 32, 33)

    FAN_VALUES: Dict[str, int] = {
        "base": 1,
        "qidui": 2,
        "shisanyao": 6,
        "duiduihu": 2,
        "qingyise": 3,
        "hunyise": 2,
        "menqing": 1,
        "qiaoxiang": 1,
    }
    SUPPORTED_SPECIAL_HU_TYPES: Tuple[str, ...] = ("qidui", "shisanyao")

    def __init__(
        self,
        max_turns: int = 200,
        enable_wealth_god: bool = True,
        protect_wealth_god_discard: bool = True,
        special_hu_types: Optional[Sequence[str]] = None,
        enable_qiaoxiang: bool = False,
        wealth_god_can_meld: bool = True,
        qiaoxiang_fan_bonus: int = 1,
        base_score_unit: int = 10,
        score_cap: Optional[int] = None,
        draw_scoring_mode: str = "zero",
    ):
        self.max_turns = max_turns
        self.enable_wealth_god = enable_wealth_god
        self.protect_wealth_god_discard = protect_wealth_god_discard
        self.special_hu_types = self._normalize_special_hu_types(special_hu_types)
        self.enable_qiaoxiang = enable_qiaoxiang
        self.wealth_god_can_meld = wealth_god_can_meld
        self.qiaoxiang_fan_bonus = max(0, int(qiaoxiang_fan_bonus))
        self.base_score_unit = max(1, int(base_score_unit))
        self.score_cap = None if score_cap is None else max(1, int(score_cap))
        self.draw_scoring_mode = str(draw_scoring_mode)
        self.rng = random.Random()
        self.np_rng = np.random.default_rng()
        self.wall: List[int] = []
        self.hands: List[np.ndarray] = [np.zeros(PLAYABLE_TILE_COUNT, dtype=np.int8) for _ in range(4)]
        self.discards: List[np.ndarray] = [np.zeros(PLAYABLE_TILE_COUNT, dtype=np.int8) for _ in range(4)]
        self.melds: List[np.ndarray] = [np.zeros(PLAYABLE_TILE_COUNT, dtype=np.int8) for _ in range(4)]
        self.dealer = 0
        self.wealth_god = 0
        self.actor = 0
        self.phase = "myturn"
        self.last_discard: Optional[int] = None
        self.last_discarder: Optional[int] = None
        self.terminated = False
        self.winner: Optional[int] = None
        self.turn_counter = 0
        self.scores = [0, 0, 0, 0]
        self.recent_actions: Deque[Tuple[str, int, int]] = deque(maxlen=16)
        self.qiaoxiang_states: List[Dict[str, Any]] = [self._new_qiaoxiang_state() for _ in range(4)]
        self.win_details: Optional[Dict[str, Any]] = None

    def _normalize_special_hu_types(self, value: Optional[Sequence[str]]) -> Tuple[str, ...]:
        if value is None:
            return tuple(self.SUPPORTED_SPECIAL_HU_TYPES)
        ordered: List[str] = []
        seen = set()
        for item in value:
            name = str(item).strip().lower()
            if not name:
                continue
            if name not in self.SUPPORTED_SPECIAL_HU_TYPES:
                raise ValueError(f"unsupported special hu type: {name}")
            if name not in seen:
                seen.add(name)
                ordered.append(name)
        return tuple(ordered)

    def _is_special_hu_enabled(self, name: str) -> bool:
        return str(name).lower() in self.special_hu_types

    def reset(self, seed: Optional[int] = None) -> Dict[str, object]:
        self.rng = random.Random(seed)
        self.np_rng = np.random.default_rng(seed)

        self.wall = [tile for tile in range(PLAYABLE_TILE_COUNT) for _ in range(4)]
        self.rng.shuffle(self.wall)

        self.hands = [np.zeros(PLAYABLE_TILE_COUNT, dtype=np.int8) for _ in range(4)]
        self.discards = [np.zeros(PLAYABLE_TILE_COUNT, dtype=np.int8) for _ in range(4)]
        self.melds = [np.zeros(PLAYABLE_TILE_COUNT, dtype=np.int8) for _ in range(4)]

        for _ in range(13):
            for seat in range(4):
                tile = self.wall.pop()
                self.hands[seat][tile] += 1

        self.dealer = self.rng.randrange(4)
        self.wealth_god = self.rng.randrange(PLAYABLE_TILE_COUNT) if self.enable_wealth_god else -1

        if self.wall:
            self.hands[self.dealer][self.wall.pop()] += 1

        self.actor = self.dealer
        self.phase = "myturn"
        self.last_discard = None
        self.last_discarder = None
        self.terminated = False
        self.winner = None
        self.turn_counter = 0
        self.scores = [0, 0, 0, 0]
        self.qiaoxiang_states = [self._new_qiaoxiang_state() for _ in range(4)]
        self.win_details = None
        self.recent_actions.clear()
        return self.snapshot()

    def snapshot(self) -> Dict[str, object]:
        return {
            "dealer": self.dealer,
            "wealth_god": self.wealth_god,
            "actor": self.actor,
            "phase": self.phase,
            "wall_len": len(self.wall),
            "last_discard": self.last_discard,
            "last_discarder": self.last_discarder,
            "terminated": self.terminated,
            "winner": self.winner,
            "turn_counter": self.turn_counter,
            "rule_flags": {
                "enable_wealth_god": self.enable_wealth_god,
                "protect_wealth_god_discard": self.protect_wealth_god_discard,
                "special_hu_types": list(self.special_hu_types),
                "enable_qiaoxiang": self.enable_qiaoxiang,
                "wealth_god_can_meld": self.wealth_god_can_meld,
                "qiaoxiang_fan_bonus": self.qiaoxiang_fan_bonus,
                "base_score_unit": self.base_score_unit,
                "score_cap": self.score_cap,
                "draw_scoring_mode": self.draw_scoring_mode,
            },
            "qiaoxiang_states": [
                (
                    str(state["state"]),
                    str(state["activated_by"]),
                    int(state["activated_turn"]),
                )
                for state in self.qiaoxiang_states
            ],
            "win_details": self.win_details,
            "hands": [tuple(int(x) for x in hand.tolist()) for hand in self.hands],
            "discards": [tuple(int(x) for x in d.tolist()) for d in self.discards],
            "melds": [tuple(int(x) for x in m.tolist()) for m in self.melds],
        }

    def _new_qiaoxiang_state(self) -> Dict[str, Any]:
        return {
            "state": "idle",
            "activated_by": "",
            "activated_turn": -1,
        }

    def is_qiaoxiang_active(self, seat: int) -> bool:
        if not self.enable_qiaoxiang:
            return False
        if not (0 <= seat < 4):
            return False
        if seat >= len(self.qiaoxiang_states):
            return False
        return str(self.qiaoxiang_states[seat]["state"]) == "active"

    def _activate_qiaoxiang(self, seat: int, source: str) -> None:
        if not self.enable_qiaoxiang:
            return
        if seat >= len(self.qiaoxiang_states):
            return
        state = self.qiaoxiang_states[seat]
        if str(state["state"]) == "active":
            return
        state["state"] = "active"
        state["activated_by"] = source
        state["activated_turn"] = self.turn_counter
        self.recent_actions.append(("qiaoxiang", seat, -1))

    def _finalize_qiaoxiang_states(self, winner: Optional[int]) -> None:
        if not self.enable_qiaoxiang:
            return
        for seat, state in enumerate(self.qiaoxiang_states):
            curr = str(state["state"])
            if curr != "active":
                continue
            if winner is None:
                state["state"] = "resolved_draw"
            elif seat == winner:
                state["state"] = "resolved_win"
            else:
                state["state"] = "resolved_lose"

    def legal_discards(self, seat: int) -> List[int]:
        discards = [tile for tile in range(PLAYABLE_TILE_COUNT) if self.hands[seat][tile] > 0]
        if not self.protect_wealth_god_discard:
            return discards

        wildcard_tile = self._wildcard_tile()
        if wildcard_tile is None:
            return discards
        if wildcard_tile in discards and len(discards) > 1:
            non_wild = [tile for tile in discards if tile != wildcard_tile]
            if non_wild:
                return non_wild
        return discards

    def legal_self_action_candidates(self, seat: int) -> Dict[str, List[int]]:
        hand = self.hands[seat]
        if self.is_qiaoxiang_active(seat):
            an_kong: List[int] = []
            add_kong: List[int] = []
        else:
            an_kong = [tile for tile in range(PLAYABLE_TILE_COUNT) if hand[tile] >= 4]
            add_kong = [tile for tile in range(PLAYABLE_TILE_COUNT) if hand[tile] >= 1 and self.melds[seat][tile] >= 3]
            wildcard_tile = self._wildcard_tile()
            if wildcard_tile is not None and not self.wealth_god_can_meld:
                an_kong = [tile for tile in an_kong if tile != wildcard_tile]
                add_kong = [tile for tile in add_kong if tile != wildcard_tile]
        hu = [1] if self._can_self_hu(seat) else []
        return {
            "an_kong": an_kong,
            "add_kong": add_kong,
            "hu": hu,
        }

    def _can_self_hu(self, seat: int) -> bool:
        hand = self.hands[seat]
        return self._is_hu_hand(hand)

    def _is_hu_hand(self, hand: np.ndarray) -> bool:
        if self._is_standard_win_hand(hand):
            return True
        if self._is_special_hu_enabled("qidui") and self._is_seven_pairs_win(hand):
            return True
        if self._is_special_hu_enabled("shisanyao") and self._is_thirteen_orphans_win(hand):
            return True
        return False

    def _is_standard_win_hand(self, hand: np.ndarray) -> bool:
        wildcard_tile = self._wildcard_tile()
        if wildcard_tile is None:
            return self._is_standard_win_hand_no_wild(hand)
        return self._is_standard_win_hand_with_wild(hand, wildcard_tile)

    def _is_standard_win_hand_no_wild(self, hand: np.ndarray) -> bool:
        if int(hand.sum()) % 3 != 2:
            return False

        base = hand.astype(np.int16, copy=True)
        for pair_tile in range(PLAYABLE_TILE_COUNT):
            if base[pair_tile] < 2:
                continue
            base[pair_tile] -= 2
            if self._can_form_all_melds(tuple(int(x) for x in base.tolist())):
                base[pair_tile] += 2
                return True
            base[pair_tile] += 2
        return False

    def _is_standard_win_hand_with_wild(self, hand: np.ndarray, wildcard_tile: int) -> bool:
        if int(hand.sum()) % 3 != 2:
            return False

        base = hand.astype(np.int16, copy=True)
        wild_count = int(base[wildcard_tile])
        base[wildcard_tile] = 0

        base_tuple = tuple(int(x) for x in base.tolist())
        for pair_tile in range(PLAYABLE_TILE_COUNT):
            if pair_tile == wildcard_tile:
                continue
            have = int(base[pair_tile])
            need_pair = max(0, 2 - have)
            if need_pair > wild_count:
                continue

            used_tile = min(2, have)
            base[pair_tile] -= used_tile
            if MahjongEngine._can_form_all_melds_with_wild(
                tuple(int(x) for x in base.tolist()),
                wild_count - need_pair,
            ):
                base[pair_tile] += used_tile
                return True
            base[pair_tile] += used_tile

        if wild_count >= 2 and MahjongEngine._can_form_all_melds_with_wild(base_tuple, wild_count - 2):
            return True
        return False

    @staticmethod
    @lru_cache(maxsize=100_000)
    def _can_form_all_melds(hand_counts: Tuple[int, ...]) -> bool:
        for tile, count in enumerate(hand_counts):
            if count > 0:
                break
        else:
            return True

        counts = list(hand_counts)

        if counts[tile] >= 3:
            counts[tile] -= 3
            if MahjongEngine._can_form_all_melds(tuple(counts)):
                return True
            counts[tile] += 3

        if tile < 27 and (tile % 9) <= 6:
            t1, t2 = tile + 1, tile + 2
            if counts[t1] > 0 and counts[t2] > 0:
                counts[tile] -= 1
                counts[t1] -= 1
                counts[t2] -= 1
                if MahjongEngine._can_form_all_melds(tuple(counts)):
                    return True

        return False

    @staticmethod
    @lru_cache(maxsize=200_000)
    def _can_form_all_melds_with_wild(hand_counts: Tuple[int, ...], wildcards: int) -> bool:
        total = int(sum(hand_counts)) + int(wildcards)
        if total % 3 != 0:
            return False

        for tile, count in enumerate(hand_counts):
            if count > 0:
                break
        else:
            return wildcards % 3 == 0

        counts = list(hand_counts)

        take = min(3, counts[tile])
        need_wild = 3 - take
        if need_wild <= wildcards:
            counts[tile] -= take
            if MahjongEngine._can_form_all_melds_with_wild(tuple(counts), wildcards - need_wild):
                return True
            counts[tile] += take

        if tile < 27 and (tile % 9) <= 6:
            missing = 0
            removed: List[int] = []
            for t in (tile, tile + 1, tile + 2):
                if counts[t] > 0:
                    counts[t] -= 1
                    removed.append(t)
                else:
                    missing += 1
            if missing <= wildcards and MahjongEngine._can_form_all_melds_with_wild(tuple(counts), wildcards - missing):
                return True
            for t in removed:
                counts[t] += 1

        return False

    @staticmethod
    @lru_cache(maxsize=200_000)
    def _can_form_triplets_only_with_wild(hand_counts: Tuple[int, ...], wildcards: int) -> bool:
        total = int(sum(hand_counts)) + int(wildcards)
        if total % 3 != 0:
            return False

        need = 0
        for c in hand_counts:
            rem = int(c) % 3
            if rem != 0:
                need += 3 - rem
        if need > wildcards:
            return False
        return (wildcards - need) % 3 == 0

    def _wildcard_tile(self) -> Optional[int]:
        if self.enable_wealth_god and 0 <= self.wealth_god < PLAYABLE_TILE_COUNT:
            return int(self.wealth_god)
        return None

    def _is_seven_pairs_win(self, hand: np.ndarray) -> bool:
        if int(hand.sum()) != 14:
            return False

        wildcard_tile = self._wildcard_tile()
        if wildcard_tile is None:
            return self._is_seven_pairs_no_wild(hand)
        return self._is_seven_pairs_with_wild(hand, wildcard_tile)

    def _is_seven_pairs_no_wild(self, hand: np.ndarray) -> bool:
        pair_count = 0
        for tile in range(PLAYABLE_TILE_COUNT):
            c = int(hand[tile])
            if c % 2 != 0:
                return False
            pair_count += c // 2
        return pair_count == 7

    def _is_seven_pairs_with_wild(self, hand: np.ndarray, wildcard_tile: int) -> bool:
        base = hand.astype(np.int16, copy=True)
        wild_count = int(base[wildcard_tile])
        base[wildcard_tile] = 0

        pair_count = 0
        single_count = 0
        for tile in range(PLAYABLE_TILE_COUNT):
            if tile == wildcard_tile:
                continue
            c = int(base[tile])
            pair_count += c // 2
            single_count += c % 2

        if single_count > wild_count:
            return False
        wild_left = wild_count - single_count
        pair_count += single_count
        pair_count += wild_left // 2
        return pair_count >= 7

    def _is_thirteen_orphans_win(self, hand: np.ndarray) -> bool:
        if int(hand.sum()) != 14:
            return False

        wildcard_tile = self._wildcard_tile()
        if wildcard_tile is None:
            return self._is_thirteen_orphans_no_wild(hand)
        return self._is_thirteen_orphans_with_wild(hand, wildcard_tile)

    def _is_thirteen_orphans_no_wild(self, hand: np.ndarray) -> bool:
        orphan_set = set(self.ORPHAN_TILES)
        for tile in range(PLAYABLE_TILE_COUNT):
            if tile not in orphan_set and int(hand[tile]) > 0:
                return False

        pair_found = False
        for tile in self.ORPHAN_TILES:
            c = int(hand[tile])
            if c == 0:
                return False
            if c >= 2:
                pair_found = True
        return pair_found

    def _is_thirteen_orphans_with_wild(self, hand: np.ndarray, wildcard_tile: int) -> bool:
        base = hand.astype(np.int16, copy=True)
        wild_count = int(base[wildcard_tile])
        base[wildcard_tile] = 0

        orphan_set = set(self.ORPHAN_TILES)
        for tile in range(PLAYABLE_TILE_COUNT):
            if tile in orphan_set:
                continue
            if int(base[tile]) > 0:
                return False

        missing = 0
        extra = 0
        for tile in self.ORPHAN_TILES:
            c = int(base[tile])
            if c == 0:
                missing += 1
            else:
                extra += c - 1

        if missing > wild_count:
            return False
        wild_left = wild_count - missing
        return (extra + wild_left) >= 1

    def _is_all_pungs_win(self, hand: np.ndarray) -> bool:
        if int(hand.sum()) % 3 != 2:
            return False

        wildcard_tile = self._wildcard_tile()
        if wildcard_tile is None:
            return self._is_all_pungs_no_wild(hand)
        return self._is_all_pungs_with_wild(hand, wildcard_tile)

    def _is_all_pungs_no_wild(self, hand: np.ndarray) -> bool:
        base = hand.astype(np.int16, copy=True)
        for pair_tile in range(PLAYABLE_TILE_COUNT):
            if base[pair_tile] < 2:
                continue
            base[pair_tile] -= 2
            ok = all((int(c) % 3) == 0 for c in base)
            base[pair_tile] += 2
            if ok:
                return True
        return False

    def _is_all_pungs_with_wild(self, hand: np.ndarray, wildcard_tile: int) -> bool:
        base = hand.astype(np.int16, copy=True)
        wild_count = int(base[wildcard_tile])
        base[wildcard_tile] = 0

        base_tuple = tuple(int(x) for x in base.tolist())
        for pair_tile in range(PLAYABLE_TILE_COUNT):
            if pair_tile == wildcard_tile:
                continue
            have = int(base[pair_tile])
            need_pair = max(0, 2 - have)
            if need_pair > wild_count:
                continue
            used = min(2, have)
            base[pair_tile] -= used
            if MahjongEngine._can_form_triplets_only_with_wild(tuple(int(x) for x in base.tolist()), wild_count - need_pair):
                base[pair_tile] += used
                return True
            base[pair_tile] += used

        if wild_count >= 2 and MahjongEngine._can_form_triplets_only_with_wild(base_tuple, wild_count - 2):
            return True
        return False

    def legal_reaction_candidates(self, seat: int) -> Dict[str, List[int | Tuple[int, ...]]]:
        out: Dict[str, List[int | Tuple[int, ...]]] = {
            "hu": [],
            "ming_kong": [],
            "pon": [],
            "chi_l": [],
            "chi_m": [],
            "chi_r": [],
        }
        if self.last_discard is None or self.last_discarder is None or seat == self.last_discarder:
            return out

        tile = self.last_discard
        hand = self.hands[seat]
        wildcard_tile = self._wildcard_tile()
        can_meld_wild = self.wealth_god_can_meld or wildcard_tile is None
        test_hand = hand.astype(np.int16, copy=True)
        test_hand[tile] += 1
        if self._is_hu_hand(test_hand):
            out["hu"] = [tile]

        if self.is_qiaoxiang_active(seat):
            return out

        if hand[tile] >= 3 and (can_meld_wild or tile != wildcard_tile):
            out["ming_kong"] = [tile]
        if hand[tile] >= 2 and (can_meld_wild or tile != wildcard_tile):
            out["pon"] = [tile]

        if seat == (self.last_discarder + 1) % 4 and tile < 27:
            suit = tile // 9
            idx = tile % 9
            chi_seen = {"chi_l": set(), "chi_m": set(), "chi_r": set()}
            for start in (idx - 2, idx - 1, idx):
                if start < 0 or start + 2 > 8:
                    continue
                seq = (suit * 9 + start, suit * 9 + start + 1, suit * 9 + start + 2)
                if tile not in seq:
                    continue
                needed = [t for t in seq if t != tile]
                if not can_meld_wild:
                    if tile == wildcard_tile or any(t == wildcard_tile for t in needed):
                        continue
                if not self._can_consume_for_chi(
                    hand=hand,
                    needed=needed,
                    wildcard_tile=wildcard_tile,
                    allow_wild_substitute=bool(can_meld_wild),
                    apply=False,
                ):
                    continue

                pos = seq.index(tile)
                if pos == 0 and seq not in chi_seen["chi_l"]:
                    out["chi_l"].append(seq)
                    chi_seen["chi_l"].add(seq)
                elif pos == 1 and seq not in chi_seen["chi_m"]:
                    out["chi_m"].append(seq)
                    chi_seen["chi_m"].add(seq)
                elif pos == 2 and seq not in chi_seen["chi_r"]:
                    out["chi_r"].append(seq)
                    chi_seen["chi_r"].add(seq)

        for key in out:
            out[key] = sorted(out[key], key=lambda c: c if isinstance(c, int) else (min(c), c))
        return out

    def resolve_reaction_priority(
        self,
        claims: Sequence[ReactionClaim],
        discarder: int,
    ) -> Optional[ReactionClaim]:
        if not claims:
            return None
        max_p = max(self.ACTION_PRIORITY[c.action] for c in claims)
        top = [c for c in claims if self.ACTION_PRIORITY[c.action] == max_p]
        seat_order = self._clockwise_order(discarder)
        for seat in seat_order:
            seat_claims = [c for c in top if c.seat == seat]
            if seat_claims:
                seat_claims.sort(key=lambda c: (c.action, c.candidate if isinstance(c.candidate, int) else min(c.candidate)))
                return seat_claims[0]
        return None

    def _clockwise_order(self, from_seat: int) -> List[int]:
        return [((from_seat + i) % 4) for i in range(1, 5)]

    def draw_tile(self, seat: int) -> bool:
        if not self.wall:
            self.terminated = True
            self.winner = None
            self._set_draw_scores()
            self._finalize_qiaoxiang_states(None)
            return False
        tile = self.wall.pop()
        self.hands[seat][tile] += 1
        self.recent_actions.append(("draw", seat, tile))
        return True

    def apply_discard(self, seat: int, tile: int) -> None:
        if self.terminated:
            return
        if self.phase != "myturn" or self.actor != seat:
            raise ValueError("discard out of turn")
        if self.hands[seat][tile] <= 0:
            raise ValueError(f"seat {seat} cannot discard tile {tile}")
        self.hands[seat][tile] -= 1
        self.discards[seat][tile] = min(4, self.discards[seat][tile] + 1)
        self.last_discard = tile
        self.last_discarder = seat
        self.phase = "reaction"
        self.actor = (seat + 1) % 4
        self.turn_counter += 1
        self.recent_actions.append(("discard", seat, tile))
        if self.turn_counter >= self.max_turns:
            self.terminated = True
            self.winner = None
            self._set_draw_scores()
            self._finalize_qiaoxiang_states(None)

    def apply_self_hu(self, seat: int) -> None:
        if self.terminated:
            return
        self.phase = "terminal"
        self.actor = seat
        self.terminated = True
        self.winner = seat
        self.win_details = self._build_win_details(
            winner=seat,
            win_mode="self_hu",
            win_tile=None,
            discarder=None,
        )
        self.scores = list(self.win_details["scores"])
        self._finalize_qiaoxiang_states(seat)
        self.recent_actions.append(("self_hu", seat, -1))

    def apply_an_kong(self, seat: int, tile: int) -> None:
        if self.hands[seat][tile] < 4:
            raise ValueError("invalid an kong")
        self.hands[seat][tile] -= 4
        self.melds[seat][tile] += 4
        self._activate_qiaoxiang(seat, "an_kong")
        self.recent_actions.append(("an_kong", seat, tile))
        self.phase = "myturn"
        self.actor = seat
        self.draw_tile(seat)

    def apply_add_kong(self, seat: int, tile: int) -> None:
        if self.hands[seat][tile] < 1 or self.melds[seat][tile] < 3:
            raise ValueError("invalid add kong")
        self.hands[seat][tile] -= 1
        self.melds[seat][tile] += 1
        self._activate_qiaoxiang(seat, "add_kong")
        self.recent_actions.append(("add_kong", seat, tile))
        self.phase = "myturn"
        self.actor = seat
        self.draw_tile(seat)

    def apply_reaction(self, claim: ReactionClaim) -> None:
        if self.terminated:
            return
        if claim.action == "hu":
            hu_tile = int(claim.candidate)
            self.terminated = True
            self.phase = "terminal"
            self.actor = claim.seat
            self.winner = claim.seat
            self.win_details = self._build_win_details(
                winner=claim.seat,
                win_mode="dian_hu",
                win_tile=hu_tile,
                discarder=self.last_discarder,
            )
            self.scores = list(self.win_details["scores"])
            self._finalize_qiaoxiang_states(claim.seat)
            self.recent_actions.append(("hu", claim.seat, hu_tile))
            self._clear_last_discard()
            return
        if claim.action == "ming_kong":
            tile = int(claim.candidate)
            if self.hands[claim.seat][tile] < 3:
                raise ValueError("invalid ming kong")
            self.hands[claim.seat][tile] -= 3
            self.melds[claim.seat][tile] += 4
            self._activate_qiaoxiang(claim.seat, "ming_kong")
            self.recent_actions.append(("ming_kong", claim.seat, tile))
            self._clear_last_discard()
            self.phase = "myturn"
            self.actor = claim.seat
            self.draw_tile(claim.seat)
            return
        if claim.action == "pon":
            tile = int(claim.candidate)
            if self.hands[claim.seat][tile] < 2:
                raise ValueError("invalid pon")
            self.hands[claim.seat][tile] -= 2
            self.melds[claim.seat][tile] += 3
            self.recent_actions.append(("pon", claim.seat, tile))
            self._clear_last_discard()
            self.phase = "myturn"
            self.actor = claim.seat
            return
        if claim.action in ("chi_l", "chi_m", "chi_r"):
            if not isinstance(claim.candidate, tuple):
                raise ValueError("invalid chi candidate")
            seq = tuple(claim.candidate)
            discarded = self.last_discard
            if discarded is None:
                raise ValueError("missing discarded tile for chi")
            wildcard_tile = self._wildcard_tile()
            can_use_wild = self.wealth_god_can_meld and wildcard_tile is not None
            needed = [tile for tile in seq if tile != discarded]
            if wildcard_tile is not None and (discarded == wildcard_tile or any(t == wildcard_tile for t in needed)):
                if not can_use_wild:
                    raise ValueError("invalid chi")
            if not self._can_consume_for_chi(
                hand=self.hands[claim.seat],
                needed=needed,
                wildcard_tile=wildcard_tile,
                allow_wild_substitute=bool(can_use_wild),
                apply=True,
            ):
                raise ValueError("invalid chi")
            for tile in seq:
                self.melds[claim.seat][tile] += 1
            self.recent_actions.append((claim.action, claim.seat, min(seq)))
            self._clear_last_discard()
            self.phase = "myturn"
            self.actor = claim.seat
            return
        raise ValueError(f"unsupported reaction action: {claim.action}")

    def _can_consume_for_chi(
        self,
        hand: np.ndarray,
        needed: Sequence[int],
        wildcard_tile: Optional[int],
        allow_wild_substitute: bool,
        apply: bool,
    ) -> bool:
        temp = hand.astype(np.int16, copy=True)
        for tile in needed:
            if allow_wild_substitute and wildcard_tile is not None:
                # Wealth-god tile is consumed as wildcard budget (including when target tile equals wealth-god).
                if tile == wildcard_tile:
                    if temp[wildcard_tile] <= 0:
                        return False
                    temp[wildcard_tile] -= 1
                    continue
                if temp[tile] > 0:
                    temp[tile] -= 1
                    continue
                if temp[wildcard_tile] > 0:
                    temp[wildcard_tile] -= 1
                    continue
                return False
            else:
                if temp[tile] <= 0:
                    return False
                temp[tile] -= 1

        if apply:
            hand[:] = temp.astype(hand.dtype, copy=False)
        return True

    def advance_after_no_claim(self) -> None:
        if self.last_discarder is None:
            return
        next_seat = (self.last_discarder + 1) % 4
        self._clear_last_discard()
        self.phase = "myturn"
        self.actor = next_seat
        self.draw_tile(next_seat)

    def get_recent_actions(self) -> List[Tuple[str, int, int]]:
        return list(self.recent_actions)

    def _clear_last_discard(self) -> None:
        self.last_discard = None
        self.last_discarder = None

    def _build_win_details(
        self,
        winner: int,
        win_mode: str,
        win_tile: Optional[int],
        discarder: Optional[int],
    ) -> Dict[str, Any]:
        hand = self.hands[winner].astype(np.int16, copy=True)
        if win_mode == "dian_hu" and win_tile is not None:
            hand[win_tile] += 1

        fan_total, fan_types = self._compute_local_fans(winner, hand)
        scores = self._score_from_fans(winner, fan_total, win_mode, discarder)
        return {
            "winner": int(winner),
            "win_mode": str(win_mode),
            "win_tile": int(win_tile) if win_tile is not None else None,
            "discarder": int(discarder) if discarder is not None else None,
            "fan_total": int(fan_total),
            "fan_types": fan_types,
            "qiaoxiang_active": bool(self.is_qiaoxiang_active(winner)),
            "scores": scores,
        }

    def _compute_local_fans(self, seat: int, hand: np.ndarray) -> Tuple[int, List[str]]:
        fan_total = int(self.FAN_VALUES["base"])
        fan_types: List[str] = ["base"]

        is_shisanyao = self._is_special_hu_enabled("shisanyao") and self._is_thirteen_orphans_win(hand)
        is_qidui = self._is_special_hu_enabled("qidui") and self._is_seven_pairs_win(hand)
        is_duidui = self._is_all_pungs_win(hand)

        if is_shisanyao:
            fan_total += int(self.FAN_VALUES["shisanyao"])
            fan_types.append("shisanyao")
        elif is_qidui:
            fan_total += int(self.FAN_VALUES["qidui"])
            fan_types.append("qidui")
        elif is_duidui:
            fan_total += int(self.FAN_VALUES["duiduihu"])
            fan_types.append("duiduihu")

        color_fan = self._detect_color_fan(hand)
        if color_fan is not None:
            fan_total += int(self.FAN_VALUES[color_fan])
            fan_types.append(color_fan)

        meld_count = int(self.melds[seat].sum()) if 0 <= seat < len(self.melds) else 0
        if meld_count == 0:
            fan_total += int(self.FAN_VALUES["menqing"])
            fan_types.append("menqing")

        if self.is_qiaoxiang_active(seat):
            if self.qiaoxiang_fan_bonus > 0:
                fan_total += self.qiaoxiang_fan_bonus
                fan_types.append("qiaoxiang")

        fan_total = max(1, fan_total)
        return fan_total, fan_types

    def _detect_color_fan(self, hand: np.ndarray) -> Optional[str]:
        wildcard_tile = self._wildcard_tile()
        suits = set()
        has_honor = False

        for tile in range(PLAYABLE_TILE_COUNT):
            c = int(hand[tile])
            if c <= 0:
                continue
            if wildcard_tile is not None and tile == wildcard_tile:
                continue
            if tile < 27:
                suits.add(tile // 9)
            else:
                has_honor = True

        if len(suits) != 1:
            return None
        if has_honor:
            return "hunyise"
        return "qingyise"

    def _score_from_fans(
        self,
        winner: int,
        fan_total: int,
        win_mode: str,
        discarder: Optional[int],
    ) -> List[int]:
        unit = self.base_score_unit * int(max(1, fan_total))
        if self.score_cap is not None:
            unit = min(unit, self.score_cap)
        scores = [0, 0, 0, 0]

        if win_mode == "self_hu" or discarder is None or discarder == winner:
            for seat in range(4):
                if seat == winner:
                    scores[seat] = 3 * unit
                else:
                    scores[seat] = -unit
            return scores

        scores[winner] = 3 * unit
        scores[discarder] = -3 * unit
        return scores

    def _set_draw_scores(self) -> None:
        if self.draw_scoring_mode == "zero":
            self.scores = [0, 0, 0, 0]
        else:
            self.scores = [0, 0, 0, 0]
        self.win_details = {
            "winner": None,
            "win_mode": "draw",
            "fan_total": 0,
            "fan_types": [],
            "qiaoxiang_active": False,
            "scores": [0, 0, 0, 0],
        }
