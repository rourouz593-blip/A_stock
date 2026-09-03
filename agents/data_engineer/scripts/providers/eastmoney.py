"""东财（经 akshare）。保留为 provider 之一，不再是唯一。

这一层很薄——它只是把原有的取数方式包成 provider 接口，
好让"换源"变成改配置而不是改代码。

**它是逐个拉的**：批量快照要 N 个请求。所以在 `datasources.yaml` 里
它排在腾讯后面，只在腾讯拿不到时兜底。
"""
from __future__ import annotations

from typing import Iterable

from ..ak_client import try_call
from core.contracts import bare


def spot(codes: Iterable[str], *, timeout: float = 10.0) -> dict:
    """逐个拉快照。**每只一个请求**——这正是要尽量避免的形态。"""
    out = {}
    for code in codes:
        df, _err = try_call("stock_bid_ask_em", {"symbol": bare(code)})
        if df is None or len(df) == 0:
            continue
        kv = dict(zip(df.iloc[:, 0], df.iloc[:, 1]))

        def _f(*names):
            for n in names:
                if n in kv and kv[n] not in ("", None):
                    try:
                        return float(kv[n])
                    except (TypeError, ValueError):
                        return None
            return None

        out[str(code)] = {
            "code": str(code), "name": str(kv.get("名称", "")),
            "price": _f("最新"), "last_close": _f("昨收"), "open": _f("今开"),
            "high": _f("最高"), "low": _f("最低"), "pct_chg": _f("涨幅"),
            "amount": _f("金额"), "turnover_rate": _f("换手"),
            "limit_up": _f("涨停"), "limit_down": _f("跌停"),
            "is_stale": False,
        }
    return out
