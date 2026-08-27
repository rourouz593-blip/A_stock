#!/usr/bin/env python3
"""数据流水线（不经过 agent，直接跑，调试用）。

用途：在没有任何 agent 参与的情况下验证数据层是否正常。
把数据层调通之后，再让 data-engineer agent 通过 tools/ 调用它。

用法:
    python scripts/run_pipeline.py --run-id 2026-01-02_demo --codes 600519.SH

TODO(datasource): 各步骤依赖的 fetch/clean/store 尚未实现，当前运行会抛 NotImplementedError。
这是预期行为——它证明流水线骨架是接通的，只是内容还空着。
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
        ("交易日历", "scripts.fetch.market_data:fetch_trading_calendar"),
        ("行情",     "scripts.fetch.market_data:fetch_ohlcv"),
        ("财报",     "scripts.fetch.financials:fetch_statements"),
        ("估值",     "scripts.fetch.financials:fetch_valuation"),
        ("公告",     "scripts.fetch.news:fetch_announcements"),
        ("新闻",     "scripts.fetch.news:fetch_news"),
        ("资金流",   "scripts.fetch.news:fetch_moneyflow"),
        ("清洗",     "scripts.clean.normalize:align_to_calendar"),
        ("组装",     "scripts.store.repository:build_dataset_json"),
    ]

    print(f"[pipeline] run_id={args.run_id} codes={req.codes}")
    for label, ref in steps:
        print(f"  ⬜ {label:<8} → {ref}   (TODO(datasource): 未实现)")
    print("\n流水线骨架已接通，实现 scripts/ 下的空函数后即可跑通。")


if __name__ == "__main__":
    main()
