"""行情数据取数。TODO(datasource): 数据源未确定，全部为空实现。"""
from __future__ import annotations

from ..contracts import AdjustMode, DataBlock, FetchRequest


def fetch_ohlcv(req: FetchRequest, freq: str = "daily", adjust: AdjustMode = "qfq") -> DataBlock:
    """取日线/周线/分钟线行情。

    要求实现时注意：
      1. 复权口径必须与入参一致，并写进 Provenance
      2. 停牌日不得补 0 或前值；按交易日历跳过，并在 flags 里标注缺口
      3. 成交额单位统一为元
      4. 新股上市不足 lookback 时返回 status='degraded' 而不是静默截断

    Returns: DataBlock(status, rows, coverage, path, provenance, flags)
    """
    raise NotImplementedError("TODO(datasource): 实现行情取数")


def fetch_trading_calendar(start: str, end: str) -> DataBlock:
    """取交易日历。所有时间序列对齐都依赖它，务必先实现这个。"""
    raise NotImplementedError("TODO(datasource): 实现交易日历取数")


def fetch_adjust_factor(req: FetchRequest) -> DataBlock:
    """取复权因子。自行复权时需要；若数据源直接给复权价可跳过。"""
    raise NotImplementedError("TODO(datasource): 实现复权因子取数")
