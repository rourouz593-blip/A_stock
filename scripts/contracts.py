"""数据层契约定义。

本文件是 scripts/ 的"接口说明书"：定义各类数据的返回结构。
**改这里等于改所有下游**，改之前先确认 schemas/dataset.schema.json 是否同步。

约定：
  - 所有金额统一为「元」(CNY_yuan)，在 Provenance.unit 中声明
  - 所有日期为 'YYYY-MM-DD' 字符串，时间戳为 ISO8601
  - 财务数据以「披露日」对齐，避免前视偏差（look-ahead bias）
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional

AdjustMode = Literal["qfq", "hfq", "none"]
BlockStatus = Literal["ok", "degraded", "missing"]
FlagLevel = Literal["info", "warning", "error"]


@dataclass
class Provenance:
    """数据出处。每一份取回来的数据都必须带上，否则报告不可追溯。"""

    source: str                                   # 实际使用的数据源标识
    fetched_at: str                               # ISO8601
    fallback_from: Optional[str] = None           # 若降级换源，记录原源
    field_mapping: dict[str, str] = field(default_factory=dict)  # 原始字段 -> 本项目字段
    unit: Optional[str] = None                    # 如 "CNY_yuan"
    params: dict[str, Any] = field(default_factory=dict)  # 请求参数，便于复现


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
    coverage: Optional[dict[str, str]] = None     # {"start": ..., "end": ...}
    path: Optional[str] = None                    # 大体量数据落盘路径
    inline: Any = None                            # 小体量数据直接内联
    flags: list[QualityFlag] = field(default_factory=list)


@dataclass
class FetchRequest:
    """取数请求的统一入参。"""

    codes: list[str]                              # 形如 ["600519.SH"]
    start: Optional[str] = None
    end: Optional[str] = None
    extra: dict[str, Any] = field(default_factory=dict)


# ── 数据类别枚举 ────────────────────────────────────────────────
# 与 schemas/dataset.schema.json 的 blocks.propertyNames 保持一致
BLOCK_NAMES = (
    "ohlcv",          # 行情
    "financials",     # 财务报表
    "valuation",      # 估值指标
    "industry",       # 行业分类与同业
    "announcements",  # 交易所公告
    "news",           # 新闻
    "moneyflow",      # 资金流（北向、龙虎榜、两融）
    "social",         # 社交舆情
)
