# PROJECT_CONTROL.md

Last Updated: 2026-02-21  
Project Root: `D:\Research\Mahjong`  
Project Name: `hangzhou_mahjong`

## 1) Goal（目标）

在单人开发、无高质量人类牌谱、算力预算受限的现实条件下，构建一个可复现、可评测、可持续迭代的四人杭州麻将 AI 工程闭环：

`规则引擎 + RuleBot 冷启动 -> 合成牌谱 BC 预热 -> MaskablePPO 微调 -> Duplicate 复式评测`

强度目标（MVP）：
- 不追求 Suphx/职业级上限。
- 目标是稳定打过一般路人/普通人机。

工程目标（必须达成）：
- 训练过程可控：不死循环、不靠玄学调参、不靠单次好运评测。
- 评测可信：固定 seeds + 座位轮换 + 分差指标。
- 全流程可复现：同 seed 可重放，同版本可回归。

---

## 2) Scope（范围）

### 2.1 In Scope（范围内）
- 从空目录初始化项目结构与规范文档。
- 实现 Gymnasium 单智能体环境（Hero 控制，3 家内嵌对手）。
- 杭麻核心规则与状态机实现（含财神与本地规则可配置入口）。
- RuleBot/RandomBot、数据生成、BC、PPO、Duplicate 评测脚本。
- 关键测试门禁（mask、priority、seed、1000 局稳定）。

### 2.2 Out of Scope（范围外）
- 基于 RLCard two-player Mahjong 的魔改路线。
- 线上对战平台部署、复杂 UI。
- 追求职业牌手级别强度。
- 无约束大规模分布式训练平台建设。

---

## 3) Priority（优先级）

P0（必须先完成）：
1. 环境闭环能长期稳定运行（无死循环、无非法状态漂移）。
2. action mask 正确、phase 正确、mask 永不全 False。
3. seed 控制完整，Duplicate 评测可信。
4. MVP 训练与评测全链路打通。

P1（稳定后推进）：
1. BC 与 PPO 指标稳定提升。
2. opponent pool 引入后不过度震荡。

P2（后续增强）：
1. 财神多方案动作显式扩展。
2. 更强 RuleBot、更多特征与策略细化。

---

## 4) Definition of Ready（DoR）

任务开始前必须满足：
1. 任务依赖的上游任务已完成并在 `CHANGELOG_AUTOPILOT.md` 有记录。
2. 目标文件、接口契约、验收方式已明确。
3. 任务命令至少 1 条可执行且有成功标准。
4. 若信息不足，先执行 Discovery 类任务；禁止凭空假设。

---

## 5) Definition of Done（DoD）

任务完成必须满足：
1. 改动已落盘（代码/文档/脚本）。
2. 至少 1 条命令执行并报告 exit code。
3. 验收标准全部满足（可量化/可验证）。
4. `CHANGELOG_AUTOPILOT.md` 追加对应任务记录。
5. 无无关改动；不破坏已通过的门禁。

---

## 6) Global Hard Rules（全局硬规则）

1. 禁止 RLCard two-player 魔改路线。  
2. SB3 训练时只控制 Hero；其余 3 家必须由 env 内对手驱动。  
3. Gymnasium 接口必须严格一致：  
   - `reset(seed=None, options=None) -> (obs, info)`  
   - `step(action) -> (obs, reward, terminated, truncated, info)`  
4. `action_masks()` 必须在 env 内实现，返回 `np.ndarray(bool)`，shape=`(47,)`。  
5. `info` 建议固定包含：`{"action_mask": mask}`；异常截断需含 debug 字段。  
6. 开发期非法动作直接 `raise ValueError`；训练期至少 `assert + 日志`。  
7. `Pass(42)` 规则写死：  
   - Reaction phase：永远 `True`  
   - MyTurn：永远 `False`（除非后续明确改规则）  
8. mask 最后防线写死：  
   - 若全 False 且 Reaction：强制 `mask[42]=True`  
   - 若全 False 且 MyTurn：强制一个安全出牌动作可选  
9. step 快进循环必须有 `max_internal_steps`（建议 10000）上限。  
10. 超限必须 `truncated=True`，并在 `info` 给出 phase/actor/last_discard/recent_actions。  
11. seed 必须控制所有随机源（牌山、庄位、财神、bot 扰动）。  
12. 禁止破坏性命令（如 `git reset --hard`）。  
13. 每个关键决策必须同步写入 `PROJECT_CONTROL.md` 或 `SPEC.md`。  
14. 所有环境测试命令统一使用 `uv` 运行（例如 `uv run pytest ...`）。  

---

## 7) Architecture & Data Contracts（架构/数据契约）

### 7.1 目标目录结构

```
hangzhou_mahjong/
  requirements.txt
  SPEC.md
  mapping.py
  engine.py
  env.py
  bots.py
  datasets/
    gen_data.py
    bc_train.py
  rl/
    train_ppo.py
    eval_duplicate.py
  tests/
    test_mask.py
    test_priority.py
    test_seed.py
    test_run_1000.py
  docs/
  logs/
  models/
  reports/
```

### 7.2 依赖与版本（Spec v1.0 pin）

`requirements.txt` 至少固定：
- `gymnasium==0.29.1`
- `stable-baselines3==2.3.0`
- `sb3-contrib==2.3.0`
- `numpy<2.0.0`
- `torch>=2.0.0`
- `cloudpickle`（建议锁定）
- `typing_extensions`（建议锁定）

Python 版本建议固定：
- 首选 `Python 3.11`
- 兼容回退 `Python 3.10`

### 7.3 Tile Mapping（必须写死）

网格 `(4,9)`，索引 `0..35`，其中 `34,35` 为 PAD：
- Row0：万 1-9 -> idx `0..8`
- Row1：筒 1-9 -> idx `9..17`
- Row2：条 1-9 -> idx `18..26`
- Row3：东南西北中发白 -> idx `27..33`，PAD `34..35`

动作映射：
- `Action 0..33` 与 tile idx `0..33` 一一对应
- PAD 永不参与动作

### 7.4 Action Space（固定 `Discrete(47)`）

- `0..33`：Discard
- `34`：Chi-L
- `35`：Chi-M
- `36`：Chi-R
- `37`：Pon
- `38`：Ming Kong
- `39`：Add Kong
- `40`：An Kong
- `41`：Hu
- `42`：Pass
- `43..46`：通用候选槽位（用于所有“多候选”动作）

候选槽位规则（固定）：
1. 生成当前状态 candidate list。
2. 排序按 `tile_index` 升序；组合类按字典序。
3. 主槽（如 34/39/40）放候选 0。
4. `43..46` 放候选 1..4，不足留空（mask=False）。

### 7.5 Observation（固定 `obs=(C,4,9)`）

v1.1 推荐固定 `C=40`，`dtype=float32`，取值 `[0,1]`：
- Hand count-to-4
- Wealth God 指示
- Last Discard 焦点牌
- Phase Flag（MyTurn vs Reaction）
- Discarder Pos（归一化）
- Discards 按相对座位展开
- Melds 按相对座位展开

Discarder Pos 归一化必须固定：
- self/none = `0.0`
- down = `1/3`
- oppo = `2/3`
- up = `1.0`

### 7.6 Engine 行为契约

1. 抢权裁决优先级固定：`胡 > 杠/碰 > 吃`。  
2. 同优先级多人时按“从出牌者下家开始顺时针”裁决。  
3. 只有 Hero 真正有决策权时才返回 Reaction 观测。  
4. `step()` 必须“Hero 动作后内部快进”，直到 Hero 下次决策或终局。  

### 7.7 Mask 契约

1. 强绑定 phase（MyTurn 与 Reaction 动作集合不同）。  
2. 永不全 False。  
3. 开发期非法动作直接报错。  
4. `info` 保留 mask 便于调试。  

### 7.8 Reward 契约

终局奖励优先：
- `hero_score - table_avg`

稳定化策略二选一：
1. Env 内压缩：`sign(x) * log1p(abs(x))`
2. VecNormalize(norm_reward=True)

禁止双重压缩（同时使用 1+2）。

### 7.9 Dataset 契约（BC 数据）

每条样本至少包含：
- `obs`：`(N,C,4,9)`
- `action`：`(N,)`，范围 `0..46`
- `legal_mask`：`(N,47)` bool
- `phase`：`(N,)`
- `meta`：规则版本、seed、bot 策略

BC 训练必须 mask-aware：
- 非法动作 logits 屏蔽为 `-inf`（或极小值）后再 softmax/CE。

### 7.10 Duplicate 评测契约

1. 固定 seeds（示例 `1001..2000`）。  
2. 每个 seed 至少 4 局（Hero 东南西北轮换）。  
3. 核心指标：平均分差、方差/置信区间。  
4. 胜率仅作辅助，不作为唯一优化目标。  

---

## 8) Top 5 Risks（风险）与缓解策略

1) 风险：mask/phase/candidate 不一致，策略无法学习  
- 触发信号：非法动作频发、loss 异常、策略无提升  
- 缓解：先写 `test_mask.py` 与 case-based fixtures；开发期非法动作直接 raise

2) 风险：环境快进死循环，CPU 长时间占满  
- 触发信号：step 卡死、单局超时  
- 缓解：`max_internal_steps` + truncated + debug state dump

3) 风险：seed 控制不完整导致评测不可比  
- 触发信号：同 seed 回放结果不一致  
- 缓解：统一 RNG 注入入口；`test_seed.py` 强制校验

4) 风险：奖励尺度爆炸导致 PPO NaN/震荡  
- 触发信号：训练日志出现 NaN、value loss 激增  
- 缓解：reward 稳定化二选一；记录 reward 分布统计

5) 风险：BC 过拟合单一 RuleBot 风格  
- 触发信号：遇到新策略显著退化  
- 缓解：RuleBot 加 epsilon 噪声，多风格 bot 混合，后续引入 opponent pool

---

## 9) Assumptions（假设）与替代路径

关键假设：
1. 当前项目从空目录启动。
2. 先求“工程稳定 + 评测可信”，再追求强度上限。
3. 可接受先用确定性财神策略降低动作歧义。

潜在不合理点提醒（仍继续执行）：
- 在无高质量人类牌谱前提下，强度上限会受限，短期目标应锁定在 MVP 稳定超 RuleBot，而非绝对强度。

替代路径：
1. 若 Reaction 复杂度导致进度阻塞，先冻结 MVP0.1+0.5，先打通 BC+PPO baseline。
2. 若算力紧张，优先完善 Duplicate 与门禁，降低单次训练规模但保持评测可信。

---

## 10) Current Status（当前状态）

当前状态（2026-02-21）：
1. 项目骨架、规范文档、核心脚本已落盘。
2. 核心测试门禁已可执行（mask/priority/seed/run_1000）。
3. 训练脚本支持 SB3 主路径与 fallback 路径。
4. duplicate 评测脚本可产出结构化报告。

---

## 11) Milestones（里程碑）

M0: Bootstrap 与规范落盘  
- 完成条件：控制文件 + SPEC + 目录骨架 + 依赖锁定
- 状态：Done (2026-02-22)

M1: MVP0.1（摸打闭环）  
- 完成条件：仅出牌动作可训练，1000 局无崩溃
- 状态：Done (2026-02-22)

M2: MVP0.5（RuleBot + 数据 + BC）  
- 完成条件：可生成样本并完成 BC 预热，强度接近 RuleBot
- 状态：Done (Smoke complete, 2026-02-22)

M3: MVP1.0（Reaction 全动作）  
- 完成条件：吃碰杠胡与裁决流程稳定，mask 完整可测
- 状态：Done (Smoke complete, 2026-02-22)

M4: MVP1.1（PPO 强化 + opponent pool + duplicate）  
- 完成条件：对 RuleBot 分差稳定正向，评测可复现
- 状态：Done (Smoke complete, 2026-02-22)

M5: 总验收  
- 完成条件：门禁全绿 + 最终报告 + 风险残留清单
- 状态：Done (2026-02-22)

---

## 12) Decision Update Rule（防遗忘规则）

以下内容任何变更都必须同步更新：
1. 动作空间定义（尤其 43~46 槽位语义）
2. 观测通道顺序与归一化约定
3. 裁决优先级与座位顺序
4. reward 稳定化策略（二选一）
5. 评测 seeds 范围与统计口径

若实现与文档冲突：先更新文档并说明理由，再提交代码变更。
