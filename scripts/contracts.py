"""数据层契约定义。

本文件是 scripts/ 的"接口说明书"：定义各类数据的返回结构。
**改这里等于改所有下游**，改之前先确认 schemas/dataset.schema.json 是否同步。

统一约定：
  - 数据源：AKShare（免费、无需 token）
  - 日期：'YYYY-MM-DD'；akshare 多数接口要 'YYYYMMDD'，用 to_ak_date() 转换
  - 金额：统一为「元」；akshare 部分接口返回万元/亿元，取回后立刻归一
  - 股票代码：内部统一 '600519.SH' 六位+后缀；akshare 多数接口只要六位，用 bare() 转换
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional

BlockStatus = Literal["ok", "degraded", "missing"]
FlagLevel = Literal["info", "warning", "error"]
RunMode = Literal["close", "premarket", "positions", "weekly"]

# 与 schemas/dataset.schema.json 的 blocks.propertyNames 保持一致
BLOCK_NAMES = (
    "calendar",      # 交易日历
    "index_spot",    # 四大指数快照（开收高低、涨跌幅、成交额）
    "index_intraday",# 指数分时（用于早盘/上午/午后/尾盘拆解）
    "index_hist",    # 指数日线（支撑压力、量能对比）
    "breadth",       # 涨跌家数、涨停跌停、炸板率、连板晋级率
    "limit_pool",    # 涨停/跌停/炸板/昨日涨停 四个池子明细
    "sectors",       # 行业与概念板块行情
    "sector_flow",   # 板块资金流
    "holdings",      # 我的持仓个股行情
    "news",          # 财联社电报等新闻
    "announcements", # 交易所公告
    "northbound",    # 北向资金
)

# 本系统固定盯的四个指数（章节一要求）
CORE_INDEXES = {
    "000001": {"name": "上证指数", "board": "sh"},
    "399001": {"name": "深证成指", "board": "sz"},
    "399006": {"name": "创业板指", "board": "cyb"},
    "000688": {"name": "科创50",  "board": "kc"},
}


@dataclass
class Provenance:
    """数据出处。每一份取回来的数据都必须带上，否则报告不可追溯。"""

    source: str                                   # 如 "akshare.stock_zh_index_spot_em"
    fetched_at: str                               # ISO8601
    params: dict[str, Any] = field(default_factory=dict)
    unit: Optional[str] = None                    # 如 "CNY_yuan"
    fallback_from: Optional[str] = None
    field_mapping: dict[str, str] = field(default_factory=dict)


@dataclass
class QualityFlag:
    """数据质量问题。宁可多标，不可漏标。"""

    block: str
    level: FlagLevel
    message: str
    affected_range: Optional[str] = None


@dataclass
class DataBlock:
    """一类数据的取回结果，对应 dataset.json 里的一个 block。"""

    status: BlockStatus
    provenance: Provenance
    rows: Optional[int] = None
    path: Optional[str] = None       # 明细落盘的 CSV 相对路径
    inline: Any = None               # 小体量数据直接内联进 dataset.json
    flags: list[QualityFlag] = field(default_factory=list)

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "status": self.status,
            "provenance": {
                "source": self.provenance.source,
                "fetched_at": self.provenance.fetched_at,
                "params": self.provenance.params,
                "unit": self.provenance.unit,
                "fallback_from": self.provenance.fallback_from,
            },
        }
        if self.rows is not None:
            d["rows"] = self.rows
        if self.path:
            d["path"] = self.path
        if self.inline is not None:
            d["inline"] = self.inline
        return d


# ── 小工具 ──────────────────────────────────────────────────────
def bare(code: str) -> str:
    """'600519.SH' -> '600519'；akshare 多数接口只认六位码。"""
    return code.split(".")[0]


def suffixed(code: str) -> str:
    """'600519' -> '600519.SH'；按首位数字推断交易所。"""
    if "." in code:
        return code
    if code.startswith(("60", "68", "9", "5")):
        return f"{code}.SH"
    if code.startswith(("00", "30", "20", "1")):
        return f"{code}.SZ"
    if code.startswith(("8", "4")):
        return f"{code}.BJ"
    return f"{code}.SZ"


def to_ak_date(date: str) -> str:
    """'2026-08-28' -> '20260828'。"""
    return date.replace("-", "")
