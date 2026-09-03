#!/usr/bin/env python3
"""计算仓位与风险指标（章节七）。position-advisor 必须调用它，不许自己心算。

用法:
    python tools/compute_risk.py --run-id 2026-08-28_close

输入：dataset.json 的 holdings 块 + config/positions.yaml + .env 的账户总资产
输出：可直接填进 positions_review.json 的 risk 段
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from core.cli import REPO_ROOT, emit, fail, read_json, run_dir

sys.path.insert(0, str(REPO_ROOT))


def _load_thresholds() -> dict:
    import yaml

    p = REPO_ROOT / "config" / "thresholds.yaml"
    if not p.is_file():
        p = REPO_ROOT / "config" / "thresholds.example.yaml"
    return (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("risk", {})


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-id", required=True)
    args = ap.parse_args()

    from agents.position_advisor.scripts.positions import PositionError, load_positions, mark_to_market

    dataset = read_json(run_dir(args.run_id) / "dataset.json")
    quotes = (dataset.get("blocks", {}).get("holdings", {}) or {}).get("inline") or []

    try:
        pos = load_positions()
    except PositionError as e:
        fail("POSITIONS_ERROR", str(e))
        return

    mtm = mark_to_market(pos, quotes)
    th = _load_thresholds()
    equity = mtm["account_equity"]
    per_trade_cap = th.get("per_trade_max_pct") or 0.5

    # 单笔风险：跌到失效位会亏多少
    per_trade = []
    for r in mtm["positions"]:
        stop = r.get("stop_level")
        close = r.get("close")
        if stop and close:
            loss = round((close - float(stop)) * r["shares"], 2)
            pct = round(loss / equity * 100, 3)
            per_trade.append({
                "code": r["code"],
                "invalidation": float(stop),
                "loss_at_invalidation": loss,
                "loss_pct_of_equity": pct,
                "over_half_percent": pct > per_trade_cap,
            })
        else:
            per_trade.append({
                "code": r["code"],
                "invalidation": None,
                "loss_at_invalidation": None,
                "loss_pct_of_equity": None,
                "over_half_percent": False,
                "note": "缺失效位，无法计算单笔风险——请在 positions.yaml 补 stop_level",
            })

    # 集中度：单票 + 同题材（同题材是重点，三只同题材 = 一个仓位）
    concentration = [
        {"scope": r["code"], "kind": "single_stock", "weight_pct": r["weight_pct"],
         "over_limit": _over(r["weight_pct"], th.get("single_stock_max_pct"))}
        for r in mtm["positions"]
    ]
    themes: dict[str, float] = {}
    for r in mtm["positions"]:
        key = r.get("sector") or "未分类"
        themes[key] = themes.get(key, 0) + (r["weight_pct"] or 0)
    concentration += [
        {"scope": k, "kind": "theme", "weight_pct": round(v, 2),
         "over_limit": _over(v, th.get("single_theme_max_pct"))}
        for k, v in themes.items()
    ]

    # 记一笔当日快照，并比对历史 —— 章节④第 3、4、7 条自检的证据来源
    from agents.position_advisor.scripts.history import append_snapshot, behavior_signals

    signals = behavior_signals(mtm["positions"])          # 先比对
    append_snapshot(mtm["positions"], source="run", as_of=dataset.get("as_of"))

    max_daily = th.get("max_daily_loss_pct")
    emit({
        "account_equity": equity,
        "total_market_value": mtm["total_market_value"],
        "total_position_pct": mtm["total_position_pct"],
        "cash_pct": mtm["cash_pct"],
        "concentration": concentration,
        "per_trade_risk": per_trade,
        "per_trade_cap_pct": per_trade_cap,
        "max_daily_loss": round(equity * max_daily / 100, 2) if max_daily else None,
        "thresholds_missing": [k for k, v in th.items() if v is None],
        "positions_marked": mtm["positions"],
        "behavior_signals": signals,
        "history_file": "memory/positions_history.jsonl",
        "note": "stop_trading 由 position-advisor 结合情绪阶段与行为自检判定，本工具只给数字。"
                "behavior_signals 只陈述发生了什么，不做定性——"
                "同样是加仓，主升期加强势票和浮亏时摊成本是两回事，代码分不出来",
    })


def _over(value, cap):
    return bool(cap) and value is not None and value > cap


if __name__ == "__main__":
    main()
