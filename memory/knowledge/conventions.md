# 全项目口径约定

> 这些约定一旦确定就**不要在单个 agent 里私自变通**。变通必须改这里，并同步改 schema。

| 项目 | 约定 | 状态 |
|---|---|---|
| 数据源 | AKShare，免费无 token | ✅ 已定 |
| 股票代码 | 内部统一 `600519.SH`；调 akshare 时用 `bare()` 转成六位 | ✅ 已定 |
| 日期 | `YYYY-MM-DD`；调 akshare 时用 `to_ak_date()` 转成 `YYYYMMDD` | ✅ 已定 |
| 金额单位 | 一律「元」；显示时再换算成亿 | ✅ 已定 |
| 复权口径 | **qfq（前复权）**，与看盘软件一致 | ✅ 已定 |
| 四大指数 | 上证 000001 / 深成 399001 / 创业板 399006 / 科创50 000688 | ✅ 已定 |
| 两市成交额 | 上证 + 深证成指，**不含**创业板与科创板（已包含在内） | ✅ 已定 |
| 日内四段 | 早盘 9:30-10:30 / 上午 10:30-11:30 / 午后 13:00-14:30 / 尾盘 14:30-15:00 | ✅ 已定 |
| 炸板率 | 炸板数 /（涨停数 + 炸板数） | ✅ 已定 |
| 连板晋级率 | 昨日涨停股中今日仍涨停的比例 | ✅ 已定 |
| 单笔风险上限 | 账户 0.5% | ✅ 已定 |
| 明细存储 | CSV（`utf-8-sig`，Excel 打开不乱码），不用 parquet | ✅ 已定 |
| 情绪阶段阈值 | 见 `config/thresholds.yaml` | ⬜ 待填 |
| 板块强弱阈值 | 见 `config/thresholds.yaml` | ⬜ 待填 |

## 落盘状态必须在 conftest 里隔离（2026-09-01）

`workspace/cache/` 下的 `budget.json`（每日请求预算）和 `circuit.json`（熔断冷却）
是**跨进程持久化**的。测试里如果不改指到 `tmp_path`，读到的是这台机器的真实状态。

后果不是"测试偶尔失败"，而是**失败信息会骗人**：
`test_browser_ua_is_injected` 曾因为 push2his 正在冷却而失败，
报错是 `CooledDown`，和它要测的 UA 注入毫无关系——
一个新人看到这个会去查 UA 代码，查半天。

规则：**新增任何落盘状态，同一次改动里就要在 `tests/conftest.py` 的
`_isolate_persistent_state` 里加一行。** 目前隔离的：

- `ak_client.BUDGET_FILE`
- `ak_client.CIRCUIT_FILE`
- `store.bars.DB_PATH`（在各自的 fixture 里，因为多数测试不碰仓库）
