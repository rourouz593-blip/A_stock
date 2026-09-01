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

### akshare 的一千多个请求不带 timeout —— 会无限挂起
- 现象：跑到某个接口不动了，Ctrl-C 之后 traceback 停在 `conn.getresponse()` → `_read_status()`。
  请求已经发出去，在**无限等响应**
- 数据：`grep requests.get` 全包 1077 处不带 timeout，只有 39 处带
- 影响：对无人值守的系统这是**最坏的失败模式**——
  报错会被记录、重试、上报；挂起什么都不会发生，第二天才发现今天没有复盘
- 处理：`_with_http_defaults()` 给每个请求补 `timeout=(10, 30)`（只在调用方没设时补）。
  可用 `ASTOCK_CONNECT_TIMEOUT` / `ASTOCK_READ_TIMEOUT` 调
- 发现于：2026-08-31

### 重试机制自己制造了限流
- 现象：关掉代理之后，东财仍然 `RemoteDisconnected`，而且是**连着几个指数都失败**
- 原因：4 个指数 × 3 次重试 × 2 条降级路径 ≈ 二三十个请求在几秒内打出去。
  东财对密集请求直接掐连接——**是重试把自己打成了限流**
- 更糟的是：`Connection aborted`（被掐）字符串里含 "Connection"，
  会被 `_is_conn_error` 认成连通性问题，于是又去试"仅 IPv4"，再多打一轮
- 处理：
  1. 每两个请求之间留最小间隔 `ASTOCK_MIN_INTERVAL`（默认 0.4s）
  2. 被掐时**收紧重试次数**（`ASTOCK_DROP_RETRY`，默认 2）并加长退避——
     死磕不如快点退到备用源
  3. 把"被掐"从"连不上"里摘出来：换 IPv4 对限流毫无帮助
  4. 没配代理时不再尝试"绕开代理"（但真报 ProxyError 时仍然试，
     因为那可能是 macOS 系统代理）
- 教训：**重试是一把双刃剑。** 在会限流的服务面前，
  盲目重试和多路降级会让情况持续恶化，而且看起来像是"对方的问题"
- 发现于：2026-08-31

### 光删代理环境变量挡不住 requests
- 现象：`ASTOCK_DIRECT=1` 之后仍然报代理相关错误
- 原因：requests 的 `trust_env` 打开时会读三处——
  ① http_proxy/https_proxy/all_proxy 环境变量
  ② **macOS 系统偏好设置里的代理**（urllib.getproxies 会返回它）
  ③ `~/.netrc`
  删 shell 变量只堵住了第一条
- 处理：`_with_http_defaults(direct=True)` 直接给每个 Session 置 `trust_env=False`，
  三条路一刀切断。比设 no_proxy 更彻底
- 诊断：`tools/net_probe.py` 里 "requests 无环境" 那一行就是测这个——
  它通而 "requests 默认" 不通，就说明问题出在环境配置
- 发现于：2026-08-31

### 东财会按 IP 封禁，而且封禁范围会随重试扩大（本项目最贵的一课）
- 现象：TLS 握手成功、请求发出去、服务器**一个字节都不返回就关连接**。
  `RemoteDisconnected` / curl exit 52 `Empty reply from server`
- 判定：`tools/net_probe.py` 七种打法（urllib / requests 四变体 / 裸 socket / curl）
  **全部失败且症状一致** → 与 Python 库、shell 配置、代理都无关，是对端在拒绝这个 IP
- 演化过程（实测）：
  1. 最初只有 `push2ex` / `17.push2` / `legulegu` 不通
  2. 一轮轮重试之后，原本正常的 `push2his` / `80.push2` 也开始被拒
  3. 新浪始终正常 —— 说明网络没问题，是东财单方面在封
- **根因是重试本身**：4 个指数 × 3 次重试 × 2 条降级路径，几秒内二三十个请求
- 处理：
  1. `MIN_INTERVAL` 请求间隔
  2. 被掐时收紧重试次数（`ASTOCK_DROP_RETRY`）
  3. **熔断器**：一个域名连续被拒 3 次 → 冷却 10 分钟，期间**一次请求都不发**，
     直接走备用源。连续被封则冷却时间递增。状态落盘 `workspace/cache/circuit.json`，
     因为用户往往反复重跑脚本，只存内存的熔断器一重启就白做了
  4. `python tools/astock.py cooldown` 看状态，`--clear` 清空
- **不要做的事**：给涨跌家数加"新浪全市场快照"兜底。
  akshare 自己的注释写着「重复运行本函数会被新浪暂时封 IP」——它要翻 80 多页。
  拿它兜底等于在唯一还活着的源上重犯同样的错
- 教训：**面对会限流的服务，重试是负债不是资产。**
  失败要快、要少打、要让位给备用源；硬打的代价是把可用的东西也打没
- 发现于：2026-08-31

<!-- 下面继续追加你实际遇到的坑 -->

## 请求量才是变量（2026-09-01）

被封之后第一反应是「换个数据源」，但这个反应是错的。

一次正常复盘只要 **30–50 个请求**。这个量级下东财、新浪从来不封人。
8-31 被封，是重试风暴把它放大到了几百个——**问题不在源，在没人给请求量设过上限。**
在设上限之前换源，只是把同一个 bug 搬到新源上重演一遍。

所以加了第三道闸，现在是三道：

| 闸 | 管什么 | 能不能在出事前发现 |
|---|---|---|
| `MIN_INTERVAL` 限流 | 请求太密 | 不能，只是放慢 |
| **`MAX_REQUESTS` 预算** | **每个都成功、但总量失控** | **能** |
| `circuit.json` 熔断 | 已经开始被拒 | 不能，事后止损 |

中间那道是唯一能在**还全是 200 的时候**就叫停的。熔断永远慢一步。

两个容易写错的地方：

1. **超额必须在请求发出之前抛错。** 先发再计数的话，撞上限那一刻已经打出去了。
2. **`BudgetExceeded` 要继承 `FetchError`**，才能命中 `call()` 里的 `except FetchError: raise`。
   否则会被当成网络错误再重试三次——「限量之后再打三次」，正好是它要防的事。

判读规则：**撞上限说明有地方在重复取数，不是该调大上限。**

## SQLite 不能放在网络盘 / 同步盘上（2026-09-01）

本地行情仓库用的是 SQLite。它依赖**文件锁**，
而网络文件系统（NFS/SMB）、FUSE 挂载、部分云同步目录不支持完整的锁语义——
表现是建表就报 `sqlite3.OperationalError: disk I/O error`，
看起来像磁盘坏了，其实是文件系统不支持。

处理：`ASTOCK_HISTORY_DB=~/astock-history.sqlite` 换到本地磁盘。

更重要的是**仓库坏了不能拖垮复盘**。它是优化，不是依赖：
`scripts/fetch/market.py` 里所有对仓库的读写都包了 try/except，
失败就退化成"这次全部走网络"，并打一行提示。
有测试 `test_store_failure_never_blocks_the_review` 守着这条。

## 403 与断连是两回事（2026-09-01）

以前把它们一样对待：都重试、都走"绕代理 / 换 IPv4"降级。这是错的。

| | 断连（RemoteDisconnected / Connection reset） | 403 Forbidden |
|---|---|---|
| 含义 | 对方在抖动 | **风控在明确拒绝你** |
| 重试 | 可能成功 | **一定不成功**，而且每次都在给封禁计数加分 |
| 换出口降级 | 合理 | **最糟的选择**——换 IP 试探正是风控最讨厌的行为 |

现在 `_is_waf()` 单独识别 403：直接抛错并说明"重试无用"，降级阶梯对 403 返回空。
有对照测试保证断连仍然重试，否则这条改动会悄悄退化成"什么都不重试"。

来源：a-stock-data v3.7.1「防封铁律」，与我们 8-31 的经历一致。

## 东财不同子域走不同 WAF（2026-09-01）

一手记录（a-stock-data issue #36，2026-06-30）：某人 10 线程并发、完全不限流，
1 小时 45000+ 请求，`push2` / `push2his` **全系列 IP 级封禁 20 小时以上**——
但 **`datacenter-web.eastmoney.com` 完全不受影响**。

结论：**熔断必须按域名，不能按公司。** 按 `eastmoney.com` 整体熔断，
会在还有一半接口可用的时候自己把自己关掉。我们的 `circuit.json` 本来就是 per-host，
这条是外部证实。

顺带两个阈值（社区实测 2026-05）：>5 次/秒 · 单 IP 并发 ≥10 · 1 分钟 ≥200 次。
我们的东财间隔因此从 0.4 秒提到 **1.0 秒**（`ASTOCK_EM_MIN_INTERVAL`）。

## 腾讯是限流不是封 IP（2026-09-01，待验证）

同一份记录里：腾讯 K 线连续 5000+ 次后会返回空，但那是**限流不是封 IP**，
降速或换新浪即可恢复。所以腾讯适合做高频主源——但**不等于可以不限流**，
接进来时照样要走预算和熔断。这条我们自己还没实测过，先按"待验证"处理。
