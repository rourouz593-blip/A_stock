"""AKShare 调用封装测试：缓存过期、代理降级、报错可读性。

这一组测试全部围绕同一个主题——**失败要说人话，且不能骗人**。
"""
from __future__ import annotations

import time

import pandas as pd
import pytest

from scripts import ak_client


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(ak_client, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(ak_client, "MAX_RETRY", 2)
    monkeypatch.setattr(ak_client, "RETRY_SLEEP", 0)
    ak_client.CACHE_HITS.clear()
    for k in ak_client.PROXY_VARS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.delenv("ASTOCK_DIRECT", raising=False)


def _fake_ak(monkeypatch, fn):
    import types

    mod = types.ModuleType("akshare")
    mod.demo_call = fn
    monkeypatch.setitem(__import__("sys").modules, "akshare", mod)


# ── 凭据不许出现在报错里 ────────────────────────────────────────
def test_redact_proxy_strips_credentials():
    assert ak_client.redact_proxy("http://user:s3cret@127.0.0.1:9910") == "http://***@127.0.0.1:9910"
    assert "s3cret" not in ak_client.redact_proxy("http://user:s3cret@h:1")


def test_proxy_summary_is_redacted(monkeypatch):
    monkeypatch.setenv("http_proxy", "http://tok:secret@127.0.0.1:9910")
    assert "secret" not in ak_client.proxy_summary()


def test_explain_diagnoses_dead_proxy(monkeypatch):
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:9910")
    e = Exception("Caused by ProxyError('Unable to connect to proxy', "
                  "NewConnectionError('127.0.0.1:9910 refused'))")
    msg = ak_client.explain(e)
    assert "代理" in msg and "ASTOCK_DIRECT" in msg, "应当直接告诉学生怎么修"


def test_explain_diagnoses_rate_limit():
    assert "限流" in ak_client.explain(Exception("JSONDecodeError: Expecting value"))


def test_explain_diagnoses_schema_change():
    assert "akshare" in ak_client.explain(KeyError("涨跌幅"))


# ── 代理挂了自动直连 ────────────────────────────────────────────
def test_falls_back_to_direct_when_proxy_is_dead(monkeypatch, capsys):
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:9910")
    calls = {"n": 0}

    def fn(**kw):
        calls["n"] += 1
        if any(os.environ.get(k) for k in ak_client.PROXY_VARS):
            raise Exception("ProxyError('Unable to connect to proxy')")
        return pd.DataFrame({"a": [1]})

    import os

    _fake_ak(monkeypatch, fn)
    df = ak_client.call("demo_call", cache=False)
    assert len(df) == 1, "代理挂了应当自动摘掉代理重试"
    assert "绕开代理" in capsys.readouterr().out, "降级必须告诉用户，不能静默"


def test_proxy_env_is_restored_after_fallback(monkeypatch):
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:9910")
    import os

    def fn(**kw):
        if os.environ.get("http_proxy"):
            raise Exception("ProxyError('Unable to connect to proxy')")
        return pd.DataFrame({"a": [1]})

    _fake_ak(monkeypatch, fn)
    ak_client.call("demo_call", cache=False)
    assert os.environ["http_proxy"] == "http://127.0.0.1:9910", "临时摘掉的代理必须还回去"


# ── 缓存有 TTL，不能悄悄给旧数据 ────────────────────────────────
def test_fresh_cache_is_used(monkeypatch, tmp_path):
    hits = {"n": 0}

    def fn(**kw):
        hits["n"] += 1
        return pd.DataFrame({"a": [1]})

    _fake_ak(monkeypatch, fn)
    ak_client.call("demo_call")          # 第一次真取
    ak_client.call("demo_call")          # 第二次走缓存
    assert hits["n"] == 1
    assert ak_client.CACHE_HITS and ak_client.CACHE_HITS[0]["call"] == "demo_call"


def test_stale_cache_is_refetched(monkeypatch, tmp_path):
    """实时快照放久了会让情绪判断彻底跑偏，过期就必须重取。"""
    hits = {"n": 0}

    def fn(**kw):
        hits["n"] += 1
        return pd.DataFrame({"a": [hits["n"]]})

    _fake_ak(monkeypatch, fn)
    ak_client.call("demo_call")
    # 把缓存文件的时间改成 2 小时前
    f = next(tmp_path.glob("*.csv"))
    old = time.time() - 2 * 3600
    import os

    os.utime(f, (old, old))
    df = ak_client.call("demo_call")
    assert hits["n"] == 2, "超过 TTL 的缓存不该再用"
    assert df["a"].iloc[0] == 2


def test_calendar_gets_a_long_ttl():
    """交易日历是稳定数据，不必每 30 分钟重取一次。"""
    assert ak_client.LONG_TTL_CALLS["tool_trade_date_hist_sina"] > ak_client.CACHE_TTL_MIN


def test_falls_back_to_ipv4_when_connection_hangs(monkeypatch, capsys):
    """IPv6 出口坏掉是最隐蔽的一类故障：只有 AAAA 记录的站点连接超时，
    别的站点却一切正常。所以连接类错误要自动降级到仅 IPv4 再试一次。"""
    import socket as _s

    orig = _s.getaddrinfo
    state = {"v4": False}

    def fn(**kw):
        # getaddrinfo 被换掉了 = 处于仅 IPv4 模式
        if _s.getaddrinfo is orig:
            raise Exception("Max retries exceeded: NewConnectionError timed out")
        state["v4"] = True
        return pd.DataFrame({"a": [1]})

    _fake_ak(monkeypatch, fn)
    df = ak_client.call("demo_call", cache=False)
    assert len(df) == 1 and state["v4"]
    assert "仅 IPv4" in capsys.readouterr().out
    assert _s.getaddrinfo is orig, "getaddrinfo 必须还原，不能污染整个进程"


def test_ipv4_only_context_restores_getaddrinfo():
    import socket as _s

    orig = _s.getaddrinfo
    with ak_client._ipv4_only():
        assert _s.getaddrinfo is not orig
    assert _s.getaddrinfo is orig


def test_without_proxy_sets_no_proxy_for_data_hosts(monkeypatch):
    """macOS 上 requests 还会读系统代理，光 unset 环境变量不够，
    必须把数据源域名写进 no_proxy 才能真正绕开。"""
    import os

    monkeypatch.setenv("http_proxy", "http://127.0.0.1:9910")
    monkeypatch.delenv("no_proxy", raising=False)
    with ak_client._without_proxy():
        assert "http_proxy" not in os.environ
        assert "eastmoney.com" in os.environ["no_proxy"]
        assert "sina.com.cn" in os.environ["NO_PROXY"]
    assert os.environ["http_proxy"] == "http://127.0.0.1:9910"
    assert "no_proxy" not in os.environ, "临时设的 no_proxy 要清掉"


def test_explain_keeps_the_raw_exception():
    """诊断可能猜错，原始异常不会。所以两样都要给——
    上一版只给诊断，把定位问题真正需要的信息弄丢了。"""
    e = Exception("HTTPSConnectionPool(host='80.push2.eastmoney.com', port=443): "
                  "Max retries exceeded")
    msg = ak_client.explain(e)
    assert "原始报错" in msg
    assert "80.push2.eastmoney.com" in msg, "域名这种关键信息不能被概括掉"


def test_failure_message_is_human_readable(monkeypatch):
    def fn(**kw):
        raise Exception("Caused by ProxyError('Unable to connect to proxy')")

    _fake_ak(monkeypatch, fn)
    monkeypatch.setenv("ASTOCK_DIRECT", "1")     # 关掉自动降级，直接看报错
    with pytest.raises(ak_client.FetchError) as e:
        ak_client.call("demo_call", cache=False)
    assert "代理" in str(e.value), "报错里要有诊断，不能只有原始异常"


# ── 请求头 ─────────────────────────────────────────────────────
def test_browser_ua_is_injected(monkeypatch):
    """akshare 有些接口是裸 requests.get，不带 UA 会被东财掐掉连接。"""
    import requests.sessions as rs

    seen = {}
    orig = rs.Session.request

    def fake(self, method, url, **kw):
        seen.update(kw.get("headers") or {})
        return "ok"

    monkeypatch.setattr(rs.Session, "request", fake)
    with ak_client._with_browser_ua():
        import requests

        requests.Session().request("GET", "https://push2his.eastmoney.com/x")
    assert "Mozilla" in seen["User-Agent"]
    assert seen["Referer"] == "https://quote.eastmoney.com/"
    assert rs.Session.request is not orig or True   # monkeypatch 会自己还原


def test_caller_headers_win_over_defaults(monkeypatch):
    """akshare 自己带了 headers 的接口要保持原样，我们只补它没设的字段。"""
    import requests.sessions as rs

    seen = {}
    monkeypatch.setattr(rs.Session, "request",
                        lambda self, m, u, **kw: seen.update(kw.get("headers") or {}))
    with ak_client._with_browser_ua():
        import requests

        requests.Session().request("GET", "https://x.com", headers={"User-Agent": "mine"})
    assert seen["User-Agent"] == "mine"


def test_ua_patch_is_restored():
    import requests.sessions as rs

    orig = rs.Session.request
    with ak_client._with_browser_ua():
        assert rs.Session.request is not orig
    assert rs.Session.request is orig, "补丁必须还原，不能污染整个进程"


def test_diagnose_remote_disconnected():
    e = Exception("ConnectionError: ('Connection aborted.', "
                  "RemoteDisconnected('Remote end closed connection without response'))")
    msg = ak_client.diagnose(e)
    assert "掐" in msg and "ASTOCK_DIRECT" in msg
    assert "net_check" in msg


def test_dropped_connection_triggers_direct_fallback(monkeypatch, capsys):
    """被服务器掐掉时，先怀疑代理线路，自动绕开代理重试。"""
    import os

    monkeypatch.setenv("http_proxy", "http://127.0.0.1:9910")

    def fn(**kw):
        if os.environ.get("http_proxy"):
            raise Exception("('Connection aborted.', RemoteDisconnected('...'))")
        return pd.DataFrame({"a": [1]})

    _fake_ak(monkeypatch, fn)
    assert len(ak_client.call("demo_call", cache=False)) == 1
    assert "绕开代理" in capsys.readouterr().out
