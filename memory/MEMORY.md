# 记忆索引

> 一条一行，指向具体文件。**本文件只做索引，不放内容。**
> agent 先读这份索引，再按需展开具体文件。

## 知识（knowledge/）

- [数据源踩坑记录](knowledge/datasource-gotchas.md) — 各数据源的字段口径、单位、限流与已知错误
- [口径约定](knowledge/conventions.md) — 全项目统一的复权、单位、日期口径

## 决策（decisions/）

- [ADR-0001 用文件契约做 agent 通信](decisions/0001-file-contract.md) — 为什么不用内存传参
- [ADR-0002 AKShare 仅用于第一阶段 OHLCV](decisions/0002-akshare-for-ohlcv.md) — 行情已接入，新闻等类别保持关闭

## 运行记录（runs/）

<!-- orchestrator 每次 run 结束后在此追加一行，格式：
- 2026-01-02_example | 000000.SZ | partial（情绪面 blocked） | runs/2026-01-02_example.json
-->
- 2026-01-02_example | 000000.SZ（虚构示例） | partial，情绪面 blocked | [记录](runs/2026-01-02_example.json)
