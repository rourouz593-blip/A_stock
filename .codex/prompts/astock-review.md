<!-- 本文件由 tools/sync_harness.py 生成，不要手改；改 agents/ 或 AGENTS.md 后重新生成 -->

# 跑一次 A 股每日复盘

Codex 会自动读仓库根目录的 `AGENTS.md`，所以直接照它做即可。

```bash
python tools/astock.py review
```

然后循环 `astock next` → 完成 → `astock done <agent>`。

（若你的 Codex 版本只从 `~/.codex/prompts` 读自定义提示词，把本文件复制过去即可。）
