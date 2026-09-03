# 记忆索引

> 一条一行，指向具体文件。**本文件只做索引，不放内容。**
> agent 先读这份索引，再按需展开具体文件——这样上下文才不会被撑爆。

## 知识（knowledge/）

- [AKShare 踩坑记录](knowledge/akshare-gotchas.md) — 接口口径、限流、字段变更、已知错误
- [口径约定](knowledge/conventions.md) — 全项目统一的复权、单位、成交额、日期口径

## 决策（decisions/）

- [ADR-0001 用文件契约做 agent 通信](decisions/0001-file-contract.md) — 为什么不用内存传参
- [ADR-0002 选 AKShare 作为唯一数据源](decisions/0002-akshare.md) — 取舍与已知限制

## 运行记录（runs/）

<!-- orchestrator 每次 run 结束后在此追加一行：
- <YYYY-MM-DD>_close | <一句话定性> | [记录](runs/<YYYY-MM-DD>_close.json)
-->
- 2026-08-28_example | 示例（虚构数据） | 分歧 | 行为自检触发 2 条 | [记录](runs/2026-08-28_example.json)
- 2026-08-28_close | 2026-08-28 | 冲高回落的分歧日：四大指数低开冲高全线回吐（创业板 -1.41%、科创50 -1 | [记录](runs/2026-08-28_close.json)
