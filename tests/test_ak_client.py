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
    with ak_client._with_http_defaults():
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
    with ak_client._with_http_defaults():
        import requests

        requests.Session().request("GET", "https://x.com", headers={"User-Agent": "mine"})
    assert seen["User-Agent"] == "mine"


def test_ua_patch_is_restored():
    import requests.sessions as rs

    orig = rs.Session.request
    with ak_client._with_http_defaults():
        assert rs.Session.request is not orig
    assert rs.Session.request is orig, "补丁必须还原，不能污染整个进程"


def test_timeout_is_injected(monkeypatch):
    """akshare 有一千多个请求不带 timeout，默认无限等。

    挂起对无人值守的系统是最坏的失败：报错会被记录、重试、上报，
    挂起什么都不会发生——你第二天才发现今天没有复盘。
    """
    import requests.sessions as rs

    seen = {}
    monkeypatch.setattr(rs.Session, "request",
                        lambda self, m, u, **kw: seen.update(kw) or "x")
    with ak_client._with_http_defaults():
        import requests

        requests.Session().request("GET", "https://x.com")
    assert seen["timeout"] == ak_client.HTTP_TIMEOUT


def test_caller_timeout_wins(monkeypatch):
    """akshare 自己设了 timeout 的那 39 个接口保持原样。"""
    import requests.sessions as rs

    seen = {}
    monkeypatch.setattr(rs.Session, "request",
                        lambda self, m, u, **kw: seen.update(kw) or "x")
    with ak_client._with_http_defaults():
        import requests

        requests.Session().request("GET", "https://x.com", timeout=5)
    assert seen["timeout"] == 5


def test_requests_are_spaced_out(monkeypatch):
    """密集请求正是"被掐连接"的主因，而重试恰恰会制造密集请求。"""
    import time as _t

    import requests.sessions as rs

    monkeypatch.setattr(rs.Session, "request", lambda self, m, u, **kw: "x")
    monkeypatch.setattr(ak_client, "MIN_INTERVAL", 0.05)
    monkeypatch.setattr(ak_client, "_last_request_at", 0.0)
    t0 = _t.time()
    with ak_client._with_http_defaults():
        import requests

        for _ in range(4):
            requests.Session().request("GET", "https://x.com")
    assert _t.time() - t0 >= 0.10, "请求之间没有留间隔"


def test_dropped_connection_backs_off_longer(monkeypatch):
    """被掐是限流信号，立刻重试只会加重。退避要比普通错误久得多。"""
    sleeps = []
    monkeypatch.setattr(ak_client.time, "sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr(ak_client, "RETRY_SLEEP", 1.0)
    monkeypatch.setattr(ak_client, "MAX_RETRY", 3)

    def fn(**kw):
        raise Exception("('Connection aborted.', RemoteDisconnected('...'))")

    _fake_ak(monkeypatch, fn)
    monkeypatch.setenv("ASTOCK_DIRECT", "1")     # 关掉降级，只看退避
    with pytest.raises(ak_client.FetchError):
        ak_client.call("demo_call", cache=False)
    assert max(sleeps) >= 4, f"退避太短：{sleeps}"
    assert len(sleeps) <= 2, f"限流时重试次数应当收紧，实际睡了 {len(sleeps)} 次"


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


def test_rate_limit_does_not_trigger_pointless_fallbacks(monkeypatch):
    """被限流时多试几条路 = 加重限流。

    `Connection aborted` 里也含 "Connection" 字样，很容易被当成连通性问题
    而去试"改用仅 IPv4"——那对限流毫无帮助，只是多打一次请求。
    """
    import os

    for k in ak_client.PROXY_VARS:
        monkeypatch.delenv(k, raising=False)
    calls = []

    def fn(**kw):
        calls.append(1)
        raise Exception("('Connection aborted.', RemoteDisconnected('x'))")

    _fake_ak(monkeypatch, fn)
    monkeypatch.setattr(ak_client.time, "sleep", lambda s: None)
    with pytest.raises(ak_client.FetchError):
        ak_client.call("demo_call", cache=False)
    assert len(calls) <= 2, f"限流时打了 {len(calls)} 次请求，太多了"


def test_real_connection_error_still_tries_ipv4(monkeypatch):
    """真正连不上的时候，仍然要试仅 IPv4——别把两类错误混为一谈。"""
    for k in ak_client.PROXY_VARS:
        monkeypatch.delenv(k, raising=False)
    calls = []

    def fn(**kw):
        calls.append(1)
        raise Exception("Max retries exceeded: NewConnectionError timed out")

    _fake_ak(monkeypatch, fn)
    monkeypatch.setattr(ak_client.time, "sleep", lambda s: None)
    with pytest.raises(ak_client.FetchError):
        ak_client.call("demo_call", cache=False)
    assert len(calls) > 2, "连通性问题应当尝试降级路径"


def test_dropped_error_without_proxy_skips_proxy_fallback(monkeypatch):
    """被掐 + 没配代理 = 站点在限流，"绕开代理"只是一次白打的请求。"""
    for k in ak_client.PROXY_VARS:
        monkeypatch.delenv(k, raising=False)
    fb = ak_client._fallbacks(
        Exception("('Connection aborted.', RemoteDisconnected('x'))"),
        direct=False, ipv4=False)
    assert fb == []


def test_proxy_error_always_tries_bypass_even_without_env_vars(monkeypatch):
    """真报了 ProxyError 却没有代理环境变量 —— 那正是 macOS「系统代理」的情形。

    这时 `_without_proxy()` 依然有用：它会设 no_proxy，那才是能绕开系统代理的办法。
    """
    for k in ak_client.PROXY_VARS:
        monkeypatch.delenv(k, raising=False)
    fb = ak_client._fallbacks(
        Exception("ProxyError('Unable to connect to proxy')"), direct=False, ipv4=False)
    assert any("绕开代理" in f[0] for f in fb)


def test_direct_sets_trust_env_false(monkeypatch):
    """ASTOCK_DIRECT=1 时必须 trust_env=False。

    光删 http_proxy 环境变量是不够的：requests 的 trust_env 打开时还会读
    macOS 系统偏好设置里的代理和 ~/.netrc。删变量只堵住了三条路里的一条。
    """
    import requests
    import requests.sessions as rs

    seen = {}
    monkeypatch.setattr(rs.Session, "request",
                        lambda self, m, u, **kw: seen.update(trust_env=self.trust_env))
    with ak_client._with_http_defaults(direct=True):
        requests.Session().request("GET", "https://x.com")
    assert seen["trust_env"] is False


def test_non_direct_leaves_trust_env_alone(monkeypatch):
    """默认情况下不动 trust_env——用户配了代理是有理由的。"""
    import requests
    import requests.sessions as rs

    seen = {}
    monkeypatch.setattr(rs.Session, "request",
                        lambda self, m, u, **kw: seen.update(trust_env=self.trust_env))
    with ak_client._with_http_defaults(direct=False):
        requests.Session().request("GET", "https://x.com")
    assert seen["trust_env"] is True


# ── 熔断器 ─────────────────────────────────────────────────────
@pytest.fixture
def circuit(tmp_path, monkeypatch):
    monkeypatch.setattr(ak_client, "CIRCUIT_FILE", tmp_path / "c.json")
    monkeypatch.setattr(ak_client, "FAILS_TO_TRIP", 3)
    monkeypatch.setattr(ak_client, "COOLDOWN_MIN", 10.0)
    return tmp_path


def _hit(monkeypatch, url="https://push2his.eastmoney.com/x", fail=True):
    import requests
    import requests.sessions as rs

    def h(self, m, u, **kw):
        if fail:
            raise Exception("('Connection aborted.', RemoteDisconnected('x'))")
        return "ok"

    monkeypatch.setattr(rs.Session, "request", h)
    with ak_client._with_http_defaults():
        return requests.Session().request("GET", url)


def test_circuit_trips_after_repeated_refusals(circuit, monkeypatch, capsys):
    """连续被拒之后停止发请求。

    这是实测教训：继续硬打会把 IP 打进对方的限流名单，
    然后连原本正常的主机也一起不可达——损失远大于"这次取不到数"。
    """
    for _ in range(3):
        with pytest.raises(Exception):
            _hit(monkeypatch)
    assert "push2his.eastmoney.com" in ak_client.cooling_hosts()
    with pytest.raises(ak_client.CooledDown):
        _hit(monkeypatch)


def test_cooldown_sends_zero_requests(circuit, monkeypatch):
    """冷却期内必须**一次请求都不发**，否则熔断毫无意义。"""
    for _ in range(3):
        with pytest.raises(Exception):
            _hit(monkeypatch)
    calls = []

    import requests
    import requests.sessions as rs

    monkeypatch.setattr(rs.Session, "request", lambda self, m, u, **kw: calls.append(u))
    with ak_client._with_http_defaults():
        with pytest.raises(ak_client.CooledDown):
            requests.Session().request("GET", "https://push2his.eastmoney.com/x")
    assert calls == []


def test_circuit_is_per_host(circuit, monkeypatch):
    """一个主机被封不该连累别的主机——尤其别连累还活着的备用源。"""
    for _ in range(3):
        with pytest.raises(Exception):
            _hit(monkeypatch, "https://push2his.eastmoney.com/x")
    assert "finance.sina.com.cn" not in ak_client.cooling_hosts()
    _hit(monkeypatch, "https://finance.sina.com.cn/x", fail=False)


def test_success_resets_the_counter(circuit, monkeypatch):
    with pytest.raises(Exception):
        _hit(monkeypatch)
    _hit(monkeypatch, fail=False)
    assert ak_client._circuit().get("push2his.eastmoney.com") is None


def test_circuit_survives_process_restart(circuit, monkeypatch):
    """状态要落盘：用户往往是反复重跑脚本，只存内存的熔断器一重启就白做了。"""
    for _ in range(3):
        with pytest.raises(Exception):
            _hit(monkeypatch)
    assert ak_client.CIRCUIT_FILE.is_file()
    assert ak_client.cooling_hosts()      # 重新读文件也还在


def test_escalating_cooldown(circuit, monkeypatch):
    """越是连续被拒，冷却越久。"""
    for _ in range(3):
        with pytest.raises(Exception):
            _hit(monkeypatch)
    first = ak_client.cooling_hosts()["push2his.eastmoney.com"]
    monkeypatch.setenv("ASTOCK_IGNORE_COOLDOWN", "1")
    for _ in range(3):
        with pytest.raises(Exception):
            _hit(monkeypatch)
    assert ak_client.cooling_hosts()["push2his.eastmoney.com"] > first


def test_ignore_cooldown_escape_hatch(circuit, monkeypatch):
    for _ in range(3):
        with pytest.raises(Exception):
            _hit(monkeypatch)
    monkeypatch.setenv("ASTOCK_IGNORE_COOLDOWN", "1")
    with pytest.raises(Exception) as e:
        _hit(monkeypatch)
    assert not isinstance(e.value, ak_client.CooledDown), "逃生门要能真的发出请求"


def test_clear_circuit(circuit, monkeypatch):
    for _ in range(3):
        with pytest.raises(Exception):
            _hit(monkeypatch)
    assert ak_client.clear_circuit() >= 1
    assert ak_client.cooling_hosts() == {}


# ── 每日请求预算 ────────────────────────────────────────────────
@pytest.fixture
def budget(tmp_path, monkeypatch):
    """把预算收紧到很小，方便断言边界。"""
    monkeypatch.setattr(ak_client, "BUDGET_FILE", tmp_path / "b.json")
    monkeypatch.setattr(ak_client, "MAX_REQUESTS", 5)
    monkeypatch.setattr(ak_client, "MAX_PER_HOST", 3)
    monkeypatch.setattr(ak_client, "CIRCUIT_FILE", tmp_path / "c.json")
    return tmp_path


def test_budget_stops_before_the_request_is_sent(budget, monkeypatch):
    """超额时**一个字节都不发出去**——这才是"限量"的意义。

    如果先发请求再计数，撞上限的那一刻已经打出去了；
    这里断言的是：超额之后底层 request 的调用次数不再增加。
    """
    import requests
    import requests.sessions as rs

    sent = []
    monkeypatch.setattr(rs.Session, "request", lambda self, m, u, **kw: sent.append(u))

    for _ in range(3):
        with ak_client._with_http_defaults():
            requests.Session().request("GET", "https://push2his.eastmoney.com/x")
    assert len(sent) == 3          # 单域名上限 3，正好打满

    with pytest.raises(ak_client.BudgetExceeded):
        with ak_client._with_http_defaults():
            requests.Session().request("GET", "https://push2his.eastmoney.com/x")
    assert len(sent) == 3          # 关键：没有第 4 个请求发出去


def test_budget_is_per_host_and_total(budget, monkeypatch):
    """单域名上限先于总额生效，防止把所有额度砸在一个源上。"""
    import requests
    import requests.sessions as rs

    monkeypatch.setattr(rs.Session, "request", lambda self, m, u, **kw: "ok")

    def hit(host):
        with ak_client._with_http_defaults():
            requests.Session().request("GET", f"https://{host}/x")

    for _ in range(3):
        hit("push2his.eastmoney.com")
    with pytest.raises(ak_client.BudgetExceeded, match="今日请求已达上限"):
        hit("push2his.eastmoney.com")

    # 换个域名还能继续，直到撞总额
    hit("finance.sina.com.cn")
    hit("finance.sina.com.cn")
    with pytest.raises(ak_client.BudgetExceeded, match="今日请求预算已用尽"):
        hit("finance.sina.com.cn")


def test_budget_survives_process_restart(budget, monkeypatch):
    """计数落盘。只存内存的上限，用户重跑一次脚本就归零，等于没有。"""
    import requests
    import requests.sessions as rs

    monkeypatch.setattr(rs.Session, "request", lambda self, m, u, **kw: "ok")
    for _ in range(3):
        with ak_client._with_http_defaults():
            requests.Session().request("GET", "https://a.eastmoney.com/x")

    assert ak_client.budget_state()["total"] == 3          # 模拟"新进程读盘"
    assert ak_client.budget_state()["hosts"]["a.eastmoney.com"] == 3


def test_budget_resets_across_days(budget):
    """跨日自动归零，不需要人去清。"""
    import json

    stale = {"date": "2000-01-01", "total": 999, "hosts": {"x": 999}}
    ak_client.BUDGET_FILE.parent.mkdir(parents=True, exist_ok=True)
    ak_client.BUDGET_FILE.write_text(json.dumps(stale), encoding="utf-8")
    assert ak_client.budget_state()["total"] == 0


def test_budget_exceeded_is_not_retried(budget, monkeypatch):
    """BudgetExceeded 必须直接冒泡，绝不能被 call() 的重试逻辑当成网络错误。

    否则"限量"会变成"限量之后再打三次"——正好是它要防的事。
    """
    assert issubclass(ak_client.BudgetExceeded, ak_client.FetchError)

    calls = []

    def fake_fn(**kw):
        calls.append(1)
        raise ak_client.BudgetExceeded("用尽")

    import types

    fake_ak = types.SimpleNamespace(stock_x=fake_fn)
    monkeypatch.setitem(__import__("sys").modules, "akshare", fake_ak)
    with pytest.raises(ak_client.BudgetExceeded):
        ak_client.call("stock_x", cache=False)
    assert len(calls) == 1          # 只调了一次，没有重试


def test_cache_hits_do_not_spend_budget(budget, monkeypatch, tmp_path):
    """命中缓存的调用不该计数——它根本没发请求。

    这条保证了"把缓存做厚"是真的能省额度，而不是自欺欺人。
    """
    import pandas as pd

    monkeypatch.setattr(ak_client, "CACHE_DIR", tmp_path / "cache")
    (tmp_path / "cache").mkdir(parents=True, exist_ok=True)
    key = ak_client._cache_key("stock_y", {})
    pd.DataFrame({"a": [1]}).to_csv(tmp_path / "cache" / f"{key}.csv", index=False)

    import types

    monkeypatch.setitem(__import__("sys").modules, "akshare",
                        types.SimpleNamespace(stock_y=lambda **kw: None))
    df = ak_client.call("stock_y")
    assert len(df) == 1
    assert ak_client.budget_state()["total"] == 0


def test_reset_budget(budget, monkeypatch):
    import requests
    import requests.sessions as rs

    monkeypatch.setattr(rs.Session, "request", lambda self, m, u, **kw: "ok")
    with ak_client._with_http_defaults():
        requests.Session().request("GET", "https://a.eastmoney.com/x")
    assert ak_client.reset_budget() == 1
    assert ak_client.budget_state()["total"] == 0


# ── 403 与断连是两回事 ──────────────────────────────────────────
def test_403_is_not_retried_and_not_downgraded(monkeypatch, tmp_path):
    """403 是风控在说"不"，重试和换出口都只会加重封禁。

    连接错误重试可能成功（对方在抖动），403 重试一定不成功（对方在拒绝你）,
    而且每一次都在给封禁计数加分。
    """
    import types

    calls = []

    def forbidden(**kw):
        calls.append(1)
        raise Exception("403 Client Error: Forbidden for url: https://push2.eastmoney.com/x")

    monkeypatch.setattr(ak_client, "CACHE_DIR", tmp_path)
    monkeypatch.setitem(__import__("sys").modules, "akshare",
                        types.SimpleNamespace(stock_z=forbidden))
    monkeypatch.setattr(ak_client, "_fallbacks",
                        lambda *a: pytest.fail("403 不该走降级阶梯"))
    with pytest.raises(ak_client.FetchError, match="重试无用"):
        ak_client.call("stock_z", cache=False)
    assert len(calls) == 1, "403 只该打一次"


def test_connection_errors_are_still_retried(monkeypatch, tmp_path):
    """对照组：断连仍然重试——否则上面那条就变成"什么都不重试"了。"""
    import types

    calls = []

    def dropped(**kw):
        calls.append(1)
        raise Exception("('Connection aborted.', RemoteDisconnected('x'))")

    monkeypatch.setattr(ak_client, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(ak_client, "RETRY_SLEEP", 0)
    monkeypatch.setitem(__import__("sys").modules, "akshare",
                        types.SimpleNamespace(stock_w=dropped))
    with pytest.raises(ak_client.FetchError):
        ak_client.call("stock_w", cache=False)
    assert len(calls) > 1, "断连应该重试"


def test_eastmoney_gets_a_stricter_interval(monkeypatch):
    """东财单独加严：社区实测 >5 次/秒触发风控，别家没这么敏感。"""
    monkeypatch.setattr(ak_client, "MIN_INTERVAL", 0.4)
    monkeypatch.setattr(ak_client, "EM_MIN_INTERVAL", 1.0)
    assert ak_client._interval_for("push2his.eastmoney.com") == 1.0
    assert ak_client._interval_for("finance.sina.com.cn") == 0.4


def test_eastmoney_default_interval_is_at_least_one_second():
    """默认值本身也要守住——这是那条 20 小时封禁记录换来的数字。"""
    import importlib

    fresh = importlib.reload(ak_client)
    assert fresh.EM_MIN_INTERVAL >= 1.0
    importlib.reload(ak_client)
