from __future__ import annotations

import math
import random
from typing import Dict, List, Optional, Tuple

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from bots import MinLegalBot, OldPolicyBot, RandomBot, RuleBot
from engine import MahjongEngine, ReactionClaim
from mapping import (
    ACTION_ADD_KONG,
    ACTION_AN_KONG,
    ACTION_CHI_L,
    ACTION_CHI_M,
    ACTION_CHI_R,
    ACTION_DIM,
    ACTION_DISCARD_END,
    ACTION_HU,
    ACTION_MING_KONG,
    ACTION_PASS,
    ACTION_PON,
    PLAYABLE_TILE_COUNT,
    assign_multi_action_candidates,
)


class HangzhouMahjongEnv(gym.Env):
    metadata = {"render_modes": []}

    def __init__(
        self,
        hero_seat: int = 0,
        reward_mode: str = "log1p",
        max_internal_steps: int = 10_000,
        bot_epsilon: float = 0.08,
        enable_wealth_god: bool = True,
        protect_wealth_god_discard: bool = True,
        special_hu_types: Optional[List[str]] = None,
        enable_qiaoxiang: bool = False,
        wealth_god_can_meld: bool = True,
        qiaoxiang_fan_bonus: int = 1,
        base_score_unit: int = 10,
        score_cap: Optional[int] = None,
        draw_scoring_mode: str = "zero",
        use_opponent_pool: bool = False,
        opponent_pool_paths: Optional[List[str]] = None,
        opponent_replace_count: int = 1,
        opponent_mix: str = "rule:1.0",
    ):
        super().__init__()
        self.hero_seat = hero_seat
        self.reward_mode = reward_mode
        self.max_internal_steps = max_internal_steps
        self.bot_epsilon = bot_epsilon
        self.enable_wealth_god = enable_wealth_god
        self.protect_wealth_god_discard = protect_wealth_god_discard
        self.special_hu_types = special_hu_types
        self.enable_qiaoxiang = enable_qiaoxiang
        self.wealth_god_can_meld = wealth_god_can_meld
        self.qiaoxiang_fan_bonus = qiaoxiang_fan_bonus
        self.base_score_unit = base_score_unit
        self.score_cap = score_cap
        self.draw_scoring_mode = draw_scoring_mode
        self.use_opponent_pool = use_opponent_pool
        self.opponent_pool_paths = opponent_pool_paths or []
        self.opponent_replace_count = opponent_replace_count
        self.opponent_mix = opponent_mix
        self._opponent_mix_weights = self._parse_opponent_mix(opponent_mix)

        self.engine = MahjongEngine(
            enable_wealth_god=enable_wealth_god,
            protect_wealth_god_discard=protect_wealth_god_discard,
            special_hu_types=special_hu_types,
            enable_qiaoxiang=enable_qiaoxiang,
            wealth_god_can_meld=wealth_god_can_meld,
            qiaoxiang_fan_bonus=qiaoxiang_fan_bonus,
            base_score_unit=base_score_unit,
            score_cap=score_cap,
            draw_scoring_mode=draw_scoring_mode,
        )
        self.action_space = spaces.Discrete(ACTION_DIM)
        self.observation_space = spaces.Box(
            low=0.0,
            high=1.0,
            shape=(40, 4, 9),
            dtype=np.float32,
        )

        self._bots: Dict[int, RuleBot | OldPolicyBot | RandomBot | MinLegalBot] = {}
        self._action_context: Dict[int, Tuple[str, object]] = {}
        self._awaiting_hero_reaction = False
        self._hero_reaction_claims: Dict[str, List[int | Tuple[int, ...]]] = {}
        self._pending_bot_claims: List[ReactionClaim] = []
        self._last_trunc_debug: Dict[str, object] = {}
        self._seed: Optional[int] = None

    def __getstate__(self):
        # SubprocVecEnv may pickle bound methods (e.g., get_attr("action_masks")).
        # Opponent pool bots can hold loaded SB3 models with non-picklable closures.
        # Exclude runtime bot instances from pickled snapshots used for capability checks.
        state = dict(self.__dict__)
        state["_bots"] = {}
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)

    def reset(self, seed: Optional[int] = None, options: Optional[dict] = None):
        super().reset(seed=seed)
        self._seed = seed
        self.engine.reset(seed=seed)
        self._build_opponents(seed)
        self._awaiting_hero_reaction = False
        self._hero_reaction_claims = {}
        self._pending_bot_claims = []
        self._last_trunc_debug = {}

        truncated = self._fast_forward_until_hero_or_terminal()

        obs = self._get_observation()
        info = {"action_mask": self.action_masks()}
        if truncated:
            info.update(self._last_trunc_debug)
        return obs, info

    def action_masks(self) -> np.ndarray:
        mask = np.zeros(ACTION_DIM, dtype=bool)
        self._action_context = {}

        if self.engine.terminated:
            mask[ACTION_PASS] = True
            return mask

        hero_turn = (self.engine.phase == "myturn" and self.engine.actor == self.hero_seat) or (
            self.engine.phase == "reaction" and self._awaiting_hero_reaction
        )
        if not hero_turn:
            truncated = self._fast_forward_until_hero_or_terminal()
            if truncated and not self.engine.terminated:
                self.engine.terminated = True
                self.engine.phase = "terminal"
                self.engine.winner = None
                self.engine.scores = [0, 0, 0, 0]
            if self.engine.terminated:
                mask[ACTION_PASS] = True
                self._action_context[ACTION_PASS] = ("pass", None)
                return mask

        if self.engine.phase == "myturn" and self.engine.actor == self.hero_seat:
            mask, context = self._build_myturn_mask_for_seat(self.hero_seat)
            self._action_context = context
            # Hard rule: MyTurn pass is disabled.
            mask[ACTION_PASS] = False
            if not mask.any():
                discards = self.engine.legal_discards(self.hero_seat)
                if discards:
                    safe_tile = min(discards)
                    mask[safe_tile] = True
                    self._action_context[safe_tile] = ("discard", safe_tile)
                else:
                    mask[0] = True
                    self._action_context[0] = ("discard", 0)
            return mask

        if self.engine.phase == "reaction" and self._awaiting_hero_reaction:
            mask, context = self._build_reaction_mask_from_claims(self._hero_reaction_claims, include_pass=True)
            self._action_context = context
            # Hard rule: Reaction pass is always enabled.
            mask[ACTION_PASS] = True
            if not mask.any():
                mask[ACTION_PASS] = True
                self._action_context[ACTION_PASS] = ("pass", None)
            return mask

        # Safety fallback for unexpected state.
        if self.engine.phase == "reaction":
            mask[ACTION_PASS] = True
            self._action_context[ACTION_PASS] = ("pass", None)
        else:
            discards = self.engine.legal_discards(self.hero_seat)
            if discards:
                safe_tile = min(discards)
                mask[safe_tile] = True
                self._action_context[safe_tile] = ("discard", safe_tile)
        return mask

    def step(self, action: int):
        if self.engine.terminated:
            obs = self._get_observation()
            info = {"action_mask": self.action_masks()}
            return obs, 0.0, True, False, info

        mask = self.action_masks()
        decision_phase = "reaction" if (self.engine.phase == "reaction" and self._awaiting_hero_reaction) else "myturn"
        if action < 0 or action >= ACTION_DIM or not mask[action]:
            raise ValueError(f"illegal action {action}")

        truncated = False
        if self.engine.phase == "myturn" and self.engine.actor == self.hero_seat:
            self._apply_action_for_seat(self.hero_seat, action, self._action_context)
        elif self.engine.phase == "reaction" and self._awaiting_hero_reaction:
            self._resolve_hero_reaction(action)
        else:
            raise ValueError("step called when hero does not own decision")

        if not self.engine.terminated:
            truncated = self._fast_forward_until_hero_or_terminal()

        terminated = self.engine.terminated
        reward = self._compute_reward(terminated)
        obs = self._get_observation()
        info = {
            "action_mask": self.action_masks(),
            "decision_phase": decision_phase,
            "chosen_action": int(action),
            "illegal_action": False,
        }
        if truncated:
            info.update(self._last_trunc_debug)
            info["truncated_by_internal_limit"] = True
        else:
            info["truncated_by_internal_limit"] = False
        return obs, reward, terminated, truncated, info

    def _build_opponents(self, seed: Optional[int]) -> None:
        self._bots = {}
        base_rng = random.Random(seed)
        bot_seats = [seat for seat in range(4) if seat != self.hero_seat]
        replace_seats: List[int] = []

        if self.use_opponent_pool and self.opponent_pool_paths:
            count = max(0, min(self.opponent_replace_count, len(bot_seats)))
            replace_seats = base_rng.sample(bot_seats, count)

        for seat in bot_seats:
            if seat in replace_seats:
                model_path = base_rng.choice(self.opponent_pool_paths)
                self._bots[seat] = OldPolicyBot(model_path)
            else:
                self._bots[seat] = self._sample_mixed_opponent(base_rng, (seed or 0) + seat + 101)

    def _parse_opponent_mix(self, spec: str) -> List[Tuple[str, float]]:
        allowed = {"rule", "defensive", "aggressive", "random", "minlegal"}
        parts = [p.strip() for p in str(spec).split(",") if p.strip()]
        if not parts:
            return [("rule", 1.0)]

        parsed: List[Tuple[str, float]] = []
        for part in parts:
            if ":" in part:
                name, weight_raw = part.split(":", 1)
            else:
                name, weight_raw = part, "1.0"
            name = name.strip().lower()
            if name == "balanced":
                name = "rule"
            if name not in allowed:
                raise ValueError(f"unsupported opponent mix entry: {name}")
            weight = float(weight_raw)
            if weight <= 0.0:
                continue
            parsed.append((name, weight))

        if not parsed:
            raise ValueError("opponent_mix has no positive-weight entries")

        total = sum(w for _, w in parsed)
        return [(name, float(weight / total)) for name, weight in parsed]

    def _sample_mixed_opponent(self, rng: random.Random, seed: int) -> RuleBot | RandomBot | MinLegalBot:
        r = rng.random()
        cum = 0.0
        picked = "rule"
        for name, weight in self._opponent_mix_weights:
            cum += float(weight)
            if r <= cum:
                picked = name
                break

        if picked == "defensive":
            return RuleBot(epsilon=self.bot_epsilon, seed=seed, style="defensive")
        if picked == "aggressive":
            return RuleBot(epsilon=self.bot_epsilon, seed=seed, style="aggressive")
        if picked == "random":
            return RandomBot(seed=seed)
        if picked == "minlegal":
            return MinLegalBot()
        return RuleBot(epsilon=self.bot_epsilon, seed=seed, style="balanced")

    def _build_myturn_mask_for_seat(self, seat: int) -> Tuple[np.ndarray, Dict[int, Tuple[str, object]]]:
        mask = np.zeros(ACTION_DIM, dtype=bool)
        context: Dict[int, Tuple[str, object]] = {}

        for tile in self.engine.legal_discards(seat):
            mask[tile] = True
            context[tile] = ("discard", tile)

        self_candidates = self.engine.legal_self_action_candidates(seat)
        primary = {}
        if self_candidates["add_kong"]:
            primary[ACTION_ADD_KONG] = self_candidates["add_kong"]
        if self_candidates["an_kong"]:
            primary[ACTION_AN_KONG] = self_candidates["an_kong"]

        selected, slot_map = assign_multi_action_candidates(primary)
        for action, cand in selected.items():
            if action == ACTION_ADD_KONG:
                context[action] = ("add_kong", cand)
            elif action == ACTION_AN_KONG:
                context[action] = ("an_kong", cand)
            mask[action] = True

        for slot_action, (primary_action, cand) in slot_map.items():
            mask[slot_action] = True
            if primary_action == ACTION_ADD_KONG:
                context[slot_action] = ("add_kong", cand)
            elif primary_action == ACTION_AN_KONG:
                context[slot_action] = ("an_kong", cand)

        if self_candidates["hu"]:
            mask[ACTION_HU] = True
            context[ACTION_HU] = ("self_hu", None)

        return mask, context

    def _build_reaction_mask_from_claims(
        self,
        claims: Dict[str, List[int | Tuple[int, ...]]],
        include_pass: bool,
    ) -> Tuple[np.ndarray, Dict[int, Tuple[str, object]]]:
        mask = np.zeros(ACTION_DIM, dtype=bool)
        context: Dict[int, Tuple[str, object]] = {}

        primary = {}
        if claims.get("chi_l"):
            primary[ACTION_CHI_L] = claims["chi_l"]
        if claims.get("chi_m"):
            primary[ACTION_CHI_M] = claims["chi_m"]
        if claims.get("chi_r"):
            primary[ACTION_CHI_R] = claims["chi_r"]
        if claims.get("pon"):
            primary[ACTION_PON] = claims["pon"]
        if claims.get("ming_kong"):
            primary[ACTION_MING_KONG] = claims["ming_kong"]

        selected, slot_map = assign_multi_action_candidates(primary)

        for action, cand in selected.items():
            mask[action] = True
            context[action] = ("reaction", self._reaction_action_name(action), cand)

        for slot_action, (primary_action, cand) in slot_map.items():
            mask[slot_action] = True
            context[slot_action] = ("reaction", self._reaction_action_name(primary_action), cand)

        if claims.get("hu"):
            mask[ACTION_HU] = True
            context[ACTION_HU] = ("reaction", "hu", claims["hu"][0])

        if include_pass:
            mask[ACTION_PASS] = True
            context[ACTION_PASS] = ("pass", None)

        return mask, context

    def _reaction_action_name(self, action: int) -> str:
        if action == ACTION_CHI_L:
            return "chi_l"
        if action == ACTION_CHI_M:
            return "chi_m"
        if action == ACTION_CHI_R:
            return "chi_r"
        if action == ACTION_PON:
            return "pon"
        if action == ACTION_MING_KONG:
            return "ming_kong"
        raise ValueError(f"unknown reaction action {action}")

    def _apply_action_for_seat(self, seat: int, action: int, context: Dict[int, Tuple[str, object]]) -> None:
        action_type, payload = context[action]
        if action_type == "discard":
            self.engine.apply_discard(seat, int(payload))
            return
        if action_type == "self_hu":
            self.engine.apply_self_hu(seat)
            return
        if action_type == "an_kong":
            self.engine.apply_an_kong(seat, int(payload))
            return
        if action_type == "add_kong":
            self.engine.apply_add_kong(seat, int(payload))
            return
        raise ValueError(f"unsupported myturn action type {action_type}")

    def _resolve_hero_reaction(self, action: int) -> None:
        hero_claim = None
        if action != ACTION_PASS:
            info = self._action_context[action]
            if info[0] != "reaction":
                raise ValueError("hero selected non-reaction action in reaction phase")
            hero_claim = ReactionClaim(
                seat=self.hero_seat,
                action=str(info[1]),
                candidate=info[2],  # type: ignore[arg-type]
            )

        claims = list(self._pending_bot_claims)
        if hero_claim is not None:
            claims.append(hero_claim)

        winner = self.engine.resolve_reaction_priority(claims, self.engine.last_discarder or 0)
        if winner is None:
            self.engine.advance_after_no_claim()
        else:
            self.engine.apply_reaction(winner)

        self._awaiting_hero_reaction = False
        self._hero_reaction_claims = {}
        self._pending_bot_claims = []

    def _fast_forward_until_hero_or_terminal(self) -> bool:
        for _ in range(self.max_internal_steps):
            if self.engine.terminated:
                return False

            if self.engine.phase == "myturn":
                if self.engine.actor == self.hero_seat:
                    return False
                seat = self.engine.actor
                mask, context = self._build_myturn_mask_for_seat(seat)
                bot = self._bots[seat]
                action = bot.select_action(None, mask, env=self)
                if not mask[action]:
                    action = int(np.flatnonzero(mask)[0])
                self._apply_action_for_seat(seat, action, context)
                continue

            if self.engine.phase == "reaction":
                if self._prepare_or_resolve_reaction():
                    return False
                continue

            if self.engine.phase == "terminal":
                return False

        self._last_trunc_debug = {
            "truncated_reason": "max_internal_steps",
            "phase": self.engine.phase,
            "actor": self.engine.actor,
            "last_discard": self.engine.last_discard,
            "recent_actions": self.engine.get_recent_actions(),
        }
        return True

    def _prepare_or_resolve_reaction(self) -> bool:
        discarder = self.engine.last_discarder
        if discarder is None:
            return False

        hero_claims: Dict[str, List[int | Tuple[int, ...]]] = {}
        bot_claims: List[ReactionClaim] = []
        for seat in self.engine._clockwise_order(discarder):
            seat_claims = self.engine.legal_reaction_candidates(seat)
            if seat == self.hero_seat:
                hero_claims = seat_claims
            else:
                bot_claim = self._pick_bot_reaction_claim(seat, seat_claims)
                if bot_claim is not None:
                    bot_claims.append(bot_claim)

        hero_best = self._best_claim_from_claims(self.hero_seat, hero_claims)
        if hero_best is not None:
            probe = bot_claims + [hero_best]
            winner_probe = self.engine.resolve_reaction_priority(probe, discarder)
            if winner_probe is not None and winner_probe.seat == self.hero_seat:
                self._awaiting_hero_reaction = True
                self._hero_reaction_claims = hero_claims
                self._pending_bot_claims = bot_claims
                return True

        winner = self.engine.resolve_reaction_priority(bot_claims, discarder)
        if winner is None:
            self.engine.advance_after_no_claim()
        else:
            self.engine.apply_reaction(winner)
        self._awaiting_hero_reaction = False
        self._hero_reaction_claims = {}
        self._pending_bot_claims = []
        return False

    def _pick_bot_reaction_claim(
        self,
        seat: int,
        claims: Dict[str, List[int | Tuple[int, ...]]],
    ) -> Optional[ReactionClaim]:
        mask, context = self._build_reaction_mask_from_claims(claims, include_pass=True)
        bot = self._bots[seat]
        action = bot.select_action(None, mask, env=self)
        if action == ACTION_PASS:
            return None
        if action not in context or context[action][0] != "reaction":
            return None
        info = context[action]
        return ReactionClaim(seat=seat, action=str(info[1]), candidate=info[2])  # type: ignore[arg-type]

    def _best_claim_from_claims(
        self,
        seat: int,
        claims: Dict[str, List[int | Tuple[int, ...]]],
    ) -> Optional[ReactionClaim]:
        ordered_actions = ["hu", "ming_kong", "pon", "chi_l", "chi_m", "chi_r"]
        for act in ordered_actions:
            cands = claims.get(act, [])
            if cands:
                return ReactionClaim(seat=seat, action=act, candidate=cands[0])  # type: ignore[arg-type]
        return None

    def _compute_reward(self, terminated: bool) -> float:
        if not terminated:
            return 0.0
        hero = self.engine.scores[self.hero_seat]
        others = [self.engine.scores[s] for s in range(4) if s != self.hero_seat]
        raw = float(hero - (sum(others) / 3.0))
        if self.reward_mode == "log1p":
            return float(math.copysign(math.log1p(abs(raw)), raw))
        return raw

    def _get_observation(self) -> np.ndarray:
        obs = np.zeros(self.observation_space.shape, dtype=np.float32)
        hero = self.hero_seat

        hand = self.engine.hands[hero]
        for tile in range(PLAYABLE_TILE_COUNT):
            row, col = divmod(tile, 9)
            for level in range(4):
                if hand[tile] >= level + 1:
                    obs[level, row, col] = 1.0

        wg = self.engine.wealth_god
        if 0 <= wg < PLAYABLE_TILE_COUNT:
            wg_row, wg_col = divmod(wg, 9)
            obs[4, wg_row, wg_col] = 1.0

        if self.engine.last_discard is not None:
            ld_row, ld_col = divmod(self.engine.last_discard, 9)
            obs[5, ld_row, ld_col] = 1.0

        obs[6, :, :] = 1.0 if self.engine.phase == "myturn" and self.engine.actor == hero else 0.0
        obs[7, :, :] = self._normalized_discarder_pos()

        seat_order = [hero, (hero + 1) % 4, (hero + 2) % 4, (hero + 3) % 4]

        # Discards channels 8..23
        base = 8
        for i, seat in enumerate(seat_order):
            counts = self.engine.discards[seat]
            for tile in range(PLAYABLE_TILE_COUNT):
                row, col = divmod(tile, 9)
                for level in range(4):
                    if counts[tile] >= level + 1:
                        obs[base + i * 4 + level, row, col] = 1.0

        # Melds channels 24..39
        base = 24
        for i, seat in enumerate(seat_order):
            counts = self.engine.melds[seat]
            for tile in range(PLAYABLE_TILE_COUNT):
                row, col = divmod(tile, 9)
                for level in range(4):
                    if counts[tile] >= level + 1:
                        obs[base + i * 4 + level, row, col] = 1.0

        return obs

    def _normalized_discarder_pos(self) -> float:
        discarder = self.engine.last_discarder
        if discarder is None:
            return 0.0
        rel = (discarder - self.hero_seat) % 4
        if rel == 0:
            return 0.0
        if rel == 1:
            return 1.0 / 3.0
        if rel == 2:
            return 2.0 / 3.0
        return 1.0
