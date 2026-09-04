"""Sina-backed industry and concept sector rankings."""
from __future__ import annotations


INDICATORS = {"industry": "新浪行业", "concept": "概念"}


def sector_rankings(kind: str):
    """Return one full sector ranking in the pipeline column contract."""
    from ..ak_client import try_call

    try:
        indicator = INDICATORS[kind]
    except KeyError as exc:
        raise ValueError(f"unsupported sector kind: {kind}") from exc

    frame, error = try_call("stock_sector_spot", {"indicator": indicator})
    if frame is None or frame.empty:
        raise RuntimeError(error or f"Sina returned no {kind} sector rankings")
    return frame.rename(columns={
        "label": "板块代码",
        "板块": "板块名称",
        "股票名称": "领涨股票",
    })
