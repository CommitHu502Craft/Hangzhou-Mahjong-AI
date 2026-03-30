# Hangzhou Mahjong AI (MVP)

四人杭州麻将 AI 工程化基线项目（MVP），目标是先打通可复现闭环，再逐步提升强度。

核心路线：
- 规则引擎 + RuleBot 冷启动
- 合成数据行为克隆（BC，mask-aware）
- MaskablePPO 微调
- Duplicate 固定牌山评测（固定 seeds + 座位轮换）

## Known Limitations

- 真实对局验证仍不完整，当前不能对外宣称已稳定打赢真人局
- 规则覆盖主要面向当前杭州麻将 MVP 画像，不代表完整地区规则全集
- 公开仓库默认不包含模型、报告、数据集等大体积生成产物
- 现阶段评测证据在 duplicate / simulation 场景下更充分，真人场景证据较弱
- 前端目前偏展示与演示，不是完整产品化界面

## 0) 当前验证状态（2026-02-22）

- 回归门禁：`uv run pytest tests -q` -> `110 passed`
- 规则画像版本：`rules/hz_local_v2026_02_A.yaml`
- 仿真 readiness：`L2 PASS`
  - `reports/readiness_hzvA_testSeeds.json`
  - `reports/human_readiness_hzvA.json`
  - `reports/readiness_levels_hzvA_testSeeds.json`（`highest_level=L2`）
- 注意：当前还没有 `real_ab_report`，未达到 `L3`，不应发布“可稳定打赢路人真人局”结论。
- 已补齐真人闭环工具：`datasets/build_replay_offline.py`、`rl/assess_real_ab.py`，可直接产出标准 `real_ab_report` 并接入 `L3` 门禁。

已执行单变量实验矩阵（`dev` 口径）：
- `reports/matrix_hzvA_svmatrix_v1_hz_local_v2026_02_A_dev.md`
- `reports/matrix_hzvA_svmatrix_v1_hz_local_v2026_02_A_dev.json`
- 结论摘要：
  - `baseline`：`mean_diff=14.5333`，`PASS`
  - `reward_raw_vecnorm`：`mean_diff=-15.9933`，`FAIL`
  - `opponent_mix_diverse`：`mean_diff=7.3200`，`PASS`

## 1) 快速开始

### 1.0 CMD 菜单版（推荐）

Windows 下可直接启动：

```powershell
.\sim_train_tui.cmd
```

查看非交互帮助：

```powershell
uv run python tools/sim_train_tui.py --help
```

进入后可选：
- `1`：短训（Quick Baseline，含 dev 评测与 L1）
- `2`：短训矩阵（Baseline + OpponentMix）
- `3`：评测最新模型（test 场景 + sim-only readiness）
- `4`：查看长训进度（checkpoint/meta）
- `5`：全量测试门禁
- `6`：启动长训（守护模式：可断点 + 卡住自动重试）
- `7`：继续上次长训（守护模式自动续训）
- `8`：查看最近日志（tail）

运行日志会写入：`logs/tui_*.log`  
状态会写入：`reports/tui_state.json`
看板会显示轻量训练细节：模型步数、门禁指标、磁盘剩余、长训 heartbeat/speed/ETA（仅摘要，不读取大日志）。
长训执行期间控制台会输出 `[WATCH]` 进度行（`status/steps/target/hb_age`）。

### 1.1 环境安装

```powershell
uv venv .venv --python 3.11 --managed-python
uv pip install --python .venv/Scripts/python.exe -r requirements.txt
```

### 1.2 一键门禁（先跑测试）

```powershell
uv run pytest tests -q
```

成功标准：
- 输出包含 `passed`
- 无 `ERROR` 或 `FAILED`

### 1.3 启动后端 API（前端联调）

```powershell
uv run uvicorn api.server:app --host 127.0.0.1 --port 8000
```

接口：
- `GET /api/health`
- `POST /api/leads`

## 2) 小规模端到端（推荐首次运行）

```powershell
uv run python datasets/gen_data.py --episodes 20 --target_decisions 200 --min_samples 50 --out datasets/artifacts/smoke_data.npz
uv run python datasets/bc_train.py --data datasets/artifacts/smoke_data.npz --epochs 1 --out models/bc_smoke.pt
uv run python rl/train_ppo.py --timesteps 3000 --num-envs 4 --reward_mode log1p --seed 2026 --vec_backend dummy --out models/ppo_smoke
uv run python rl/eval_duplicate.py --model models/ppo_smoke --seeds 1001 1002 1003 1004 --strict_load --fail_on_fallback --out reports/dup_smoke.json
uv run python rl/eval_duplicate.py --model models/unused --policy_mode rule --seeds 1001 1002 1003 1004 --out reports/dup_rule_smoke.json
uv run python rl/assess_model_readiness.py --model_report reports/dup_smoke.json --rule_report reports/dup_rule_smoke.json --out reports/readiness_smoke.json
```

产物检查：
- `datasets/artifacts/smoke_data.npz`
- `models/bc_smoke.pt`
- `models/ppo_smoke.zip` 与 `models/ppo_smoke.json`
- `reports/dup_smoke.json`

## 3) 标准训练流程

### 3.1 生成训练数据

```powershell
uv run python datasets/gen_data.py --episodes 200 --target_decisions 20000 --min_samples 1000 --out datasets/artifacts/train_data.npz
```

建议开启分布门禁（硬检查）：

```powershell
uv run python datasets/gen_data.py --episodes 200 --target_decisions 20000 --min_samples 1000 --out datasets/artifacts/train_data.npz --enforce_distribution_gates --gate_min_myturn_ratio 0.10 --gate_min_reaction_ratio 0.10 --gate_max_action_share 0.95 --gate_min_avg_legal_actions 1.2 --gate_max_truncated_rate 0.05
```

### 3.2 BC 预热

```powershell
uv run python datasets/bc_train.py --data datasets/artifacts/train_data.npz --epochs 3 --out models/bc_main.pt
```

### 3.3 PPO 训练

```powershell
uv run python rl/train_ppo.py --timesteps 50000 --num-envs 8 --reward_mode log1p --seed 2026 --vec_backend subproc --out models/ppo_main
```

可选：对手多样化混合（守备/进攻/随机/minlegal）：

```powershell
uv run python rl/train_ppo.py --timesteps 50000 --num-envs 8 --reward_mode log1p --seed 2026 --vec_backend subproc --opponent_mix "rule:0.4,defensive:0.2,aggressive:0.2,random:0.1,minlegal:0.1" --use_opponent_pool --pool_dir models/pool --opponent_replace_count 1 --out models/ppo_main_mix
```

训练后监控门禁（默认开启）会写入 `*.json`：
- `myturn/reaction` 决策占比
- reaction `Pass` 使用率
- 非法动作率（理论应为 `0`）
- `max_internal_steps` 截断率

Reward 稳定策略硬约束：
- `reward_mode=log1p` 时，禁止 `--use_vec_normalize_reward`
- 若启用 `--use_vec_normalize_reward`，必须配 `--reward_mode raw`

### 3.3.1 断点续训（本地长训推荐）

`train_ppo.py` 已支持断点续训参数：
- `--checkpoint_every`：按步数周期保存 checkpoint
- `--checkpoint_dir` / `--checkpoint_prefix`：checkpoint 路径与命名前缀
- `--resume_latest_checkpoint`：自动从最新 checkpoint 恢复
- `--target_total_timesteps`：目标总步数（用于多次分段推进）
- `--heartbeat_every/--heartbeat_path`：训练心跳（用于卡住检测）
- `--min_free_disk_gb`：训练前磁盘余量门禁（防磁盘写满）

示例（每次跑 200k，目标总步数 2M，支持中断后重跑同命令）：

```powershell
uv run python rl/train_ppo.py ^
  --timesteps 200000 ^
  --target_total_timesteps 2000000 ^
  --num-envs 8 ^
  --vec_backend subproc ^
  --reward_mode log1p ^
  --seed 2026 ^
  --bot_epsilon 0.08 ^
  --opponent_mix "rule:1.0" ^
  --enable_qiaoxiang ^
  --checkpoint_every 50000 ^
  --checkpoint_dir models/checkpoints ^
  --checkpoint_prefix ppo_long_main_ckpt ^
  --resume_latest_checkpoint ^
  --out models/ppo_long_main ^
  --run_tag long-main
```

说明：
- 若已达到 `target_total_timesteps`，脚本会跳过训练并在 `models/*.json` 标记 `skipped_training=true`。
- PPO 以 rollout 粒度更新，`num_timesteps_total` 可能略高于目标值属正常现象。

### 3.3.2 守护训练器（防卡死/防白跑）

新增 `tools/guarded_train.py`：
- 监控 `heartbeat`，超时判定“疑似卡死”后自动终止并重试。
- 每次尝试后读取 `num_timesteps_total`，若连续无进展会失败退出（防无限重试）。
- 生成守护报告：`reports/guarded_train_<run_id>.json`。

示例：

```powershell
uv run python tools/guarded_train.py ^
  --run_id long_main ^
  --out models/ppo_long_main ^
  --report_out reports/guarded_train_long_main.json ^
  --chunk_timesteps 200000 ^
  --target_total_timesteps 2000000 ^
  --num_envs 14 ^
  --seed 2026 ^
  --vec_backend subproc ^
  --reward_mode log1p ^
  --checkpoint_every 50000 ^
  --checkpoint_dir models/checkpoints ^
  --checkpoint_prefix ppo_long_main_ckpt ^
  --heartbeat_every 10000 ^
  --heartbeat_path reports/heartbeat_long_main.json ^
  --stale_timeout_minutes 20 ^
  --max_attempts 100 ^
  --max_no_progress_attempts 5
```

### 3.4 使用 opponent pool（可选）

```powershell
uv run python rl/train_ppo.py --timesteps 20000 --num-envs 4 --use_opponent_pool --pool_dir models/pool --out models/ppo_pool
```

说明：
- 当前 pool 扫描只接收 `.zip` 模型，避免无效模型文件污染。
- 训练失败时默认抛错；若需降级运行，显式加 `--allow_fallback`。

### 3.5 Duplicate 评测

```powershell
uv run python rl/eval_duplicate.py --model models/ppo_main --seeds 1001 1002 1003 1004 --strict_load --fail_on_fallback --out reports/dup_main.json
```

大规模（推荐）可直接用区间参数：

```powershell
uv run python rl/eval_duplicate.py --model models/ppo_main --seed_start 1001 --seed_end 2000 --strict_load --fail_on_fallback --out reports/dup_main_1001_2000.json
```

推荐把评测种子固定拆成两套，防止 seed overfit：

```powershell
uv run python rl/eval_duplicate.py --model models/ppo_main --seed_set dev --strict_load --fail_on_fallback --out reports/dup_main_seedset_dev.json
uv run python rl/eval_duplicate.py --model models/ppo_main --seed_set test --strict_load --fail_on_fallback --out reports/dup_main_seedset_test.json
uv run python rl/eval_duplicate.py --model models/unused --policy_mode rule --seed_set test --out reports/dup_rule_seedset_test.json
```

说明：
- `dev = 1001..1500`，用于日常调参
- `test = 1501..2000`，用于里程碑结论和对外口径
- 对外结论只看 `test`

建议同时生成 RuleBot 基线并做自动判定：

```powershell
uv run python rl/eval_duplicate.py --model models/unused --policy_mode rule --seeds 1001 1002 1003 1004 --out reports/dup_rule_main.json
uv run python rl/assess_model_readiness.py --model_report reports/dup_main.json --rule_report reports/dup_rule_main.json --out reports/readiness_main.json
```

可选：控制环境内对手扰动强度（鲁棒性测试）：

```powershell
uv run python rl/eval_duplicate.py --model models/ppo_main --seed_set test --strict_load --fail_on_fallback --opponent_epsilon 0.0 --out reports/dup_main_seedset_test_opp0.json
uv run python rl/eval_duplicate.py --model models/ppo_main --seed_set test --strict_load --fail_on_fallback --opponent_epsilon 0.16 --out reports/dup_main_seedset_test_opp16.json
uv run python rl/eval_duplicate.py --model models/unused --policy_mode rule --seed_set test --opponent_epsilon 0.0 --out reports/dup_rule_seedset_test_opp0.json
uv run python rl/eval_duplicate.py --model models/unused --policy_mode rule --seed_set test --opponent_epsilon 0.16 --out reports/dup_rule_seedset_test_opp16.json
```

可选：评测时也固定对手混合策略口径（避免口径漂移）：

```powershell
uv run python rl/eval_duplicate.py --model models/ppo_main --seed_set test --strict_load --fail_on_fallback --opponent_mix "rule:0.4,defensive:0.2,aggressive:0.2,random:0.1,minlegal:0.1" --out reports/dup_main_seedset_test_mix.json
```

趋势汇总：

```powershell
uv run python rl/build_duplicate_trend.py --reports reports/dup_main.json reports/dup_rule_main.json --out_md reports/duplicate_trend.md --out_json reports/duplicate_trend.json
```

多场景“路人局可用性”门禁（推荐）：

```powershell
uv run python rl/assess_human_readiness.py ^
  --model_reports reports/dup_main_seedset_test.json reports/dup_main_seedset_test_opp0.json reports/dup_main_seedset_test_opp16.json ^
  --rule_reports reports/dup_rule_seedset_test.json reports/dup_rule_seedset_test_opp0.json reports/dup_rule_seedset_test_opp16.json ^
  --scenario_names test_default_eps08 test_opp0 test_opp16 ^
  --min_games 2000 --min_advantage 2.0 --min_pass_ratio 1.0 ^
  --out reports/human_readiness_suite_seedset_test.json
```

分层 readiness（L1/L2/L3）：

```powershell
uv run python rl/assess_readiness_levels.py ^
  --l1_model_report reports/dup_main_seedset_test.json ^
  --l1_rule_report reports/dup_rule_seedset_test.json ^
  --l2_suite_report reports/human_readiness_suite_seedset_test.json ^
  --rule_profile rules/profile_hangzhou_mvp.yaml ^
  --pytest_passed ^
  --out reports/readiness_levels_seedset_test.json
```

如果你选择“纯仿真口径”（不采集真人 A/B），可显式关闭 L3 的真人数据要求：

```powershell
uv run python rl/assess_readiness_levels.py ^
  --l1_model_report reports/dup_ppo_20k_hzvA_testSeeds.json ^
  --l1_rule_report reports/dup_rule_hzvA_testSeeds.json ^
  --l2_suite_report reports/human_readiness_hzvA.json ^
  --rule_profile rules/hz_local_v2026_02_A.yaml ^
  --expected_rule_profile_id hz_local_v2026_02_A ^
  --expected_spec_version v1.1 ^
  --expected_seed_set_id test ^
  --pytest_passed ^
  --no_require_real_ab_for_l3 ^
  --out reports/readiness_levels_hzvA_sim_only.json
```

说明：该口径用于“仿真可用性结论”，不等价于真人牌桌外部宣称。

### 3.6 版本化命名与报告上下文（防结论串线）

推荐命名规范：
- 规则画像：`rules/hz_local_v2026_02_A.yaml`
- 模型：`models/ppo_20k_hzvA_bc1_ppo3.zip`
- Duplicate 报告：`reports/dup_ppo_20k_hzvA_testSeeds.json`
- Human readiness：`reports/human_readiness_hzvA.json`

`eval_duplicate` 现在会在报告中写入并要求后续门禁对齐：
- `rule_profile_id`
- `spec_version`
- `seed_set_id`
- `opponent_suite_id`

示例（显式标注版本上下文）：

```powershell
uv run python rl/eval_duplicate.py ^
  --model models/ppo_20k_hzvA_bc1_ppo3 ^
  --seed_set test ^
  --rule_profile rules/hz_local_v2026_02_A.yaml ^
  --rule_profile_id hz_local_v2026_02_A ^
  --spec_version v1.1 ^
  --seed_set_id testSeeds ^
  --opponent_suite_id mix_rule_defensive_aggressive_v1 ^
  --strict_load --fail_on_fallback ^
  --out reports/dup_ppo_20k_hzvA_testSeeds.json
```

`assess_model_readiness.py` / `assess_human_readiness.py` / `assess_readiness_levels.py` 会校验上下文一致性；若版本串线将直接报错。

推荐的完整执行链（`hzvA`）：

```powershell
uv run python rl/eval_duplicate.py ^
  --model models/ppo_20k_check --policy_mode model --seed_set test ^
  --strict_load --fail_on_fallback ^
  --rule_profile rules/hz_local_v2026_02_A.yaml ^
  --rule_profile_id hz_local_v2026_02_A --spec_version v1.1 ^
  --seed_set_id test --opponent_suite_id opp_suite_eps08_rule ^
  --opponent_mix "rule:1.0" ^
  --out reports/dup_ppo_20k_hzvA_testSeeds.json

uv run python rl/eval_duplicate.py ^
  --model models/unused --policy_mode rule --seed_set test --rulebot_epsilon 0.0 ^
  --rule_profile rules/hz_local_v2026_02_A.yaml ^
  --rule_profile_id hz_local_v2026_02_A --spec_version v1.1 ^
  --seed_set_id test --opponent_suite_id opp_suite_eps08_rule ^
  --opponent_mix "rule:1.0" ^
  --out reports/dup_rule_hzvA_testSeeds.json

uv run python rl/assess_model_readiness.py ^
  --model_report reports/dup_ppo_20k_hzvA_testSeeds.json ^
  --rule_report reports/dup_rule_hzvA_testSeeds.json ^
  --expected_rule_profile_id hz_local_v2026_02_A ^
  --expected_spec_version v1.1 ^
  --expected_seed_set_id test ^
  --expected_opponent_suite_id opp_suite_eps08_rule ^
  --min_games 2000 --min_advantage 2.0 ^
  --out reports/readiness_hzvA_testSeeds.json
```

### 3.7 真人回放离线集与 A/B 报告（L3 必需）

先把真人对局原始记录构造成可复现离线集：

```powershell
uv run python datasets/build_replay_offline.py ^
  --inputs data/human_ab_batch1.jsonl ^
  --out_dir datasets/replay_offline ^
  --tag hzvA_batch1 ^
  --rule_profile_id hz_local_v2026_02_A ^
  --spec_version v1.1 ^
  --seed_set_id human_live ^
  --opponent_suite_id human_table_v1
```

再从原始记录或离线集记录直接生成 `real_ab_report`：

```powershell
uv run python rl/assess_real_ab.py ^
  --inputs data/human_ab_batch1.jsonl ^
  --out reports/real_ab_2026_02_hzvA.json ^
  --min_games 200 ^
  --min_advantage 0.0 ^
  --rule_profile_id hz_local_v2026_02_A ^
  --spec_version v1.1 ^
  --seed_set_id human_live ^
  --opponent_suite_id human_table_v1
```

最后把 `real_ab_report` 接入分层门禁：

```powershell
uv run python rl/assess_readiness_levels.py ^
  --l1_model_report reports/dup_ppo_20k_hzvA_testSeeds.json ^
  --l1_rule_report reports/dup_rule_hzvA_testSeeds.json ^
  --l2_suite_report reports/human_readiness_hzvA.json ^
  --rule_profile rules/hz_local_v2026_02_A.yaml ^
  --expected_rule_profile_id hz_local_v2026_02_A ^
  --expected_spec_version v1.1 ^
  --expected_seed_set_id test ^
  --pytest_passed ^
  --real_ab_report reports/real_ab_2026_02_hzvA.json ^
  --min_real_ab_games 200 ^
  --min_real_ab_advantage 0.0 ^
  --out reports/readiness_levels_hzvA_l3.json
```

## 4) 本地规则开关（杭麻 MVP）

当前支持的规则参数（数据/训练/评测脚本已统一支持）：
- `--disable_wealth_god`：关闭财神规则
- `--allow_discard_wealth_god`：允许在有其他可打牌时也可打财神
- `--enable_qiaoxiang`：启用敲响状态机（杠后进入敲响态；敲响态下仅可胡/过，且胡牌+1番）

当前已实现的胡型/番型（MVP 本地计分）：
- 特殊胡型：`七对`、`十三幺`
- 常见番型：`对对胡`、`清一色`、`混一色`、`门清`
- 敲响加番：`qiaoxiang +1 番`

示例（关闭财神）：

```powershell
uv run python rl/train_ppo.py --timesteps 5000 --num-envs 4 --disable_wealth_god --out models/ppo_no_wg
uv run python rl/eval_duplicate.py --model models/ppo_no_wg --seeds 1001 1002 --strict_load --fail_on_fallback --disable_wealth_god --out reports/dup_no_wg.json
```

### 4.1 Rule Profile + Top10 争议规则回归

规则画像文件：
- `rules/profile_hangzhou_mvp.yaml`

Top10 争议规则 fixtures：
- `tests/fixtures/local_rules/*.json`

统一回归入口：
```powershell
uv run pytest tests/test_local_rule_profiles.py -q
```

覆盖项（每个 fixture 可包含一个或多个断言）：
- 合法动作 mask 期望
- 抢权裁决优先级与同优先级座位顺序
- 本地番型计分结果期望
## 5) 项目结构

```text
.
|- mapping.py              # tile/action mapping 与候选槽位分配
|- engine.py               # 规则引擎与状态推进
|- env.py                  # Gymnasium 单智能体环境（Hero + 内嵌对手）
|- bots.py                 # RandomBot / RuleBot / OldPolicyBot
|- datasets/
|  |- gen_data.py          # 合成数据生成
|  |- bc_train.py          # 行为克隆训练
|  |- build_replay_offline.py  # 真人回放离线集构建
|- rl/
|  |- train_ppo.py         # PPO 训练入口
|  |- eval_duplicate.py    # Duplicate 评测入口
|  |- assess_real_ab.py    # 真人A/B报告评估
|- tests/                  # mask/priority/seed/stability 回归门禁
|- docs/
|  |- runbook.md           # 运维与故障处理
|  |- architecture.md      # 架构与契约说明
```

## 6) 关键契约（必须遵守）

- Env API：`reset(seed=None, options=None)`、`step(action)` 符合 Gymnasium。
- Action space：固定 `Discrete(47)`，`43..46` 为通用候选槽位。
- `action_masks()`：必须返回 `shape=(47,)` 的 `bool` 数组，且不能全 False。
- `Pass(42)`：Reaction 永远可选，MyTurn 默认不可选。
- 快进保护：`max_internal_steps` 超限必须 `truncated=True` 并输出 debug 信息。

详情见：
- `PROJECT_CONTROL.md`
- `SPEC.md`
- `CHANGELOG_MAHJONG.md`（麻将主线）
- `CHANGELOG_FRONTEND.md`（前端主线）

## 7) 常见问题

### Torch 导入失败

先检查：
```powershell
uv run python -c "import torch; print(torch.__version__)"
```

若失败，重新初始化并安装：
```powershell
uv venv .venv --python 3.11 --managed-python
uv pip install --python .venv/Scripts/python.exe -r requirements.txt
```

### Duplicate 报告异常

检查报告字段：
```powershell
uv run python -c "import json; d=json.load(open('reports/dup_smoke.json','r',encoding='utf-8')); print(all(k in d for k in ['mean_diff','std_diff','ci95','n_games']))"
```

## 8) 当前状态

本仓库已完成 MVP 闭环，包含测试门禁、训练入口、评测入口和交付文档。当前结果适用于“流程可执行性与稳定性”验证，不代表最终强度上限。

## 9) 外部结论门禁（必须满足）

要对外发布“可打赢路人”结论，至少需要：

1. `L1 PASS`：回归门禁全绿 + duplicate 优势显著。
2. `L2 PASS`：多场景仿真门禁通过（例如 eps08/opp0/opp16）。
3. `L3 PASS`：在锁定规则画像版本下，真人 A/B 小样本达到阈值，并有 `real_ab_report`。

当前状态：
- `L1 PASS`
- `L2 PASS`
- `L3 FAIL`（缺 `real_ab_report`）

## 10) 前端展示站（Vue3）

仓库已新增 `frontend/` 商业化展示页面（Vue3 + Vite + TypeScript）。

### 9.1 启动开发环境

```powershell
uv run uvicorn api.server:app --host 127.0.0.1 --port 8000
cd frontend
npm install
npm run dev
```

### 9.2 构建生产包

```powershell
cd frontend
npm run build
```

构建产物：`frontend/dist/`

页面包含：
- 现代营销首页视觉系统（响应式、渐变背景、动画入场）
- 能力与训练闭环展示区块
- 指标看板与 FAQ 折叠
- 预约演示表单（前端校验 + 后端 API 提交 + 状态反馈）

可选环境变量：
- `VITE_API_BASE_URL`：前端 API 基地址。默认走相对路径 `/api`，开发时由 Vite proxy 转发到 `http://127.0.0.1:8000`。
