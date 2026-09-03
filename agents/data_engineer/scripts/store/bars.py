"""本地行情仓库：已收盘的交易日只取一次，之后永远从本地读。

# 为什么缓存不够

`ak_client` 里已经有缓存了，但它是**按响应整体、按时间过期**的：
30 分钟一到，同样的数据要重新取一次。

而一个**已经收盘的交易日**，它的开高低收成交额**永远不会再变**。
对这种数据谈"过期"是没有意义的——它不该有 TTL，它该被**存下来**。

两者的区别：

|            | 缓存 `workspace/cache/*.csv` | 仓库 `workspace/history.sqlite` |
|------------|------------------------------|--------------------------------|
| 键         | 请求参数的哈希               | (数据集, 标的, **日期**)        |
| 失效       | TTL 到期                     | 永不（已收盘的日子不会变）      |
| 命中效果   | 省掉这一次请求               | 省掉**以后所有**对这一天的请求  |
| 适用       | 实时快照、盘中数据           | 日线、交易日历这类历史事实      |

每日请求计数只做观测，不设上限；
仓库是减量，让正常复盘本身就不需要那么多请求。两件事，都要做。

# 三条必须守住的规则

1. **只存已收盘的交易日。** 盘中把当天的"收盘价"写进仓库，
   等于把一个还在变的数字冻成了历史事实，之后再也不会被纠正——
   这比取不到数严重得多。见 `is_settled()`。

2. **用交易日历判断缺不缺，不要用日期减法。**
   否则国庆假期会被永远当成"缺 7 天"，每次复盘都去重取一遍，
   仓库反而变成了新的请求放大器。

3. **原样存整行，不做字段收敛。** 上游改字段名时，
   读取处会报错（好），而不是静默地把某一列错位（灾难）。
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from core.paths import REPO_ROOT

DB_PATH = Path(os.getenv("ASTOCK_HISTORY_DB",
                         REPO_ROOT / "workspace" / "history.sqlite"))

# 收盘之后多久算"数据已定稿"。15:00 收盘，行情商还要几分钟结算，
# 留到 15:05 比较稳。想改：ASTOCK_CLOSE_GUARD=15:30
CLOSE_GUARD = os.getenv("ASTOCK_CLOSE_GUARD", "15:05")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS bars (
    dataset    TEXT NOT NULL,      -- 'index_daily' / 'stock_daily' ...
    symbol     TEXT NOT NULL,      -- '000001'；不分标的的数据集用 '_'
    date       TEXT NOT NULL,      -- 'YYYY-MM-DD'
    row        TEXT NOT NULL,      -- 原始整行的 JSON，不做字段收敛
    source     TEXT,               -- 实际命中的源，跨源时要能查
    fetched_at TEXT,
    PRIMARY KEY (dataset, symbol, date)
);
CREATE INDEX IF NOT EXISTS idx_bars_lookup ON bars(dataset, symbol, date);
"""


def connect() -> sqlite3.Connection:
    """打开仓库。选 SQLite 而不是 parquet：标准库自带，无需额外依赖，
    单文件好备份，出问题能直接 `sqlite3 workspace/history.sqlite` 进去看。"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def is_settled(date: str, now: datetime | None = None) -> bool:
    """这一天的行情是否已经定稿（可以进仓库了）。

    今天且还没到收盘保护时点 → False。**盘中数据绝不入库。**
    """
    now = now or datetime.now()
    today = now.strftime("%Y-%m-%d")
    if date < today:
        return True
    if date > today:
        return False          # 未来的日期，显然还没发生
    hh, mm = (int(x) for x in CLOSE_GUARD.split(":"))
    return (now.hour, now.minute) >= (hh, mm)


def have_dates(dataset: str, symbol: str, start: str, end: str) -> set:
    """仓库里已有哪些日期。"""
    with connect() as conn:
        rows = conn.execute(
            "SELECT date FROM bars WHERE dataset=? AND symbol=? AND date>=? AND date<=?",
            (dataset, symbol, start, end)).fetchall()
    return {r["date"] for r in rows}


def missing_dates(dataset: str, symbol: str, want: Iterable) -> set:
    """还缺哪些交易日。

    `want` 必须来自**交易日历**，不能是 `range(start, end)`——
    否则周末和节假日会被当成永远补不上的缺口（见模块文档规则 2）。
    """
    want = set(want)
    if not want:
        return set()
    have = have_dates(dataset, symbol, min(want), max(want))
    return want - have


def load(dataset: str, symbol: str, start: str, end: str) -> list:
    """读回区间内的原始行，按日期升序。"""
    with connect() as conn:
        rows = conn.execute(
            "SELECT row FROM bars WHERE dataset=? AND symbol=? AND date>=? AND date<=?"
            " ORDER BY date",
            (dataset, symbol, start, end)).fetchall()
    return [json.loads(r["row"]) for r in rows]


def save(dataset: str, symbol: str, rows: Iterable, *,
         date_key: str = "日期", source: str = "", now: datetime = None) -> int:
    """写入。**未收盘的日期会被静默跳过**，返回真正写进去的行数。

    用 upsert 而不是 insert：重跑同一天不该报错，
    但如果上游修订了数据（偶尔发生），新值应该覆盖旧值。
    """
    payload = []
    fetched_at = (now or datetime.now()).astimezone().isoformat(timespec="seconds")
    for row in rows:
        date = str(row.get(date_key, ""))[:10]
        if not date or not is_settled(date, now):
            continue          # 盘中数据不入库——冻错了比没有更糟
        payload.append((dataset, symbol, date,
                        json.dumps(row, ensure_ascii=False, default=str),
                        source, fetched_at))
    if not payload:
        return 0
    with connect() as conn:
        conn.executemany(
            "INSERT INTO bars (dataset, symbol, date, row, source, fetched_at)"
            " VALUES (?,?,?,?,?,?)"
            " ON CONFLICT(dataset, symbol, date) DO UPDATE SET"
            " row=excluded.row, source=excluded.source, fetched_at=excluded.fetched_at",
            payload)
        conn.commit()
    return len(payload)


def stats() -> list:
    """仓库里有什么。给 `astock store` 和 doctor 用。"""
    if not DB_PATH.is_file():
        return []
    with connect() as conn:
        rows = conn.execute(
            "SELECT dataset, COUNT(*) AS n_rows, COUNT(DISTINCT symbol) AS symbols,"
            " MIN(date) AS first, MAX(date) AS last"
            " FROM bars GROUP BY dataset ORDER BY dataset").fetchall()
    return [dict(r) for r in rows]


def db_size_mb() -> float:
    return round(DB_PATH.stat().st_size / 1e6, 2) if DB_PATH.is_file() else 0.0


def purge(dataset: str = None) -> int:
    """删数据。整库删掉也没关系——下次复盘会重新取，只是慢一点。"""
    if not DB_PATH.is_file():
        return 0
    with connect() as conn:
        if dataset:
            n = conn.execute("DELETE FROM bars WHERE dataset=?", (dataset,)).rowcount
        else:
            n = conn.execute("DELETE FROM bars").rowcount
        conn.commit()
    return n
