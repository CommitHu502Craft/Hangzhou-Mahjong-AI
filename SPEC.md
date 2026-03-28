# SPEC.md

Version: v1.1  
Last Updated: 2026-02-22

## 1. Runtime and Dependency

- Python: `3.11` (fallback `3.10`)
- `gymnasium==0.29.1`
- `stable-baselines3==2.3.0`
- `sb3-contrib==2.3.0`
- `numpy<2.0.0`
- `torch>=2.0.0`

## 2. Tile Mapping (fixed)

Board grid is `(4, 9)` with two PAD cells in row 3:

- Row0: 万 `1..9` -> idx `0..8`
- Row1: 筒 `1..9` -> idx `9..17`
- Row2: 条 `1..9` -> idx `18..26`
- Row3: 东南西北中发白 -> idx `27..33`, PAD idx `34..35`

Action IDs `0..33` map one-to-one to playable tile idx `0..33`.  
PAD tiles are never playable actions.

## 3. Action Space

Type: `Discrete(47)`

- `0..33`: Discard(tile idx)
- `34`: Chi-L
- `35`: Chi-M
- `36`: Chi-R
- `37`: Pon
- `38`: Ming Kong
- `39`: Add Kong
- `40`: An Kong
- `41`: Hu
- `42`: Pass
- `43..46`: General candidate slots (multi-option extension)

## 4. Candidate Slot Rule (v1.1 fixed)

`43~46` are not kong-only slots; they are shared for all multi-candidate actions.

Rule:
1. Build candidate list for the current state (chi variants, kong options, wildcard alternatives).
2. Sort by `tile_index` ascending; combo candidate uses lexicographic order.
3. Primary action slot keeps candidate #0.
4. `43~46` keep candidate #1..#4.
5. Missing candidates are masked `False`.

Example:
- An Kong candidates: `[tile 3, tile 19, tile 22]`
- Slot `40` -> tile 3
- Slot `43` -> tile 19
- Slot `44` -> tile 22
- Slot `45,46` invalid

## 5. Observation Space

Type: `Box(low=0, high=1, shape=(40,4,9), dtype=float32)`

Channels:
- `0..3`: Hero hand count-to-4
- `4`: Wealth God indicator
- `5`: Last Discard indicator
- `6`: Phase flag (`1=MyTurn`, `0=Reaction`)
- `7`: Discarder Pos normalized
- `8..23`: Discards by relative seat (`Self/Down/Oppo/Up` x `>=1..>=4`)
- `24..39`: Melds by relative seat (`Self/Down/Oppo/Up` x `>=1..>=4`, MVP coarse)

Discarder Pos normalization (must not exceed Box high=1):
- self/none -> `0.0`
- down -> `1/3`
- oppo -> `2/3`
- up -> `1.0`

## 6. Gymnasium Interface

- `reset(seed=None, options=None) -> (obs, info)`
- `step(action) -> (obs, reward, terminated, truncated, info)`
- `action_masks() -> np.ndarray[bool]` shape `(47,)`

`info` must include `action_mask`, and on truncation include debug keys.

## 7. Step Fast-forward Loop

Single-agent environment behavior:
1. Validate action by mask.
2. Execute Hero action.
3. Internally fast-forward engine (other players + arbitration).
4. Stop when:
   - Hero reaches next decision point, or
   - terminal game state.

Safety:
- `max_internal_steps` required (default `10000`).
- If exceeded: `truncated=True` and add debug info (`phase`, `actor`, `last_discard`, `recent_actions`).

## 8. Reaction Priority Contract

Priority is deterministic:
- `Hu > 杠/碰 > 吃`
- Same priority tie-breaker: clockwise from discarder's next seat.

Hero receives reaction observation only when Hero actually owns the decision right.

## 9. Action Mask Rules

Mask must be phase-bound:
- MyTurn: discard/kong/hu-like self actions only
- Reaction: response actions + pass

Hard rules:
- Reaction phase: `Pass(42)=True`
- MyTurn phase: `Pass(42)=False`

Last defense (must exist):
- If all False in Reaction -> force `mask[42]=True`
- If all False in MyTurn -> force one safe discard action

## 10. Seed Determinism

`reset(seed=x)` controls all randomness:
- deck order
- dealer seat
- wealth-god indicator
- bot exploration randomness

## 11. Wildcard (财神) MVP Strategy

MVP deterministic strategy:
- Prefer non-wildcard usage.
- Use wildcard only when mandatory.
- Apply same deterministic policy to Hero and bots.

After environment stability and PPO win over RuleBot, expand wildcard alternatives to candidate slots.

## 11.1 Qiaoxiang (敲响) State Machine

When `enable_qiaoxiang=True`, the engine uses deterministic state transitions:
- `idle` -> `active`: triggered by kong actions (`an_kong` / `add_kong` / `ming_kong`)
- `active` -> `resolved_win|resolved_lose|resolved_draw`: resolved at hand terminal

Qiaoxiang behavior:
- During `active`, that seat can only take reaction `hu` (or pass). `chi/pon/ming_kong` are disabled.
- During `active`, self kong candidates are disabled for that seat.
- If the active seat wins, scoring adds `qiaoxiang` fan.

## 11.2 Local Fan Scoring (MVP)

Terminal scoring uses fan-based settlement with winner-centric zero-sum scores.

Implemented fan detection:
- `base`
- `qidui` (seven pairs)
- `shisanyao` (thirteen orphans)
- `duiduihu` (all pungs)
- `qingyise` / `hunyise`
- `menqing`
- `qiaoxiang`

## 12. Reward Contract

Primary terminal reward:
- `hero_score - mean(other_scores)` (or table average equivalent)

Stability option (choose exactly one):
1. Env compression: `sign(x) * log1p(abs(x))`
2. VecNormalize reward normalization

Do not apply both simultaneously.

## 13. Data Contract for BC

Each sample includes:
- `obs`: `(N,40,4,9)` float32
- `action`: `(N,)` int64 in `[0,46]`
- `legal_mask`: `(N,47)` bool
- `phase`: `(N,)` uint8 (`0=Reaction,1=MyTurn`)
- `meta`: json-like descriptor

BC must be mask-aware:
- set illegal logits to very small value (`-inf` equivalent) before CE.

## 14. Duplicate Evaluation

- Fixed seed list (e.g. `1001..2000`)
- Seat rotation per seed (4 seats)
- Metrics:
  - mean score diff
  - std / confidence interval
  - optional Elo vs RuleBot
