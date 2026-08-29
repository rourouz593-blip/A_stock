"""市场宽度与涨停生态：涨跌家数、涨停跌停、炸板率、连板晋级率。

对应报告章节一。这一块是短线情绪判断的核心原料，
**炸板率与晋级率必须由明细算出来，不能凭感觉写**。
"""
from __future__ import annotations

from ..ak_client import now_iso, try_call
from ..contracts import DataBlock, Provenance, QualityFlag, to_ak_date


def fetch_breadth(as_of: str, prev_trading_day: str | None) -> tuple[DataBlock, dict]:
    """返回 (DataBlock, 四个涨停池的明细 DataFrame 字典)。

    数据来源与口径：
      - 涨跌家数        akshare.stock_market_activity_legu（乐咕乐股，实时快照）
      - 涨停池          akshare.stock_zt_pool_em          （含"连板数"）
      - 炸板池          akshare.stock_zt_pool_zbgc_em     （仅最近 30 个交易日）
      - 跌停池          akshare.stock_zt_pool_dtgc_em     （仅最近 30 个交易日）
      - 昨日涨停池      akshare.stock_zt_pool_previous_em （算晋级率用）

    炸板率  = 炸板家数 / (涨停家数 + 炸板家数)
    晋级率  = 昨日涨停股中今日仍涨停的家数 / 昨日涨停家数
    """
    d = to_ak_date(as_of)
    flags: list[QualityFlag] = []
    pools: dict = {}
    inline: dict = {"as_of": as_of}

    # ── 涨跌家数 ────────────────────────────────────────────────
    act, err = try_call("stock_market_activity_legu")
    if act is not None:
        kv = {str(r["item"]).strip(): r["value"] for _, r in act.iterrows()}
        inline["advance_decline"] = {
            "up": _num(kv.get("上涨")),
            "down": _num(kv.get("下跌")),
            "flat": _num(kv.get("平盘")),
            "limit_up_legu": _num(kv.get("涨停")),
            "limit_down_legu": _num(kv.get("跌停")),
            "suspended": _num(kv.get("停牌")),
            "activity": kv.get("活跃度"),
            "snapshot_time": kv.get("统计日期") or kv.get("日期"),
        }
    else:
        flags.append(QualityFlag("breadth", "warning", f"涨跌家数取不到: {err}"))
        inline["advance_decline"] = None

    # ── 四个涨停池 ──────────────────────────────────────────────
    specs = {
        "zt": ("stock_zt_pool_em", {"date": d}, "涨停池"),
        "zb": ("stock_zt_pool_zbgc_em", {"date": d}, "炸板池"),
        "dt": ("stock_zt_pool_dtgc_em", {"date": d}, "跌停池"),
    }
    if prev_trading_day:
        specs["prev_zt"] = ("stock_zt_pool_previous_em", {"date": d}, "昨日涨停池")

    counts = {}
    for key, (fn, params, label) in specs.items():
        df, err = try_call(fn, params)
        if df is None:
            flags.append(QualityFlag("breadth", "warning", f"{label}取不到: {err}"))
            counts[key] = None
            continue
        pools[key] = df
        counts[key] = len(df)

    inline["limit_stats"] = {
        "limit_up": counts.get("zt"),
        "broken_board": counts.get("zb"),
        "limit_down": counts.get("dt"),
        "prev_limit_up": counts.get("prev_zt"),
    }

    # ── 炸板率 ──────────────────────────────────────────────────
    zt_n, zb_n = counts.get("zt"), counts.get("zb")
    if zt_n is not None and zb_n is not None and (zt_n + zb_n) > 0:
        inline["broken_board_rate"] = round(zb_n / (zt_n + zb_n) * 100, 2)
    else:
        inline["broken_board_rate"] = None
        flags.append(QualityFlag("breadth", "warning", "炸板率无法计算（涨停池或炸板池缺失）"))

    # ── 连板梯队与晋级率 ────────────────────────────────────────
    if "zt" in pools and "连板数" in pools["zt"].columns:
        import pandas as pd

        lb = pd.to_numeric(pools["zt"]["连板数"], errors="coerce").fillna(1).astype(int)
        ladder = lb.value_counts().sort_index()
        inline["ladder"] = {f"{int(k)}板": int(v) for k, v in ladder.items()}
        inline["highest_board"] = int(lb.max())
        top = pools["zt"].assign(_lb=lb).sort_values("_lb", ascending=False).head(15)
        inline["ladder_detail"] = [
            {
                "code": str(r["代码"]),
                "name": r["名称"],
                "boards": int(r["_lb"]),
                "industry": r.get("所属行业"),
                "seal_amount": _num(r.get("封板资金")),
                "first_seal_time": r.get("首次封板时间"),
                "broken_times": _num(r.get("炸板次数")),
            }
            for _, r in top.iterrows()
        ]
    else:
        inline["ladder"] = None
        inline["highest_board"] = None
        inline["ladder_detail"] = []

    inline["promotion_rate"] = _promotion_rate(pools, inline, flags)

    status = "ok" if not flags else ("degraded" if pools else "missing")
    block = DataBlock(
        status=status,
        rows=sum(len(v) for v in pools.values()),
        inline=inline,
        provenance=Provenance(
            source="akshare.stock_market_activity_legu + stock_zt_pool_*",
            fetched_at=now_iso(),
            params={"date": d},
        ),
        flags=flags,
    )
    return block, pools


def _promotion_rate(pools: dict, inline: dict, flags: list) -> float | None:
    """昨日涨停股中今日仍涨停的比例。衡量赚钱效应最直接的指标。"""
    if "prev_zt" not in pools or "zt" not in pools:
        flags.append(QualityFlag("breadth", "warning", "晋级率无法计算（缺昨日涨停池或今日涨停池）"))
        return None
    prev_codes = set(pools["prev_zt"]["代码"].astype(str))
    today_codes = set(pools["zt"]["代码"].astype(str))
    if not prev_codes:
        return None
    return round(len(prev_codes & today_codes) / len(prev_codes) * 100, 2)


def _num(v):
    try:
        import pandas as pd

        if v is None or (isinstance(v, float) and pd.isna(v)):
            return None
        return float(str(v).replace(",", "").replace("%", ""))
    except Exception:
        return None
