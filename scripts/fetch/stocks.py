"""个股行情：持仓股与题材龙头的快照、日线、资金流。对应报告章节四。"""
from __future__ import annotations

from ..ak_client import now_iso, try_call
from ..contracts import DataBlock, Provenance, QualityFlag, bare, to_ak_date


def fetch_holdings_quotes(codes: list[str], as_of: str, lookback_days: int = 90) -> tuple[DataBlock, dict]:
    """取持仓股的日线（前复权）与最新一日快照。

    复权口径固定 qfq：短线复盘看的是"我实际经历的价格路径"，
    前复权能保证均线与形态和看盘软件一致。口径写进 provenance。
    """
    import pandas as pd

    if not codes:
        return DataBlock(
            status="missing",
            rows=0,
            inline=[],
            provenance=Provenance(source="akshare.stock_zh_a_hist", fetched_at=now_iso(), params={}),
            flags=[QualityFlag("holdings", "info", "positions.yaml 里没有持仓，章节四将为空")],
        ), {}

    start = (pd.Timestamp(as_of) - pd.Timedelta(days=lookback_days * 2)).strftime("%Y%m%d")
    flags, frames, inline = [], {}, []
    for code in codes:
        df, err = try_call(
            "stock_zh_a_hist",
            {
                "symbol": bare(code),
                "period": "daily",
                "start_date": start,
                "end_date": to_ak_date(as_of),
                "adjust": "qfq",
            },
        )
        if df is None or len(df) == 0:
            flags.append(QualityFlag("holdings", "error", f"{code} 日线取不到: {err}"))
            continue
        frames[code] = df
        last = df.iloc[-1]
        inline.append(
            {
                "code": code,
                "date": str(last["日期"]),
                "open": float(last["开盘"]),
                "close": float(last["收盘"]),
                "high": float(last["最高"]),
                "low": float(last["最低"]),
                "pct_chg": float(last["涨跌幅"]),
                "amplitude": float(last.get("振幅", 0) or 0),
                "turnover_rate": float(last.get("换手率", 0) or 0),
                "amount": float(last["成交额"]),
                "ma5": round(float(df["收盘"].tail(5).mean()), 2),
                "ma10": round(float(df["收盘"].tail(10).mean()), 2),
                "ma20": round(float(df["收盘"].tail(20).mean()), 2),
                "high_20d": round(float(df["最高"].tail(20).max()), 2),
                "low_20d": round(float(df["最低"].tail(20).min()), 2),
                "vol_ratio_5d": round(
                    float(last["成交量"]) / max(float(df["成交量"].tail(6).head(5).mean()), 1e-9), 2
                ),
                "stale": str(last["日期"]) != as_of,
            }
        )
        if str(last["日期"]) != as_of:
            flags.append(
                QualityFlag("holdings", "warning", f"{code} 最新日线为 {last['日期']}，可能停牌或数据未更新")
            )

    return DataBlock(
        status="ok" if len(frames) == len(codes) else ("degraded" if frames else "missing"),
        rows=sum(len(v) for v in frames.values()),
        inline=inline,
        provenance=Provenance(
            source="akshare.stock_zh_a_hist",
            fetched_at=now_iso(),
            params={"adjust": "qfq", "codes": codes, "end_date": as_of},
            unit="CNY_yuan",
        ),
        flags=flags,
    ), frames


def fetch_northbound() -> DataBlock:
    """北向资金汇总。可选数据块，缺了不阻塞。"""
    df, err = try_call("stock_hsgt_fund_flow_summary_em")
    if df is None:
        return DataBlock(
            status="missing",
            rows=0,
            provenance=Provenance(source="akshare.stock_hsgt_fund_flow_summary_em", fetched_at=now_iso()),
            flags=[QualityFlag("northbound", "info", f"北向资金取不到（沪深港通数据披露规则已多次调整）: {err}")],
        )
    return DataBlock(
        status="ok",
        rows=len(df),
        inline=df.head(20).to_dict("records"),
        provenance=Provenance(
            source="akshare.stock_hsgt_fund_flow_summary_em", fetched_at=now_iso(), unit="CNY_yuan"
        ),
    )
