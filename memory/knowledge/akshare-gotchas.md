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

### 全部东财接口 — 代理开着但代理客户端没运行
- 现象：`ProxyError('Unable to connect to proxy', ... 127.0.0.1:9910 Connection refused)`。
  更迷惑的是**交易日历那步会通过**——因为它命中了本地缓存，看起来"网络是好的"
- 影响：所有需要联网的数据块，整个复盘停在第一步
- 处理：`scripts/ak_client.py` 现在会识别代理错误并**自动摘掉代理直连重试一次**，
  成功时打印提示。仍失败则报出可读诊断（含三种修法）。
  想强制直连：`ASTOCK_DIRECT=1`
- 教训：东财、新浪都是**境内站点**，走境外代理反而更容易失败。国内数据源应当直连
- 发现于：2026-08-30，学生首次真实取数

### 缓存会掩盖网络问题，也会掩盖数据过期
- 现象：`doctor` 显示网络正常、第一步交易日历秒过，但其实都来自本地缓存
- 影响：更隐蔽的是**实时快照**——涨跌家数、板块行情、资金流上午取的数，
  拿到 15:30 的复盘里用，情绪阶段会判错
- 处理：缓存加了 TTL，默认 30 分钟（`ASTOCK_CACHE_TTL_MIN`）；
  交易日历这种稳定数据单独给 7 天。命中缓存会在 `quality_flags` 里如实标注
- 发现于：2026-08-30

### 「连不上」其实有四种，处理方式完全不同
- 现象：报错都长得像 `Max retries exceeded`，但原因可能是
  DNS 解析不了 / 代理拦截 / **IPv6 出口坏掉** / 站点本身不可达
- 影响：把四种混成一句"网络不好"，就永远修不好
- 处理：`python tools/net_check.py` 逐域名测四种组合并给结论。
  `ak_client` 遇到连接失败会依次自动降级重试：绕开代理 → 仅 IPv4 → 两者都用，
  每次降级都会打印提示（**静默降级比失败更糟**）
- 特别注意 **IPv6**：网络通告了 IPv6 但出口是坏的时，
  有 AAAA 记录的站点会连接超时，只有 A 记录的站点却一切正常——
  表现成"新浪能连、东财连不上"这种看起来毫无道理的现象。
  开关：`ASTOCK_IPV4_ONLY=1`
- macOS 补充：`unset http_proxy` **不够**，requests 还会读「系统偏好设置」里的代理；
  必须同时把数据源域名写进 `no_proxy`（`_without_proxy()` 已经这么做了）
- 发现于：2026-08-30

### index_zh_a_hist 等接口是裸 requests.get，不带 User-Agent
- 现象：`ConnectionError: ('Connection aborted.', RemoteDisconnected(
  'Remote end closed connection without response'))`。
  注意这**不是**连不上——TCP 握手成功了，是服务器不给响应就把连接掐了
- 原因：akshare 里 `index_zh_a_hist` / `index_zh_a_hist_min_em` 等写的是
  `requests.get(url, params=params)`，UA 是 `python-requests/2.x`，
  东财 push2 系列会直接断开这类连接
- 影响：指数日线取不到 → 章节①②直接 blocked，整个复盘停在第二步
- 处理：`scripts/ak_client.py` 的 `_with_browser_ua()` 给所有请求补上浏览器请求头
  （UA + Accept-Language + 按域名补 Referer），**只补调用方没设的字段**。
  可用 `ASTOCK_UA` 覆盖，`ASTOCK_NO_UA=1` 关掉
- 同一个报错也可能是**代理线路把境内站点绕到了境外节点**，所以 `_fallbacks()` 里
  被掐时会先自动绕开代理重试。`tools/net_check.py` 的「裸UA」一列能分辨是哪一种
- 发现于：2026-08-30，学生真实取数

### index_zh_a_hist 会先请求 80.push2 拉一张多余的对照表
- 现象：`ConnectTimeout: HTTPSConnectionPool(host='80.push2.eastmoney.com', port=443)`。
  最迷惑的是 `net_check` 显示 **push2his（真正取 K 线的主机）是通的**，
  却卡在另一台机器上
- 原因：`index_zh_a_hist()` 取 K 线前先调 `index_code_id_map_em()`，
  向 `80.push2.eastmoney.com` 拉「全部指数 → 市场号」对照表，
  只为知道 000001 属于沪市还是深市。东财的分片主机（80.push2 / 17.push2 /
  push2ex …）在不同网络下可达性差别很大
- 影响：章节①②直接取不到数，整个复盘停在第二步
- 处理：`scripts/fetch/market.py` 的 `_skip_index_code_map()` 把那张表直接喂给 akshare
  （我们只盯四个固定指数，市场号是常数：000001→1 沪、399001→0 深、
  399006→0 深、000688→1 沪）。省掉一次请求，也去掉一个故障点。
  `index_zh_a_hist_min_em` 同样受益
- 兜底：东财整体不可达时退到新浪 `stock_zh_index_daily`，
  但**新浪不返回成交额**，会打 warning 并让章节①的两市成交额缺失
- 教训：**一个多余的前置请求就是一个多余的故障点。**
  遇到"数据源明明能连却报连不上"，先看它到底连的是哪台主机
- 发现于：2026-08-30，学生真实取数

### macOS 的系统代理独立于环境变量（真实根因）
- 现象：`unset http_proxy` 甚至 `ASTOCK_DIRECT=1` 都还是报代理连不上
- 原因：VPN 客户端会同时改两处——shell 环境变量 **和**
  「系统设置 → 网络 → Wi-Fi → 详细信息 → 代理」里的「网页代理」「SOCKS 代理」。
  退出 VPN 客户端时后者不会被清掉，端口一失效，Python 的所有请求都卡在那里
- 处理：去 Wi-Fi 详细信息里把那两个开关关掉。
  `net_check` 会分别打印「环境变量代理」与「系统代理」，就是为了让这个区别可见
- 发现于：2026-08-30，用户自己排查出来的

### dataset.json 写盘时 TypeError: Object of type date is not JSON serializable
- 现象：取数全部跑完（三分钟），最后一步写文件崩溃，**整轮数据丢光**
- 原因：`stock_notice_report` 等接口返回的日期是 `datetime.date`；
  DataFrame 里还有 `numpy.int64`、`NaN`。内存里都正常，`json.dumps` 一个都不认
- 处理：`scripts/store/repository.py:_sanitize()` 统一转换：
  日期 → ISO 字符串，numpy 标量 → Python 原生，NaN/NaT/NA → `null`（**绝不用 0 代替**），
  认不出来的类型转字符串并记进 `COERCED` 打 flag。
  另外 `build_dataset` 兜底：写 dataset.json 失败时先把原始数据落到 `dataset.raw.json`，
  绝不让几分钟的取数白费
- 坑中坑：`pd.NaT` 是 `datetime` 的子类，判缺失必须在 isoformat 之前，
  否则会写出字符串 `"NaT"`——下游会把它当成一个有效值，比 null 危险得多
- 发现于：2026-08-30

<!-- 下面继续追加你实际遇到的坑 -->
