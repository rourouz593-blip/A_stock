"""AKShare 调用封装：统一重试、超时、缓存与"响亮失败"。

为什么要包一层，而不是到处直接 `ak.xxx()`：
  1. akshare 背后是第三方网页接口，会限流、会偶发超时——重试逻辑只写一次
  2. 同一天的数据反复取没意义，本地缓存能让调试快十倍，也少给数据源添麻烦
  3. 取数失败必须"响亮地失败"（抛异常），不能返回空 DataFrame 让上层误以为"今天就是没数据"
"""
from __future__ import annotations

import hashlib
import json
import os
import socket
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = Path(os.getenv("ASTOCK_CACHE_DIR", REPO_ROOT / "workspace" / "cache"))
MAX_RETRY = int(os.getenv("ASTOCK_MAX_RETRY", "3"))
RETRY_SLEEP = float(os.getenv("ASTOCK_RETRY_SLEEP", "1.5"))

# 缓存有效期（分钟）。默认只有 30 分钟——
# 涨跌家数、板块行情、资金流这些都是**实时快照**，
# 上午 11 点取的数拿到 15:30 的复盘里用，会得出完全错误的情绪判断。
CACHE_TTL_MIN = float(os.getenv("ASTOCK_CACHE_TTL_MIN", "30"))
# 少数接口的数据是稳定的，可以长期缓存
LONG_TTL_CALLS = {"tool_trade_date_hist_sina": 7 * 24 * 60}

PROXY_VARS = ("http_proxy", "https_proxy", "all_proxy",
              "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")

# 本次进程里命中缓存的调用，build_dataset 会据此在报告里标注"用了缓存"
CACHE_HITS: list[dict] = []


class FetchError(RuntimeError):
    """取数失败。上层应把对应 block 标为 missing，而不是伪造数据。"""


def redact_proxy(url: str) -> str:
    """把代理地址里的用户名密码抹掉，只留 scheme://host:port。

    代理 URL 里经常带 token（http://user:secret@host:3128）。
    报错信息会被复制到 issue、群里、日志里——**凭据绝不能出现在报错里**。
    """
    if not url:
        return ""
    scheme, sep, rest = url.partition("://")
    if not sep:
        scheme, rest = "", url
    if "@" in rest:
        rest = "***@" + rest.rsplit("@", 1)[1]
    return f"{scheme}://{rest}" if sep else rest


def proxy_env(redacted: bool = True) -> dict[str, str]:
    """当前生效的代理环境变量（默认已抹掉凭据）。"""
    out = {}
    for k in PROXY_VARS:
        v = os.environ.get(k)
        if v:
            out[k] = redact_proxy(v) if redacted else v
    return out


def proxy_summary() -> str:
    """去重后的代理地址，用于报错提示。"""
    seen = sorted({redact_proxy(v) for v in
                   (os.environ.get(k) for k in PROXY_VARS) if v})
    return "、".join(seen)


# 本项目会访问的数据源域名。绕过代理时按域名放行
DATA_HOSTS = ("eastmoney.com", "sina.com.cn", "sinajs.cn", "legulegu.com",
              "push2.eastmoney.com", "push2his.eastmoney.com", "push2ex.eastmoney.com")


# akshare 的不少接口是裸 `requests.get(url, params=...)`，不带任何请求头，
# UA 就是 `python-requests/2.x`。东财的 push2 系列会**直接掐掉**这种连接，
# 表现为 RemoteDisconnected('Remote end closed connection without response')。
BROWSER_HEADERS = {
    "User-Agent": os.getenv("ASTOCK_UA") or (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"),
    "Accept": "*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
}
REFERERS = {"eastmoney.com": "https://quote.eastmoney.com/",
            "legulegu.com": "https://legulegu.com/stockdata/market-activity"}


@contextmanager
def _with_browser_ua():
    """给 akshare 发出的每个请求补上浏览器请求头。

    只补**调用方没设的**字段：akshare 自己带了 headers 的接口保持原样。
    这不是伪装身份，是补上一个正常 HTTP 客户端本就该有的 UA——
    没有 UA 的请求会被很多站点当成扫描器直接断开。
    """
    try:
        import requests.sessions as rs
    except ImportError:
        yield
        return

    orig = rs.Session.request

    def patched(self, method, url, **kw):
        headers = dict(kw.get("headers") or {})
        for k, v in BROWSER_HEADERS.items():
            headers.setdefault(k, v)
        for domain, ref in REFERERS.items():
            if domain in str(url):
                headers.setdefault("Referer", ref)
                break
        kw["headers"] = headers
        return orig(self, method, url, **kw)

    rs.Session.request = patched
    try:
        yield
    finally:
        rs.Session.request = orig


@contextmanager
def _ipv4_only():
    """强制只走 IPv4。

    很经典的一类故障：网络对外通告了 IPv6，但 IPv6 出口其实是坏的。
    这时解析出 AAAA 记录的站点会**连接超时**，而只有 A 记录的站点照常工作——
    表现出来就是"新浪能连，东财连不上"这种看起来毫无道理的现象。

    macOS 尤其容易踩到（Happy Eyeballs 在某些网络下会卡住）。
    """
    orig = socket.getaddrinfo

    def v4_only(host, port, family=0, type=0, proto=0, flags=0):
        return orig(host, port, socket.AF_INET, type, proto, flags)

    socket.getaddrinfo = v4_only
    try:
        yield
    finally:
        socket.getaddrinfo = orig


@contextmanager
def _without_proxy():
    """临时绕开代理。

    两件事都要做：
      1. 摘掉 http_proxy / https_proxy / all_proxy 环境变量
      2. **把数据源域名写进 no_proxy** —— 在 macOS 上，requests 会通过
         urllib 读取「系统偏好设置里的代理」，光 unset 环境变量挡不住它；
         而 no_proxy 里的域名会被 requests 显式跳过。

    东财、新浪都是境内站点，走境外代理反而更容易失败，直连往往就是正确答案。
    """
    saved = {k: os.environ.pop(k, None) for k in PROXY_VARS}
    saved_no = {k: os.environ.get(k) for k in ("no_proxy", "NO_PROXY")}
    bypass = ",".join(DATA_HOSTS)
    os.environ["no_proxy"] = bypass
    os.environ["NO_PROXY"] = bypass
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v
        for k, v in saved_no.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _is_proxy_error(e: Exception) -> bool:
    txt = f"{type(e).__name__}: {e}"
    return ("ProxyError" in txt or "Unable to connect to proxy" in txt
            or "Cannot connect to proxy" in txt)


def diagnose(e: Exception) -> str:
    """给出一句人能照着做的诊断。拿不准就返回空串。"""
    txt = f"{type(e).__name__}: {e}"
    if _is_proxy_error(e):
        px = proxy_summary() or "（系统代理）"
        return (f"代理连不上：当前代理设置指向 {px}，但那个代理没在运行。\n"
                f"    三选一：① 打开你的 VPN/代理客户端；"
                f"② 关掉代理：unset {' '.join(PROXY_VARS[:3])}；"
                f"③ ASTOCK_DIRECT=1 强制直连（东财新浪都是境内站）")
    if _is_dropped(e):
        return ("TCP 连上了，但服务器不给响应就把连接掐了。三种常见原因：\n"
                "    ① 代理线路把境内站点绕到了境外节点 → ASTOCK_DIRECT=1\n"
                "    ② 请求被识别成脚本（本项目已自动补浏览器 UA，"
                "若你设过 ASTOCK_NO_UA=1 请去掉）\n"
                "    ③ 被限流 → 等几分钟，或调大 ASTOCK_RETRY_SLEEP\n"
                "    跑 python tools/net_check.py 能直接分辨是哪一种")
    if "Max retries exceeded" in txt or "NewConnectionError" in txt or "Timeout" in txt:
        return ("连不上这个域名。跑 `python tools/net_check.py` 逐个域名测，"
                "它会告诉你是 DNS、代理、还是站点本身的问题")
    if "JSONDecode" in txt or "Expecting value" in txt:
        return "数据源返回了非 JSON 内容，通常是被限流。等几分钟再试，或调大 ASTOCK_RETRY_SLEEP"
    if "KeyError" in txt or "columns" in txt:
        return ("接口返回的字段变了，试 pip install -U akshare；"
                "若仍不行请记进 memory/knowledge/akshare-gotchas.md")
    return ""


def explain(e: Exception) -> str:
    """诊断 + **原始异常**。

    诊断可能猜错，原始异常不会。所以永远两样都给——
    上一版只给诊断，结果把定位问题真正需要的信息弄丢了。
    """
    raw = " ".join(f"{type(e).__name__}: {e}".split())
    tip = diagnose(e)
    return f"{tip}\n    原始报错：{raw[:400]}" if tip else raw[:500]


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _cache_key(name: str, params: dict) -> str:
    raw = name + json.dumps(params, sort_keys=True, ensure_ascii=False)
    return f"{name}_{hashlib.md5(raw.encode()).hexdigest()[:10]}"


def call(name: str, params: dict[str, Any] | None = None, *, cache: bool = True):
    """调用一个 akshare 接口并返回 DataFrame。

    name   : akshare 函数名，如 'stock_zh_index_spot_em'
    params : 关键字参数
    cache  : 是否使用本地 CSV 缓存（默认开，调试时省时间）
    """
    params = params or {}
    try:
        import akshare as ak
    except ImportError as e:  # pragma: no cover
        raise FetchError(
            "未安装 akshare。请先 pip install -r requirements.txt"
        ) from e

    fn: Callable | None = getattr(ak, name, None)
    if fn is None:
        raise FetchError(f"akshare 没有接口 {name}（可能版本太旧，试试 pip install -U akshare）")

    cache_file = CACHE_DIR / f"{_cache_key(name, params)}.csv"
    ttl_min = LONG_TTL_CALLS.get(name, CACHE_TTL_MIN)
    if cache and cache_file.is_file():
        import pandas as pd

        age_min = (time.time() - cache_file.stat().st_mtime) / 60
        if age_min <= ttl_min:
            CACHE_HITS.append({"call": name, "age_min": round(age_min, 1),
                               "cached_at": datetime.fromtimestamp(
                                   cache_file.stat().st_mtime).astimezone().isoformat(
                                       timespec="seconds")})
            return pd.read_csv(cache_file, dtype={"代码": str, "板块代码": str})
        # 过期就当没有——实时快照放久了会让情绪判断彻底跑偏

    direct = os.getenv("ASTOCK_DIRECT") == "1"
    ipv4_only = os.getenv("ASTOCK_IPV4_ONLY") == "1"
    last_err: Exception | None = None
    for attempt in range(1, MAX_RETRY + 1):
        try:
            with _base_ctx(direct, ipv4_only):
                df = fn(**params)
            if df is None or len(df) == 0:
                raise FetchError(f"{name} 返回空数据 params={params}")
            if cache:
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                df.to_csv(cache_file, index=False)
            return df
        except FetchError:
            raise
        except Exception as e:  # 网络/限流/接口变更
            last_err = e
            # 连不上时依次尝试两种降级：① 绕开代理　② 只走 IPv4
            for label, ctx, hint in _fallbacks(e, direct, ipv4_only):
                try:
                    with ctx():
                        df = fn(**params)
                    if df is not None and len(df):
                        print(f"[ak_client] {label}后取到 {name}。{hint}", flush=True)
                        if cache:
                            cache_file.parent.mkdir(parents=True, exist_ok=True)
                            df.to_csv(cache_file, index=False)
                        return df
                except Exception as e2:
                    last_err = e2
            if attempt < MAX_RETRY:
                time.sleep(RETRY_SLEEP * attempt)
    raise FetchError(f"{name} 取数失败（重试 {MAX_RETRY} 次）\n    原因：{explain(last_err)}")


@contextmanager
def _nullcontext():
    yield


@contextmanager
def _base_ctx(direct: bool, ipv4: bool, ua: bool = True):
    """按开关组合出本次调用的网络环境。默认总是补浏览器请求头。"""
    if os.getenv("ASTOCK_NO_UA") == "1":
        ua = False
    with (_without_proxy() if direct else _nullcontext()):
        with (_ipv4_only() if ipv4 else _nullcontext()):
            with (_with_browser_ua() if ua else _nullcontext()):
                yield


def _is_conn_error(e: Exception) -> bool:
    txt = f"{type(e).__name__}: {e}"
    return any(k in txt for k in ("Max retries exceeded", "NewConnectionError",
                                  "Timeout", "timed out", "Connection"))


def _is_dropped(e: Exception) -> bool:
    """服务器主动断开：连上了，但对方不给响应就关了。"""
    txt = f"{type(e).__name__}: {e}"
    return any(k in txt for k in ("RemoteDisconnected", "Connection aborted",
                                  "ConnectionResetError", "Connection reset"))


def _fallbacks(e: Exception, direct: bool, ipv4: bool):
    """连不上时该按什么顺序降级重试。

    顺序有讲究：先试"绕开代理"（最常见），再试"只走 IPv4"（最隐蔽）。
    每一次降级都会打印出来——**静默降级比失败更糟**，
    用户会以为一切正常，却不知道数据是用另一条路取的。
    """
    out = []
    if _is_proxy_error(e) and not direct:
        out.append(("绕开代理", _without_proxy,
                    "建议关掉代理或设 ASTOCK_DIRECT=1"))
    if _is_dropped(e):
        # 连上了却被掐 —— 先怀疑代理线路，再怀疑站点限流
        if not direct:
            out.append(("绕开代理", _without_proxy,
                        "服务器主动断开，多半是代理线路把境内站点绕出去了；"
                        "建议 ASTOCK_DIRECT=1"))
            out.append(("绕开代理 + 仅 IPv4", lambda: _base_ctx(True, True),
                        "建议 ASTOCK_DIRECT=1 ASTOCK_IPV4_ONLY=1"))
    if _is_conn_error(e) and not ipv4:
        out.append(("改用仅 IPv4", _ipv4_only,
                    "你的网络 IPv6 出口可能是坏的，建议设 ASTOCK_IPV4_ONLY=1"))
        if not direct:
            out.append(("绕开代理 + 仅 IPv4",
                        lambda: _base_ctx(True, True),
                        "建议同时设 ASTOCK_DIRECT=1 ASTOCK_IPV4_ONLY=1"))
    return out


def try_call(name: str, params: dict[str, Any] | None = None, *, cache: bool = True):
    """同 call()，但失败时返回 (None, 错误信息) 而不是抛异常。

    用于"缺了也能继续"的可选数据块（如北向资金）。
    必需数据块请用 call()，让它响亮地失败。
    """
    try:
        return call(name, params, cache=cache), None
    except Exception as e:
        return None, str(e)
