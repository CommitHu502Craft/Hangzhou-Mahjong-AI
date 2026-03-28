# EXECUTION_HEADER.md

将下面整段作为“每次任务执行提示词尾部”粘贴给执行 AI。

```text
你现在是本项目的执行代理。严格按下述规则执行当前 TASK：

1) 先读 `PROJECT_CONTROL.md`、`TASK_QUEUE.md`、`CHANGELOG_AUTOPILOT.md`。
2) 只执行我指定的一个 TASK（不要提前做后续任务）。
3) 必须先做该 TASK 的 Context discovery，再进行编辑。
4) 编辑仅限该 TASK 声明的文件范围；不要做无关重构。
5) 至少运行该 TASK 指定的一条命令，并报告 exit code。
6) 满足 Acceptance criteria 后，向 `CHANGELOG_AUTOPILOT.md` 追加记录。
7) 输出必须包含：
   - 改动摘要
   - 文件列表
   - 命令与 exit code
   - 验收证据
   - changelog 追加内容
8) 若阻塞：
   - 输出 `BLOCKED`
   - 给出已尝试步骤、失败证据、最小化解阻建议
   - 不要静默跳过验收。
9) 保持幂等：已完成项要可跳过，未完成项要可续跑。
10) 严禁破坏性操作或回退未知改动。
11) 发现契约冲突时，先更新文档契约再改代码，并在 changelog 说明原因。
12) 如命令失败，必须提供可复制复现的失败命令和输出摘要。
13) 所有测试命令统一使用 `uv run pytest ...`，不要使用 `python -m pytest ...`。
```
