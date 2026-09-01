#!/usr/bin/env python3
"""同一个地址，用六种方式各打一次，看是哪一维决定成败。

    python tools/net_probe.py

## 为什么需要它

`net_check.py` 用标准库 `urllib` 测下来是通的，
`astock review` 用 `requests`（akshare 用的）打同一台主机却每次被掐。
同一台机器、同一个地址、同一时刻——那问题一定在**两者之间的某个差异**里。

可能的差异有一串：代理解析方式、请求头、压缩协商、连接复用、TLS 栈、
甚至只是"上一次调用过近被限流了"。

一个个猜是猜不出来的。本工具把它们拆成正交的几维，各打一次，
**用结果表告诉你是哪一维在起作用**，而不是让你继续试。
"""
from __future__ import annotations

import argparse
import os
import socket
import ssl
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# 真实会被 index_zh_a_hist 调用的那个端点
URL = ("https://push2his.eastmoney.com/api/qt/stock/kline/get"
       "?secid=1.000001&fields1=f1%2Cf2%2Cf3%2Cf4%2Cf5%2Cf6"
       "&fields2=f51%2Cf52%2Cf53%2Cf54%2Cf55%2Cf56%2Cf57%2Cf58"
       "&klt=101&fqt=0&beg=0&end=20500000")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept": "*/*",
           "Accept-Language": "zh-CN,zh;q=0.9", "Referer": "https://quote.eastmoney.com/"}
OK, NO, DIM, B, END = "\033[32m", "\033[31m", "\033[2m", "\033[1m", "\033[0m"


def c(s, color):
    return s if os.getenv("NO_COLOR") else f"{color}{s}{END}"


def _short(e: Exception) -> str:
    return " ".join(f"{type(e).__name__}: {e}".split())[:120]


# ── 六种打法 ────────────────────────────────────────────────────
def via_urllib_noproxy(timeout):
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with op.open(urllib.request.Request(URL, headers=HEADERS), timeout=timeout) as r:
        return f"HTTP {r.status} · {len(r.read(400))}+B"


def via_requests_default(timeout):
    import requests
    r = requests.get(URL, headers=HEADERS, timeout=timeout)
    return f"HTTP {r.status_code} · {len(r.content)}B"


def via_requests_notrustenv(timeout):
    """trust_env=False：完全无视环境变量与系统代理，也不读 ~/.netrc。"""
    import requests
    s = requests.Session()
    s.trust_env = False
    r = s.get(URL, headers=HEADERS, timeout=timeout)
    return f"HTTP {r.status_code} · {len(r.content)}B"


def via_requests_identity(timeout):
    """关掉压缩协商。requests 默认会带 gzip/deflate/br/zstd，
    装了 brotli / zstandard 时头会更长，个别服务端对此敏感。"""
    import requests
    h = {**HEADERS, "Accept-Encoding": "identity"}
    s = requests.Session()
    s.trust_env = False
    r = s.get(URL, headers=h, timeout=timeout)
    return f"HTTP {r.status_code} · {len(r.content)}B"


def via_requests_close(timeout):
    """不复用连接。keep-alive 被中间设备或服务端提前关闭时会表现成 RemoteDisconnected。"""
    import requests
    h = {**HEADERS, "Connection": "close"}
    s = requests.Session()
    s.trust_env = False
    r = s.get(URL, headers=h, timeout=timeout)
    return f"HTTP {r.status_code} · {len(r.content)}B"


def via_raw_socket(timeout):
    """绕开 urllib 和 requests，自己拼一个 HTTP/1.1 请求。

    这一条能把"Python 的 HTTP 库"整体排除掉：
    它要是也失败，问题就在网络或对端，跟哪个库无关。
    """
    u = urllib.parse.urlparse(URL)
    ctx = ssl.create_default_context()
    with socket.create_connection((u.hostname, 443), timeout=timeout) as sock:
        with ctx.wrap_socket(sock, server_hostname=u.hostname) as ss:
            path = u.path + ("?" + u.query if u.query else "")
            req = (f"GET {path} HTTP/1.1\r\nHost: {u.hostname}\r\n"
                   + "".join(f"{k}: {v}\r\n" for k, v in HEADERS.items())
                   + "Connection: close\r\n\r\n")
            ss.sendall(req.encode())
            buf = b""
            while len(buf) < 400:
                chunk = ss.recv(4096)
                if not chunk:
                    break
                buf += chunk
    if not buf:
        raise RuntimeError("服务器直接关闭了连接，一个字节都没返回")
    return buf.split(b"\r\n", 1)[0].decode("latin1")


def via_curl(timeout):
    """curl 用的是完全独立的 HTTP/TLS 栈。它通而 Python 不通，就说明是 Python 侧的事。"""
    r = subprocess.run(
        ["curl", "-sS", "-o", "/dev/null", "-w", "HTTP %{http_code} · %{size_download}B",
         "--max-time", str(int(timeout)), "--noproxy", "*",
         "-H", f"User-Agent: {UA}", "-H", "Referer: https://quote.eastmoney.com/", URL],
        capture_output=True, text=True, timeout=timeout + 5)
    if r.returncode != 0:
        raise RuntimeError(f"curl exit {r.returncode}: {r.stderr.strip()[:100]}")
    return r.stdout.strip()


PROBES = [
    ("urllib 直连",        via_urllib_noproxy,     "标准库，net_check 用的就是它"),
    ("requests 默认",      via_requests_default,   "akshare 用的路径"),
    ("requests 无环境",    via_requests_notrustenv, "trust_env=False：不读代理/netrc"),
    ("requests 不压缩",    via_requests_identity,  "Accept-Encoding: identity"),
    ("requests 不复用",    via_requests_close,     "Connection: close"),
    ("裸 socket",          via_raw_socket,         "绕开所有 HTTP 库"),
    ("curl",               via_curl,               "独立的 HTTP/TLS 栈"),
]


def env_report() -> None:
    from scripts.ak_client import PROXY_VARS, redact_proxy

    print(c(" ① 这个 shell 到底是什么环境", B))
    print(f"   python        {sys.executable}")
    print(f"   版本          {sys.version.split()[0]}")
    for mod in ("requests", "urllib3", "certifi", "socks", "brotli", "zstandard", "akshare"):
        try:
            m = __import__(mod)
            print(f"   {mod:<13} {getattr(m, '__version__', '(已装)')}")
        except ImportError:
            print(f"   {mod:<13} {c('未安装', DIM)}")

    px = {k: redact_proxy(v) for k in PROXY_VARS if (v := os.environ.get(k))}
    sysp = {k: redact_proxy(v) for k, v in urllib.request.getproxies().items()
            if k in ("http", "https", "all")}
    print(f"   环境变量代理  {px or '（无）'}")
    print(f"   系统代理      {sysp or '（无）'}")
    for k in ("no_proxy", "NO_PROXY", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE",
              "SSL_CERT_FILE", "PYTHONHTTPSVERIFY"):
        if os.environ.get(k):
            print(f"   {k:<13} {os.environ[k][:70]}")
    print()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--timeout", type=float, default=15)
    ap.add_argument("--rounds", type=int, default=2, help="每种方式打几次（看是否时好时坏）")
    ap.add_argument("--gap", type=float, default=1.5, help="每次之间隔多久，避免自己造成限流")
    args = ap.parse_args()

    print(c("网络实验 —— 同一个地址，七种打法，看哪一维决定成败", B))
    print(c(f"   目标：push2his.eastmoney.com（index_zh_a_hist 真正取 K 线的那台）", DIM))
    print()
    env_report()

    print(c(" ② 逐种打法", B))
    results: dict[str, list[bool]] = {}
    for label, fn, note in PROBES:
        oks, msgs = [], []
        for _ in range(args.rounds):
            try:
                msgs.append(fn(args.timeout))
                oks.append(True)
            except Exception as e:
                msgs.append(_short(e))
                oks.append(False)
            time.sleep(args.gap)
        results[label] = oks
        marks = " ".join(c("✓", OK) if o else c("✗", NO) for o in oks)
        print(f"   {label:<16}{marks}   {c(note, DIM)}")
        for m, o in zip(msgs, oks):
            if not o:
                print(f"       {c(m, DIM)}")
            elif all(oks):
                print(f"       {c(m, DIM)}")
                break
    print()

    # ── 结论 ────────────────────────────────────────────────────
    def ok(name):
        return any(results.get(name, []))

    def dead(name):
        return name in results and not any(results[name])

    print(c(" ③ 结论", B))
    if all(any(v) for v in results.values()):
        print(c("   ✓ 七种方式都能通 —— 刚才的失败是**间歇性**的，最可能是限流。", OK))
        print("     对策：把 ASTOCK_MIN_INTERVAL 调大（默认 0.4，可以试 1.5），")
        print("     少量多次比密集重试更容易成功。")
    elif not any(any(v) for v in results.values()):
        print(c("   ✗ 七种方式全不通 —— 跟 Python 库无关，是网络或对端的问题。", NO))
        print("     可能：IP 被临时封（前面重试打得太密）、运营商拦截、站点故障。")
        print("     建议：等 10-30 分钟再试；或换个网络（手机热点）验证一次。")
    else:
        if ok("urllib 直连") and dead("requests 默认"):
            print(c("   ✗ urllib 通、requests 不通 —— 问题在 requests 这一侧。", NO))
            if ok("requests 无环境"):
                print(c("   → 是**环境变量/系统代理**：trust_env=False 就好了。", OK))
                print("     说明 ASTOCK_DIRECT 没能完全绕开（macOS 系统代理会被 urllib 读到）。")
                print("     我可以把 trust_env=False 也注入进去。")
            elif ok("requests 不压缩"):
                print(c("   → 是**压缩协商**：带 br/zstd 的 Accept-Encoding 被对端拒绝。", OK))
                print("     对策：给所有请求固定 Accept-Encoding: gzip, deflate。")
            elif ok("requests 不复用"):
                print(c("   → 是**连接复用**：keep-alive 的连接被提前关闭。", OK))
                print("     对策：给所有请求加 Connection: close。")
            else:
                print("     四种 requests 变体都不通，但 urllib 通 —— "
                      "多半是 urllib3 的 TLS/HTTP 行为差异，把上面整段发我。")
        elif dead("裸 socket") and ok("curl"):
            print(c("   ✗ Python 的裸 socket 不通、curl 通 —— 是 Python 的 TLS 栈问题。", NO))
            print("     检查 certifi 版本，或 REQUESTS_CA_BUNDLE / SSL_CERT_FILE 是否指错了。")
        elif ok("裸 socket") and dead("requests 默认"):
            print(c("   ✗ 裸 socket 通、requests 不通 —— 差异在 HTTP 库层。", NO))
            print("     看上面哪个 requests 变体是通的，那就是关键的那一维。")
        else:
            print("   结果不典型，把上面整段发我，我按实际情况改。")

    print()
    print(c("   把整段输出发回来，我按结论改代码——不用你再试。", DIM))


if __name__ == "__main__":
    main()
