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
from urllib.parse import urlparse
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

# ⚠️ akshare 里 1000+ 个 requests.get 是**不带 timeout** 的。
# requests 的默认 timeout 是 None＝无限等——服务器只要不回，进程就一直挂在那里。
# 对无人值守的系统来说，挂起比报错糟糕得多：报错会被记录、会重试、会上报，
# 挂起什么都不会发生，你第二天才发现今天没有复盘。
HTTP_TIMEOUT = (float(os.getenv("ASTOCK_CONNECT_TIMEOUT", "10")),
                float(os.getenv("ASTOCK_READ_TIMEOUT", "30")))

# 两次请求之间的最小间隔。东财对短时间内的密集请求会直接掐连接，
# 而"重试"恰恰会制造密集请求——4 个指数 × 3 次重试 × 2 条降级路径，
# 十几个请求几秒内打过去，等于自己把自己限流了。
MIN_INTERVAL = float(os.getenv("ASTOCK_MIN_INTERVAL", "0.4"))

# 东财单独加严。依据是 a-stock-data 项目整理的社区实测阈值（2026-05）：
#   >5 次/秒、单 IP 并发 ≥10、1 分钟 ≥200 次 → 触发风控
# 以及那份项目里一条一手封禁记录（2026-06-30）：10 线程并发、完全不限流、
# 1 小时 45000+ 请求 → push2 全系列 IP 级封禁**持续 20 小时以上**。
# 它们的限流器默认间隔就是 1.0 秒；我们原来的 0.4 秒对东财偏松，跟齐。
EM_MIN_INTERVAL = float(os.getenv("ASTOCK_EM_MIN_INTERVAL", "1.0"))
EM_HOSTS = ("eastmoney.com",)
_last_request_at = 0.0


def _interval_for(host: str) -> float:
    return EM_MIN_INTERVAL if any(h in host for h in EM_HOSTS) else MIN_INTERVAL
# 少数接口的数据是稳定的，可以长期缓存
LONG_TTL_CALLS = {"tool_trade_date_hist_sina": 7 * 24 * 60}

PROXY_VARS = ("http_proxy", "https_proxy", "all_proxy",
              "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")

# 本次进程里命中缓存的调用，build_dataset 会据此在报告里标注"用了缓存"
CACHE_HITS: list[dict] = []


class FetchError(RuntimeError):
    """取数失败。上层应把对应 block 标为 missing，而不是伪造数据。"""


class CooledDown(FetchError):
    """这个域名正在冷却期，本次**不发请求**。"""


# ── 熔断器 ──────────────────────────────────────────────────────
# 血的教训：连续失败时继续重试，会把自己的 IP 打进对方的限流名单。
# 一旦被封，连原本正常的主机也会跟着不可达——损失远大于"这次取不到数"。
#
# 所以：一个域名连续被拒若干次之后，**在冷却期内一次请求都不发**，
# 直接失败、让位给备用源。状态落盘，因为用户往往是反复重跑脚本——
# 只存在内存里的熔断器，一重启就白做了。
CIRCUIT_FILE = CACHE_DIR / "circuit.json"
COOLDOWN_MIN = float(os.getenv("ASTOCK_COOLDOWN_MIN", "10"))
FAILS_TO_TRIP = int(os.getenv("ASTOCK_FAILS_TO_TRIP", "3"))


def _circuit() -> dict:
    if CIRCUIT_FILE.is_file():
        try:
            return json.loads(CIRCUIT_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def _save_circuit(c: dict) -> None:
    CIRCUIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    CIRCUIT_FILE.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")


def cooling_hosts() -> dict[str, float]:
    """当前处于冷却期的域名 → 还剩几分钟。"""
    now = time.time()
    return {h: round((v["until"] - now) / 60, 1)
            for h, v in _circuit().items() if v.get("until", 0) > now}


def clear_circuit() -> int:
    n = len(_circuit())
    if CIRCUIT_FILE.is_file():
        CIRCUIT_FILE.unlink()
    return n


def _note_failure(host: str) -> None:
    c = _circuit()
    e = c.setdefault(host, {"fails": 0, "until": 0})
    e["fails"] = e.get("fails", 0) + 1
    if e["fails"] >= FAILS_TO_TRIP:
        # 连续失败越多，冷却越久：3 次 → 10 分钟，6 次 → 20 分钟，以此类推
        mult = e["fails"] // FAILS_TO_TRIP
        e["until"] = time.time() + COOLDOWN_MIN * 60 * mult
        print(f"[ak_client] {host} 连续 {e['fails']} 次被拒，"
              f"冷却 {COOLDOWN_MIN * mult:.0f} 分钟——期间不再发请求，直接走备用源。"
              f"\n           继续硬打只会让封禁范围扩大（这是实测教训）", flush=True)
    _save_circuit(c)


def _note_success(host: str) -> None:
    c = _circuit()
    if host in c:
        c.pop(host)
        _save_circuit(c)


# ── 每日请求预算 ────────────────────────────────────────────────
# 熔断器解决的是"已经被拒之后别再打"，但它救不了另一种情况：
# **每个请求都成功，只是数量失控**。8-31 那次就是这样开始的——
# 前几十个请求全是 200，等到开始被拒时，请求量已经放大了一个数量级。
#
# 所以再加一道更笨也更可靠的闸：**一天最多发多少个请求，数满即停**。
# 它不判断对错、不看返回码、不管是主源还是备用源，只数数。
#
# 关键设计：
#   1. 落盘按日计数——用户往往反复重跑脚本，只存内存等于没有上限
#   2. 检查放在最底层（patched Session.request 里），任何路径都绕不过
#   3. 超额直接抛错，**绝不等待、绝不重试**——超额本身就是"今天已经打太多了"
#   4. 命中缓存的调用根本走不到这里，天然不计数
BUDGET_FILE = CACHE_DIR / "budget.json"
MAX_REQUESTS = int(os.getenv("ASTOCK_MAX_REQUESTS", "300"))    # 全部域名合计/天
MAX_PER_HOST = int(os.getenv("ASTOCK_MAX_PER_HOST", "120"))    # 单域名/天
_warned_at: set[str] = set()


class BudgetExceeded(FetchError):
    """今日请求预算用尽。不是网络问题，是自我保护。"""


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def budget_state() -> dict:
    """今日用量。跨日自动归零。"""
    if BUDGET_FILE.is_file():
        try:
            b = json.loads(BUDGET_FILE.read_text(encoding="utf-8"))
            if b.get("date") == _today():
                return b
        except json.JSONDecodeError:
            pass
    return {"date": _today(), "total": 0, "hosts": {}}


def reset_budget() -> int:
    """手动清零，返回清掉的请求数。"""
    n = budget_state()["total"]
    if BUDGET_FILE.is_file():
        BUDGET_FILE.unlink()
    return n


def _spend(host: str) -> None:
    """记一个请求。超额抛 BudgetExceeded——在请求发出**之前**。"""
    b = budget_state()
    used_host = b["hosts"].get(host, 0)
    if b["total"] >= MAX_REQUESTS:
        raise BudgetExceeded(
            f"今日请求预算已用尽（{b['total']}/{MAX_REQUESTS}）。\n"
            f"    这是自我保护，不是网络故障：请求量失控正是被封 IP 的前奏。\n"
            f"    缺的数据请按 blocked 处理，不要绕过。\n"
            f"    确认无误要放开：ASTOCK_MAX_REQUESTS=<更大的数>；"
            f"清零：python tools/astock.py budget --reset")
    if used_host >= MAX_PER_HOST:
        raise BudgetExceeded(
            f"{host} 今日请求已达上限（{used_host}/{MAX_PER_HOST}）。\n"
            f"    单个域名打太多是被封的直接原因。请换源或按 blocked 处理。\n"
            f"    放开：ASTOCK_MAX_PER_HOST=<更大的数>")
    b["total"] += 1
    b["hosts"][host] = used_host + 1
    # 到 70% 时提醒一次，让人有机会在撞墙前发现异常
    if b["total"] == int(MAX_REQUESTS * 0.7) and "total" not in _warned_at:
        _warned_at.add("total")
        print(f"[ak_client] 今日已发 {b['total']}/{MAX_REQUESTS} 个请求。"
              f"一次正常复盘约 30–50 个——数字异常说明有地方在重复取数。", flush=True)
    BUDGET_FILE.parent.mkdir(parents=True, exist_ok=True)
    BUDGET_FILE.write_text(json.dumps(b, ensure_ascii=False, indent=2), encoding="utf-8")


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
def _with_http_defaults(direct: bool = False):
    """给 akshare 发出的每个请求补它自己不做的几件事。

    1. **超时**——akshare 有一千多个 `requests.get(url, params=...)` 不带 timeout，
       默认是无限等。挂起对无人值守的系统是最坏的失败：
       报错会被记录、重试、上报；挂起什么都不会发生。
    2. **浏览器请求头**——没有 UA 的请求会被东财当成扫描器直接断开。
       只补调用方没设的字段，akshare 自己带 headers 的接口保持原样。
    3. **限流**——两次请求之间留最小间隔。密集请求正是"被掐连接"的主因，
       而重试机制恰恰会制造密集请求。
    4. **direct 时置 `trust_env=False`**——这才是"彻底不走代理"的正解。

       为什么光删环境变量不够：requests 的 `trust_env` 打开时，
       会去读 http_proxy/https_proxy/all_proxy、**macOS 系统偏好设置里的代理**、
       甚至 `~/.netrc`。删掉 shell 变量只堵住了第一条路。
       `trust_env=False` 是一刀切，三条路一起断。
    """
    global _last_request_at
    try:
        import requests.sessions as rs
    except ImportError:
        yield
        return

    orig = rs.Session.request

    def patched(self, method, url, **kw):
        global _last_request_at
        host = urlparse(str(url)).hostname or "?"
        left = cooling_hosts().get(host)
        if left and os.getenv("ASTOCK_IGNORE_COOLDOWN") != "1":
            raise CooledDown(
                f"{host} 正在冷却，还剩 {left:.0f} 分钟（连续被拒后自动触发）。\n"
                f"    继续硬打只会扩大封禁范围。想强行试：ASTOCK_IGNORE_COOLDOWN=1；"
                f"想清空：python tools/astock.py cooldown --clear")
        _spend(host)                    # 超额在这里抛错——请求还没发出去
        if direct:
            self.trust_env = False      # 无视一切 shell / 系统 / netrc 配置
        gap, need = time.time() - _last_request_at, _interval_for(host)
        if gap < need:
            time.sleep(need - gap)
        _last_request_at = time.time()

        headers = dict(kw.get("headers") or {})
        for k, v in BROWSER_HEADERS.items():
            headers.setdefault(k, v)
        for domain, ref in REFERERS.items():
            if domain in str(url):
                headers.setdefault("Referer", ref)
                break
        kw["headers"] = headers
        if kw.get("timeout") is None:      # 只在调用方没设时才补
            kw["timeout"] = HTTP_TIMEOUT
        try:
            resp = orig(self, method, url, **kw)
        except Exception as e:
            if _is_dropped(e) or _is_conn_error(e):
                _note_failure(host)
            raise
        _note_success(host)
        return resp

    rs.Session.request = patched
    try:
        yield
    finally:
        rs.Session.request = orig


_with_browser_ua = _with_http_defaults      # 旧名字保留，免得引用处漏改


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
    if isinstance(e, CooledDown):
        return str(e)
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
    max_retry = MAX_RETRY
    for attempt in range(1, MAX_RETRY + 1):
        if attempt > max_retry:
            break
        try:
            with _base_ctx(direct, ipv4_only):
                df = fn(**params)
            if df is None or len(df) == 0:
                raise FetchError(f"{name} 返回空数据 params={params}")
            if cache:
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                df.to_csv(cache_file, index=False)
            return df
        except CooledDown:
            raise      # 冷却期：一次请求都不发，也不重试
        except FetchError:
            raise
        except Exception as e:  # 网络/限流/接口变更
            last_err = e
            # 连不上时依次尝试两种降级：① 绕开代理　② 只走 IPv4
            # 403 不走降级——换个出口 IP 试探正是风控最讨厌的行为
            for label, ctx, hint in ([] if _is_waf(e)
                                     else _fallbacks(e, direct, ipv4_only)):
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
            if _is_waf(e):
                # 风控明确拒绝：立刻停手。重试改变不了结果，只会加重封禁。
                raise FetchError(
                    f"{name} 被风控拒绝（403）。这不是网络问题，重试无用。"
                    f"\n    等几分钟再试，或换备用源。"
                    f"\n    原因：{explain(e)}") from e
            if _is_dropped(e):
                # 限流信号：退避加长，但**总次数收紧**——
                # 死磕这个源不如快点退到备用源，多打的每一次都在加重限流
                max_retry = min(max_retry, int(os.getenv("ASTOCK_DROP_RETRY", "2")))
            if attempt < max_retry:
                time.sleep(RETRY_SLEEP * attempt * (4 if _is_dropped(e) else 1))
    raise FetchError(f"{name} 取数失败（重试 {min(MAX_RETRY, max_retry)} 次）"
                     f"\n    原因：{explain(last_err)}")


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
            with (_with_http_defaults(direct) if ua else _nullcontext()):
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


def _is_waf(e: Exception) -> bool:
    """403：这是风控在说"不"，不是网络出问题。

    区别很重要——**403 重试没有任何意义，只会加重风控**。
    连接错误重试可能成功（对方在抖动），403 重试一定不成功（对方在拒绝你），
    而且每一次都在给封禁计数加分。
    见 memory/knowledge/akshare-gotchas.md「403 与断连是两回事」。
    """
    txt = f"{type(e).__name__}: {e}"
    return "403" in txt or "Forbidden" in txt


def _fallbacks(e: Exception, direct: bool, ipv4: bool):
    """连不上时该按什么顺序降级重试。

    顺序有讲究：先试"绕开代理"（最常见），再试"只走 IPv4"（最隐蔽）。
    每一次降级都会打印出来——**静默降级比失败更糟**，
    用户会以为一切正常，却不知道数据是用另一条路取的。
    """
    out = []
    has_proxy = bool(proxy_env())      # 压根没配代理就别试"绕开代理"，那是白打请求
    if _is_proxy_error(e) and not direct:
        out.append(("绕开代理", _without_proxy,
                    "建议关掉代理或设 ASTOCK_DIRECT=1"))
    if _is_dropped(e):
        # 连上了却被掐：有代理就先怀疑线路；没代理就是站点在限流，
        # **这时候多试几条路等于加重限流**，什么都不做、快点退到备用源才是对的
        if has_proxy and not direct:
            out.append(("绕开代理", _without_proxy,
                        "服务器主动断开，多半是代理线路把境内站点绕出去了；"
                        "建议 ASTOCK_DIRECT=1"))
    # 注意：`Connection aborted`（被掐）也含 "Connection" 字样，但它**不是连通性问题**，
    # 换 IPv4 毫无帮助，只会多打一次请求、加重限流。所以这里要把它排除掉。
    if _is_conn_error(e) and not _is_dropped(e) and not ipv4:
        out.append(("改用仅 IPv4", _ipv4_only,
                    "你的网络 IPv6 出口可能是坏的，建议设 ASTOCK_IPV4_ONLY=1"))
        if has_proxy and not direct:
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
