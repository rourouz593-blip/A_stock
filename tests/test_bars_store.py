"""本地行情仓库。

这些测试守的不是"能存能读"，而是几条**存错了不会自己好**的规则：
盘中数据不入库、降级源不入库、节假日不能被当成缺口。
"""
from datetime import datetime

import pytest

from agents.data_engineer.scripts.store import bars


@pytest.fixture(autouse=True)
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(bars, "DB_PATH", tmp_path / "h.sqlite")
    return tmp_path


NOON = datetime(2026, 8, 28, 12, 0)      # 盘中
AFTER = datetime(2026, 8, 28, 15, 40)    # 收盘后


def test_intraday_bars_never_enter_the_store():
    """盘中不入库。

    把还在跳动的"收盘价"冻成历史事实，之后再也不会被纠正——
    这比取不到数严重得多，所以宁可不存。
    """
    n = bars.save("index_daily", "000001",
                  [{"日期": "2026-08-28", "收盘": 3100.0}], now=NOON)
    assert n == 0
    assert bars.load("index_daily", "000001", "2026-08-28", "2026-08-28") == []


def test_same_day_is_stored_after_close():
    n = bars.save("index_daily", "000001",
                  [{"日期": "2026-08-28", "收盘": 3200.0}], now=AFTER)
    assert n == 1
    assert bars.load("index_daily", "000001", "2026-08-28", "2026-08-28")[0]["收盘"] == 3200.0


def test_past_days_in_the_same_batch_still_get_stored():
    """盘中跑复盘时，昨天及以前的数据是定稿的，照存不误——
    只有当天那一行被挡掉。"""
    rows = [{"日期": "2026-08-26", "收盘": 1.0},
            {"日期": "2026-08-27", "收盘": 2.0},
            {"日期": "2026-08-28", "收盘": 3.0}]
    assert bars.save("index_daily", "000001", rows, now=NOON) == 2


def test_missing_dates_is_calendar_driven():
    """缺口按交易日算。

    传进来的 want 来自交易日历，所以周末和节假日根本不会出现在里面，
    也就不会被当成永远补不上的缺口——那会让仓库变成新的请求放大器。
    """
    bars.save("index_daily", "000001",
              [{"日期": "2026-08-27", "收盘": 1.0},
               {"日期": "2026-08-28", "收盘": 2.0}], now=AFTER)
    # 8-29/8-30 是周末，交易日历里没有，所以不在 want 里
    want = {"2026-08-27", "2026-08-28"}
    assert bars.missing_dates("index_daily", "000001", want) == set()
    assert bars.missing_dates("index_daily", "000001",
                              want | {"2026-08-31"}) == {"2026-08-31"}


def test_upsert_lets_upstream_revisions_through():
    """同一天重跑不该报错；上游修订了数据，新值应该覆盖旧值。"""
    bars.save("index_daily", "000001", [{"日期": "2026-08-27", "收盘": 1.0}], now=AFTER)
    bars.save("index_daily", "000001", [{"日期": "2026-08-27", "收盘": 9.9}], now=AFTER)
    got = bars.load("index_daily", "000001", "2026-08-27", "2026-08-27")
    assert len(got) == 1 and got[0]["收盘"] == 9.9


def test_rows_are_stored_verbatim():
    """原样存整行。上游改字段名时该在读取处报错，而不是静默错位。"""
    row = {"日期": "2026-08-27", "开盘": 1, "收盘": 2, "成交额": None, "怪字段": "x"}
    bars.save("index_daily", "000001", [row], now=AFTER)
    assert bars.load("index_daily", "000001", "2026-08-27", "2026-08-27")[0] == row


def test_store_is_per_symbol_and_dataset():
    bars.save("index_daily", "000001", [{"日期": "2026-08-27", "收盘": 1.0}], now=AFTER)
    assert bars.load("index_daily", "399001", "2026-08-27", "2026-08-27") == []
    assert bars.load("index_intraday", "000001", "2026-08-27", "2026-08-27") == []


def test_purge_and_stats():
    bars.save("index_daily", "000001", [{"日期": "2026-08-27", "收盘": 1.0}], now=AFTER)
    bars.save("index_daily", "399001", [{"日期": "2026-08-27", "收盘": 2.0}], now=AFTER)
    st = bars.stats()
    assert st[0]["dataset"] == "index_daily" and st[0]["symbols"] == 2
    assert bars.purge("index_daily") == 2
    assert bars.stats() == []


def test_is_settled_boundary(monkeypatch):
    monkeypatch.setattr(bars, "CLOSE_GUARD", "15:05")
    assert not bars.is_settled("2026-08-28", datetime(2026, 8, 28, 15, 4))
    assert bars.is_settled("2026-08-28", datetime(2026, 8, 28, 15, 5))
    assert bars.is_settled("2026-08-27", datetime(2026, 8, 28, 9, 0))
    assert not bars.is_settled("2026-08-29", datetime(2026, 8, 28, 23, 0))
