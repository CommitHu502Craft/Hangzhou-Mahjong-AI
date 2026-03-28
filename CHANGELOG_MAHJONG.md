# CHANGELOG_MAHJONG.md

## Purpose

仅记录麻将引擎、训练、评测与后端 API 相关变更，降低跨项目噪音。

## Entries

### 2026-02-22 11:40
- 新增大规模 Duplicate 评测能力：`rl/eval_duplicate.py` 支持 `--seed_start/--seed_end`。
- 新增 Duplicate 趋势表生成脚本：`rl/build_duplicate_trend.py`。
- 引擎胡牌判定扩展：支持七对子（含财神万能牌补对）。
- 数据生成 meta 增加 phase/action 分布统计，便于训练前质量审查。
- 增强回归测试（priority/mask/hu/data/cleanup）。
- 新增 `tools/cleanup_models.py` 并将模型池默认目录切换到 `models/pool`（`rl/train_ppo.py`）。

### 2026-02-22 12:20
- 复核通过：`uv run pytest tests -q`（`34 passed`）。
- 复算并刷新趋势表：`reports/duplicate_trend.md` 与 `reports/duplicate_trend.json`。
- 复算并确认 readiness：`reports/readiness_ppo_20k_1001_2000.json`（`status=PASS`）。
- 更新项目总览：`RUN_SUMMARY.md` 与 `reports/project_overall_completion_summary.md` 对齐最新证据。

### 2026-02-22 13:30
- 落地敲响状态机：`idle -> active -> resolved_*`，并在 `kong` 触发敲响态。
- 敲响态规则约束生效：反应阶段仅 `hu/pass`，并加入计分加番。
- 胡牌扩展：新增 `十三幺` 判定，配合既有 `七对`。
- 本地番型计分：`对对胡/清一色/混一色/门清/敲响`。
- 新口径 duplicate（`1001..2000`）评测完成并通过 readiness gate（`status=PASS`）。

### 2026-02-22 13:45
- 新增 `qiaoxiang` env 掩码回归测试：确保敲响态屏蔽 `chi/pon/ming_kong`。
- 全量门禁更新为 `uv run pytest tests -q -> 40 passed`。

### 2026-02-22 14:10
- `eval_duplicate` 新增 `opponent_epsilon`，可做对手扰动鲁棒性评测。
- 新增 `assess_human_readiness.py` 多场景门禁（支持通过比例阈值）。
- 完成 3 场景门禁评估（base/opp0/opp16），`reports/human_readiness_suite.json` 为 `PASS`。
- 全量门禁更新为 `uv run pytest tests -q -> 43 passed`。

### 2026-02-22 14:30
- 新增规则画像：`rules/profile_hangzhou_mvp.yaml`（Top10 争议规则）。
- 新增 `rules/profiles.py` 与 `tests/test_local_rule_profiles.py`。
- 新增 `tests/fixtures/local_rules/*.json`（10 个 fixture，覆盖 mask/priority/scoring）。
- 引擎参数化增强：`wealth_god_can_meld`、`qiaoxiang_fan_bonus`、`base_score_unit`、`score_cap`、`draw_scoring_mode`。
- 全量门禁更新为 `uv run pytest tests -q -> 54 passed`。

### 2026-02-22 15:20
- 增补 test-seed 鲁棒性场景：新增 `opp0` 对照报告  
  - `reports/dup_ppo_20k_seedset_test_opp0.json`
  - `reports/dup_rule_seedset_test_opp0.json`
- 新增并固化 test-seed 三场景门禁报告：`reports/human_readiness_suite_seedset_test.json`（`PASS 3/3`）。
- 新增分层 readiness 报告：`reports/readiness_levels_seedset_test.json`（`highest_level=L2`）。
- 修复 `rl/assess_readiness_levels.py` 的直跑兼容性，支持 `uv run python rl/assess_readiness_levels.py ...`。
- 文档同步更新：`README.md`、`docs/architecture.md`、`RUN_SUMMARY.md`、`reports/project_overall_completion_summary.md`。
- 全量门禁更新为 `uv run pytest tests -q -> 60 passed`。

### 2026-02-22 16:35
- 扩展高频财神歧义动作：`chi` 反应已支持“财神替代”合法性展开，并统一 legal/apply 逻辑，修复 mask 与执行可能不一致问题。
- 新增候选槽位稳定性回归：`tests/test_candidate_slots.py`（含多暗杠槽位稳定、财神替代 chi 掩码暴露）。
- 对手体系升级：`opponent_mix` 支持 `rule/defensive/aggressive/random/minlegal` 混合对手，评测与训练脚本均可配置。
- 训练稳定门禁升级：
  - `datasets/gen_data.py` 新增分布门禁（phase 比例、动作占比、合法动作均值、截断率）。
  - `rl/train_ppo.py` 新增训练后监控门禁（phase 比例、reaction pass、非法动作率、截断率）。
- Reward 稳定性硬约束：`rl/train_ppo.py` 新增 `log1p` 与 `VecNormalize reward` 互斥检查，防止双重归一化。
- 全量门禁更新为 `uv run pytest tests -q -> 69 passed`。

### 2026-02-22 17:10
- 版本化报告上下文落地：`eval_duplicate` 输出新增  
  - `rule_profile_id`
  - `spec_version`
  - `seed_set_id`
  - `opponent_suite_id`
- readiness 脚本新增上下文一致性校验，防止“规则版本/种子口径/对手口径”串线：
  - `rl/assess_model_readiness.py`
  - `rl/assess_human_readiness.py`
  - `rl/assess_readiness_levels.py`
- 新增稳定性零容忍回归：`tests/test_stability_gates.py`
  - `test_no_all_false_mask_under_random_rollout`
  - `test_no_priority_deadlock_on_multi_reaction`
  - `test_truncation_rate_under_rulebot_selfplay_below_threshold`
- 文档补充版本化命名规范与上下文字段：`README.md`、`docs/architecture.md`。
- 全量门禁复核：`uv run pytest tests -q -> 75 passed`。

### 2026-02-22 17:35
- 文档体系完善：新增 `docs/readiness_status.md`，明确 `L1/L2/L3` 当前状态与外部结论前置条件。
- `README.md` 增加“当前验证状态”与版本化评测完整链路，明确当前为 `L2 PASS`、`L3 FAIL`。
- `docs/runbook.md` 增加版本化评测执行剧本、上下文校验命令、真人 A/B 报告最小模板。
- `docs/architecture.md` 同步规则画像主路径为 `rules/hz_local_v2026_02_A.yaml`，并补充 `report_context.py` 契约说明。

### 2026-02-22 17:45
- 新增单变量实验矩阵执行器：`rl/run_single_variable_matrix.py`，自动串联 `gen_data -> bc_train -> train_ppo -> eval_duplicate -> readiness`。
- 新增矩阵脚本回归测试：`tests/test_single_variable_matrix.py`。
- 完成首轮 `dev` 口径矩阵重训并自动落盘版本化报告：
  - `reports/matrix_hzvA_svmatrix_v1_hz_local_v2026_02_A_dev.json`
  - `reports/matrix_hzvA_svmatrix_v1_hz_local_v2026_02_A_dev.md`
- 核心结果（同规则画像/同 seed_set）：
  - `baseline`: `mean_diff=14.5333`, readiness `PASS`
  - `reward_raw_vecnorm`: `mean_diff=-15.9933`, readiness `FAIL`
  - `opponent_mix_diverse`: `mean_diff=7.3200`, readiness `PASS`
- 全量门禁复核：`uv run pytest tests -q -> 78 passed`。

### 2026-02-22 18:20
- 补齐真人闭环执行能力：
  - 新增 `datasets/build_replay_offline.py`，把真人A/B原始记录构建为可复现离线集（`records_*.ndjson + summary_*.json`）。
  - 新增 `rl/assess_real_ab.py`，将真人A/B原始记录自动汇总为标准 `real_ab_report`（含 `mean_diff/std/ci95` 和门禁状态）。
  - 新增共享解析与统计模块：`rl/real_ab_utils.py`。
- 修复 `assess_readiness_levels.py` 的规则画像锁定门禁误判：支持 `--expected_rule_profile_id` 显式锁定，避免 profile 别名导致 L3 假失败。
- 新增回归测试：
  - `tests/test_assess_real_ab.py`
  - `tests/test_build_replay_offline.py`
  - `tests/test_assess_readiness_levels.py` 增补 profile alias 用例
- 文档同步：`README.md`、`docs/runbook.md`、`docs/readiness_status.md`、`RUN_SUMMARY.md`、`reports/project_overall_completion_summary.md`。
- 全量门禁复核：`uv run pytest tests -q -> 83 passed`。

### 2026-02-22 18:35
- 新增“纯仿真口径”readiness 固定命令与报告产物：
  - `reports/readiness_levels_hzvA_sim_only.json`
- 文档补充：
  - `README.md` 增加 `--no_require_real_ab_for_l3` 用法
  - `docs/readiness_status.md` 增加 Simulation-Only 模式说明

### 2026-02-22 18:46
- 新增 Windows CMD 菜单式训练入口：
  - `sim_train_tui.cmd`
  - `tools/sim_train_tui.py`
- 功能覆盖：
  - 短训（Quick Baseline）
  - 短训矩阵（Baseline + OpponentMix）
  - 最新模型 test 评测 + sim-only readiness
  - 一键测试门禁（`uv run pytest tests -q`）
  - 状态面板（最新模型、矩阵Top、readiness路径、上次任务状态）
- 新增回归测试：`tests/test_sim_train_tui.py`。
- 文档补充：`README.md` 增加 CMD 启动方式与菜单说明。
- 全量门禁复核：`uv run pytest tests -q -> 86 passed`。

### 2026-02-22 18:55
- 训练脚本增强为可断点续训：
  - `rl/train_ppo.py` 新增参数：
    - `--resume_from`
    - `--resume_latest_checkpoint`
    - `--checkpoint_every/--checkpoint_dir/--checkpoint_prefix`
    - `--target_total_timesteps`
  - 支持按 chunk 续训到目标总步数，并在元数据写入：
    - `num_timesteps_total`
    - `target_total_timesteps`
    - `target_reached`
    - `resumed/resume_source`
- CMD/TUI 增强：
  - `tools/sim_train_tui.py` 新增长训能力：
    - 启动长训（创建配置）
    - 继续上次长训（自动从最新 checkpoint 恢复）
    - 查看长训进度（checkpoint/meta 聚合）
  - 状态文件 `reports/tui_state.json` 增加 `long_run` 配置持久化。
- 新增回归测试：
  - `tests/test_train_resume.py`
  - `tests/test_sim_train_tui.py` 增补长训进度用例
- 文档同步：
  - `README.md`
  - `docs/runbook.md`
  - `RUN_SUMMARY.md`
  - `reports/project_overall_completion_summary.md`
- 全量门禁复核：`uv run pytest tests -q -> 91 passed`。

### 2026-02-22 19:15
- 补强“本地长训防翻车”能力：
  - `rl/train_ppo.py` 新增心跳与磁盘门禁：
    - `--heartbeat_every/--heartbeat_path`
    - `--min_free_disk_gb`
  - 训练心跳落盘支持状态机：`running/finished/done/skipped/interrupted/error`。
- 新增守护训练器：`tools/guarded_train.py`
  - 心跳超时自动终止并重试
  - 连续无进展自动失败（防无限重试）
  - 产出守护报告 `reports/guarded_train_<run_id>.json`
- CMD/TUI 长训改为守护模式，并新增心跳/日志可视化：
  - 长训配置持久化到 `reports/tui_state.json`
  - 面板显示心跳状态与年龄（可识别 stale）
  - 新增“最近日志 tail”查看
- 新增测试：`tests/test_guarded_train.py`。
- 全量门禁复核：`uv run pytest tests -q -> 93 passed`。

### 2026-02-22 19:30
- 修复 `tools/guarded_train.py` 进度判定盲区：守护器现在使用 `max(model_meta_steps, latest_checkpoint_steps)` 作为总步数，避免 `model.json` 落后时被误判为“无进展”。
- 新增守护器参数硬校验（启动即失败，避免低级配置错误长时间占机）：
  - `target_total_timesteps > 0`
  - `chunk_timesteps > 0`
  - `max_attempts >= 1`
  - `max_no_progress_attempts >= 1`
  - `stale_timeout_minutes > 0`
  - `poll_seconds > 0`
  - `checkpoint_every > 0`
  - `heartbeat_every > 0`
- 新增/更新回归测试：
  - `tests/test_guarded_train.py` 增加 checkpoint 回退进度与参数校验用例。
- 全量门禁复核：`uv run pytest tests -q -> 95 passed`。

### 2026-02-22 19:40
- `tools/sim_train_tui.py` 增加 CLI 级容错：
  - 支持 `--help/-h/help` 文本帮助，避免脚本在无交互场景直接进入输入循环。
  - 主循环与“继续提示”处新增 `EOFError` 兜底，遇到无 stdin 时优雅退出，不再抛栈追踪。
- 新增回归测试：
  - `tests/test_sim_train_tui.py` 增补 help flag 与 EOF 退出用例。
- 全量门禁复核：`uv run pytest tests -q -> 97 passed`。

### 2026-02-22 19:50
- `tools/guarded_train.py` 增加进程树终止机制（Windows `taskkill /T /F`，非 Windows killpg），避免心跳超时时遗留子进程占满 CPU。
- 守护训练流程烟雾验证通过：
  - `reports/guarded_train_guard_fix_smoke2.json` -> `status=PASS`。
- 新增回归测试：
  - `tests/test_guarded_train.py` 增加 `_terminate_process_tree` 基础行为用例。
- 全量门禁复核：`uv run pytest tests -q -> 98 passed`。

### 2026-02-22 20:00
- TUI 看板增强为“轻量细节摘要”，在不增加重 IO 的前提下补充关键运行信息：
  - 模型元信息：`backend/reward/envs/resumed`。
  - 模型训练状态：`num_timesteps_total/target`、monitor gate 指标（myturn/reaction/illegal/trunc）。
  - 运行态信息：剩余磁盘空间、最近日志文件大小与更新时间。
  - 长训细节：heartbeat elapsed/speed/ETA、守护报告最近 attempt 摘要。
- 新增解析辅助函数：`_collect_model_insights`、`_collect_guard_report_summary`、`_collect_runtime_insights`。
- 新增测试覆盖：`tests/test_sim_train_tui.py`（模型摘要、守护摘要、duration 格式化）。
- 全量门禁复核：`uv run pytest tests -q -> 101 passed`。

### 2026-02-22 20:10
- 修复 Windows 续训偶发失败：`rl/train_ppo.py` 的 `_write_json_atomic` 增加“PID 临时文件 + PermissionError 重试退避”，避免 heartbeat 原子替换瞬时锁冲突导致训练中断。
- 新增回归测试：`tests/test_train_controls.py::test_write_json_atomic_retries_permission_error`。
- 复现实测通过：此前失败的 `--resume_latest_checkpoint` 命令已可正常完成（`skipped=true num_timesteps_total=256`）。
- 全量门禁复核：`uv run pytest tests -q -> 102 passed`。

### 2026-02-22 20:20
- 针对“杭麻规则可配置性”补齐关键缺口：
  - `engine.py` 新增 `special_hu_types` 开关并真正接入判胡/计分逻辑（`qidui`、`shisanyao` 可按规则画像启停）。
  - `env.py` 接收并透传 `special_hu_types` 到引擎，确保 profile -> env -> engine 行为一致。
  - `rules/profiles.py` 增强规则画像校验：
    - 校验 `special_hu_types` 合法值；
    - 对当前未实现项做硬拦截，避免“配置写了但实际未生效”：
      - `qiaoxiang.lianzhuang_multiplier` 仅支持 `1.0`
      - `scoring.package_liability` 仅支持 `none`
      - `scoring.flow_scoring_mode` 仅支持 `zero`
      - `reaction.priority/tie_break` 仅支持当前实现口径
      - `reaction.qiangganghu` 仅支持 `false`
- 新增回归测试：
  - `tests/test_engine_hu.py`：特殊胡型开关生效用例
  - `tests/test_local_rule_profiles.py`：profile 映射与不支持配置拦截用例
- 全量门禁复核：`uv run pytest tests -q -> 108 passed`。

### 2026-02-22 20:30
- 修复 Windows `SubprocVecEnv + opponent pool` 训练崩溃：
  - 报错：`AttributeError: Can't pickle local object 'constant_fn.<locals>.func'`（发生在 `get_attr("action_masks")`）。
  - 根因：环境对象在跨进程序列化时携带了运行期 bot（含 SB3 模型闭包），导致 bound method 无法 pickle。
  - 修复：`env.py` 增加 `__getstate__/__setstate__`，序列化时剥离 `_bots` 运行态对象。
- 新增回归测试：
  - `tests/test_env_pickle.py`，验证 `action_masks` 绑定方法在存在不可 pickle bot 时仍可序列化。
- 复现实测通过：
  - `uv run python rl/train_ppo.py ... --vec_backend subproc --use_opponent_pool ...` 成功落盘模型。
- 全量门禁复核：`uv run pytest tests -q -> 109 passed`。

### 2026-02-22 20:35
- TUI 长训参数新增防误配自校正（`tools/sim_train_tui.py`）：
  - 当 `checkpoint_every > chunk_timesteps` 自动下调到 `chunk/2`。
  - 当 `heartbeat_every >= checkpoint_every` 自动下调到 `checkpoint/2`。
  - 对过小 `stale_timeout_minutes` 自动抬高到安全阈值。
  - `resume` 路径同样执行配置纠偏并回写 `reports/tui_state.json`。
- 新增回归测试：
  - `tests/test_sim_train_tui.py::test_sanitize_long_run_cfg_adjusts_bad_intervals`。
- 全量门禁复核：`uv run pytest tests -q -> 110 passed`。

### 2026-02-22 20:45
- 增强长训“进行中可见性”：
  - `tools/guarded_train.py` 轮询期间新增 `[WATCH]` 实时输出（`status/steps/target/hb_age`），不再只有启动命令无进度。
  - 守护器调用训练改为 `python -u`，减少缓冲导致的“长时间无输出”。
  - TUI 长训调用将 `poll_seconds` 下调到 `10s`，进度刷新更及时。
- 复现实测：
  - `reports/guarded_train_watch_smoke.json` 跑通，控制台可见连续 watch 行。
- 全量门禁复核：`uv run pytest tests -q -> 110 passed`。
