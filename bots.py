from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np


def _legal_actions_from_mask(action_mask: np.ndarray) -> np.ndarray:
    legal = np.flatnonzero(action_mask)
    if legal.size == 0:
        raise ValueError("action mask contains no legal action")
    return legal


def _reaction_phase(env) -> bool:
    if env is None or not hasattr(env, "engine"):
        return False
    return bool(getattr(env.engine, "phase", "") == "reaction")


def _choose_discard(
    discard_actions: np.ndarray,
    style: str,
    env,
) -> int:
    if discard_actions.size == 0:
        raise ValueError("no discard actions available")

    if style == "aggressive":
        return int(discard_actions.max())

    if style == "defensive" and env is not None and hasattr(env, "engine"):
        # Heuristic: prefer tiles that are already frequently discarded table-wide.
        seen = np.zeros(34, dtype=np.int64)
        try:
            for seat_discards in getattr(env.engine, "discards", []):
                seen += np.asarray(seat_discards, dtype=np.int64)
            ordered = sorted((int(t) for t in discard_actions.tolist()), key=lambda t: (-int(seen[t]), t))
            return int(ordered[0])
        except Exception:
            pass

    # Balanced fallback.
    return int(discard_actions.min())


@dataclass
class RandomBot:
    seed: Optional[int] = None

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed)

    def reseed(self, seed: Optional[int]) -> None:
        self.rng = random.Random(seed)

    def select_action(self, obs: np.ndarray | None, action_mask: np.ndarray, env=None) -> int:
        legal = _legal_actions_from_mask(action_mask)
        return int(legal[self.rng.randrange(len(legal))])


@dataclass
class RuleBot:
    epsilon: float = 0.08
    seed: Optional[int] = None
    style: str = "balanced"

    def __post_init__(self) -> None:
        self.style = str(self.style).strip().lower()
        if self.style in ("rule", "default"):
            self.style = "balanced"
        if self.style not in {"balanced", "defensive", "aggressive"}:
            raise ValueError(f"unsupported RuleBot style: {self.style}")
        self.rng = random.Random(self.seed)

    def reseed(self, seed: Optional[int]) -> None:
        self.rng = random.Random(seed)

    def select_action(self, obs: np.ndarray | None, action_mask: np.ndarray, env=None) -> int:
        legal = _legal_actions_from_mask(action_mask)
        if self.rng.random() < self.epsilon:
            return int(legal[self.rng.randrange(len(legal))])

        reaction = _reaction_phase(env)

        if reaction and self.style == "defensive":
            if 41 in legal:
                return 41
            if 42 in legal:
                return 42

        if self.style == "aggressive":
            preferred_actions = (41, 38, 37, 34, 35, 36, 40, 39)
        elif self.style == "defensive":
            preferred_actions = (41, 40, 39, 38, 37, 34, 35, 36)
        else:
            # deterministic priorities:
            # hu > kong > pon > chi > discard (low tile) > pass
            preferred_actions = (41, 40, 39, 38, 37, 34, 35, 36)

        for preferred in preferred_actions:
            if preferred in legal:
                return int(preferred)
        discard_actions = legal[(legal >= 0) & (legal <= 33)]
        if discard_actions.size > 0:
            return _choose_discard(discard_actions, self.style, env=env)
        if 42 in legal:
            return 42
        return int(legal.min())


@dataclass
class MinLegalBot:
    def select_action(self, obs: np.ndarray | None, action_mask: np.ndarray, env=None) -> int:
        legal = _legal_actions_from_mask(action_mask)
        return int(legal.min())


class OldPolicyBot:
    def __init__(self, model_path: str, fallback: Optional[RuleBot] = None):
        self.model_path = Path(model_path)
        self.fallback = fallback or RuleBot(epsilon=0.0)
        self.model = None
        self._load_model()

    def _load_model(self) -> None:
        try:
            from sb3_contrib import MaskablePPO

            candidates = []
            if self.model_path.suffix == ".zip":
                candidates.append(self.model_path)
            else:
                # Prefer SB3 default checkpoint path when a basename is provided.
                candidates.append(self.model_path.with_suffix(".zip"))
                candidates.append(self.model_path)

            for candidate in candidates:
                if not candidate.exists():
                    continue
                try:
                    self.model = MaskablePPO.load(str(candidate))
                    return
                except Exception:
                    continue
        except Exception:
            self.model = None

    def select_action(self, obs: np.ndarray | None, action_mask: np.ndarray, env=None) -> int:
        if self.model is None or obs is None:
            return self.fallback.select_action(obs, action_mask, env=env)
        try:
            action, _ = self.model.predict(obs, deterministic=True, action_masks=action_mask)
            action = int(action)
            if action_mask[action]:
                return action
        except Exception:
            pass
        return self.fallback.select_action(obs, action_mask, env=env)
