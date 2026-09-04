"""板块与题材：行业板块、概念板块、板块资金流、成分股。对应报告章节三。

**警告**：本模块只负责把数据取回来。
"哪个是主线""龙头是谁"是 sector-analyst 的判断，不在这里写死。
"""
from __future__ import annotations

from .. import providers
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

    sources: list[str] = []
    for key, label in [("industry", "行业板块"), ("concept", "概念板块")]:
        df = None
        errors = []
        source = None
        for provider_name, fetch in providers.get("sectors", "sector_rankings"):
            try:
                df = fetch(key)
                source = provider_name
                break
            except Exception as exc:
                errors.append(f"{provider_name}: {exc}")
        if df is None:
            reason = "; ".join(errors) or "未配置可用 provider"
            flags.append(QualityFlag("sectors", "warning", f"{label}取不到: {reason}"))
            continue
        sources.append(source or "unknown")
        frames[key] = df
        inline[key] = _top(df, top_n)

    status = "ok" if len(frames) == 2 else ("degraded" if frames else "missing")
    block = DataBlock(
        status=status,
        rows=sum(len(v) for v in frames.values()),
        inline=inline,
        provenance=Provenance(
            source=" + ".join(dict.fromkeys(sources)) or "none",
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
    keep = [
        "板块名称", "板块代码", "涨跌幅", "换手率", "上涨家数", "下跌家数",
        "领涨股票", "总市值", "总成交量", "总成交额",
    ]
    cols = [c for c in keep if c in d.columns]
    return d.head(n)[cols].to_dict("records")


def fetch_sector_flow() -> DataBlock:
    """板块资金流。判断“是不是真有资金在做”的硬证据，比涨幅榜可信。"""
    # 新浪板块行情只有成交额，没有“主力净流入”的等价口径。宁可缺失，
    # 也不能把成交额冒充资金流，或静默回退到会封 IP 的 Eastmoney。
    return DataBlock(
        status="missing",
        rows=0,
        inline={},
        provenance=Provenance(
            source="none",
            fetched_at=now_iso(),
            params={},
            unit="CNY_yuan",
        ),
        flags=[QualityFlag(
            "sector_flow",
            "warning",
            "未配置独立且口径等价的板块主力资金流数据源；已禁用 Eastmoney 请求",
        )],
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
