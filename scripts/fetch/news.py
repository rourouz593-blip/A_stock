"""公告、新闻、舆情与资金流取数。TODO(datasource): 数据源未确定，全部为空实现。"""
from __future__ import annotations

from ..contracts import DataBlock, FetchRequest


def fetch_announcements(req: FetchRequest) -> DataBlock:
    """取交易所公告（T1 级信源，可信度最高）。

    每条必须含：ann_date、title、type、url、关联股票代码。
    """
    raise NotImplementedError("TODO(datasource): 实现公告取数")


def fetch_news(req: FetchRequest, sources: list[str] | None = None) -> DataBlock:
    """取财经新闻。

    要求实现时注意：
      1. 每条必须带 source_tier（T1-T4）与 timestamp，否则下游无法加权
      2. 转载去重在 clean/ 层做，本层只负责如实取回
      3. 无法确定来源层级的条目标 T4，不要猜高
    """
    raise NotImplementedError("TODO(datasource): 实现新闻取数")


def fetch_social(req: FetchRequest) -> DataBlock:
    """取社交平台舆情（股吧、雪球等，T4 级信源，噪音为主）。"""
    raise NotImplementedError("TODO(datasource): 实现舆情取数")


def fetch_moneyflow(req: FetchRequest) -> DataBlock:
    """取资金流：北向持股、龙虎榜、融资融券余额。

    资金流是情绪面里最"硬"的证据，与舆情背离时价值最高。
    """
    raise NotImplementedError("TODO(datasource): 实现资金流取数")
