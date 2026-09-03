---
description: 为每只持仓做独立卡片（地位、强弱、逻辑是否成立、三种情景、明确动作），并计算仓位与风险纪律。涉及"我的票该怎么办"的问题派它。
mode: subagent
---

<!-- 本文件由 tools/sync_harness.py 生成，不要手改；改 agent package 或 AGENTS.md 后重新生成 -->

完整职责定义在 `agents/position_advisor/AGENT.md`，先读那份文件。
只读 workspace/runs/{run_id}/dataset.json、workspace/runs/{run_id}/market.json、workspace/runs/{run_id}/sectors.json、config/positions.yaml、memory/positions_history.jsonl；只写 workspace/runs/{run_id}/positions_review.json；
结构见 `schemas/positions_review.schema.json`；完成后跑 `python tools/astock.py done position-advisor`。
