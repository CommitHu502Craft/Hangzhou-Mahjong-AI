# RUN_SUMMARY.md

Date: 2026-02-22  
Project: Hangzhou Mahjong AI

## 1) 完成的任务列表

- 已完成项目主线：规则引擎、Gym 环境、RuleBot/BC/PPO、Duplicate 评测、前后端联调。
- 已完成 `qiaoxiang` 完整状态机与本地番型扩展（含七对、十三幺）。
- 已完成 Rule Profile + Top10 争议规则 fixture 回归套件。
- 已完成 Duplicate seed 拆分（`dev/test`）与 anti-overfit 口径固化。
- 已完成 readiness 分层门禁（L1/L2/L3）脚本与产物。
- 已完成“单变量实验矩阵”重训与自动版本化报告输出（`baseline` / `reward_raw_vecnorm` / `opponent_mix_diverse`）。
- 已补齐真人闭环工具：`datasets/build_replay_offline.py`（回放离线集）与 `rl/assess_real_ab.py`（A/B 报告自动评估）。
- 已新增本地断点续训能力：`rl/train_ppo.py` 支持 checkpoint+resume+target_total；CMD TUI 支持“长训/续训/进度看板”。
- 已新增守护训练能力：`tools/guarded_train.py` 支持心跳超时重试与无进展保护，降低长训白跑风险。
- 已补强守护训练与 TUI 稳定性：守护进度读取支持 `meta+checkpoint` 聚合，CMD 菜单支持 `--help` 与 EOF 优雅退出。

## 2) 未完成任务列表

- 未完成真人牌桌 A/B 对战报告（L3 需要）。
- 未完成全部杭麻地方番型与争议细则全覆盖（当前为可训练 MVP + Top10 争议点）。
- 未完成大规模长期训练实验矩阵（当前为可运行和可评测基线）。

## 3) 关键命令与 exit codes

1. `uv run pytest tests -q` -> `exit 0` (`110 passed`)
2. `uv run python rl/run_single_variable_matrix.py --matrix_id hzvA_svmatrix_v1 --rule_profile rules/hz_local_v2026_02_A.yaml --rule_profile_id hz_local_v2026_02_A --spec_version v1.1 --seed_set dev --seed_set_id dev --enable_qiaoxiang --data_episodes 80 --data_max_episodes 120 --data_target_decisions 1200 --data_min_samples 300 --bc_epochs 1 --ppo_timesteps 5000 --ppo_num_envs 4 --vec_backend dummy --monitor_episodes 8` -> `exit 0`
3. `uv run python rl/eval_duplicate.py --model models/ppo_20k_check --policy_mode model --seed_set test --opponent_epsilon 0.0 --strict_load --fail_on_fallback --out reports/dup_ppo_20k_seedset_test_opp0.json` -> `exit 0`
4. `uv run python rl/eval_duplicate.py --model models/ppo_20k_check --policy_mode rule --seed_set test --opponent_epsilon 0.0 --strict_load --fail_on_fallback --out reports/dup_rule_seedset_test_opp0.json` -> `exit 0`
5. `uv run python rl/assess_human_readiness.py --model_reports reports/dup_ppo_20k_seedset_test.json reports/dup_ppo_20k_seedset_test_opp0.json reports/dup_ppo_20k_seedset_test_opp16.json --rule_reports reports/dup_rule_seedset_test.json reports/dup_rule_seedset_test_opp0.json reports/dup_rule_seedset_test_opp16.json --scenario_names test_default_eps08 test_opp0 test_opp16 --min_games 2000 --min_advantage 2.0 --min_pass_ratio 1.0 --out reports/human_readiness_suite_seedset_test.json` -> `exit 0`
6. `uv run python rl/assess_readiness_levels.py --l1_model_report reports/dup_ppo_20k_seedset_test.json --l1_rule_report reports/dup_rule_seedset_test.json --l2_suite_report reports/human_readiness_suite_seedset_test.json --rule_profile rules/profile_hangzhou_mvp.yaml --pytest_passed --out reports/readiness_levels_seedset_test.json` -> `exit 0`
7. `uv run pytest tests/test_assess_readiness_levels.py -q` -> `exit 0`
8. `uv run pytest tests/test_assess_real_ab.py tests/test_build_replay_offline.py -q` -> `exit 0`
9. `uv run python rl/assess_real_ab.py --inputs reports/real_ab_synthetic_smoke.jsonl --out reports/real_ab_synthetic_smoke.json --min_games 5 --min_advantage 0.5 --rule_profile_id hz_local_v2026_02_A --spec_version v1.1 --seed_set_id human_live --opponent_suite_id human_table_v1` -> `exit 0`
10. `uv run pytest tests/test_train_resume.py tests/test_sim_train_tui.py -q` -> `exit 0`
11. `uv run python tools/guarded_train.py --run_id guard_check --out models/tmp/ppo_guard_check --report_out reports/guarded_train_guard_check.json --chunk_timesteps 80 --target_total_timesteps 160 --num_envs 1 --seed 5252 --vec_backend dummy --reward_mode log1p --bot_epsilon 0.08 --opponent_mix rule:1.0 --monitor_episodes 2 --checkpoint_every 40 --checkpoint_dir models/checkpoints/tmp --checkpoint_prefix ppo_guard_check_ckpt --heartbeat_every 20 --heartbeat_path reports/heartbeat_guard_check.json --stale_timeout_minutes 2 --poll_seconds 2 --max_attempts 3 --max_no_progress_attempts 2 --min_free_disk_gb 1 --run_tag guard-check` -> `exit 0`

## 4) 生成的核心产物清单

- 规则画像与回归：
  - `rules/profile_hangzhou_mvp.yaml`
  - `rules/hz_local_v2026_02_A.yaml`
  - `tests/fixtures/local_rules/*.json`
  - `tests/test_local_rule_profiles.py`
- seed split 与门禁：
  - `rl/report_context.py`
  - `rl/seed_splits.py`
  - `reports/dup_ppo_20k_seedset_dev.json`
  - `reports/dup_rule_seedset_dev.json`
  - `reports/dup_ppo_20k_seedset_test.json`
  - `reports/dup_rule_seedset_test.json`
  - `reports/dup_ppo_20k_seedset_test_opp0.json`
  - `reports/dup_rule_seedset_test_opp0.json`
  - `reports/dup_ppo_20k_seedset_test_opp16.json`
  - `reports/dup_rule_seedset_test_opp16.json`
  - `reports/readiness_seedset_test.json`
  - `reports/human_readiness_suite_seedset_test.json`
  - `reports/readiness_levels_seedset_test.json`
  - `reports/dup_context_smoke.json`
- 单变量矩阵产物：
  - `rl/run_single_variable_matrix.py`
  - `tests/test_single_variable_matrix.py`
  - `datasets/artifacts/train_data_hzvA_svmatrix_v1_hz_local_v2026_02_A_20260222_152220.npz`
  - `models/bc_hzvA_svmatrix_v1_hz_local_v2026_02_A_20260222_152220.pt`
  - `models/ppo_hzvA_svmatrix_v1_hz_local_v2026_02_A_baseline.zip`
  - `models/ppo_hzvA_svmatrix_v1_hz_local_v2026_02_A_reward_raw_vecnorm.zip`
  - `models/ppo_hzvA_svmatrix_v1_hz_local_v2026_02_A_opponent_mix_diverse.zip`
  - `reports/matrix_hzvA_svmatrix_v1_hz_local_v2026_02_A_dev.json`
  - `reports/matrix_hzvA_svmatrix_v1_hz_local_v2026_02_A_dev.md`
  - `reports/dup_hzvA_svmatrix_v1_hz_local_v2026_02_A_baseline_dev.json`
  - `reports/dup_hzvA_svmatrix_v1_hz_local_v2026_02_A_reward_raw_vecnorm_dev.json`
  - `reports/dup_hzvA_svmatrix_v1_hz_local_v2026_02_A_opponent_mix_diverse_dev.json`
  - `reports/readiness_hzvA_svmatrix_v1_hz_local_v2026_02_A_baseline_dev.json`
  - `reports/readiness_hzvA_svmatrix_v1_hz_local_v2026_02_A_reward_raw_vecnorm_dev.json`
  - `reports/readiness_hzvA_svmatrix_v1_hz_local_v2026_02_A_opponent_mix_diverse_dev.json`
- 真人闭环工具与验证产物：
  - `datasets/build_replay_offline.py`
  - `rl/assess_real_ab.py`
  - `rl/real_ab_utils.py`
  - `tests/test_assess_real_ab.py`
  - `tests/test_build_replay_offline.py`
  - `reports/real_ab_synthetic_smoke.json`
  - `reports/readiness_levels_hzvA_synthetic_l3_smoke.json`
- 断点续训与本地训练增强：
  - `rl/train_ppo.py`（resume/checkpoint/target_total）
  - `tools/guarded_train.py`（heartbeat watchdog + auto retry）
  - `tests/test_train_resume.py`
  - `tests/test_guarded_train.py`
  - `tools/sim_train_tui.py`（长训菜单）
  - `tests/test_sim_train_tui.py`
- 文档同步：
  - `README.md`
  - `docs/architecture.md`
  - `reports/project_overall_completion_summary.md`
  - `CHANGELOG_MAHJONG.md`
  - `CHANGELOG_AUTOPILOT.md`

## 5) 风险 / 已知限制

1. 目前最高门禁为 `L2`，未满足 `L3`（缺真人 A/B 报告）。
2. 当前强度结论是相对 RuleBot 基线，不代表对所有真人群体都稳定优势。
3. 地方规则仍是“可训练 MVP + Top10 争议点”阶段，仍需持续补齐。
4. 仍需长期训练与多版本淘汰赛，避免一次性评测结论失真。

## 6) 下一步建议（最多 5 条）

1. 固定 `test` 集持续做版本淘汰赛，并维护 `duplicate_trend`。
2. 开始真人小样本 A/B（同规则画像）并沉淀 `real_ab_report`，推进到 `L3`。
3. 继续扩展本地番型与裁决边界 fixture，先测后改。
4. 执行大规模 `target_decisions` 数据生成和阶段化训练实验（一次只改 1~2 个变量）。
5. 若要上线推广，补数据库持久化与基础监控告警。
