---
description: 跑一次 A 股每日复盘（建 run + 取数 + 进入分析循环）
argument-hint: "[YYYY-MM-DD] [close|premarket|positions|weekly]"
---

<!-- 本文件由 tools/sync_harness.py 生成，不要手改；改 agent package 或 AGENTS.md 后重新生成 -->

先读 `AGENTS.md`，然后：

```bash
python tools/astock.py review $ARGUMENTS
```

之后进入循环：`astock next` → 完成那一步 → `astock done <agent>` → 回到 `next`，
直到它输出「全部完成」。每一步的输入、产物、schema、技能都由 `next` 告诉你。

纪律：数据缺了写 blocked，不编造；每只持仓只给一个动作；不荐股、不给目标价。
