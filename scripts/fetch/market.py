"""指数行情：快照、日线、分时。对应报告章节一（市场总览）与章节二（指数复盘）。"""
from __future__ import annotations

from contextlib import contextmanager

from ..ak_client import call, now_iso, try_call
from ..contracts import CORE_INDEXES, DataBlock, Provenance, QualityFlag, to_ak_date

# ── 绕开 index_code_id_map_em() ────────────────────────────────
# akshare 的 index_zh_a_hist() 在取 K 线之前，会先请求 80.push2.eastmoney.com
# 拉一份「全部指数 → 市场号」的对照表，只为了知道 000001 属于沪市还是深市。
#
# 问题是：K 线接口 push2his.eastmoney.com 在很多网络上是通的，
# 而 80.push2 这个分片主机经常连不上（超时 / reset）。
# 于是"明明数据源能连"，却卡在一个纯粹多余的前置请求上。
#
# 我们只盯四个固定指数，市场号是常数，根本不需要去问。
# 直接把那张表喂给 akshare，省掉一次请求，也去掉一个故障点。
INDEX_MARKET_ID = {"000001": 1, "399001": 0, "399006": 0, "000688": 1}  # 1=沪 0=深


@contextmanager
def _skip_index_code_map():
    try:
        from akshare.index import index_zh_em as m
    except Exception:
        yield
        return
    orig = getattr(m, "index_code_id_map_em", None)
    if orig is None:
        yield
        return
    m.index_code_id_map_em = lambda: dict(INDEX_MARKET_ID)
    try:
        yield
    finally:
        m.index_code_id_map_em = orig


def _from_sina(code: str, as_of: str, lookback_days: int):
    """备用源：新浪指数日线。

    什么时候用：东财整个不可达时。
    代价要说清楚——**新浪这个接口不返回成交额**，
    所以章节①的"两市成交额"会缺失。宁可缺一个字段并标注，也不编一个数。
    """
    import pandas as pd

    board = "sh" if INDEX_MARKET_ID.get(code) == 1 else "sz"
    df = call("stock_zh_index_daily", {"symbol": f"{board}{code}"})
    df = df.copy()
    df["日期"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    df = df[df["日期"] <= as_of].tail(lookback_days * 2)
    df = df.rename(columns={"open": "开盘", "close": "收盘", "high": "最高",
                            "low": "最低", "volume": "成交量"})
    prev = df["收盘"].shift(1)
    df["涨跌幅"] = ((df["收盘"] / prev - 1) * 100).round(2)
    df["振幅"] = ((df["最高"] - df["最低"]) / prev * 100).round(2)
    df["成交额"] = float("nan")          # 新浪不给，如实留空
    return df[["日期", "开盘", "收盘", "最高", "最低", "成交量", "成交额", "振幅", "涨跌幅"]]

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
    fallback_from = None
    for code, meta in CORE_INDEXES.items():
        try:
            with _skip_index_code_map():
                df = call(
                    "index_zh_a_hist",
                    {"symbol": code, "period": "daily",
                     "start_date": start, "end_date": to_ak_date(as_of)},
                )
        except Exception as e:
            # 东财不可达 → 退到新浪。降级必须出声，并且如实记进 provenance
            print(f"[market] 东财取 {meta['name']} 失败，改用新浪备用源：{str(e)[:120]}",
                  flush=True)
            df = _from_sina(code, as_of, lookback_days)
            fallback_from = "akshare.index_zh_a_hist"
            flags.append(QualityFlag(
                "index_hist", "warning",
                f"{meta['name']} 用了新浪备用源，**成交额缺失**——"
                f"章节①的两市成交额将无法计算"))
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
            source=("akshare.stock_zh_index_daily(新浪备用)" if fallback_from
                    else "akshare.index_zh_a_hist"),
            fetched_at=now_iso(),
            params={"symbols": list(CORE_INDEXES), "period": "daily"},
            unit="CNY_yuan",
            fallback_from=fallback_from,
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

        def _f(v):
            """NaN → None。新浪备用源不返回成交额，缺失就是缺失，不能当成 0。"""
            try:
                x = float(v)
            except (TypeError, ValueError):
                return None
            return None if x != x else x

        amt = _f(today["成交额"])
        prev_amt = _f(prev["成交额"]) if prev is not None else None
        out.append(
            {
                "code": code,
                "name": meta["name"],
                "date": str(today["日期"]),
                "open": _f(today["开盘"]),
                "close": _f(today["收盘"]),
                "high": _f(today["最高"]),
                "low": _f(today["最低"]),
                "pct_chg": _f(today["涨跌幅"]),
                "amplitude": _f(today["振幅"]),
                "amount": amt,
                "prev_close": _f(prev["收盘"]) if prev is not None else None,
                "amount_chg_pct": (round((amt / prev_amt - 1) * 100, 2)
                                   if (amt and prev_amt) else None),
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
        with _skip_index_code_map():
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
