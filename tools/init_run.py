#!/usr/bin/env python3
"""创建一次复盘运行的 workspace 目录并写入初始 run_manifest.json。

用法:
    python tools/init_run.py --as-of 2026-08-28 --mode close
"""
from __future__ import annotations

import argparse
import re
from datetime import datetime, timezone

from _common import WORKSPACE, emit, fail, write_json

MODE_STEPS = {
    "close":     ["data-engineer", "market-analyst", "sector-analyst", "news-analyst",
                  "position-advisor", "report-writer"],
    "premarket": ["data-engineer", "news-analyst", "position-advisor", "report-writer"],
    "positions": ["data-engineer", "position-advisor", "report-writer"],
    "weekly":    ["data-engineer", "market-analyst", "sector-analyst",
                  "position-advisor", "report-writer"],
}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--as-of", required=True, help="分析基准日 YYYY-MM-DD")
    p.add_argument("--mode", default="close", choices=sorted(MODE_STEPS),
                   help="运行模式：close 收盘复盘 / premarket 盘前 / positions 持仓更新 / weekly 周复盘")
    p.add_argument("--slug", default=None, help="run 目录后缀，默认用 mode")
    args = p.parse_args()

    if not re.match(r"^\d{4}-\d{2}-\d{2}$", args.as_of):
        fail("BAD_DATE", f"日期格式不合法: {args.as_of}", expected="YYYY-MM-DD")

    run_id = f"{args.as_of}_{args.slug or args.mode}"
    d = WORKSPACE / "runs" / run_id
    (d / "logs").mkdir(parents=True, exist_ok=True)

    manifest = {
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "as_of": args.as_of,
        "mode": args.mode,
        "trading_day": None,
        "status": "pending",
        "steps": [
            {"agent": a, "status": "pending", "artifact": None, "note": None}
            for a in MODE_STEPS[args.mode]
        ],
        "notes": [],
    }
    write_json(d / "run_manifest.json", manifest)
    emit({"run_id": run_id, "run_dir": str(d), "mode": args.mode,
          "steps": MODE_STEPS[args.mode]})


if __name__ == "__main__":
    main()
