# Architecture Overview

## 1) 目标与边界

项目目标是构建可复现、可评测、可迭代的杭州麻将 AI MVP：
- 不追求职业级强度
- 优先工程稳定性与评测可信性
- 训练链路可控（可重放、可排错）

硬约束见：
- `PROJECT_CONTROL.md`
- `SPEC.md`
- `rules/hz_local_v2026_02_A.yaml`
- `rules/profile_hangzhou_mvp.yaml`（兼容别名）

## 2) 核心组件

### 2.1 `mapping.py`

职责：
- 固定 tile/action 编号契约
- 提供候选动作排序和 `43..46` 通用槽位填充工具

关键常量：
- `ACTION_DIM = 47`
- `PLAYABLE_TILE_COUNT = 34`
- `ACTION_PASS = 42`
- `ACTION_SLOT_START = 43`, `ACTION_SLOT_END = 46`

### 2.2 `engine.py`

职责：
- 管理牌局状态（手牌、牌山、弃牌、吃碰杠信息）
- 实现回合推进与反应裁决
- 控制 seed 下的确定性行为

关键行为：
- 抢权优先级：`hu > ming_kong/pon > chi`
- 同优先级按出牌者下家开始顺时针裁决
- 可导出 `recent_actions` 用于截断排障
- 本地规则开关：
  - `enable_wealth_god`
  - `protect_wealth_god_discard`
  - `enable_qiaoxiang`（完整状态机：`idle -> active -> resolved_*`）
  - `wealth_god_can_meld`（财神是否可参与吃碰杠）
- 反应候选扩展：
  - `chi` 已支持财神替代可行性判定，且“合法性判断”和“实际扣牌执行”共用同一逻辑，避免 mask/执行不一致
- 胡牌判定已支持：
  - 标准 `4 面子 + 1 对将`
  - `七对`
  - `十三幺`
  - 财神万能牌求解
- 本地番型计分已支持：
  - `对对胡`、`清一色`、`混一色`、`门清`
  - 敲响加番（`qiaoxiang +1 fan`）

### 2.3 `env.py`

职责：
- 将 `engine` 封装为 Gymnasium 单智能体环境
- Hero 之外的 3 家由 bot 内嵌驱动
- 负责 action mask、快进循环、观测构建、奖励计算

关键契约：
- `reset(seed=None, options=None) -> (obs, info)`
- `step(action) -> (obs, reward, terminated, truncated, info)`
- `action_masks() -> np.ndarray(bool, shape=(47,))`

安全阀：
- `max_internal_steps` 防死循环
- 截断时在 `info` 输出 `phase/actor/last_discard/recent_actions`

规则透传：
- `HangzhouMahjongEnv` 会把本地规则开关透传给 `MahjongEngine`，并保持对训练脚本/评测脚本参数一致。
- `opponent_mix` 支持 `rule/defensive/aggressive/random/minlegal` 混合对手采样，并可与 `opponent_pool` 并用。

### 2.4 `bots.py`

包含：
- `RandomBot`: 合法动作随机采样
- `RuleBot`: 规则优先策略，支持 `balanced/defensive/aggressive` 风格 + epsilon 噪声
- `MinLegalBot`: 固定选择最小合法动作（基准噪声对照）
- `OldPolicyBot`: 加载历史策略模型用于 opponent pool

加载约定：
- 优先加载 `.zip` 模型
- basename 模式会优先尝试 `<name>.zip`

### 2.5 `datasets/`

- `gen_data.py`: 用 RuleBot 生成合成样本（`obs/action/legal_mask/phase/meta`）
- `bc_train.py`: mask-aware BC 训练，非法动作 logits 屏蔽

### 2.6 `rl/`

- `train_ppo.py`: MaskablePPO 训练入口，支持 opponent pool、fallback 控制、reward 归一化互斥检查、训练后监控门禁
- `eval_duplicate.py`: 固定 seed + 座位轮换评测，支持 `strict_load/fail_on_fallback`、`policy_mode(model/rule/random/minlegal)`、`opponent_epsilon` 对手扰动控制、`seed_set(dev/test)` 防调参过拟合，输出分差统计与加载诊断
- `eval_duplicate.py`: 报告中固定写入 `rule_profile_id/spec_version/seed_set_id/opponent_suite_id`，供后续 readiness 校验上下文一致性
- `assess_model_readiness.py`: 基于 duplicate 报告自动判定“是否达到可用阈值”（下置信界、样本量、对 RuleBot 优势）
- `assess_human_readiness.py`: 多场景门禁（例如 base/opp0/opp16），支持最小通过比例判定
- `assess_readiness_levels.py`: 分层门禁（L1 可训练稳定 / L2 仿真稳健 / L3 真人可宣称）
- `build_duplicate_trend.py`: 聚合多份 duplicate 报告，输出版本趋势表（Markdown/JSON）
- `seed_splits.py`: 管理固定评测种子集（`dev=1001..1500`, `test=1501..2000`）
- `report_context.py`: 统一生成/解析/校验评测上下文字段，避免跨版本结论串线

### 2.7 `api/`

- `api/server.py`: 前后端联调 API（`GET /api/health`, `POST /api/leads`）
- 线索数据默认追加写入 `logs/leads.ndjson`
- 支持 `LEAD_LOG_PATH` 与 `FRONTEND_ORIGINS` 环境变量

### 2.7 `tests/`

回归门禁：
- `test_mask.py`
- `test_priority.py`
- `test_seed.py`
- `test_run_1000.py`
- `test_stability_gates.py`（无全 False mask / 多反应无死锁 / truncation 率阈值）
- `test_local_rule_profiles.py`（Rule Profile + Top10 争议规则 fixtures）

## 3) 决策流（单步）

1. Hero 选择动作（MyTurn 或 Reaction）
2. `env.step()` 执行动作
3. 环境内部快进：
   - 非 Hero 轮次由 bots 驱动
   - 若出现反应阶段，先做抢权探测
4. 返回到 Hero 决策点或终局

说明：
- 这不是“一手一步”的多智能体接口，而是单智能体快进式接口。

## 4) 观测与动作契约

动作空间：
- `Discrete(47)`，`0..33` 打牌，`34..42` 特殊动作，`43..46` 通用候选槽位

观测空间：
- `obs.shape = (40, 4, 9)`
- 包含手牌计数、财神、last_discard、phase、discarder_pos、discards、melds

mask 约束：
- MyTurn 与 Reaction 强绑定
- 不能全 False
- Reaction 下 `Pass(42)` 永远可选

## 5) 训练与评测路径

标准链路：
1. RuleBot 生成合成数据
2. BC 预热
3. PPO 微调
4. Duplicate 固定牌山评测
5. Readiness 门禁（L1/L2/L3）输出版本结论

指标建议：
- 主指标：`mean_diff`
- 稳定性：`std_diff`, `ci95`
- 胜率仅作辅助

评测口径建议：
- 日常调参：`seed_set=dev`
- 里程碑结论：`seed_set=test`
- 对外宣称只使用 `test` 报告
- 训练/评测需固定 `opponent_mix` 配置，避免跨版本对手口径漂移

## 6) 可扩展方向

1. 扩展 Reaction 候选表达（财神多方案）
2. 增加 opponent pool 回归测试
3. 扩大 Duplicate seeds 规模（例如 `1001..2000`）
4. 引入更强 RuleBot 作为基线
5. 形成真人回放离线评测集 + 真人 A/B 报告，闭合 L3 门禁
