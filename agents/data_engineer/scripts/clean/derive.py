"""派生指标：从原始数据算出报告要用的比率与强弱。

这一层的存在意义：**让"炸板率是多少"这种问题有唯一答案**。
如果交给模型口算，同一份数据每次跑出的数字都可能不一样，报告就不可复现了。
"""
from __future__ import annotations

from core.contracts import QualityFlag


def two_market_amount(index_snapshot: list[dict]) -> dict:
    """两市成交额 = 上证 + 深证成指所在市场的成交额。

    注意：创业板指与科创50的成交额已包含在深市/沪市里，**不能直接相加**，
    否则会重复计算——这是新手最常犯的错。
    """
    sh = next((i for i in index_snapshot if i["code"] == "000001"), None)
    sz = next((i for i in index_snapshot if i["code"] == "399001"), None)
    if not sh or not sz:
        return {"total": None, "note": "缺指数快照，无法计算两市成交额"}
    if sh.get("amount") is None or sz.get("amount") is None:
        missing = [i.get("name") for i in (sh, sz) if i.get("amount") is None]
        return {"total": None, "total_yi": None,
                "note": f"{'、'.join(missing)} 的成交额缺失（多半用了不返回成交额的备用源），"
                        f"两市成交额无法计算——**不会用 0 代替**"}
    total = sh["amount"] + sz["amount"]
    prev = None
    if sh.get("amount_chg_pct") is not None and sz.get("amount_chg_pct") is not None:
        prev_sh = sh["amount"] / (1 + sh["amount_chg_pct"] / 100)
        prev_sz = sz["amount"] / (1 + sz["amount_chg_pct"] / 100)
        prev = prev_sh + prev_sz
    return {
        "total": round(total, 2),
        "total_yi": round(total / 1e8, 1),
        "prev_total_yi": round(prev / 1e8, 1) if prev else None,
        "chg_yi": round((total - prev) / 1e8, 1) if prev else None,
        "chg_pct": round((total / prev - 1) * 100, 2) if prev else None,
        "note": "上证 + 深证成指市场成交额之和；创业板/科创板已含其中，未重复计入",
    }


def relative_strength(stock_pct: float, bench_pct: float) -> float:
    """个股相对基准的超额涨跌（百分点）。章节四"相对大盘/板块/核心的强弱"用。"""
    return round(stock_pct - bench_pct, 2)


def position_vs_key_levels(quote: dict) -> dict:
    """个股相对均线与近期高低点的位置。给 position-advisor 提供客观位置描述。"""
    close = quote.get("close")
    if close is None:
        return {}
    out = {}
    for k in ("ma5", "ma10", "ma20"):
        v = quote.get(k)
        if v:
            out[f"vs_{k}"] = round((close / v - 1) * 100, 2)
    if quote.get("high_20d"):
        out["drawdown_from_20d_high"] = round((close / quote["high_20d"] - 1) * 100, 2)
    if quote.get("low_20d"):
        out["rebound_from_20d_low"] = round((close / quote["low_20d"] - 1) * 100, 2)
    return out


def sanity_check(dataset: dict) -> list[QualityFlag]:
    """交付前的自检。发现问题只标记，不修改。"""
    flags: list[QualityFlag] = []
    blocks = dataset.get("blocks", {})
    cal = blocks.get("calendar", {}).get("inline") or {}
    if cal and not cal.get("is_trading_day"):
        flags.append(
            QualityFlag("calendar", "error", f"{cal.get('as_of')} 不是交易日，当日行情数据不存在")
        )
    breadth = blocks.get("breadth", {}).get("inline") or {}
    if breadth.get("broken_board_rate") is None:
        flags.append(QualityFlag("breadth", "warning", "炸板率缺失，章节一的情绪判断会受影响"))
    if breadth.get("promotion_rate") is None:
        flags.append(QualityFlag("breadth", "warning", "连板晋级率缺失，章节一的情绪判断会受影响"))
    return flags
