"""板块与题材：行业板块、概念板块、板块资金流、成分股。对应报告章节三。

**警告**：本模块只负责把数据取回来。
"哪个是主线""龙头是谁"是 sector-analyst 的判断，不在这里写死。
"""
from __future__ import annotations

from ..ak_client import now_iso, try_call
from core.contracts import DataBlock, Provenance, QualityFlag


def fetch_sectors(top_n: int = 25) -> tuple[DataBlock, dict]:
    """取行业板块与概念板块行情，按涨跌幅排序。

    返回的 inline 只含前 top_n，明细全量落 CSV——
    因为 sector-analyst 需要能回查"涨幅榜之外"的板块（章节三明确要求不能只看涨幅榜）。
    """
    flags: list[QualityFlag] = []
    frames: dict = {}
    inline: dict = {}

    for key, fn, label in [
        ("industry", "stock_board_industry_name_em", "行业板块"),
        ("concept", "stock_board_concept_name_em", "概念板块"),
    ]:
        df, err = try_call(fn)
        if df is None:
            flags.append(QualityFlag("sectors", "warning", f"{label}取不到: {err}"))
            continue
        frames[key] = df
        inline[key] = _top(df, top_n)

    status = "ok" if len(frames) == 2 else ("degraded" if frames else "missing")
    block = DataBlock(
        status=status,
        rows=sum(len(v) for v in frames.values()),
        inline=inline,
        provenance=Provenance(
            source="akshare.stock_board_industry_name_em + stock_board_concept_name_em",
            fetched_at=now_iso(),
            params={"top_n": top_n},
        ),
        flags=flags,
    )
    return block, frames


def _top(df, n: int) -> list[dict]:
    import pandas as pd

    d = df.copy()
    if "涨跌幅" in d.columns:
        d["涨跌幅"] = pd.to_numeric(d["涨跌幅"], errors="coerce")
        d = d.sort_values("涨跌幅", ascending=False)
    keep = ["板块名称", "板块代码", "涨跌幅", "换手率", "上涨家数", "下跌家数", "领涨股票", "总市值"]
    cols = [c for c in keep if c in d.columns]
    return d.head(n)[cols].to_dict("records")


def fetch_sector_flow() -> DataBlock:
    """板块资金流。判断"是不是真有资金在做"的硬证据，比涨幅榜可信。"""
    flags: list[QualityFlag] = []
    inline: dict = {}
    for key, sector_type, label in [
        ("industry", "行业资金流", "行业"),
        ("concept", "概念资金流", "概念"),
    ]:
        df, err = try_call(
            "stock_sector_fund_flow_rank",
            {"indicator": "今日", "sector_type": sector_type},
        )
        if df is None:
            flags.append(QualityFlag("sector_flow", "warning", f"{label}资金流取不到: {err}"))
            continue
        cols = [c for c in df.columns if c in ("名称", "今日涨跌幅", "今日主力净流入-净额", "今日主力净流入-净占比")]
        inline[key] = df.head(20)[cols].to_dict("records") if cols else df.head(20).to_dict("records")

    return DataBlock(
        status="ok" if len(inline) == 2 else ("degraded" if inline else "missing"),
        rows=sum(len(v) for v in inline.values()),
        inline=inline,
        provenance=Provenance(
            source="akshare.stock_sector_fund_flow_rank",
            fetched_at=now_iso(),
            params={"indicator": "今日"},
            unit="CNY_yuan",
        ),
        flags=flags,
    )


def fetch_board_constituents(board_names: list[str], kind: str = "concept") -> dict:
    """取指定板块的成分股，用于判断梯队与联动性（章节三"核心带动性"）。

    只在 sector-analyst 明确点名了几个板块之后才调用——
    全市场板块成分一次拉完既慢又没必要。
    """
    fn = "stock_board_concept_cons_em" if kind == "concept" else "stock_board_industry_cons_em"
    out = {}
    for name in board_names:
        df, err = try_call(fn, {"symbol": name})
        out[name] = df if df is not None else None
    return out
