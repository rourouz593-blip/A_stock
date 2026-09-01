"""provider 层：换源是改配置，不是改代码。

这些测试全部离线——用固定的返回体样本，不联网。
联网核对是另一件事，见 tools/verify_provider.py。
"""
import pytest

from scripts import providers
from scripts.providers import tencent


# ── 代码前缀路由 ────────────────────────────────────────────────
# 每一条都对应一类"静默拿到另一只股票的数据"，比报错危险得多
@pytest.mark.parametrize("code,want", [
    ("600519", "sh600519"),      # 沪市主板
    ("000858", "sz000858"),      # 深市主板
    ("300476", "sz300476"),      # 创业板
    ("688017", "sh688017"),      # 科创板
    ("920982", "bj920982"),      # 北交所 920 号段，必须先于 9x 判断
    ("sz000001", "sz000001"),    # 显式前缀原样透传
])
def test_prefix_routing(code, want):
    assert tencent._prefix(code) == want


def test_sh_index_whitelist_beats_first_digit():
    """000001 是歧义码：sh000001=上证指数，sz000001=平安银行。

    只看首位会把上证指数路由到深市，拿回平安银行的报价——
    而且不会报任何错。白名单就是为了挡这一下。
    """
    assert tencent._prefix("000001") == "sh000001"
    assert tencent._prefix("000300") == "sh000300"
    assert tencent._prefix("000858") == "sz000858"      # 对照：真·深市主板


def _line(code="sh600519", name="贵州茅台", n=60, **over):
    vals = [str(i) for i in range(n)]
    vals[1], vals[3], vals[4] = name, "1298.00", "1300.00"
    vals[37], vals[44], vals[45] = "12345.6", "10.5", "16300"
    for i, v in over.items():
        vals[int(i)] = v
    return f'v_{code}="' + "~".join(vals) + '";'


def test_parse_maps_fields_and_scales_amount():
    q = tencent.parse(_line(), {"sh600519": "600519"})["600519"]
    assert q["name"] == "贵州茅台" and q["price"] == 1298.0
    assert q["amount"] == 12345.6 * 1e4, "腾讯的成交额单位是万元，必须换算成元"


def test_short_response_is_dropped_not_misparsed():
    """返回体不完整时宁可丢掉。

    按位置解析的接口，字段少一个就会整体错位——
    "少了几个字段" 会变成 "市值填进了 PE"。丢掉比错位安全。
    """
    assert tencent.parse('v_sh600519="1~茅台~600519~1298";', {"sh600519": "600519"}) == {}


def test_stale_quote_is_flagged():
    """僵尸报价：停牌股/废码照样返回 200 + 定格报价，不报错。

    成交额 0 且现价==昨收 → 标 is_stale，由上层决定怎么处理，
    绝不静默当成当日真实成交。
    """
    stale = tencent.parse(_line(**{"37": "0", "3": "1300.00"}),
                          {"sh600519": "600519"})["600519"]
    assert stale["is_stale"] is True
    live = tencent.parse(_line(), {"sh600519": "600519"})["600519"]
    assert live["is_stale"] is False


def test_explicit_prefixes_do_not_collide():
    """同时查 sh000001 和 sz000001 时不能撞成同一个键。

    若都退回裸六位码，后者会静默覆盖前者——显式前缀就白写了。
    """
    text = _line("sh000001", "上证指数") + _line("sz000001", "平安银行")
    got = tencent.parse(text, {"sh000001": "sh000001", "sz000001": "sz000001"})
    assert got["sh000001"]["name"] == "上证指数"
    assert got["sz000001"]["name"] == "平安银行"


# ── 优先级链 ────────────────────────────────────────────────────
def test_chain_reads_config():
    assert providers.chain("spot")[0] == "tencent", "批量快照必须优先走不封 IP 的源"
    assert "eastmoney" in providers.chain("spot")


def test_env_overrides_config(monkeypatch):
    """能临时改源，是排障和教学演示都要用的开关。"""
    monkeypatch.setenv("ASTOCK_PROVIDER_SPOT", "eastmoney,tencent")
    assert providers.chain("spot") == ["eastmoney", "tencent"]


def test_unknown_dataset_is_empty_not_crash():
    assert providers.chain("没这个数据集") == []
    assert providers.get("没这个数据集", "spot") == []


def test_get_returns_named_callables():
    got = providers.get("spot", "spot")
    assert [n for n, _ in got] == ["tencent", "eastmoney"]
    assert all(callable(f) for _, f in got)


# ── 持仓取数：仓库 + 批量快照 ───────────────────────────────────
from datetime import datetime          # noqa: E402

import pandas as pd                    # noqa: E402

from scripts.fetch import stocks as S  # noqa: E402
from scripts.store import bars         # noqa: E402

CAL = ["2026-08-26", "2026-08-27", "2026-08-28"]
AFTER = datetime(2026, 8, 28, 15, 40)


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(bars, "DB_PATH", tmp_path / "h.sqlite")
    return tmp_path


def _hist(close=100.0):
    return pd.DataFrame([{"日期": d, "开盘": close, "收盘": close, "最高": close,
                          "最低": close, "成交量": 1000, "成交额": 1e7,
                          "振幅": 1.0, "涨跌幅": 0.5, "换手率": 1.0} for d in CAL])


def test_snapshot_is_one_request_for_all_holdings(db, monkeypatch):
    """N 只持仓 → 1 个快照请求，不是 N 个。

    这是整个改造的重点：原来每只一个东财请求，
    而"批量循环逐个拉"正是被点名的头号封禁成因。
    """
    seen = []

    def fake_spot(codes, **kw):
        seen.append(list(codes))
        return {c: {"code": c, "price": 100.0, "is_stale": False} for c in codes}

    monkeypatch.setattr("scripts.providers.tencent.spot", fake_spot)
    monkeypatch.setattr(S, "try_call", lambda *a, **k: (_hist(), None))
    S.fetch_holdings_quotes(["600519", "000858", "300476"], "2026-08-28",
                            trading_days=CAL)
    assert len(seen) == 1, "只该发一次快照请求"
    assert seen[0] == ["600519", "000858", "300476"], "三只票在同一个请求里"


def test_history_comes_from_the_store_on_rerun(db, monkeypatch):
    """同一天重跑：历史不再联网。"""
    bars.save("stock_daily_qfq", "600519", _hist().to_dict("records"),
              source="test", now=AFTER)
    monkeypatch.setattr("scripts.providers.tencent.spot",
                        lambda codes, **kw: {c: {"code": c, "is_stale": False} for c in codes})
    monkeypatch.setattr(S, "try_call",
                        lambda *a, **k: pytest.fail("历史齐了就不该再取日线"))
    block, frames = S.fetch_holdings_quotes(["600519"], "2026-08-28", trading_days=CAL)
    assert block.provenance.from_store == ["600519"]
    assert len(frames["600519"]) == 3


def test_qfq_drift_invalidates_the_stored_series(db, monkeypatch):
    """除权之后，前复权历史全变了——仓库存量必须整个作废。

    这是个股和指数的关键区别：指数日线永远不变，
    qfq 个股历史会被除权改写，而且不会报错，只是安静地对不上。
    """
    bars.save("stock_daily_qfq", "600519", _hist(100.0).to_dict("records"),
              source="test", now=AFTER)
    monkeypatch.setattr("scripts.providers.tencent.spot",
                        lambda codes, **kw: {c: {"code": c, "is_stale": False} for c in codes})
    # 少一天 → 触发联网重取；返回的价格整体变了（除权）
    with bars.connect() as c:
        c.execute("DELETE FROM bars WHERE symbol='600519' AND date='2026-08-28'")
        c.commit()
    monkeypatch.setattr(S, "try_call", lambda *a, **k: (_hist(88.0), None))
    block, _ = S.fetch_holdings_quotes(["600519"], "2026-08-28", trading_days=CAL)
    assert block.provenance.params["qfq_refetched"] == ["600519"]
    stored = bars.load("stock_daily_qfq", "600519", "2026-08-26", "2026-08-28")
    assert all(r["收盘"] == 88.0 for r in stored), "旧口径必须被清掉，不能新旧混存"


def test_no_drift_means_no_invalidation(db, monkeypatch):
    """对照组：价格没变就别乱清，否则等于每天全量重取。"""
    bars.save("stock_daily_qfq", "600519", _hist(100.0).to_dict("records"),
              source="test", now=AFTER)
    with bars.connect() as c:
        c.execute("DELETE FROM bars WHERE symbol='600519' AND date='2026-08-28'")
        c.commit()
    monkeypatch.setattr("scripts.providers.tencent.spot",
                        lambda codes, **kw: {c: {"code": c, "is_stale": False} for c in codes})
    monkeypatch.setattr(S, "try_call", lambda *a, **k: (_hist(100.0), None))
    block, _ = S.fetch_holdings_quotes(["600519"], "2026-08-28", trading_days=CAL)
    assert block.provenance.params["qfq_refetched"] is None


def test_stale_snapshot_is_flagged(db, monkeypatch):
    monkeypatch.setattr("scripts.providers.tencent.spot",
                        lambda codes, **kw: {c: {"code": c, "price": 10.0,
                                                 "is_stale": True} for c in codes})
    monkeypatch.setattr(S, "try_call", lambda *a, **k: (_hist(), None))
    block, _ = S.fetch_holdings_quotes(["600519"], "2026-08-28", trading_days=CAL)
    assert any("停牌" in f.message for f in block.flags)


def test_snapshot_failure_does_not_block_the_review(db, monkeypatch):
    """快照拿不到不该毁掉章节四——日线还在，标记缺失即可。"""
    def boom(codes, **kw):
        raise RuntimeError("网络不通")

    monkeypatch.setattr("scripts.providers.tencent.spot", boom)
    monkeypatch.setattr("scripts.providers.eastmoney.spot", boom)
    monkeypatch.setattr(S, "try_call", lambda *a, **k: (_hist(), None))
    block, frames = S.fetch_holdings_quotes(["600519"], "2026-08-28", trading_days=CAL)
    assert block.status == "ok" and frames
    assert block.provenance.params["spot_provider"] is None
