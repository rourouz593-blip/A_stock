---
description: 把当天板块分成主线、次主线、指数共振、逆指数抱团、退潮风险五类，识别每个方向的梯队与阶段。涉及"今天什么在涨、明天看什么"的问题派它。
mode: subagent
---

<!-- 本文件由 tools/sync_harness.py 生成，不要手改；改 agents/ 或 AGENTS.md 后重新生成 -->

完整职责定义在 `agents/sector-analyst.md`，先读那份文件。
只读 workspace/runs/{run_id}/dataset.json、workspace/runs/{run_id}/market.json；只写 workspace/runs/{run_id}/sectors.json；
结构见 `schemas/sectors.schema.json`；完成后跑 `python tools/astock.py done sector-analyst`。
