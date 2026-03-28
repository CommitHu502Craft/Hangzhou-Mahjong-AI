# Readiness Status

Date: 2026-02-22  
Rule Profile: `hz_local_v2026_02_A`  
Spec Version: `v1.1`  
Seed Set: `test` (`1501..2000`)

## 1) Current Level

- `L1`: PASS
- `L2`: PASS
- `L3`: FAIL (missing real-table A/B report)

Primary evidence:
- `reports/readiness_hzvA_testSeeds.json`
- `reports/human_readiness_hzvA.json`
- `reports/readiness_levels_hzvA_testSeeds.json`

## 2) Scenario Metrics Snapshot

- Base (`opp_suite_eps08_rule`)
  - Model: `reports/dup_ppo_20k_hzvA_testSeeds.json`
  - Rule: `reports/dup_rule_hzvA_testSeeds.json`
- Opponent epsilon 0 (`opp_suite_eps00_rule`)
  - Model: `reports/dup_ppo_20k_hzvA_testSeeds_opp0.json`
  - Rule: `reports/dup_rule_hzvA_testSeeds_opp0.json`
- Opponent epsilon 0.16 (`opp_suite_eps16_rule`)
  - Model: `reports/dup_ppo_20k_hzvA_testSeeds_opp16.json`
  - Rule: `reports/dup_rule_hzvA_testSeeds_opp16.json`

## 3) Mandatory Preconditions For External Claim

1. 真人回放离线回测集落盘（可复现）。
2. 真人小样本 A/B（至少 200 局，建议 200~500 局）落盘。
3. `assess_readiness_levels.py` 引入 `real_ab_report` 后达到 `L3 PASS`。
4. 保持同一 `rule_profile_id/spec_version`，避免口径漂移。

## 4) Next Action Checklist

1. 使用 `datasets/build_replay_offline.py` 产出 `datasets/replay_offline/*`（带最小元数据与回放索引）。
2. 使用 `rl/assess_real_ab.py` 生成 `reports/real_ab_<date>_hzvA.json`。
3. 复跑：
   - `assess_model_readiness.py`
   - `assess_human_readiness.py`
   - `assess_readiness_levels.py --real_ab_report ...`
4. 若 `highest_level=L3`，再更新对外结论文案。

## 5) Simulation-Only Mode（无真人数据）

若你明确不采集真人 A/B，可使用：

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

注意：该报告是“仿真口径结论”，不代表真人牌桌结论。
