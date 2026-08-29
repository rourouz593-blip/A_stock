"""交易日历。所有时间对齐都依赖它，是第一个要跑通的接口。"""
from __future__ import annotations

from ..ak_client import FetchError, call, now_iso
from ..contracts import DataBlock, Provenance


def fetch_calendar(as_of: str) -> tuple[DataBlock, list[str]]:
    """取交易日历，返回 (DataBlock, 最近 N 个交易日列表, 倒序)。

    用途：
      - 判断 as_of 当天是不是交易日（不是就该提示用户，而不是拿到空数据硬算）
      - 找出"昨日"是哪一天（算成交额增减、连板晋级率都要用）
    """
    df = call("tool_trade_date_hist_sina")
    col = "trade_date"
    days = [str(d) for d in df[col].tolist()]
    days = [d if "-" in d else f"{d[:4]}-{d[4:6]}-{d[6:]}" for d in days]
    past = sorted([d for d in days if d <= as_of], reverse=True)

    if not past:
        raise FetchError(f"交易日历里找不到 {as_of} 之前的交易日")

    is_trading_day = past[0] == as_of
    block = DataBlock(
        status="ok",
        rows=len(days),
        inline={
            "as_of": as_of,
            "is_trading_day": is_trading_day,
            "last_trading_day": past[0],
            "prev_trading_day": past[1] if len(past) > 1 else None,
            "recent_20": past[:20],
        },
        provenance=Provenance(
            source="akshare.tool_trade_date_hist_sina",
            fetched_at=now_iso(),
            params={},
        ),
    )
    return block, past
