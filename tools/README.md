# tools/ — 工具层

## 这一层是什么

**Skill 让 agent"知道怎么做"，Tool 让 agent"真的能做"。**

工具是 agent 与确定性代码之间的接口。凡是需要精确结果的事——算指标、校验 JSON、
读写文件、拉数据——都必须走工具，**不允许让模型心算或凭印象生成**。

> 教学要点：判断一件事该交给 prompt 还是交给 tool，看它是否需要**可复现的精确结果**。
> "MA20 是多少" → tool；"这个趋势结构说明什么" → prompt。

## 设计约定

1. 每个工具是一个**独立可执行的 CLI**，输入输出都是 JSON，走 stdin/stdout。
   这样任何 harness（Claude Code / opencode / 一个 shell 脚本）都能调用，零耦合。
2. 工具**只做一件事**，不做编排，不做判断。
3. 工具**不实现业务逻辑**，只做 `scripts/` 的薄封装。业务逻辑在 `scripts/`，方便单测。
4. 失败时 **exit code 非 0 + stderr 输出结构化错误**，绝不返回半成品。

## 调用约定

```bash
python tools/<tool_name>.py --help
echo '{"run_id":"2026-01-02_example"}' | python tools/validate_artifact.py --artifact dataset
```

所有工具在 `tool_manifest.yaml` 中登记。**没登记的工具，agent 不许调用。**

## 当前状态

| 工具 | 状态 | 说明 |
|---|---|---|
| `init_run` | ✅ 可用 | 纯管道逻辑，已实现 |
| `validate_artifact` | ✅ 可用 | 纯管道逻辑，已实现 |
| `fetch_market_data` | ✅ 可用 | AKShare A 股日/周/月历史行情 |
| `fetch_financials` | ⬜ 空壳 | 等数据源确定 |
| `fetch_news` | ⏸️ 静默 | 等用户确认新闻 API，不调用 |
| `clean_dataset` | ⬜ 空壳 | 等数据源确定 |
| `compute_indicators` | ⬜ 空壳 | 等指标集合确定 |
| `score_sentiment` | ⬜ 空壳 | 等打分口径确定 |

"空壳"= CLI 骨架在、参数定义在、调用 `scripts/` 时抛 `NotImplementedError`。

## 静态工具与动态数据

工具本身应当稳定，例如 `fetch_market_data(codes, start, end, freq, adjust)`；变化的是
每次调用产生的数据。工具把请求参数、抓取时间、实际来源和字段映射写进 provenance，
因此同一个静态程序在不同时间返回不同数据，仍然可追溯、可复核。
