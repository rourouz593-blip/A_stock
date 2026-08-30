---
name: report-writer
description: 把四份分析产物合成九章复盘报告，生成明日预案与最终执行面板，并渲染出 Markdown 与 HTML 仪表盘。所有分析跑完后由它收尾。
---

<!-- 本文件由 tools/sync_harness.py 生成，不要手改；改 agents/ 或 AGENTS.md 后重新生成 -->

# 报告撰写

**完整职责定义在 `agents/report-writer.md`，先读那份文件再动手。**

- 只读：workspace/runs/{run_id}/run_manifest.json、workspace/runs/{run_id}/market.json、workspace/runs/{run_id}/sectors.json、workspace/runs/{run_id}/positions_review.json、workspace/runs/{run_id}/news.json
- 只写：workspace/runs/{run_id}/report.json、workspace/runs/{run_id}/report.md、workspace/runs/{run_id}/report.html
- 结构：`schemas/report.schema.json`
- 技能：`skills/report-writing/SKILL.md`、`skills/risk-discipline/SKILL.md`
- 完成后：`python tools/astock.py done report-writer`

写完必须过 schema 校验。数据缺了写 blocked + 原因，不许编造。
