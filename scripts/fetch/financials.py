"""财务与估值数据取数。TODO(datasource): 数据源未确定，全部为空实现。"""
from __future__ import annotations

from ..contracts import DataBlock, FetchRequest


def fetch_statements(req: FetchRequest, statements: list[str] | None = None) -> DataBlock:
    """取三大报表。statements 默认 ['income', 'balance', 'cashflow']。

    要求实现时注意：
      1. **必须同时返回 report_period（报告期）与 ann_date（披露日）**，
         下游按披露日对齐，否则产生前视偏差
      2. 区分合并报表与母公司报表，默认合并，并在 Provenance 中声明
      3. 金额单位统一为元（部分源返回万元）
      4. 追溯调整（重述）的历史数据要标 flag
    """
    raise NotImplementedError("TODO(datasource): 实现财报取数")


def fetch_valuation(req: FetchRequest) -> DataBlock:
    """取每日估值指标：PE_TTM / PB / PS / 股息率 / 总市值 / 流通市值。

    注意亏损股 PE 为负或空值，不要用 0 代替。
    """
    raise NotImplementedError("TODO(datasource): 实现估值取数")


def fetch_industry(req: FetchRequest, standard: str = "sw") -> DataBlock:
    """取行业分类与同业列表。standard: sw(申万) / csi(中证) / csrc(证监会)。

    TODO(strategy): 行业分类标准的选择会直接影响"同业对比"的结论，需确认。
    """
    raise NotImplementedError("TODO(datasource): 实现行业分类取数")
