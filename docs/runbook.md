# Runbook

本手册用于日常运行、快速验收与故障排查。所有命令默认在仓库根目录执行。

## 1) 运行模式

### 1.1 Fast Gate（仅门禁）

```powershell
uv run pytest tests -q
```

适用：
- 合并前快速回归
- 文档/脚本变更后的安全检查

### 1.2 Smoke Pipeline（小规模全链路）

```powershell
uv run python datasets/gen_data.py --episodes 20 --out datasets/artifacts/smoke_data.npz
uv run python datasets/bc_train.py --data datasets/artifacts/smoke_data.npz --epochs 1 --out models/bc_smoke.pt
uv run python rl/train_ppo.py --timesteps 3000 --num-envs 4 --reward_mode log1p --out models/ppo_smoke
uv run python rl/eval_duplicate.py --model models/ppo_smoke --seeds 1001 1002 1003 1004 --out reports/dup_smoke.json
```

### 1.3 Train-Only（已有数据）

```powershell
uv run python datasets/bc_train.py --data datasets/artifacts/train_data.npz --epochs 3 --out models/bc_main.pt
uv run python rl/train_ppo.py --timesteps 50000 --num-envs 8 --reward_mode log1p --out models/ppo_main
```

### 1.3.1 Train-Only（断点续训）

中断后可直接重跑同一命令继续推进到目标总步数：

```powershell
uv run python rl/train_ppo.py ^
  --timesteps 200000 ^
  --target_total_timesteps 2000000 ^
  --num-envs 8 ^
  --vec_backend subproc ^
  --reward_mode log1p ^
  --seed 2026 ^
  --checkpoint_every 50000 ^
  --checkpoint_dir models/checkpoints ^
  --checkpoint_prefix ppo_long_main_ckpt ^
  --resume_latest_checkpoint ^
  --out models/ppo_long_main
```

关键点：
- `timesteps` 是本次训练 chunk。
- `target_total_timesteps` 是总目标步数。
- `resume_latest_checkpoint` 会自动选同前缀的最新 checkpoint。
- 训练元数据见 `models/ppo_long_main.json`，字段关注：
  - `num_timesteps_total`
  - `target_total_timesteps`
  - `target_reached`
  - `resumed`
  - `resume_source`

### 1.4 Frontend + API 联调（线索表单）

```powershell
uv run uvicorn api.server:app --host 127.0.0.1 --port 8000
cd frontend
npm run dev
```

默认请求路径：
- 前端：`POST /api/leads`
- 后端：`api/server.py`
- 开发转发：`frontend/vite.config.ts` (`/api -> 127.0.0.1:8000`)

### 1.5 版本化评测（推荐主流程）

目标：同一规则画像/同一评测口径下产出可追溯结论，避免报告串线。

最小流程：
1. 固定 `rule_profile_id/spec_version/seed_set_id/opponent_suite_id`
2. 产出 model vs rule 的 duplicate 报告
3. 运行 `assess_model_readiness.py` 与 `assess_human_readiness.py`
4. 运行 `assess_readiness_levels.py` 得到 `L1/L2/L3`

## 2) 前置检查（Preflight）

```powershell
uv --version
uv run python --version
uv run python -c "import gymnasium, numpy, torch; print('deps_ok')"
```

若 `torch` 导入失败，先修复环境再跑训练（见第 5 节）。

## 3) 每阶段验收标准

### 3.1 数据生成

成功条件：
- 命令 exit code 为 0
- 输出 `saved=... npz`
- 文件中包含 `obs/action/legal_mask/phase/meta`

快速校验：
```powershell
uv run python -c "import numpy as np; d=np.load('datasets/artifacts/smoke_data.npz', allow_pickle=True); print(d['obs'].shape, d['legal_mask'].shape)"
```

### 3.2 BC 训练

成功条件：
- 命令 exit code 为 0
- 输出 `final_loss=...`
- 生成 `models/*.pt` 或 fallback 产物

### 3.3 PPO 训练

成功条件：
- 生成 `models/<name>.zip` 与 `models/<name>.json`
- 元数据包含 `backend`

快速校验：
```powershell
uv run python -c "import json; d=json.load(open('models/ppo_smoke.json','r',encoding='utf-8')); print(d.get('backend'))"
```

### 3.4 Duplicate 评测

成功条件：
- 生成 `reports/*.json`
- 包含 `mean_diff/std_diff/ci95/n_games`

快速校验：
```powershell
uv run python -c "import json; d=json.load(open('reports/dup_smoke.json','r',encoding='utf-8')); print(d['n_games'], all(k in d for k in ['mean_diff','std_diff','ci95','n_games']))"
```

版本化上下文字段校验：
```powershell
uv run python -c "import json; d=json.load(open('reports/dup_ppo_20k_hzvA_testSeeds.json','r',encoding='utf-8')); print(d['rule_profile_id'], d['spec_version'], d['seed_set_id'], d['opponent_suite_id'])"
```

### 3.6 Readiness 分层验收

关键产物：
- `reports/readiness_hzvA_testSeeds.json`
- `reports/human_readiness_hzvA.json`
- `reports/readiness_levels_hzvA_testSeeds.json`

关键判定：
- `L1`：训练稳定
- `L2`：仿真稳健
- `L3`：真人可宣称（必须有真人 A/B 报告）

### 3.5 API 线索提交

成功条件：
- `GET /api/health` 返回 `{"status":"ok"}`
- `POST /api/leads` 返回 `status=ok`
- 日志文件 `logs/leads.ndjson`（或 `LEAD_LOG_PATH` 指定路径）有新增记录

## 4) 对手池（opponent pool）使用约定

- 训练脚本仅扫描 `.zip` 模型加入 pool。
- basename 与 `.zip` 同名时，旧策略加载优先 `.zip`。
- 若需要允许训练失败自动回退，显式使用 `--allow_fallback`。
- 默认 pool 目录：`models/pool`（建议与训练输出目录分离）。

示例：
```powershell
uv run python rl/train_ppo.py --timesteps 20000 --num-envs 4 --use_opponent_pool --pool_dir models/pool --out models/ppo_pool
```

模型目录清理：
```powershell
uv run python tools/cleanup_models.py --models_dir models --archive_dir models/archive --apply
```

## 5) 常见故障与处理

### 5.1 Torch DLL 加载失败（WinError 1114）

现象：
- `import torch` 失败，报 `c10.dll` 或依赖库初始化错误。

处理：
1. `uv venv .venv --python 3.11 --managed-python`
2. `uv pip install --python .venv/Scripts/python.exe -r requirements.txt`
3. `uv run python -c "import torch; print(torch.__version__)"`

### 5.2 `ValueError: illegal action ...`

现象：
- 环境 step 阶段触发非法动作异常。

处理：
1. 打印 `info['action_mask']`，确认动作来自合法索引。
2. 检查 phase 是否正确（MyTurn/Reaction）。
3. 执行 `uv run pytest tests/test_mask.py -q`。

### 5.3 `truncated=True`（内部快进上限触发）

现象：
- 对局被 `max_internal_steps` 截断。

处理：
1. 检查 `info['phase']`、`info['actor']`、`info['last_discard']`、`info['recent_actions']`。
2. 执行 `uv run pytest tests/test_run_1000.py -q`。
3. 用固定 seed 复现并补回归用例。

### 5.5 本地长训卡住/无进展

建议用守护训练器替代裸跑：

```powershell
uv run python tools/guarded_train.py ^
  --run_id long_main ^
  --out models/ppo_long_main ^
  --report_out reports/guarded_train_long_main.json ^
  --chunk_timesteps 200000 ^
  --target_total_timesteps 2000000 ^
  --num_envs 14 ^
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

排查顺序：
1. 先看 `reports/guarded_train_<run_id>.json` 的 `fail_reason` 与每次 `progress_delta`。
2. 再看 `reports/heartbeat_<run_id>.json` 的 `status/updated_at_unix`。
3. 最后看 `logs/tui_*.log` 尾部错误。

### 5.4 Duplicate 报告字段缺失

处理：
1. 确认 `--out` 指向 `reports/*.json`。
2. 重新执行评测命令。
3. 检查报告 key 完整性（见第 3.4 节命令）。

## 6) 交付前检查清单

1. `uv run pytest tests -q` 通过。
2. 至少一个 PPO 模型元数据为 `backend=sb3_maskableppo`。
3. 至少一个 Duplicate 报告 `backend=sb3` 且 `n_games > 0`。
4. `CHANGELOG_AUTOPILOT.md` 追加本次执行记录。
5. 文档命令与脚本路径保持一致（`datasets/`、`rl/`、`tests/`）。
6. Readiness 报告上下文字段一致（`rule_profile_id/spec_version/seed_set_id`）。
7. 若对外结论包含“可打赢路人”，必须有 `L3 PASS` 证据。

## 7) 强度提升实验节奏（推荐）

1. 阶段 A：RuleBot 大样本 + BC 预热（先解决“乱打”）。  
2. 阶段 B：PPO vs RuleBot（先把 `mean_diff` 拉到稳定正值）。  
3. 阶段 C：Opponent Pool 温和 self-play（先替换 1 家，再逐步加）。  
4. 阶段 D：固定 duplicate seeds 版本淘汰（同口径对比）。  

执行原则：
- 每轮只改 1~2 个变量（例如：`timesteps`、`reward_mode`、`pool 替换比例`）。
- 每轮必须保留同一组 seeds 的对照报告，避免“参数漂移导致不可比”。

## 8) 真人 A/B 记录最小模板

每次真人样本批次建议记录为 `reports/real_ab_<date>_<version>.json`，至少包含：

- `rule_profile_id`
- `spec_version`
- `seed_set_id`（若不适用填 `human_live`）
- `opponent_suite_id`（建议填 `human_table_v1`）
- `n_games`
- `mean_diff`
- `status`
- `notes`（对局环境、玩家构成、是否有裁判复盘）

没有这份报告时，`L3` 一律视为未达成。

推荐直接用脚本自动产出，避免手填出错：

```powershell
uv run python datasets/build_replay_offline.py ^
  --inputs data/human_ab_batch1.jsonl ^
  --out_dir datasets/replay_offline ^
  --tag hzvA_batch1 ^
  --rule_profile_id hz_local_v2026_02_A ^
  --spec_version v1.1 ^
  --seed_set_id human_live ^
  --opponent_suite_id human_table_v1

uv run python rl/assess_real_ab.py ^
  --inputs data/human_ab_batch1.jsonl ^
  --out reports/real_ab_2026_02_hzvA.json ^
  --min_games 200 ^
  --min_advantage 0.0 ^
  --rule_profile_id hz_local_v2026_02_A ^
  --spec_version v1.1 ^
  --seed_set_id human_live ^
  --opponent_suite_id human_table_v1

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
  --out reports/readiness_levels_hzvA_l3.json
```
