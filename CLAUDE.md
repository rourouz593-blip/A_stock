# CLAUDE.md

本仓库是一条 **A 股每日复盘流水线**。

用户说「帮我做今日股市复盘」「看看今天大盘」「我的持仓怎么办」这类话时，
**不要自己查行情、不要凭印象分析、不要手写报告**，驱动流水线：

```bash
python tools/astock.py doctor     # 首次：环境自检
python tools/astock.py review     # 开始
python tools/astock.py next       # 我该做什么（它会把一切告诉你）
python tools/astock.py done <agent>   # 做完了，校验并推进
```

完整手册见 **[`AGENTS.md`](AGENTS.md)**，赶时间只读它的第 0 节。

本文件只是给 Claude Code 的入口指针，**不要在这里重复内容**——
两份手册一旦分叉，agent 就会按过期的那份干活。

面向人的项目说明见 [`README.md`](README.md)，教学文档见 [`docs/`](docs/)。
`.claude/` 下的命令、技能、子 agent 全部由 `tools/sync_harness.py` 生成，不要手改。
