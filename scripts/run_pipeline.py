#!/usr/bin/env python3
"""数据流水线（不经过 agent，直接跑，调试用）。

用途：在没有任何 agent 参与的情况下验证数据层是否正常。
把数据层调通之后，再让 data-engineer agent 通过 tools/ 调用它。

用法:
    python scripts/run_pipeline.py --run-id 2026-01-02_demo --codes 600519.SH

当前只有 OHLCV 的 script/tool 已接通；交易日历、清洗、组装以及其他数据类别仍是
TODO。本命令只展示调试流水线状态，不发起网络请求。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.contracts import FetchRequest  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-id", required=True)
    p.add_argument("--codes", nargs="+", required=True)
    p.add_argument("--start", default=None)
    p.add_argument("--end", default=None)
    args = p.parse_args()

    req = FetchRequest(codes=args.codes, start=args.start, end=args.end)

    steps = [
        ("交易日历", "scripts.fetch.market_data:fetch_trading_calendar", False),
        ("行情",     "scripts.fetch.market_data:fetch_ohlcv", True),
        ("财报",     "scripts.fetch.financials:fetch_statements", False),
        ("估值",     "scripts.fetch.financials:fetch_valuation", False),
        ("公告",     "scripts.fetch.news:fetch_announcements", False),
        ("新闻",     "scripts.fetch.news:fetch_news", False),
        ("资金流",   "scripts.fetch.news:fetch_moneyflow", False),
        ("清洗",     "scripts.clean.normalize:align_to_calendar", False),
        ("组装",     "scripts.store.repository:build_dataset_json", False),
    ]

    print(f"[pipeline] run_id={args.run_id} codes={req.codes}")
    for label, ref, implemented in steps:
        marker = "[OK]" if implemented else "[ ]"
        note = "已实现；由 fetch_market_data tool 调用" if implemented else "TODO"
        print(f"  {marker} {label:<8} → {ref}   ({note})")
    print("\nOHLCV 最小工具链已接通；完整 dataset 流水线仍等待其余步骤。")


if __name__ == "__main__":
    main()
