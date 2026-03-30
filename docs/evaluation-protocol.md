# Evaluation Protocol

This document defines the recommended duplicate-evaluation workflow and the fields expected in generated reports.

## Goal

Keep model comparisons decision-ready and comparable across runs.

## Core Rules

- compare runs under the same `rule_profile_id`
- compare runs under the same `spec_version`
- compare runs under the same `seed_set_id`
- compare runs under the same `opponent_suite_id`
- avoid mixing exploratory dev reports with milestone-level test reports

## Recommended Flow

### 1) Generate a model duplicate report

```powershell
uv run python rl/eval_duplicate.py ^
  --model models/ppo_main ^
  --seed_set test ^
  --strict_load ^
  --fail_on_fallback ^
  --out reports/dup_main_seedset_test.json
```

### 2) Generate the rule baseline report

```powershell
uv run python rl/eval_duplicate.py ^
  --model models/unused ^
  --policy_mode rule ^
  --seed_set test ^
  --out reports/dup_rule_seedset_test.json
```

### 3) Build a comparison trend report

```powershell
uv run python rl/build_duplicate_trend.py ^
  --reports reports/dup_main_seedset_test.json reports/dup_rule_seedset_test.json ^
  --out_md reports/duplicate_trend.md ^
  --out_json reports/duplicate_trend.json
```

## Required Fields In Duplicate Reports

The duplicate evaluation report should include:

- `report_schema_version`
- `mean_diff`
- `std_diff`
- `ci95`
- `n_games`
- `rule_profile_id`
- `spec_version`
- `seed_set_id`
- `opponent_suite_id`

## Required Fields In Trend Reports

The trend JSON should include:

- `report_schema_version`
- `rows`

Each row should preserve:

- version name derived from the report path
- policy/backend summary
- duplicate metrics
- comparison context (`rule_profile_id`, `spec_version`, `seed_set_id`, `opponent_suite_id`)

## Comparison Example

Interpretation example:

- use `mean_diff` as the headline value
- use `lower_ci95` to check whether advantage remains positive under uncertainty
- reject comparisons when context fields do not match

## Recommendation

- use `seed_set=dev` for tuning
- use `seed_set=test` for milestone statements
- keep the JSON report outputs under version control only when they are intentionally curated artifacts

