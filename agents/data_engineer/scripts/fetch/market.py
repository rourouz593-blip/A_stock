"""指数行情：快照、日线、分时。对应报告章节一（市场总览）与章节二（指数复盘）。"""
from __future__ import annotations

from ..ak_client import now_iso
from .. import providers
from core.contracts import CORE_INDEXES, DataBlock, Provenance, QualityFlag


# ── 本地仓库（已收盘的日子只取一次）──────────────────────────────
# 见同一 Agent 下 scripts/store/bars.py 的模块文档。这里只做三件事：
#   ① 问仓库要不要发请求　② 发完把结果存回去　③ 仓库坏了不能拖垮复盘
_STORE_WARNED = False


def _store():
    """拿到仓库模块；任何异常都退化成"没有仓库"，绝不阻断取数。

    仓库是**优化**，不是依赖。SQLite 建不起来（只读目录、网络盘、
    磁盘满）时，正确的行为是照常联网取数，而不是让整份复盘挂掉。
    """
    global _STORE_WARNED
    try:
        from ..store import bars

        bars.connect().close()
        return bars
    except Exception as e:
        if not _STORE_WARNED:
            _STORE_WARNED = True
            print(f"[market] 本地仓库不可用，本次全部走网络：{str(e)[:100]}", flush=True)
        return None


def _want_days(as_of: str, lookback_days: int, trading_days=None):
    """这次需要哪些交易日。

    **没有交易日历就返回 None（＝不启用仓库）**——
    因为判断"缺不缺"必须按交易日算，用日期减法会把节假日当成永远的缺口，
    每次复盘都去重取，仓库反而变成新的请求放大器。
    宁可不优化，也不要错误地优化。
    """
    if not trading_days:
        return None
    past = sorted([d for d in trading_days if d <= as_of], reverse=True)
    return set(past[:lookback_days]) or None

# 日内四段（章节二要求），左闭右开
SESSIONS = [
    ("早盘", "09:30", "10:30"),
    ("上午", "10:30", "11:30"),
    ("午后", "13:00", "14:30"),
    ("尾盘", "14:30", "15:01"),
]


def _fetch(dataset: str, capability: str, *args):
    errors = []
    for name, call in providers.get(dataset, capability):
        try:
            return call(*args), name, None
        except Exception as exc:
            errors.append(f"{name}: {exc}")
    return None, None, "; ".join(errors) or f"没有配置 {dataset} provider"


def fetch_index_daily(as_of: str, lookback_days: int = 60,
                      trading_days=None) -> DataBlock:
    """四大指数日线：三只使用 Baostock，科创50 使用 AShare。

    `trading_days`：交易日历（build_dataset 会传）。给了就启用本地仓库——
    仓库里已经齐全的指数**一个请求都不发**。不给就照常全部走网络。
    """
    import pandas as pd

    start = (pd.Timestamp(as_of) - pd.Timedelta(days=lookback_days * 2)).strftime("%Y-%m-%d")
    frames, flags = [], []
    store, want = _store(), _want_days(as_of, lookback_days, trading_days)
    from_store, fresh, used = [], 0, {}
    for code, meta in CORE_INDEXES.items():
        # ① 仓库里齐了就直接用——已收盘的日线不会变，没有任何理由再取一次
        if store and want:
            try:
                if not store.missing_dates("index_daily", code, want):
                    rows = store.load("index_daily", code, min(want), max(want))
                    df = pd.DataFrame(rows)
                    df["指数代码"] = code
                    df["指数名称"] = meta["name"]
                    frames.append(df)
                    from_store.append(code)
                    fresh += int(str(df["日期"].iloc[-1]) == as_of)
                    continue
            except Exception as e:
                print(f"[market] 读仓库失败，改走网络：{str(e)[:80]}", flush=True)
        dataset = "index_daily_000688" if code == "000688" else "index_daily"
        df, provider, error = _fetch(dataset, "index_daily", code, start, as_of)
        if df is None or len(df) == 0:
            print(f"[market] {meta['name']} 日线失败：{str(error)[:120]}", flush=True)
            flags.append(QualityFlag(
                "index_hist", "error", f"{meta['name']} 日线取数失败: {error}"))
            continue
        used[code] = provider
        df = df.copy()
        if store:
            try:
                store.save("index_daily", code, df.to_dict("records"),
                           source=f"{provider}.index_daily")
            except Exception as e:
                print(f"[market] 写仓库失败（不影响本次复盘）：{str(e)[:80]}", flush=True)
        df["指数代码"] = code
        df["指数名称"] = meta["name"]
        frames.append(df)
        if str(df["日期"].iloc[-1]) != as_of:
            flags.append(
                QualityFlag(
                    "index_hist", "error",
                    f"{meta['name']} 最新日线是 {df['日期'].iloc[-1]}，不是 {as_of}；当天数据尚未发布",
                )
            )
        else:
            fresh += 1
    if not frames:
        return DataBlock(
            status="missing", rows=0,
            provenance=Provenance(
                source="configured.index_daily", fetched_at=now_iso(),
                params={"symbols": list(CORE_INDEXES), "period": "daily"},
            ),
            flags=flags,
        ), None
    all_df = pd.concat(frames, ignore_index=True)
    return DataBlock(
        status="ok" if fresh == len(CORE_INDEXES) else "degraded",
        rows=len(all_df),
        inline=_today_snapshot(all_df, as_of),
        provenance=Provenance(
            source="+".join(sorted(set(used.values()))) or "local_store",
            fetched_at=now_iso(),
            params={"symbols": list(CORE_INDEXES), "period": "daily",
                    "provider_by_symbol": used},
            unit="CNY_yuan",
            from_store=from_store or None,
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
            """NaN → None。缺失就是缺失，不能当成 0。"""
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

    注意：腾讯分时接口只保留近期数据，取历史日期可能拿不到——
    这时标 degraded 而不是编造分段走势。
    """
    import pandas as pd

    frames, flags, sessions = [], [], {}
    store, from_store, used = _store(), [], {}
    for code, meta in CORE_INDEXES.items():
        # ① 先问仓库。分时这一块的仓库价值比日线还大：
        #    腾讯只保留近期分钟线，**过了窗口就再也取不到了**。
        #    存下来不只是省请求，是让"复盘上个月某一天"这件事从不可能变成可能。
        df = None
        if store:
            try:
                got = store.load("index_intraday", code, as_of, as_of)
                if got and got[0].get("rows"):
                    import pandas as _pd

                    df = _pd.DataFrame(got[0]["rows"])
                    from_store.append(code)
            except Exception as e:
                print(f"[market] 读分时仓库失败，改走网络：{str(e)[:80]}", flush=True)
        if df is None:
            df, provider, err = _fetch("index_intraday", "index_intraday", code, as_of)
            if df is None or len(df) == 0:
                flags.append(QualityFlag(
                    "index_intraday", "warning",
                    f"{meta['name']} 分时数据取不到: {err}"))
                continue
            used[code] = provider
            # ② 存回仓库。整天的分钟线打包成一行——
            #    仓库的键是"哪一天"，不是"哪一分钟"
            if store:
                try:
                    store.save("index_intraday", code,
                               [{"日期": as_of, "rows": df.to_dict("records")}],
                               source=f"{provider}.index_intraday")
                except Exception as e:
                    print(f"[market] 写分时仓库失败（不影响本次复盘）：{str(e)[:80]}",
                          flush=True)
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
                source="configured.index_intraday", fetched_at=now_iso(), params={"date": as_of}
            ),
            flags=flags,
        ), None

    all_df = pd.concat(frames, ignore_index=True)
    return DataBlock(
        status="ok" if len(frames) == len(CORE_INDEXES) else "degraded",
        rows=len(all_df),
        inline=sessions,
        provenance=Provenance(
            source="+".join(sorted(set(used.values()))) or "local_store",
            fetched_at=now_iso(),
            params={"date": as_of, "period": "1", "provider_by_symbol": used},
            from_store=from_store or None,
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
                "amount": _nullable_sum(seg["成交额"]),
            }
        )
    return out


def _nullable_sum(values):
    """Unknown turnover stays unknown; it must never silently become zero."""
    import pandas as pd

    total = pd.to_numeric(values, errors="coerce").sum(min_count=1)
    return None if pd.isna(total) else float(total)
