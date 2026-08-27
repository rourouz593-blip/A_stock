"""口径统一与清洗。TODO(datasource): 依赖数据源结构，全部为空实现。

本模块的每个函数都对应一类 A 股特有的坑，实现时务必配套写测试。
"""
from __future__ import annotations

from typing import Any

from ..contracts import AdjustMode, QualityFlag


def align_to_calendar(df: Any, calendar: Any) -> tuple[Any, list[QualityFlag]]:
    """按交易日历对齐时间序列。停牌日保留为缺失，不补值。"""
    raise NotImplementedError("TODO(datasource): 实现交易日历对齐")


def unify_adjust(df: Any, factor: Any, mode: AdjustMode) -> tuple[Any, list[QualityFlag]]:
    """统一复权口径。同一个 dataset 内只允许一种口径。"""
    raise NotImplementedError("TODO(datasource): 实现复权统一")


def unify_units(df: Any, mapping: dict[str, str]) -> tuple[Any, list[QualityFlag]]:
    """金额单位统一为元。A 股财报最常见的错误来源。"""
    raise NotImplementedError("TODO(datasource): 实现单位统一")


def align_by_disclosure_date(df: Any) -> tuple[Any, list[QualityFlag]]:
    """财务数据按披露日对齐，消除前视偏差。

    示例：2025 年报在 2026-04 才披露，那么 2026-03 的分析里不得使用它。
    """
    raise NotImplementedError("TODO(datasource): 实现披露日对齐")


def detect_outliers(df: Any) -> list[QualityFlag]:
    """异常值检测，只标记不修改。修不修由人决定。"""
    raise NotImplementedError("TODO(datasource): 实现异常值检测")
