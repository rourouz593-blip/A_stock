---
description: 把当日新闻、政策、公告、外围科技表现去重后分成利好/中性/利空，并回验昨日新闻的价格反馈。涉及"今天发生了什么"的问题派它。
mode: subagent
---

<!-- 本文件由 tools/sync_harness.py 生成，不要手改；改 agent package 或 AGENTS.md 后重新生成 -->

完整职责定义在 `agents/news_analyst/AGENT.md`，先读那份文件。
只读 workspace/runs/{run_id}/dataset.json、memory/runs/；只写 workspace/runs/{run_id}/news.json；
结构见 `schemas/news.schema.json`；完成后跑 `python tools/astock.py done news-analyst`。
