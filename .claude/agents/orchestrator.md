---
name: orchestrator
description: 每日复盘的入口。确定运行模式与日期、按依赖顺序派发各 agent、校验产物、决定重试或降级。任何"跑一次复盘"的请求都先给它。
---

<!-- 本文件由 tools/sync_harness.py 生成，不要手改；改 agent package 或 AGENTS.md 后重新生成 -->

# 总控编排

**完整职责定义在 `agents/orchestrator/AGENT.md`，先读那份文件再动手。**

- 只读：config/pipeline.yaml、config/positions.yaml、memory/MEMORY.md
- 只写：workspace/runs/{run_id}/run_manifest.json、memory/runs/{run_id}.json
- 结构：`schemas/run_manifest.schema.json`
- 技能：`agents/orchestrator/SKILL.md`
- 完成后：`python tools/astock.py done orchestrator`

写完必须过 schema 校验。数据缺了写 blocked + 原因，不许编造。
