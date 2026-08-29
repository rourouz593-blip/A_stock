# AKShare 踩坑记录

> 每发现一个坑就追加一条，格式固定，方便 agent 检索。
> **当前为初始清单**，后面遇到的实际问题往下加。

## 条目格式

```
### <接口名> — <一句话概括>
- 现象：
- 影响：哪个 agent 的哪类结论会被污染
- 处理：
- 发现于：YYYY-MM-DD，run_id
```

## 已知问题（写代码时已处理）

### index_zh_a_hist_min_em — 分时数据只保留最近几个交易日
- 现象：取一周以前的日期会返回空
- 影响：market-analyst 的日内四段拆解（章节二）
- 处理：`scripts/fetch/market.py` 中标 `degraded` 并加 flag；
  agent 遇到就把四段部分标 blocked，**禁止用全天涨跌幅倒推四段**
- 发现于：接口文档

### stock_zt_pool_zbgc_em / stock_zt_pool_dtgc_em — 只能取最近 30 个交易日
- 现象：超过 30 个交易日直接 raise ValueError
- 影响：炸板率、跌停家数算不出来 → 情绪阶段判断失去依据
- 处理：`try_call` 捕获后标 warning；做历史回测时要注意这个窗口限制
- 发现于：akshare 源码

### stock_market_activity_legu — 是实时快照，不是当日收盘定格
- 现象：盘中调用拿到的是当时的涨跌家数，收盘后才稳定
- 影响：涨跌家数（章节一）
- 处理：只在收盘后（15:30 之后）跑 `close` 模式
- 发现于：接口说明

### 两市成交额 — 不能把四个指数的成交额相加
- 现象：创业板指、科创50 的成交额已包含在深市、沪市成交额里
- 影响：章节一的成交额数字会虚高约 30%
- 处理：`scripts/clean/derive.py:two_market_amount` 只取上证 + 深证成指
- 发现于：设计阶段

<!-- 下面继续追加你实际遇到的坑 -->
