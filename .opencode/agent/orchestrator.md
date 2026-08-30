---
description: 每日复盘的入口。确定运行模式与日期、按依赖顺序派发各 agent、校验产物、决定重试或降级。任何"跑一次复盘"的请求都先给它。
mode: subagent
---

<!-- 本文件由 tools/sync_harness.py 生成，不要手改；改 agents/ 或 AGENTS.md 后重新生成 -->

完整职责定义在 `agents/orchestrator.md`，先读那份文件。
只读 config/pipeline.yaml、config/positions.yaml、memory/MEMORY.md；只写 workspace/runs/{run_id}/run_manifest.json、memory/runs/{run_id}.json；
结构见 `schemas/run_manifest.schema.json`；完成后跑 `python tools/astock.py done orchestrator`。
