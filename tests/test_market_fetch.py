"""Index daily source, local-store, and Eastmoney intraday safety tests."""
from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest

from agents.data_engineer.scripts.fetch import market as M
from agents.data_engineer.scripts.providers import ashare, baostock
from agents.data_engineer.scripts.store import bars
from core.contracts import CORE_INDEXES

CAL = ["2026-08-26", "2026-08-27", "2026-08-28"]
AFTER = datetime(2026, 8, 28, 15, 40)


def _bar(date: str, close: float = 3000.0) -> dict:
    return {"日期": date, "开盘": close, "收盘": close, "最高": close, "最低": close,
            "成交量": 1, "成交额": 1e8, "振幅": 1.0, "涨跌幅": 0.5}


def _frame() -> pd.DataFrame:
    return pd.DataFrame([_bar(date) for date in CAL])


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(bars, "DB_PATH", tmp_path / "history.sqlite")
    monkeypatch.setattr(M, "_STORE_WARNED", False)
    return tmp_path


def _seed_all_indexes() -> None:
    for code in CORE_INDEXES:
        bars.save("index_daily", code, [_bar(date) for date in CAL], source="test", now=AFTER)


def test_full_store_coverage_sends_zero_baostock_requests(store, monkeypatch) -> None:
    _seed_all_indexes()
    monkeypatch.setattr(baostock, "index_daily", lambda *a: pytest.fail("network called"))
    monkeypatch.setattr(ashare, "index_daily", lambda *a: pytest.fail("network called"))
    block, frame = M.fetch_index_daily("2026-08-28", lookback_days=3, trading_days=CAL)
    assert block.status == "ok"
    assert len(block.provenance.from_store) == 4
    assert set(frame["指数代码"]) == set(CORE_INDEXES)


def test_partial_store_only_fetches_missing_index(store, monkeypatch) -> None:
    _seed_all_indexes()
    with bars.connect() as connection:
        connection.execute("DELETE FROM bars WHERE symbol='000001' AND date='2026-08-27'")
        connection.commit()
    fetched = []

    def fake(code, start_date, end_date):
        fetched.append(code)
        return _frame()

    monkeypatch.setattr(baostock, "index_daily", fake)
    block, _ = M.fetch_index_daily("2026-08-28", lookback_days=3, trading_days=CAL)
    assert fetched == ["000001"]
    assert block.provenance.source == "baostock"


def test_no_calendar_bypasses_store(store, monkeypatch) -> None:
    _seed_all_indexes()
    fetched = []
    fake = lambda code, *_: (fetched.append(code), _frame())[1]
    monkeypatch.setattr(baostock, "index_daily", fake)
    monkeypatch.setattr(ashare, "index_daily", fake)
    M.fetch_index_daily("2026-08-28", lookback_days=3, trading_days=None)
    assert fetched == list(CORE_INDEXES)


def test_configured_daily_provider_failure_is_explicit(store, monkeypatch) -> None:
    fail = lambda *a: (_ for _ in ()).throw(RuntimeError("offline"))
    monkeypatch.setattr(baostock, "index_daily", fail)
    monkeypatch.setattr(ashare, "index_daily", fail)
    block, frame = M.fetch_index_daily("2026-08-28", lookback_days=3, trading_days=CAL)
    assert block.status == "missing"
    assert frame is None
    assert bars.stats() == []
    assert all(flag.level == "error" for flag in block.flags)


def test_stale_daily_bar_is_explicitly_degraded(store, monkeypatch) -> None:
    stale = pd.DataFrame([_bar("2026-08-27")])
    monkeypatch.setattr(baostock, "index_daily", lambda *a: stale.copy())
    monkeypatch.setattr(ashare, "index_daily", lambda *a: stale.copy())
    block, _ = M.fetch_index_daily("2026-08-28", lookback_days=3, trading_days=CAL)
    assert block.status == "degraded"
    assert all("尚未发布" in flag.message for flag in block.flags)


def test_store_failure_does_not_block_providers(store, monkeypatch, capsys) -> None:
    monkeypatch.setattr(bars, "connect",
                        lambda: (_ for _ in ()).throw(RuntimeError("disk I/O error")))
    monkeypatch.setattr(baostock, "index_daily", lambda *a: _frame())
    monkeypatch.setattr(ashare, "index_daily", lambda *a: _frame())
    block, _ = M.fetch_index_daily("2026-08-28", lookback_days=3, trading_days=CAL)
    assert block.status == "ok"
    assert "仓库不可用" in capsys.readouterr().out


def test_snapshot_converts_nan_amount_to_none() -> None:
    frame = pd.DataFrame([
        {**_bar("2026-08-27"), "指数代码": "000001", "指数名称": "上证指数", "成交额": float("nan")},
        {**_bar("2026-08-28"), "指数代码": "000001", "指数名称": "上证指数", "成交额": float("nan")},
    ])
    snapshot = M._today_snapshot(frame, "2026-08-28")
    assert snapshot[0]["amount"] is None
    assert snapshot[0]["amount_chg_pct"] is None


def test_session_unknown_amount_stays_none() -> None:
    frame = pd.DataFrame([
        {"时间": "2026-08-28 09:30:00", "收盘": 100, "最高": 101,
         "最低": 99, "成交额": float("nan")},
        {"时间": "2026-08-28 09:31:00", "收盘": 101, "最高": 102,
         "最低": 100, "成交额": float("nan")},
    ])
    assert M._split_sessions(frame, "测试")["sessions"][0]["amount"] is None
