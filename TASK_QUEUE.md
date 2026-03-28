# TASK_QUEUE.md

Last Updated: 2026-02-21  
Project Root: `D:\Research\Mahjong`  
Queue Policy: 单任务执行、强验收、可断点续跑

## 执行总则（适用于所有任务）

1. 每个任务必须先做 Context discovery，再编辑。  
2. 每个任务至少执行 1 条命令并给出 exit code。  
3. 完成后必须追加 `CHANGELOG_AUTOPILOT.md`。  
4. 若发现阻塞，输出 `BLOCKED`，并记录失败证据与最小解阻步骤。  
5. 禁止越界修改与任务无关文件。  
6. 每个任务按 10-30 分钟拆分，宁小勿大。  

---

## Workflow 1: Discovery

### Group D-1（建议串行）
推荐 agent 角色：`explorer`, `docs`, `reviewer`

=== TASK 0: Bootstrap 控制面与日志 ===  
Goal:  
初始化并校验核心控制文件与目录，建立后续自动化执行基础。

Context discovery (必须先搜索/打开文件/确认现状):  
1. 扫描根目录确认是否已有 `PROJECT_CONTROL.md` / `TASK_QUEUE.md` / `CHANGELOG_AUTOPILOT.md`。  
2. 确认 `docs/`、`logs/` 是否存在。  

Edits (预期改哪些文件/新增哪些文件/或生成哪些内容):  
1. 若缺失则创建上述 3 个 md 文件。  
2. 创建 `docs/`、`logs/`。  
3. 在 `CHANGELOG_AUTOPILOT.md` 写入模板头。  

Acceptance criteria (可验证、可量化):  
1. 三个控制文件存在且非空。  
2. `docs/`、`logs/` 目录存在。  
3. `CHANGELOG_AUTOPILOT.md` 含 `Task ID / Date / Summary / Files changed / Commands + exit codes / Evidence / Next steps` 字段。  

Commands to run (至少1条；成功标准写清):  
1. `Get-ChildItem -Force`  
成功标准：可见 3 个 md 文件与 2 个目录。  

Idempotency & continuation (已完成如何跳过；未完成如何续跑):  
1. 若文件与目录齐全，直接记录“已完成，跳过”。  
2. 若部分缺失，仅补缺失项，不改动已有正确内容。  

Output format (改动摘要/文件列表/命令结果/证据/更新日志要求):  
1. 改动摘要（3-5 行）  
2. 文件列表  
3. 命令与 exit code  
4. 证据（关键 grep 或目录清单）  
5. 追加到 changelog 的原文片段  

---

=== TASK 1: 环境与工具链基线探测 ===  
Goal:  
确认可执行环境版本与关键工具可用性，落盘基线文档。

Context discovery (必须先搜索/打开文件/确认现状):  
1. 检查是否已有 `docs/discovery_baseline.md`。  
2. 若存在，核对日期是否为当天。  

Edits (预期改哪些文件/新增哪些文件/或生成哪些内容):  
1. 新建或更新 `docs/discovery_baseline.md`，记录 Python/pip/pytest/rg。  
2. 明确 Python pin 推荐：3.11（优先）或 3.10（备选）。  

Acceptance criteria (可验证、可量化):  
1. 文档包含命令、输出、结论三段。  
2. 包含可用性状态（available/missing）。  
3. 包含下一步建议（依赖安装或 fallback）。  

Commands to run (至少1条；成功标准写清):  
1. `python --version`  
2. `pip --version`  
3. `pytest --version`  
4. `if (Get-Command rg -ErrorAction SilentlyContinue) { rg --version } else { Write-Output "rg_missing" }`  
成功标准：4 条命令至少 3 条可执行并有记录。  

Idempotency & continuation (已完成如何跳过；未完成如何续跑):  
1. 若基线文件已含当天记录，则跳过并只补缺失工具项。  
2. 工具缺失时记录阻塞，不中断其他纯文档任务。  

Output format (改动摘要/文件列表/命令结果/证据/更新日志要求):  
同 TASK 0。  

---

=== TASK 2: 项目骨架初始化 ===  
Goal:  
建立最小可开发目录树与空占位文件，支持后续并行开发。

Context discovery (必须先搜索/打开文件/确认现状):  
1. 检查目录是否已存在：`datasets/`, `rl/`, `tests/`, `docs/`, `logs/`, `models/`, `reports/`。  
2. 检查根目录目标文件是否存在。  

Edits (预期改哪些文件/新增哪些文件/或生成哪些内容):  
1. 创建目录树。  
2. 创建空占位：`mapping.py`, `engine.py`, `env.py`, `bots.py`, `SPEC.md`, `requirements.txt`。  

Acceptance criteria (可验证、可量化):  
1. 目录树完整。  
2. 占位文件全部存在。  

Commands to run (至少1条；成功标准写清):  
1. `Get-ChildItem -Recurse -Force`  
成功标准：显示全部目标目录与占位文件。  

Idempotency & continuation (已完成如何跳过；未完成如何续跑):  
1. 已存在则不重建。  
2. 缺项则增量创建。  

Output format (改动摘要/文件列表/命令结果/证据/更新日志要求):  
同 TASK 0。  

---

=== TASK 3: 依赖锁定与安装可行性校验 ===  
Goal:  
写入固定依赖版本，验证安装路径可执行。

Context discovery (必须先搜索/打开文件/确认现状):  
1. 查看 `requirements.txt` 是否已有版本冲突。  
2. 查看 `docs/discovery_baseline.md` 的 Python 版本结论。  

Edits (预期改哪些文件/新增哪些文件/或生成哪些内容):  
1. 更新 `requirements.txt` 固定版本：  
   - gymnasium==0.29.1  
   - stable-baselines3==2.3.0  
   - sb3-contrib==2.3.0  
   - numpy<2.0.0  
   - torch>=2.0.0  
   - cloudpickle（建议锁）  
   - typing_extensions（建议锁）  
2. 在 `docs/discovery_baseline.md` 补依赖安装结论。  

Acceptance criteria (可验证、可量化):  
1. requirements 包含所有关键 pin。  
2. 安装命令可执行（至少 dry-run 思路明确）。  

Commands to run (至少1条；成功标准写清):  
1. `Select-String -Path requirements.txt -Pattern "gymnasium==0.29.1|stable-baselines3==2.3.0|sb3-contrib==2.3.0|numpy<2.0.0"`  
成功标准：4 项关键依赖均命中。  

Idempotency & continuation (已完成如何跳过；未完成如何续跑):  
1. 若 pin 已一致，跳过写入并记录。  
2. 若冲突，仅替换冲突行并说明。  

Output format (改动摘要/文件列表/命令结果/证据/更新日志要求):  
同 TASK 0。  

---

=== TASK 4: 固化 SPEC v1.1（契约先行） ===  
Goal:  
把实现边界与动作/观测/mask/裁决/seed/奖励规范写死到 `SPEC.md`。

Context discovery (必须先搜索/打开文件/确认现状):  
1. 打开 `PROJECT_CONTROL.md`，提取契约条款。  
2. 检查 `SPEC.md` 是否已有冲突定义。  

Edits (预期改哪些文件/新增哪些文件/或生成哪些内容):  
1. 完整更新 `SPEC.md`。  
2. 明确 v1.1 要点：`43~46` 通用候选位、Discarder Pos 归一化、`max_internal_steps`、mask 最后防线。  

Acceptance criteria (可验证、可量化):  
1. `SPEC.md` 包含 Tile Mapping / Action(47) / Obs(C,4,9) / mask / priority / seed。  
2. 含至少 1 个明确示例（候选槽位填充示例）。  

Commands to run (至少1条；成功标准写清):  
1. `Select-String -Path SPEC.md -Pattern "Discrete\\(47\\)|43~46|max_internal_steps|Discarder Pos|Hu > 杠/碰 > 吃"`  
成功标准：以上关键词全部命中。  

Idempotency & continuation (已完成如何跳过；未完成如何续跑):  
1. 若已有完整 SPEC，仅做差异修补。  
2. 若缺关键章节，增补章节后记录版本号。  

Output format (改动摘要/文件列表/命令结果/证据/更新日志要求):  
同 TASK 0。  

---

## Workflow 2: Implementation

### Group I-1（可并行）
推荐 agent 角色：`worker`, `reviewer`

=== TASK 5: 实现 mapping 常量与转换工具 ===  
Goal:  
实现 tile/action 映射、候选排序、槽位填充工具，供 env/engine 共用。

Context discovery (必须先搜索/打开文件/确认现状):  
1. 打开 `SPEC.md` 校验映射契约。  
2. 检查 `mapping.py` 是否已有定义。  

Edits (预期改哪些文件/新增哪些文件/或生成哪些内容):  
1. 更新 `mapping.py`。  
2. 输出常量：`ACTION_DIM=47`、`TILE_PLAYABLE=34` 等。  

Acceptance criteria (可验证、可量化):  
1. `0..33` 与可打牌一一对应。  
2. `43..46` 槽位可通过统一函数填充。  
3. 单元 smoke 可输出映射结果。  

Commands to run (至少1条；成功标准写清):  
1. `@'from mapping import ACTION_DIM; print(ACTION_DIM)'@ | python -`  
成功标准：输出 `47`。  

Idempotency & continuation (已完成如何跳过；未完成如何续跑):  
1. 若接口齐全，跳过新增，仅修不一致。  
2. 若函数缺失，按最小增量补齐。  

Output format (改动摘要/文件列表/命令结果/证据/更新日志要求):  
同 TASK 0。  

---

=== TASK 6: 实现 engine MVP0.1（摸打） ===  
Goal:  
先打通可重放摸打流程，确保回合推进稳定。

Context discovery (必须先搜索/打开文件/确认现状):  
1. 检查 `engine.py` 当前结构与状态字段。  
2. 读取 `SPEC.md` seed 约定。  

Edits (预期改哪些文件/新增哪些文件/或生成哪些内容):  
1. 更新 `engine.py`。  
2. 实现 reset(seed)、摸牌、出牌、终局最小判定。  

Acceptance criteria (可验证、可量化):  
1. 同 seed 初始状态一致。  
2. 单局可推进到终局。  
3. 无无限循环。  

Commands to run (至少1条；成功标准写清):  
1. `@'from engine import MahjongEngine; e1=MahjongEngine(); e2=MahjongEngine(); print(e1.reset(seed=9)==e2.reset(seed=9))'@ | python -`  
成功标准：输出 `True`。  

Idempotency & continuation (已完成如何跳过；未完成如何续跑):  
1. 已有实现则对照契约补缺失字段。  
2. 若 smoke 失败，先修 seed 再修流程。  

Output format (改动摘要/文件列表/命令结果/证据/更新日志要求):  
同 TASK 0。  

---

=== TASK 7: 实现 env MVP0.1（Gym + 快进 + mask） ===  
Goal:  
接入 engine，完成 Hero 单智能体接口与快进循环。

Context discovery (必须先搜索/打开文件/确认现状):  
1. 读取 `engine.py` 接口。  
2. 校验 `SPEC.md` 对 obs 与 mask 的定义。  

Edits (预期改哪些文件/新增哪些文件/或生成哪些内容):  
1. 更新 `env.py`。  
2. 实现 `reset/step/action_masks`。  

Acceptance criteria (可验证、可量化):  
1. `reset/step` 签名符合 Gymnasium。  
2. `action_masks()` shape 为 `(47,)` bool。  
3. `max_internal_steps` 生效。  

Commands to run (至少1条；成功标准写清):  
1. `@'from env import HangzhouMahjongEnv; env=HangzhouMahjongEnv(); o,i=env.reset(seed=1); m=env.action_masks(); print(o.shape, len(m), m.dtype)'@ | python -`  
成功标准：输出含 `(40, 4, 9)`、`47`、`bool`。  

Idempotency & continuation (已完成如何跳过；未完成如何续跑):  
1. 若接口已存在，仅补契约缺失与断言。  
2. 若 mask 异常，优先修复全 False 防线。  

Output format (改动摘要/文件列表/命令结果/证据/更新日志要求):  
同 TASK 0。  

---

=== TASK 8: bots 实现（RandomBot + RuleBot） ===  
Goal:  
实现可复现基线 bot，支持 epsilon 噪声。

Context discovery (必须先搜索/打开文件/确认现状):  
1. 检查 `bots.py` 是否已存在策略接口。  
2. 查看 env 提供的决策上下文。  

Edits (预期改哪些文件/新增哪些文件/或生成哪些内容):  
1. 更新 `bots.py`，实现 RandomBot/RuleBot。  
2. RuleBot 支持 `epsilon` 参数（默认 0.05-0.1）。  

Acceptance criteria (可验证、可量化):  
1. RandomBot 只在合法动作内采样。  
2. RuleBot 同 seed 可复现。  
3. 可被 env 内调用。  

Commands to run (至少1条；成功标准写清):  
1. `@'from bots import RandomBot, RuleBot; print("ok")'@ | python -`  
成功标准：输出 `ok`。  

Idempotency & continuation (已完成如何跳过；未完成如何续跑):  
1. 已存在则补 `epsilon` 与 seed 控制。  
2. 不重写已稳定接口。  

Output format (改动摘要/文件列表/命令结果/证据/更新日志要求):  
同 TASK 0。  

---

### Group I-2（可并行，依赖 I-1）
推荐 agent 角色：`worker`, `data`

=== TASK 9: 生成 BC 数据脚本 ===  
Goal:  
实现 RuleBot 对战样本生成，产出标准化 npz。

Context discovery (必须先搜索/打开文件/确认现状):  
1. 检查 `datasets/` 下是否已有脚本。  
2. 校验数据字段契约。  

Edits (预期改哪些文件/新增哪些文件/或生成哪些内容):  
1. 新增或更新 `datasets/gen_data.py`。  
2. 默认输出到 `datasets/artifacts/`。  

Acceptance criteria (可验证、可量化):  
1. 生成 `.npz` 成功。  
2. 包含 `obs/action/legal_mask/phase/meta` 字段。  
3. 样本中的 action 均满足 legal_mask。  

Commands to run (至少1条；成功标准写清):  
1. `python datasets/gen_data.py --episodes 20 --out datasets/artifacts/smoke_data.npz`  
成功标准：exit code=0 且文件存在。  

Idempotency & continuation (已完成如何跳过；未完成如何续跑):  
1. 输出文件已存在则按参数判断跳过。  
2. 如损坏则仅重生该文件。  

Output format (改动摘要/文件列表/命令结果/证据/更新日志要求):  
同 TASK 0。  

---

=== TASK 10: BC 训练脚本（mask-aware） ===  
Goal:  
实现基于合法动作掩码的行为克隆训练。

Context discovery (必须先搜索/打开文件/确认现状):  
1. 检查 `datasets/gen_data.py` 输出字段。  
2. 检查 torch 可用性。  

Edits (预期改哪些文件/新增哪些文件/或生成哪些内容):  
1. 新增或更新 `datasets/bc_train.py`。  
2. 输出模型到 `models/`。  

Acceptance criteria (可验证、可量化):  
1. 至少 1 epoch 可运行完成。  
2. loss 非 NaN。  
3. 生成模型文件。  

Commands to run (至少1条；成功标准写清):  
1. `python datasets/bc_train.py --data datasets/artifacts/smoke_data.npz --epochs 1 --out models/bc_smoke.pt`  
成功标准：exit code=0 且模型文件存在。  

Idempotency & continuation (已完成如何跳过；未完成如何续跑):  
1. 若参数与模型同名已存在，默认跳过。  
2. 新参数使用新输出名续跑。  

Output format (改动摘要/文件列表/命令结果/证据/更新日志要求):  
同 TASK 0。  

---

### Group I-3（建议串行，依赖 I-1）
推荐 agent 角色：`worker`, `reviewer`

=== TASK 11: engine 扩展 Reaction 与抢权裁决 ===  
Goal:  
加入完整 Reaction 状态机与优先级裁决。

Context discovery (必须先搜索/打开文件/确认现状):  
1. 打开 `engine.py` 检查当前 phase 流转。  
2. 打开 `SPEC.md` 对照优先级定义。  

Edits (预期改哪些文件/新增哪些文件/或生成哪些内容):  
1. 更新 `engine.py`。  
2. 明确同优先级 seat-order 裁决函数。  

Acceptance criteria (可验证、可量化):  
1. 优先级固定：胡 > 杠/碰 > 吃。  
2. 同优先级 seat-order 可重放。  
3. 非 Hero 实际决策点不泄露给 Hero。  

Commands to run (至少1条；成功标准写清):  
1. `@'from engine import MahjongEngine; print(hasattr(MahjongEngine(), \"resolve_reaction_priority\"))'@ | python -`  
成功标准：输出 `True`。  

Idempotency & continuation (已完成如何跳过；未完成如何续跑):  
1. 若已有裁决函数，先补单测再微调实现。  
2. 若状态机冲突，先修 phase 再修细节动作。  

Output format (改动摘要/文件列表/命令结果/证据/更新日志要求):  
同 TASK 0。  

---

=== TASK 12: env 扩展到完整 47 动作 ===  
Goal:  
实现 MyTurn/Reaction 全动作 mask 与 43~46 通用候选槽位。

Context discovery (必须先搜索/打开文件/确认现状):  
1. 检查 `env.py` 当前动作分支。  
2. 读取 `mapping.py` 候选槽位函数。  

Edits (预期改哪些文件/新增哪些文件/或生成哪些内容):  
1. 更新 `env.py`（必要时同步 `mapping.py`）。  
2. 在 info 中输出 action_mask 与候选调试信息。  

Acceptance criteria (可验证、可量化):  
1. MyTurn/Reaction 可选动作集合正确区分。  
2. `Pass(42)` 规则严格符合契约。  
3. mask 永不全 False。  
4. 候选槽位同状态不漂移。  

Commands to run (至少1条；成功标准写清):  
1. `@'from env import HangzhouMahjongEnv; env=HangzhouMahjongEnv(); obs,info=env.reset(seed=3); m=env.action_masks(); print(len(m), any(m))'@ | python -`  
成功标准：输出 `47 True`。  

Idempotency & continuation (已完成如何跳过；未完成如何续跑):  
1. 若已全动作实现，仅修 SPEC 偏差。  
2. 若 smoke 不稳，先修 mask 再修候选排序。  

Output format (改动摘要/文件列表/命令结果/证据/更新日志要求):  
同 TASK 0。  

---

=== TASK 13: PPO 训练入口实现 ===  
Goal:  
实现 `MaskablePPO` 训练脚本，支持多进程与奖励稳定策略。

Context discovery (必须先搜索/打开文件/确认现状):  
1. 检查 env 的 `action_masks()` 是否可在向量环境调用。  
2. 检查依赖版本是否匹配。  

Edits (预期改哪些文件/新增哪些文件/或生成哪些内容):  
1. 新增或更新 `rl/train_ppo.py`。  
2. 支持参数：`--timesteps --num-envs --reward_mode --out`。  

Acceptance criteria (可验证、可量化):  
1. smoke 训练可运行。  
2. 输出模型文件。  
3. 日志中无 NaN。  

Commands to run (至少1条；成功标准写清):  
1. `python rl/train_ppo.py --timesteps 5000 --num-envs 4 --reward_mode log1p --out models/ppo_smoke`  
成功标准：exit code=0 且模型文件存在。  

Idempotency & continuation (已完成如何跳过；未完成如何续跑):  
1. 已有同参数模型可跳过。  
2. 若中断，从最近 checkpoint 续跑。  

Output format (改动摘要/文件列表/命令结果/证据/更新日志要求):  
同 TASK 0。  

---

=== TASK 14: Opponent Pool（旧策略对手池） ===  
Goal:  
引入旧模型快照池，逐步替换对手，实现温和 self-play。

Context discovery (必须先搜索/打开文件/确认现状):  
1. 检查 `bots.py` 是否支持 policy wrapper。  
2. 检查 `rl/train_ppo.py` 是否已有 callback/save 机制。  

Edits (预期改哪些文件/新增哪些文件/或生成哪些内容):  
1. 更新 `bots.py`、`env.py`、`rl/train_ppo.py`。  
2. 增加对手池加载/抽样/替换比例参数。  

Acceptance criteria (可验证、可量化):  
1. 可从 `models/` 扫描旧策略。  
2. 可配置“只替换 1 个对手”（默认）。  
3. seed 下对手采样可复现。  

Commands to run (至少1条；成功标准写清):  
1. `python rl/train_ppo.py --timesteps 2000 --num-envs 2 --use_opponent_pool --pool_dir models --out models/ppo_pool_smoke`  
成功标准：exit code=0 且日志出现 pool 抽样信息。  

Idempotency & continuation (已完成如何跳过；未完成如何续跑):  
1. 若已有池机制，补齐 seed 控制与默认替换比例。  
2. 若无旧模型，允许退化为 RuleBot-only 并记录。  

Output format (改动摘要/文件列表/命令结果/证据/更新日志要求):  
同 TASK 0。  

---

## Workflow 3: Verification

### Group V-1（可并行）
推荐 agent 角色：`tester`, `reviewer`

=== TASK 15: `test_mask.py` 建立掩码门禁 ===  
Goal:  
对关键 phase 与候选槽位建立断言，防止 mask 回归。

Context discovery (必须先搜索/打开文件/确认现状):  
1. 检查 `tests/` 下是否已有 mask 测试。  
2. 找出可构造的典型局面 fixture。  

Edits (预期改哪些文件/新增哪些文件/或生成哪些内容):  
1. 新增或更新 `tests/test_mask.py`。  

Acceptance criteria (可验证、可量化):  
1. 覆盖 MyTurn/Reaction/全False防线/Pass 规则。  
2. pytest 可执行通过。  

Commands to run (至少1条；成功标准写清):  
1. `uv run pytest tests/test_mask.py -q`  
成功标准：exit code=0。  

Idempotency & continuation (已完成如何跳过；未完成如何续跑):  
1. 现有测试覆盖不足则增补 case。  
2. 失败时只修失败点。  

Output format (改动摘要/文件列表/命令结果/证据/更新日志要求):  
同 TASK 0。  

---

=== TASK 16: `test_priority.py` 验证抢权裁决 ===  
Goal:  
验证优先级与座位顺序决策完全确定。

Context discovery (必须先搜索/打开文件/确认现状):  
1. 检查 engine 裁决函数签名。  
2. 确定多人同优先级用例。  

Edits (预期改哪些文件/新增哪些文件/或生成哪些内容):  
1. 新增或更新 `tests/test_priority.py`。  

Acceptance criteria (可验证、可量化):  
1. 覆盖 `胡 > 杠/碰 > 吃`。  
2. 覆盖同优先级 seat-order。  
3. pytest 通过。  

Commands to run (至少1条；成功标准写清):  
1. `uv run pytest tests/test_priority.py -q`  
成功标准：exit code=0。  

Idempotency & continuation (已完成如何跳过；未完成如何续跑):  
1. 若已有测试则补缺失场景。  
2. 保持测试命名稳定，避免重复用例。  

Output format (改动摘要/文件列表/命令结果/证据/更新日志要求):  
同 TASK 0。  

---

=== TASK 17: `test_seed.py` 验证同 seed 可复现 ===  
Goal:  
保证 reset(seed) 结果与关键流程可重放。

Context discovery (必须先搜索/打开文件/确认现状):  
1. 找到 engine/env 的随机源注入点。  
2. 检查是否存在未控随机调用。  

Edits (预期改哪些文件/新增哪些文件/或生成哪些内容):  
1. 新增或更新 `tests/test_seed.py`。  

Acceptance criteria (可验证、可量化):  
1. 同 seed 初始状态一致。  
2. 同动作序列结果一致。  
3. pytest 通过。  

Commands to run (至少1条；成功标准写清):  
1. `uv run pytest tests/test_seed.py -q`  
成功标准：exit code=0。  

Idempotency & continuation (已完成如何跳过；未完成如何续跑):  
1. 已有 seed 测试则补“动作序列重放”断言。  
2. 若失败优先排查 bot 随机扰动。  

Output format (改动摘要/文件列表/命令结果/证据/更新日志要求):  
同 TASK 0。  

---

=== TASK 18: `test_run_1000.py` 稳定性回归 ===  
Goal:  
确保环境可连续跑 1000 局不崩溃。

Context discovery (必须先搜索/打开文件/确认现状):  
1. 确认单局执行接口。  
2. 确认异常捕获与 debug info 输出。  

Edits (预期改哪些文件/新增哪些文件/或生成哪些内容):  
1. 新增或更新 `tests/test_run_1000.py`。  

Acceptance criteria (可验证、可量化):  
1. 1000 局执行完毕。  
2. 无未处理异常。  
3. 若出现 truncated，必须有 debug 字段。  

Commands to run (至少1条；成功标准写清):  
1. `uv run pytest tests/test_run_1000.py -q`  
成功标准：exit code=0。  

Idempotency & continuation (已完成如何跳过；未完成如何续跑):  
1. 已存在测试则提升断言粒度。  
2. 失败时记录失败局 seed 并做最小修复。  

Output format (改动摘要/文件列表/命令结果/证据/更新日志要求):  
同 TASK 0。  

---

=== TASK 19: Duplicate 评测脚本 ===  
Goal:  
实现固定 seed + 座位轮换评测并导出统计报告。

Context discovery (必须先搜索/打开文件/确认现状):  
1. 检查 `rl/` 下是否已有评测入口。  
2. 确认模型加载与 env 接口兼容。  

Edits (预期改哪些文件/新增哪些文件/或生成哪些内容):  
1. 新增或更新 `rl/eval_duplicate.py`。  
2. 报告输出到 `reports/*.json`。  

Acceptance criteria (可验证、可量化):  
1. 支持外部 seeds 输入。  
2. 每 seed 自动座位轮换 4 局。  
3. 报告字段包含：`mean_diff`, `std_diff`, `ci95`, `n_games`。  

Commands to run (至少1条；成功标准写清):  
1. `python rl/eval_duplicate.py --model models/ppo_smoke --seeds 1001 1002 1003 1004 --out reports/dup_smoke.json`  
成功标准：exit code=0 且报告文件存在。  

Idempotency & continuation (已完成如何跳过；未完成如何续跑):  
1. 报告存在且参数一致可跳过。  
2. 参数变更则新文件名重跑。  

Output format (改动摘要/文件列表/命令结果/证据/更新日志要求):  
同 TASK 0。  

---

## Workflow 4: Documentation

### Group DOC-1（建议串行）
推荐 agent 角色：`docs`, `reviewer`, `tester`

=== TASK 20: README 与 Runbook 收敛 ===  
Goal:  
整理安装、训练、评测、回归测试入口，形成交接文档。

Context discovery (必须先搜索/打开文件/确认现状):  
1. 检查 `README.md`、`docs/` 是否存在。  
2. 读取当前可运行命令清单。  

Edits (预期改哪些文件/新增哪些文件/或生成哪些内容):  
1. 新增或更新 `README.md`。  
2. 新增或更新 `docs/runbook.md`。  
3. 更新 `PROJECT_CONTROL.md` 里程碑状态。  

Acceptance criteria (可验证、可量化):  
1. README 含安装、训练、评测、测试 4 段最短命令。  
2. runbook 含常见故障与排查步骤。  
3. 文档命令与当前脚本名一致。  

Commands to run (至少1条；成功标准写清):  
1. `Select-String -Path README.md -Pattern "train_ppo.py|eval_duplicate.py|pytest"`  
成功标准：3 个关键词均命中。  

Idempotency & continuation (已完成如何跳过；未完成如何续跑):  
1. 若文档已完整，按增量更新。  
2. 命令变化时同步更新所有引用位置。  

Output format (改动摘要/文件列表/命令结果/证据/更新日志要求):  
同 TASK 0。  

---

=== FINAL TASK 21: 总验收与交付汇总 ===  
Goal:  
统一执行门禁、汇总状态、输出最终交付报告。

Context discovery (必须先搜索/打开文件/确认现状):  
1. 检查 `CHANGELOG_AUTOPILOT.md` 是否覆盖 TASK 0-20。  
2. 确认模型、测试、评测报告是否存在。  

Edits (预期改哪些文件/新增哪些文件/或生成哪些内容):  
1. 更新 `PROJECT_CONTROL.md` 的里程碑状态。  
2. 追加 `CHANGELOG_AUTOPILOT.md` 最终条目。  
3. 新增 `reports/final_acceptance.md`。  

Acceptance criteria (可验证、可量化):  
1. `uv run pytest tests -q` 通过。  
2. `train_ppo.py` smoke 成功。  
3. `eval_duplicate.py` smoke 成功且报告字段完整。  
4. 最终报告包含“完成项、未完成项、风险残留、下一步建议”。  

Commands to run (至少1条；成功标准写清):  
1. `uv run pytest tests -q`  
2. `python rl/train_ppo.py --timesteps 3000 --num-envs 4 --reward_mode log1p --out models/ppo_final_smoke`  
3. `python rl/eval_duplicate.py --model models/ppo_final_smoke --seeds 1001 1002 1003 1004 --out reports/dup_final_smoke.json`  
成功标准：3 条命令均 exit code=0。  

Idempotency & continuation (已完成如何跳过；未完成如何续跑):  
1. 已通过的门禁不重复跑。  
2. 失败项定点修复后仅重跑失败命令。  

Output format (改动摘要/文件列表/命令结果/证据/更新日志要求):  
1. 交付摘要  
2. 文件清单  
3. 门禁命令结果  
4. 指标摘要  
5. 风险残留  
6. changelog 最终记录全文  
