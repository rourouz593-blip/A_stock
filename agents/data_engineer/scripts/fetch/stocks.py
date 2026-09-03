"""个股行情：持仓股与题材龙头的快照、日线、资金流。对应报告章节四。"""
from __future__ import annotations

from ..ak_client import now_iso, try_call
from core.contracts import DataBlock, Provenance, QualityFlag, bare, to_ak_date

# ── 持仓日线：仓库优先 + 批量快照 ────────────────────────────────
# 改造前：**每只持仓一个东财请求**。10 只持仓 = 10 个东财请求，每天如此。
# a-stock-data 的防封铁律把这种形态点名为被封的头号元凶：
#   「批量场景 AI 跑循环逐个拉，是被封的头号元凶」
#
# 改造后分两半：
#   历史（90 个交易日）→ 本地仓库，只有缺的那几天才联网
#   当日快照          → 腾讯**一个请求拿全部持仓**（不封 IP）
# 稳态下东财请求数从 N 降到 0。


def _store():
    """仓库不可用时返回 None，照常联网。它是优化，不是依赖。"""
    try:
        from ..store import bars

        bars.connect().close()
        return bars
    except Exception:
        return None


def _qfq_drift(stored: list, fresh, date_key: str = "日期") -> bool:
    """前复权历史是否已经被改写。

    这是**指数可以永久缓存、个股不行**的原因：qfq 是以最新价为基准倒推的，
    标的一旦除权除息，**全部历史价格都会变**。仓库里那份就成了过期数据，
    而且不会报错——它只是安静地和现在的口径对不上。

    自愈办法：拿新取到的重叠日期和仓库里的比一比，对不上就把这只票的
    存量整个作废重取。比"永不复用"省，比"无脑复用"对。
    """
    if stored is None or fresh is None or len(fresh) == 0:
        return False
    by_date = {str(r.get(date_key))[:10]: r for r in stored}
    checked = 0
    for _, row in fresh.tail(5).iterrows():
        old = by_date.get(str(row.get(date_key))[:10])
        if not old:
            continue
        a, b = old.get("收盘"), row.get("收盘")
        if a is None or b is None:
            continue
        checked += 1
        if abs(float(a) - float(b)) > max(0.01, abs(float(b)) * 0.001):
            return True
    return False


def fetch_holdings_quotes(codes: list[str], as_of: str, lookback_days: int = 90,
                          trading_days=None) -> tuple[DataBlock, dict]:
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
    store = _store()
    from_store, drifted = [], []

    # ① 当日快照：一个请求拿全部持仓（腾讯批量），失败再退回东财逐个拉
    from ..providers import get as _providers

    snap, snap_source = {}, None
    for pname, fn in _providers("spot", "spot"):
        try:
            snap = fn(codes)
        except Exception as e:
            flags.append(QualityFlag("holdings", "info", f"{pname} 快照失败：{str(e)[:80]}"))
            continue
        if snap:
            snap_source = pname
            break
    for c, q in snap.items():
        # 僵尸报价：停牌 / 废码也会返回一份定格在最后交易日的价格且不报错。
        # 标出来，绝不当成当日真实成交。
        if q.get("is_stale"):
            flags.append(QualityFlag(
                "holdings", "warning",
                f"{c} 快照疑似停牌/无成交（成交额 0 且现价==昨收），不作为当日价格使用"))

    # ② 历史：仓库优先，只补缺的交易日
    want = None
    if store and trading_days:
        want = set(sorted([d for d in trading_days if d <= as_of], reverse=True)[:lookback_days])

    for code in codes:
        df = None
        stored = None
        if store and want:
            try:
                stored = store.load("stock_daily_qfq", bare(code), min(want), max(want))
                if stored and not (want - {str(r["日期"])[:10] for r in stored}):
                    df = pd.DataFrame(stored)
                    from_store.append(code)
            except Exception:
                stored = None
        if df is None:
            raw, err = try_call(
                "stock_zh_a_hist",
                {
                    "symbol": bare(code),
                    "period": "daily",
                    "start_date": start,
                    "end_date": to_ak_date(as_of),
                    "adjust": "qfq",
                },
            )
            if raw is None or len(raw) == 0:
                flags.append(QualityFlag("holdings", "error", f"{code} 日线取不到: {err}"))
                continue
            df = raw
            if store:
                try:
                    # 前复权历史会被除权改写：新旧对不上就把这只票的存量整个作废，
                    # 否则仓库会安静地一直喂过期口径
                    if _qfq_drift(stored, raw):
                        drifted.append(code)
                        with store.connect() as conn:
                            conn.execute("DELETE FROM bars WHERE dataset=? AND symbol=?",
                                         ("stock_daily_qfq", bare(code)))
                            conn.commit()
                        flags.append(QualityFlag(
                            "holdings", "info",
                            f"{code} 前复权历史已变（多半是除权除息），仓库存量已作废重取"))
                    store.save("stock_daily_qfq", bare(code), raw.to_dict("records"),
                               source="akshare.stock_zh_a_hist(qfq)")
                except Exception as e:
                    print(f"[stocks] 写仓库失败（不影响本次复盘）：{str(e)[:80]}", flush=True)
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
            params={"adjust": "qfq", "codes": codes, "end_date": as_of,
                    "spot_provider": snap_source, "qfq_refetched": drifted or None},
            unit="CNY_yuan",
            from_store=from_store or None,
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
