"""指数行情：快照、日线、分时。对应报告章节一（市场总览）与章节二（指数复盘）。"""
from __future__ import annotations

from ..ak_client import call, now_iso, try_call
from ..contracts import CORE_INDEXES, DataBlock, Provenance, QualityFlag, to_ak_date

# 日内四段（章节二要求），左闭右开
SESSIONS = [
    ("早盘", "09:30", "10:30"),
    ("上午", "10:30", "11:30"),
    ("午后", "13:00", "14:30"),
    ("尾盘", "14:30", "15:01"),
]


def fetch_index_daily(as_of: str, lookback_days: int = 60) -> DataBlock:
    """四大指数的日线。开收高低涨跌幅成交额全部来自这里（收盘后的权威口径）。"""
    import pandas as pd

    start = (pd.Timestamp(as_of) - pd.Timedelta(days=lookback_days * 2)).strftime("%Y%m%d")
    frames, flags = [], []
    for code, meta in CORE_INDEXES.items():
        df = call(
            "index_zh_a_hist",
            {"symbol": code, "period": "daily", "start_date": start, "end_date": to_ak_date(as_of)},
        )
        df = df.copy()
        df["指数代码"] = code
        df["指数名称"] = meta["name"]
        frames.append(df)
        if str(df["日期"].iloc[-1]) != as_of:
            flags.append(
                QualityFlag(
                    "index_hist",
                    "warning",
                    f"{meta['name']} 最新日线是 {df['日期'].iloc[-1]}，不是 {as_of}（可能非交易日或数据未更新）",
                )
            )
    all_df = pd.concat(frames, ignore_index=True)
    return DataBlock(
        status="ok",
        rows=len(all_df),
        inline=_today_snapshot(all_df, as_of),
        provenance=Provenance(
            source="akshare.index_zh_a_hist",
            fetched_at=now_iso(),
            params={"symbols": list(CORE_INDEXES), "period": "daily"},
            unit="CNY_yuan",
        ),
        flags=flags,
    ), all_df


def _today_snapshot(all_df, as_of: str) -> list[dict]:
    """抽出 as_of 当日与前一交易日，算出成交额环比——章节一直接用这份。"""
    out = []
    for code, meta in CORE_INDEXES.items():
        sub = all_df[all_df["指数代码"] == code].sort_values("日期")
        if sub.empty:
            continue
        today = sub.iloc[-1]
        prev = sub.iloc[-2] if len(sub) > 1 else None
        amt = float(today["成交额"])
        prev_amt = float(prev["成交额"]) if prev is not None else None
        out.append(
            {
                "code": code,
                "name": meta["name"],
                "date": str(today["日期"]),
                "open": float(today["开盘"]),
                "close": float(today["收盘"]),
                "high": float(today["最高"]),
                "low": float(today["最低"]),
                "pct_chg": float(today["涨跌幅"]),
                "amplitude": float(today["振幅"]),
                "amount": amt,
                "prev_close": float(prev["收盘"]) if prev is not None else None,
                "amount_chg_pct": round((amt / prev_amt - 1) * 100, 2) if prev_amt else None,
            }
        )
    return out


def fetch_index_intraday(as_of: str) -> DataBlock:
    """四大指数的分钟线，用于把走势拆成早盘/上午/午后/尾盘四段。

    注意：东财分时接口只保留最近几个交易日，取历史日期会拿不到——
    这时标 degraded 而不是编造分段走势。
    """
    import pandas as pd

    frames, flags, sessions = [], [], {}
    for code, meta in CORE_INDEXES.items():
        df, err = try_call(
            "index_zh_a_hist_min_em",
            {
                "symbol": code,
                "period": "1",
                "start_date": f"{as_of} 09:15:00",
                "end_date": f"{as_of} 15:05:00",
            },
        )
        if df is None or len(df) == 0:
            flags.append(QualityFlag("index_intraday", "warning", f"{meta['name']} 分时数据取不到: {err}"))
            continue
        df = df.copy()
        df["指数代码"] = code
        df["指数名称"] = meta["name"]
        frames.append(df)
        sessions[code] = _split_sessions(df, meta["name"])

    if not frames:
        return DataBlock(
            status="missing",
            rows=0,
            provenance=Provenance(
                source="akshare.index_zh_a_hist_min_em", fetched_at=now_iso(), params={"date": as_of}
            ),
            flags=flags,
        ), None

    all_df = pd.concat(frames, ignore_index=True)
    return DataBlock(
        status="ok" if len(frames) == len(CORE_INDEXES) else "degraded",
        rows=len(all_df),
        inline=sessions,
        provenance=Provenance(
            source="akshare.index_zh_a_hist_min_em",
            fetched_at=now_iso(),
            params={"date": as_of, "period": "1"},
        ),
        flags=flags,
    ), all_df


def _split_sessions(df, name: str) -> dict:
    """把一天的分钟线切成四段，每段给出起止点位与涨跌——章节二的原料。"""
    times = df["时间"].astype(str)
    out = {"name": name, "sessions": []}
    for label, start, end in SESSIONS:
        mask = (times.str[11:16] >= start) & (times.str[11:16] < end)
        seg = df[mask]
        if seg.empty:
            continue
        first, last = float(seg["收盘"].iloc[0]), float(seg["收盘"].iloc[-1])
        out["sessions"].append(
            {
                "session": label,
                "start": start,
                "end": end,
                "open": first,
                "close": last,
                "high": float(seg["最高"].max()),
                "low": float(seg["最低"].min()),
                "pct_chg_in_session": round((last / first - 1) * 100, 2) if first else None,
                "amount": float(seg["成交额"].sum()),
            }
        )
    return out
