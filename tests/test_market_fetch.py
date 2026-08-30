"""指数取数测试：绕开多余的前置请求 + 东财不可达时退到新浪。

背景（实测）：`index_zh_a_hist()` 取 K 线之前会先请求 80.push2.eastmoney.com
拉一份「全部指数 → 市场号」对照表。K 线主机 push2his 在用户网络上是通的，
80.push2 却连接超时——于是卡在一个**纯粹多余**的前置请求上。

我们只盯四个固定指数，市场号是常数，不需要去问。
"""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.fetch import market as M


def test_index_market_ids_cover_all_core_indexes():
    from scripts.contracts import CORE_INDEXES

    assert set(M.INDEX_MARKET_ID) == set(CORE_INDEXES), "四大指数的市场号必须齐全"
    assert M.INDEX_MARKET_ID["000001"] == 1, "上证是沪市"
    assert M.INDEX_MARKET_ID["399006"] == 0, "创业板是深市"


def test_skip_index_code_map_patches_and_restores():
    pytest.importorskip("akshare")
    from akshare.index import index_zh_em as m

    orig = m.index_code_id_map_em
    with M._skip_index_code_map():
        assert m.index_code_id_map_em() == M.INDEX_MARKET_ID
        assert m.index_code_id_map_em is not orig
    assert m.index_code_id_map_em is orig, "补丁必须还原，不能污染整个进程"


def test_skip_is_safe_when_akshare_layout_changes(monkeypatch):
    """akshare 换了模块结构也不该炸——这只是个优化，不是必需品。"""
    import builtins

    real_import = builtins.__import__

    def boom(name, *a, **kw):
        if "index_zh_em" in name:
            raise ImportError("moved")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", boom)
    with M._skip_index_code_map():
        pass          # 不抛异常即可


# ── 新浪备用源 ─────────────────────────────────────────────────
def _sina_frame():
    return pd.DataFrame({
        "date": pd.to_datetime(["2026-08-26", "2026-08-27", "2026-08-28"]),
        "open": [3400.0, 3410.0, 3412.55],
        "close": [3405.0, 3412.98, 3438.21],
        "high": [3415.0, 3420.0, 3444.90],
        "low": [3395.0, 3405.0, 3405.12],
        "volume": [1e8, 1.1e8, 1.2e8],
    })


def test_sina_fallback_normalizes_columns(monkeypatch):
    monkeypatch.setattr(M, "call", lambda name, params=None: _sina_frame())
    df = M._from_sina("000001", "2026-08-28", lookback_days=30)
    assert list(df.columns) == ["日期", "开盘", "收盘", "最高", "最低",
                                "成交量", "成交额", "振幅", "涨跌幅"]
    assert df["日期"].iloc[-1] == "2026-08-28"


def test_sina_fallback_computes_pct_change(monkeypatch):
    monkeypatch.setattr(M, "call", lambda name, params=None: _sina_frame())
    df = M._from_sina("000001", "2026-08-28", lookback_days=30)
    # (3438.21 / 3412.98 - 1) * 100 ≈ 0.74
    assert df["涨跌幅"].iloc[-1] == pytest.approx(0.74, abs=0.01)


def test_sina_fallback_leaves_amount_missing(monkeypatch):
    """新浪不返回成交额。宁可缺一个字段并标注，也不编一个数。"""
    monkeypatch.setattr(M, "call", lambda name, params=None: _sina_frame())
    df = M._from_sina("000001", "2026-08-28", lookback_days=30)
    assert df["成交额"].isna().all()


def test_sina_fallback_respects_as_of(monkeypatch):
    """备用源也不许返回分析日之后的数据。"""
    monkeypatch.setattr(M, "call", lambda name, params=None: _sina_frame())
    df = M._from_sina("000001", "2026-08-27", lookback_days=30)
    assert df["日期"].max() == "2026-08-27"


def test_sina_board_prefix(monkeypatch):
    seen = {}

    def fake_call(name, params=None):
        seen["symbol"] = params["symbol"]
        return _sina_frame()

    monkeypatch.setattr(M, "call", fake_call)
    M._from_sina("399006", "2026-08-28", 30)
    assert seen["symbol"] == "sz399006", "创业板要用 sz 前缀"
    M._from_sina("000001", "2026-08-28", 30)
    assert seen["symbol"] == "sh000001"


# ── 备用源导致的成交额缺失，不许被当成 0 ─────────────────────────
def test_two_market_amount_refuses_to_guess_when_amount_missing():
    from scripts.clean import derive

    snap = [{"code": "000001", "name": "上证指数", "amount": 5.0e11, "amount_chg_pct": 8.0},
            {"code": "399001", "name": "深证成指", "amount": None, "amount_chg_pct": None}]
    out = derive.two_market_amount(snap)
    assert out["total"] is None, "缺一个就不能算，更不能用 0 代替"
    assert "深证成指" in out["note"] and "不会用 0 代替" in out["note"]


def test_snapshot_turns_nan_amount_into_none():
    """新浪备用源不返回成交额 → NaN。它必须变成 None，否则会写出非法 JSON。"""
    df = pd.DataFrame({
        "指数代码": ["000001", "000001"],
        "指数名称": ["上证指数", "上证指数"],
        "日期": ["2026-08-27", "2026-08-28"],
        "开盘": [3400.0, 3412.55], "收盘": [3412.98, 3438.21],
        "最高": [3420.0, 3444.90], "最低": [3405.0, 3405.12],
        "成交额": [float("nan"), float("nan")],
        "振幅": [1.0, 1.17], "涨跌幅": [0.3, 0.74],
    })
    snap = M._today_snapshot(df, "2026-08-28")
    assert snap[0]["amount"] is None
    assert snap[0]["amount_chg_pct"] is None
    import json

    json.dumps(snap, allow_nan=False)      # 不抛异常即为通过
