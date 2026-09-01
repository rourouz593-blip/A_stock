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

# ── 本地仓库（已收盘的日子只取一次）──────────────────────────────
# 见 scripts/store/bars.py 的模块文档。这里只做三件事：
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


def fetch_index_daily(as_of: str, lookback_days: int = 60,
                      trading_days=None) -> DataBlock:
    """四大指数的日线。开收高低涨跌幅成交额全部来自这里（收盘后的权威口径）。

    `trading_days`：交易日历（build_dataset 会传）。给了就启用本地仓库——
    仓库里已经齐全的指数**一个请求都不发**。不给就照常全部走网络。
    """
    import pandas as pd

    start = (pd.Timestamp(as_of) - pd.Timedelta(days=lookback_days * 2)).strftime("%Y%m%d")
    frames, flags = [], []
    fallback_from = None
    store, want = _store(), _want_days(as_of, lookback_days, trading_days)
    from_store = []
    for code, meta in CORE_INDEXES.items():
        degraded = None
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
                    continue
            except Exception as e:
                print(f"[market] 读仓库失败，改走网络：{str(e)[:80]}", flush=True)
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
            fallback_from = degraded = "akshare.index_zh_a_hist"
            flags.append(QualityFlag(
                "index_hist", "warning",
                f"{meta['name']} 用了新浪备用源，**成交额缺失**——"
                f"章节①的两市成交额将无法计算"))
        df = df.copy()
        # ② 存回仓库。未收盘的当天会被 bars.save 自己挡掉，这里不用判断。
        #
        # **降级源的数据不入库**：新浪那条路没有成交额，一旦存进去，
        # 以后每次都会命中仓库、再也不会回头去问东财，
        # 于是"某天临时降级"被永久固化成了"那天就是没有成交额"。
        # 缺一次可以补，存错了不会自己好。
        if store and not degraded:
            try:
                store.save("index_daily", code, df.to_dict("records"),
                           source="akshare.index_zh_a_hist" if not fallback_from
                           else "akshare.stock_zh_index_daily")
            except Exception as e:
                print(f"[market] 写仓库失败（不影响本次复盘）：{str(e)[:80]}", flush=True)
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
    store, from_store = _store(), []
    for code, meta in CORE_INDEXES.items():
        # ① 先问仓库。分时这一块的仓库价值比日线还大：
        #    东财只保留最近几个交易日，**过了窗口就再也取不到了**。
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
                flags.append(QualityFlag(
                    "index_intraday", "warning",
                    f"{meta['name']} 分时数据取不到: {err}"))
                continue
            # ② 存回仓库。整天的分钟线打包成一行——
            #    仓库的键是"哪一天"，不是"哪一分钟"
            if store:
                try:
                    store.save("index_intraday", code,
                               [{"日期": as_of, "rows": df.to_dict("records")}],
                               source="akshare.index_zh_a_hist_min_em")
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
                "amount": float(seg["成交额"].sum()),
            }
        )
    return out
