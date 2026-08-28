# 数据源踩坑记录

> 每发现一个坑就追加一条。格式固定，方便 agent 检索。

## 条目格式

```
### <数据源>.<接口> — <一句话概括>
- 现象：
- 影响：哪个 agent 的哪类结论会被污染
- 处理：
- 发现于：YYYY-MM-DD，run_id
```

## 条目

### AKShare.stock_zh_a_hist — 东财可能断开长区间请求
- 现象：五个标的一年日线请求均出现 `RemoteDisconnected`，短区间单标的曾成功。
- 影响：data-engineer 无法稳定完成 OHLCV 主源抓取。
- 处理：日线显式降级到 `stock_zh_a_hist_tx`，并在 provenance 和 quality flag 中记录；
  周线/月线不静默换接口。
- 发现于：2026-08-28，run_id `2026-08-28_akshare-demo`

### AKShare.stock_zh_a_hist_tx — 当日数据可能尚未更新
- 现象：2026-08-28 请求返回的最新交易日为 2026-08-27。
- 影响：technical-analyst 若把备用源结果当成实时数据，会错误描述当日价格状态。
- 处理：coverage 早于请求终点时打 info flag，不用前值补齐；报告必须声明 as-of 缺口。
- 发现于：2026-08-28，run_id `2026-08-28_akshare-demo`

<!-- TODO(datasource): 数据源确定后开始记录。以下为格式示例，非真实内容。

### EXAMPLE_SOURCE_B.income_statement — 金额单位不统一
- 现象：部分年份返回单位为万元，部分为元，接口文档未说明
- 影响：fundamental-analyst 的所有绝对值判断（营收规模、利润规模）会差 10000 倍
- 处理：在 clean/normalize.py:unify_units 中按量级启发式校正，并强制打 warning flag
- 发现于：YYYY-MM-DD，run_id
-->
