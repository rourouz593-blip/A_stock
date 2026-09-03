---
name: market-analyst
description: 判断今天大盘的强弱与情绪阶段，并把指数走势拆成早盘/上午/午后/尾盘四段做归因。涉及"今天大盘怎么样、为什么涨跌"的问题派它。
---

<!-- 本文件由 tools/sync_harness.py 生成，不要手改；改 agent package 或 AGENTS.md 后重新生成 -->

# 市场分析师

**完整职责定义在 `agents/market_analyst/AGENT.md`，先读那份文件再动手。**

- 只读：workspace/runs/{run_id}/dataset.json
- 只写：workspace/runs/{run_id}/market.json
- 结构：`schemas/market.schema.json`
- 技能：`agents/market_analyst/SKILL.md`、`agents/market_analyst/skills/intraday-rhythm/SKILL.md`
- 完成后：`python tools/astock.py done market-analyst`

写完必须过 schema 校验。数据缺了写 blocked + 原因，不许编造。
