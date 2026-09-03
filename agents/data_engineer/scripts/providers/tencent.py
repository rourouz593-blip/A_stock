"""腾讯财经行情。**一次请求拿一批标的**，实测不封 IP。

# 为什么加这个源

原来取持仓快照是**每只股票一个东财请求**——10 只持仓 = 10 个请求。
a-stock-data 的防封铁律里，这正是被封的头号元凶：

> 批量场景每只股票之间 sleep——AI 跑批量循环（如筛选 100 只股逐个拉）是被封的头号元凶

腾讯这个接口 `qt.gtimg.cn/q=code1,code2,...` 是**批量**的：
10 只持仓 1 个请求，而且是腾讯不是东财。请求量和风险同时降一个量级。

# 口径与实现出处

字段位置参考 a-stock-data v3.7.1 §1.2（Apache-2.0），那份实现带实测日期与踩坑注释。
其中两个坑照抄了它的处理，因为都属于**静默拿到错数据**，比报错危险得多：

  ① 44=流通市值、45=总市值（曾被标反）。总股本≠流通股本时差数倍。
  ② 僵尸报价：停牌股/废码照样返回 HTTP 200 + 一份定格在最后交易日的报价，
     不报任何错。直接拿去算会得出完全错误的结论。

# 它给不了什么

没有行业/概念字段，没有前复权历史。这两样仍然要走别处——
provider 的意义是**按能力挑源**，不是找一个万能源。
"""
from __future__ import annotations

import urllib.request
from typing import Iterable

BASE = "https://qt.gtimg.cn/q="
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# 沪市指数白名单：这些 000xxx 是沪市指数，和深市 000xxx 个股同号段，
# 只看首位会路由到 sz 拿到另一只票——又一个"静默拿到错数据"。
SH_INDEX = {"000001", "000300", "000905", "000016", "000688", "000852", "000010"}

# 字段位置 → 我们的字段名。只取复盘用得到的，不全搬 88 个。
FIELDS = {
    1: "name", 3: "price", 4: "last_close", 5: "open",
    31: "change_amt", 32: "pct_chg", 33: "high", 34: "low",
    37: "amount_wan", 38: "turnover_rate", 39: "pe_ttm",
    43: "amplitude", 44: "float_mcap_yi", 45: "mcap_yi", 46: "pb",
    47: "limit_up", 48: "limit_down", 49: "vol_ratio",
}
MIN_FIELDS = 53          # 少于这个数说明返回体不完整，宁可丢掉也不要错位解析


def _prefix(code: str) -> str:
    """六位代码 → 带市场前缀。顺序不能改，每一条都对应一类会选错票的情况。"""
    low = code.lower()
    if low.startswith(("sh", "sz", "bj")):
        return low                      # 调用方已显式指定，原样透传
    if code.startswith("92"):
        return f"bj{code}"              # 北交所 920 号段必须先于 9x 判断
    if code in SH_INDEX or code.startswith(("5", "6", "9")):
        return f"sh{code}"
    if code.startswith(("4", "8")):
        return f"bj{code}"
    return f"sz{code}"


def parse(text: str, key_of: dict) -> dict:
    """解析腾讯返回体。单独拆出来是为了能用固定样本测试，不必联网。"""
    out = {}
    for line in text.strip().split(";"):
        if not line.strip() or "=" not in line or '"' not in line:
            continue
        key = line.split("=")[0].split("_")[-1]
        vals = line.split('"')[1].split("~")
        if len(vals) < MIN_FIELDS:
            continue                    # 返回体不完整 → 丢掉，不猜
        # 用入参原样做键：同时查 sh000001 和 sz000001 时，
        # 若都退回裸六位码会撞成同一个键、后者静默覆盖前者
        code = key_of.get(key, key[2:])
        q = {"code": code}
        for idx, name in FIELDS.items():
            raw = vals[idx] if idx < len(vals) else ""
            if name == "name":
                q[name] = raw
            else:
                try:
                    q[name] = float(raw) if raw else None
                except ValueError:
                    q[name] = None
        q["amount"] = q["amount_wan"] * 1e4 if q.get("amount_wan") else None
        # 僵尸报价：停牌 / 废码 / 未开盘也会返回 200 + 定格报价，不报错。
        # 标出来让上层决定，绝不静默当成真实成交。
        q["is_stale"] = bool(q.get("amount_wan") == 0
                             and q.get("price") and q["price"] == q.get("last_close"))
        out[code] = q
    return out


def spot(codes: Iterable[str], *, timeout: float = 10.0) -> dict:
    """批量快照。**一个请求拿全部**，这是它相对东财的全部意义。

    返回 {原始入参代码: {...}}。取不到的代码不会出现在结果里——
    调用方据此标 blocked，而不是拿到一个填了 0 的假记录。
    """
    codes = [str(c) for c in codes]
    if not codes:
        return {}
    key_of, prefixed = {}, []
    for c in codes:
        p = _prefix(c)
        prefixed.append(p)
        key_of[p] = c
    req = urllib.request.Request(BASE + ",".join(prefixed), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        text = r.read().decode("gbk", "ignore")
    return parse(text, key_of)
