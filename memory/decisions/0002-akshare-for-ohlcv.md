# ADR-0002：AKShare 仅用于第一阶段 OHLCV

- 状态：已接受
- 日期：2026-08-28

## 背景

教学需要先接通一条真实、容易观察的数据链路。用户选择 AKShare，并明确要求先抓取
五只 A 股；新闻 API 尚在选型中，新闻抓取必须保持静默。

## 决策

1. 主源使用 `AKShare.stock_zh_a_hist` 获取 A 股日/周/月 OHLCV；日线主源失败时，
   允许显式降级到 `AKShare.stock_zh_a_hist_tx`。
2. 静态能力注册为 `fetch_market_data` tool；每次变化的响应作为 run artifact 落盘。
3. 每次响应强制检查必需列，并记录 source、upstream、fetched_at、参数、字段映射和单位。
4. 财务、估值、公告、新闻、资金流、社交数据源全部保持 `NONE`。
5. 复权属于策略选择，不在本决策中确定；教学首跑显式传 `adjust=none`。

## 后果

- 学生可以观察 `Agent → Tool → Script → External Data → Artifact` 的最小闭环。
- AKShare 的上游网页接口可能变化，所以测试使用 mock 响应，真实运行仍需关注质量标记。
- 基本面和情绪面不会因“AKShare 能提供某些相关接口”而被擅自启用。
