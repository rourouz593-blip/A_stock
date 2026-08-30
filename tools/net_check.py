#!/usr/bin/env python3
"""逐个数据源域名做连通性诊断，定位到底是哪一环断了。

    python tools/net_check.py

「连不上」有很多种，处理方式完全不同：

    DNS 解析不了      → 网络/DNS 问题
    解析得到但连不上   → 被墙、被防火墙挡、或代理拦截
    走代理失败、直连成功 → 代理的问题（本项目会自动降级，也可 ASTOCK_DIRECT=1）
    两种都失败         → 站点或本地网络的问题
    HTTP 200 但内容不对 → 被限流或需要特殊 UA

一句「网络连不上」把这五种混成一种，等于没诊断。
本工具对每个域名分别测「按当前设置」和「强制直连」，把区别摆出来。
"""
from __future__ import annotations

import argparse
import os
import socket
import sys
import urllib.parse
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.ak_client import DATA_HOSTS, PROXY_VARS, redact_proxy  # noqa: E402

# 真实会被调用的端点，按数据块分组
# (名称, URL, 挂了会影响哪几章, 是否必需)
TARGETS = [
    ("交易日历",   "https://finance.sina.com.cn/realstock/company/klc_td_sh.txt",
     "全部（判断是否交易日）", True),
    ("指数日线",   "https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=1.000001"
                   "&fields1=f1&fields2=f51&klt=101&fqt=0&beg=0&end=20500000",
     "①市场总览 ②指数复盘", True),
    ("指数列表",   "https://80.push2.eastmoney.com/api/qt/clist/get?pn=1&pz=1&fs=m:1+t:1&fields=f12",
     "无（本项目已绕开这个多余请求）", False),
    ("涨停池",     "https://push2ex.eastmoney.com/getTopicZTPool?ut=7eea3edcaed734bea9cbfc24409ed989"
                   "&dpt=wz.ztzt&Pageindex=0&pagesize=1&sort=fbt:asc&date=20240101",
     "①炸板率/晋级率/连板梯队 ③梯队", False),
    ("板块行情",   "https://17.push2.eastmoney.com/api/qt/clist/get?pn=1&pz=1&fs=m:90+t:2&fields=f12",
     "③板块与题材", False),
    ("涨跌家数",   "https://legulegu.com/stockdata/market-activity",
     "①涨跌家数", False),
]
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
BARE_UA = "python-requests/2.32.5"   # akshare 裸调用时的 UA，东财常直接掐掉
OK, NO, DIM, B, END = "\033[32m", "\033[31m", "\033[2m", "\033[1m", "\033[0m"


def c(s: str, color: str) -> str:
    return s if os.getenv("NO_COLOR") else f"{color}{s}{END}"


def dns(host: str) -> tuple[bool, str, bool]:
    """返回 (能否解析, 描述, 是否有 IPv6 记录)。

    单独把 AAAA 拎出来，是因为「有 IPv6 记录 + IPv6 出口坏掉」
    会表现成连接超时，而同一网络下只有 A 记录的站点一切正常——
    这是最容易看不出原因的一类故障。
    """
    v4, v6 = [], []
    try:
        for fam, *_rest, sa in socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP):
            (v4 if fam == socket.AF_INET else v6).append(sa[0])
    except Exception as e:
        return False, f"{type(e).__name__}: {e}", False
    desc = f"A={v4[0] if v4 else '无'}"
    if v6:
        desc += f"　AAAA={v6[0][:24]}"
    return bool(v4 or v6), desc, bool(v6)


def http(url: str, timeout: float, use_proxy: bool, ipv4: bool = False,
         ua: str = UA) -> tuple[bool, str]:
    """用标准库发一次请求。use_proxy=False 不走代理；ipv4=True 强制只走 IPv4。"""
    req = urllib.request.Request(url, headers={"User-Agent": ua})
    orig = socket.getaddrinfo
    if ipv4:
        socket.getaddrinfo = lambda h, p, f=0, t=0, pr=0, fl=0: orig(
            h, p, socket.AF_INET, t, pr, fl)
    try:
        opener = (urllib.request.build_opener()
                  if use_proxy else
                  urllib.request.build_opener(urllib.request.ProxyHandler({})))
        with opener.open(req, timeout=timeout) as r:
            body = r.read(200)
            return True, f"HTTP {r.status} · {len(body)}+B"
    except Exception as e:
        return False, " ".join(f"{type(e).__name__}: {e}".split())[:110]
    finally:
        socket.getaddrinfo = orig


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--timeout", type=float, default=8.0)
    args = ap.parse_args()

    print(c("网络诊断 —— 逐个数据源分别测「当前设置」与「强制直连」", B))
    print()

    env_px = sorted({redact_proxy(v) for k in PROXY_VARS if (v := os.environ.get(k))})
    sys_all = urllib.request.getproxies()
    sys_px = sorted({redact_proxy(v) for k, v in sys_all.items()
                     if k in ("http", "https", "all") and v})
    print(f" 环境变量代理 : {'、'.join(env_px) or '（无）'}")
    print(f" 系统代理     : {'、'.join(sys_px) or '（无）'}")
    if sys_px:
        print(c("   ⚠ macOS 的系统代理是**独立于环境变量**的一套，Python 一样会读到：", DIM))
        print(c("     系统设置 → 网络 → Wi-Fi → 详细信息 → 代理 →「网页代理(HTTP/HTTPS)」「SOCKS 代理」", DIM))
        print(c("     关掉 VPN 客户端不会清掉这两个开关，端口一失效，所有请求都卡在这里。", DIM))
        print(c("     只 unset 环境变量是不够的——要去那里把开关关掉。", DIM))
    print()

    hosts = sorted({urllib.parse.urlparse(t[1]).hostname for t in TARGETS})
    print(c(" ① DNS 解析", B))
    dns_bad, has_v6 = [], []
    for h in hosts:
        ok, info, v6 = dns(h)
        print(f"   {c('✓', OK) if ok else c('✗', NO)} {h:<32}{info}")
        if not ok:
            dns_bad.append(h)
        if v6:
            has_v6.append(h)
    print()

    print(c(" ② HTTP 连通（当前设置 / 强制直连 / 直连+仅IPv4 / 裸UA）", B))
    rows = []
    mark = lambda ok: c("✓", OK) if ok else c("✗", NO)  # noqa: E731
    for label, url, affects, required in TARGETS:
        host = urllib.parse.urlparse(url).hostname
        as_is, m1 = http(url, args.timeout, use_proxy=True)
        direct, m2 = http(url, args.timeout, use_proxy=False)
        v4, m3 = (direct, m2) if direct else http(url, args.timeout, False, ipv4=True)
        # 用 akshare 裸调用的 UA 再试一次：能分辨"是不是因为没带 UA 被掐"
        best_proxy = True if as_is else False
        bare, m4 = http(url, args.timeout, use_proxy=best_proxy, ua=BARE_UA)
        rows.append((label, host, as_is, direct, v4, bare, m1, m2, m3, m4,
                     affects, required))
        print(f"   {label:<8} {host:<28} 当前 {mark(as_is)}   直连 {mark(direct)}"
              f"   仅IPv4 {mark(v4)}   裸UA {mark(bare)}")
        if not as_is:
            print(c(f"        当前设置: {m1}", DIM))
        if not direct:
            print(c(f"        强制直连: {m2}", DIM))
        if not v4 and not direct:
            print(c(f"        仅 IPv4 : {m3}", DIM))
    print()

    # ── 结论 ────────────────────────────────────────────────────
    any_asis = any(r[2] for r in rows)
    any_direct = any(r[3] for r in rows)
    any_v4 = any(r[4] for r in rows)
    proxy_hurts = [r for r in rows if not r[2] and r[3]]
    v6_hurts = [r for r in rows if not r[3] and r[4]]
    ua_hurts = [r for r in rows if (r[2] or r[3] or r[4]) and not r[5]]
    all_dead = [r for r in rows if not r[2] and not r[3] and not r[4]]

    print(c(" ③ 结论", B))
    if dns_bad:
        print(c(f"   ✗ 这些域名 DNS 解析不了：{'、'.join(dns_bad)}", NO))
        print("     多半是本机 DNS 或网络问题，换个网络/DNS（如 223.5.5.5）再试")
    if proxy_hurts:
        print(c(f"   ✗ 代理挡住了 {len(proxy_hurts)} 个数据源，直连是通的", NO))
        print("     → 用 ASTOCK_DIRECT=1，或 unset http_proxy https_proxy all_proxy")
        print("     → macOS 还要检查「系统偏好设置 → 网络 → 代理」里的全局开关")
    if v6_hurts:
        names = "、".join(r[0] for r in v6_hurts)
        print(c(f"   ✗ {len(v6_hurts)} 个数据源在仅 IPv4 下才通：{names}", NO))
        print("     → 你的网络 IPv6 出口是坏的。跑：")
        print(c("        ASTOCK_IPV4_ONLY=1 python tools/astock.py review", B))
        print("     本项目遇到连接失败也会自动降级到仅 IPv4 重试一次，并打印提示")
    if ua_hurts:
        names = "、".join(r[0] for r in ua_hurts)
        print(c(f"   ！{len(ua_hurts)} 个数据源会掐掉不带浏览器 UA 的请求：{names}", NO))
        print("     akshare 有些接口是裸 requests.get，UA 是 python-requests/2.x，")
        print("     会被服务器直接断开（RemoteDisconnected）。")
        print(c("     → 本项目已自动给所有请求补浏览器请求头，无需你做什么", OK))
    if all_dead:
        blocking = [r for r in all_dead if r[11]]
        optional = [r for r in all_dead if not r[11]]
        print(c(f"   ✗ {len(all_dead)} 个数据源怎么试都连不上：", NO))
        for r in all_dead:
            tag = c("必需", NO) if r[11] else c("可降级", DIM)
            print(f"       {r[0]}（{r[1]}）  [{tag}]  影响：{r[10]}")
        print("     常见原因：公司/校园网防火墙、运营商拦截、或该站点临时故障")
        print("     可以先在浏览器里打开对应域名验证一下是不是全网不通")
        if optional and not blocking:
            print(c("   → 这些都是可降级的数据源：复盘照样能跑，", OK))
            print(c("     受影响的章节会标 blocked 并在报告开头声明，不会拿旧数据凑数", OK))
    if any_asis and not proxy_hurts and not all_dead:
        print(c("   ✓ 全部数据源可达，可以跑 python tools/astock.py review", OK))
    elif any_direct and not any_asis:
        print(c("   → 直连全通。跑： ASTOCK_DIRECT=1 python tools/astock.py review", OK))
    if not any_asis and not any_direct and not any_v4:
        print(c("   ✗ 一个都连不上。先跑 python tools/astock.py demo 看离线示例", NO))

    sys.exit(0 if (any_asis or any_direct or any_v4) else 1)


if __name__ == "__main__":
    main()
