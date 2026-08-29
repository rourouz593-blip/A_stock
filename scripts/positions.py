"""读取并校验我的持仓（config/positions.yaml）。对应报告章节四与章节七。

持仓是**手填**的：券商没有开放接口，截图识别又不可靠到能直接下结论的程度。
手填的好处是——每一笔的买入逻辑都被迫写下来，
而"买入逻辑是否仍成立"正是章节四要回答的第一个问题。
"""
from __future__ import annotations

import os
from pathlib import Path

from .contracts import suffixed

REPO_ROOT = Path(__file__).resolve().parent.parent


class PositionError(ValueError):
    pass


def load_positions(path: str | None = None) -> dict:
    """读 config/positions.yaml，返回 {account, positions[]}。

    校验规则（宁可报错，也不要用一份错的持仓去算风险）：
      - 代码格式合法
      - 成本价 > 0、数量 > 0
      - 账户总资产从 .env 的 ASTOCK_ACCOUNT_EQUITY 读，yaml 里不写钱
    """
    import yaml

    p = Path(path) if path else REPO_ROOT / "config" / "positions.yaml"
    if not p.is_file():
        raise PositionError(
            f"找不到 {p}。请先 cp config/positions.example.yaml config/positions.yaml 并填写"
        )
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    equity = os.getenv("ASTOCK_ACCOUNT_EQUITY")
    if equity is None:
        raise PositionError(
            "未设置 ASTOCK_ACCOUNT_EQUITY（账户总资产）。"
            "章节七的单笔风险与当日最大亏损都依赖它，缺了就只能给出比例、给不出金额。"
        )

    out = {"account_equity": float(equity), "positions": []}
    for i, item in enumerate(raw.get("positions") or []):
        code = str(item.get("code", "")).strip()
        if not code:
            raise PositionError(f"第 {i + 1} 条持仓缺 code")
        cost = float(item.get("cost", 0))
        shares = int(item.get("shares", 0))
        if cost <= 0 or shares <= 0:
            raise PositionError(f"{code} 的 cost/shares 必须为正数")
        out["positions"].append(
            {
                "code": suffixed(code),
                "name": item.get("name"),
                "cost": cost,
                "shares": shares,
                "buy_date": str(item.get("buy_date", "")) or None,
                "thesis": item.get("thesis"),          # 买入逻辑，章节四要逐条复核
                "module": item.get("module"),          # 交易模块：打板/低吸/趋势/套利…
                "sector": item.get("sector"),          # 我认为它属于哪个题材
                "stop_level": item.get("stop_level"),  # 失效位（我自己定的）
            }
        )
    return out


def mark_to_market(positions: dict, quotes: list[dict]) -> dict:
    """用当日收盘价给持仓估值，算出每只的盈亏与占比。纯计算，无判断。"""
    qmap = {q["code"]: q for q in quotes}
    total_mv = 0.0
    rows = []
    for p in positions["positions"]:
        q = qmap.get(p["code"])
        close = q["close"] if q else None
        mv = close * p["shares"] if close else None
        pnl = (close - p["cost"]) * p["shares"] if close else None
        rows.append(
            {
                **p,
                "close": close,
                "pct_chg": q["pct_chg"] if q else None,
                "market_value": round(mv, 2) if mv else None,
                "pnl": round(pnl, 2) if pnl is not None else None,
                "pnl_pct": round((close / p["cost"] - 1) * 100, 2) if close else None,
                "quote_stale": q.get("stale") if q else True,
            }
        )
        total_mv += mv or 0
    equity = positions["account_equity"]
    for r in rows:
        r["weight_pct"] = round((r["market_value"] or 0) / equity * 100, 2)
    return {
        "account_equity": equity,
        "total_market_value": round(total_mv, 2),
        "total_position_pct": round(total_mv / equity * 100, 2),
        "cash_pct": round((1 - total_mv / equity) * 100, 2),
        "positions": rows,
    }
