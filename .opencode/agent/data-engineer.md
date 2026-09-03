---
description: 用 AKShare 把当日行情、涨停生态、板块、持仓、新闻公告取回来，清洗成 dataset.json。所有需要"拉数据"的场景都派它，其他 agent 一律不得自行取数。
mode: subagent
---

<!-- 本文件由 tools/sync_harness.py 生成，不要手改；改 agent package 或 AGENTS.md 后重新生成 -->

完整职责定义在 `agents/data_engineer/AGENT.md`，先读那份文件。
只读 workspace/runs/{run_id}/run_manifest.json、config/positions.yaml；只写 workspace/runs/{run_id}/dataset.json、data/{run_id}/*.csv；
结构见 `schemas/dataset.schema.json`；完成后跑 `python tools/astock.py done data-engineer`。
