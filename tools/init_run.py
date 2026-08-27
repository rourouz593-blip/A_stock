#!/usr/bin/env python3
"""创建一次分析运行的 workspace 目录并写入初始 run_manifest.json。

用法:
    python tools/init_run.py --targets 600519.SH 300750.SZ --as-of 2026-01-02 --slug demo
"""
from __future__ import annotations

import argparse
import re
from datetime import datetime, timezone

from _common import WORKSPACE, emit, fail, write_json

CODE_RE = re.compile(r"^\d{6}\.(SH|SZ|BJ)$")
STEPS = [
    "data-engineer",
    "fundamental-analyst",
    "technical-analyst",
    "sentiment-analyst",
    "report-writer",
]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--targets", nargs="+", required=True, help="股票代码，形如 600519.SH")
    p.add_argument("--as-of", required=True, help="分析基准日 YYYY-MM-DD")
    p.add_argument("--slug", default="run", help="run 目录后缀")
    p.add_argument("--lookback-days", type=int, default=250)
    args = p.parse_args()

    bad = [c for c in args.targets if not CODE_RE.match(c)]
    if bad:
        fail("BAD_CODE", f"代码格式不合法: {bad}", expected="6 位数字 + .SH/.SZ/.BJ")

    run_id = f"{args.as_of}_{args.slug}"
    d = WORKSPACE / "runs" / run_id
    (d / "logs").mkdir(parents=True, exist_ok=True)

    manifest = {
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "as_of": args.as_of,
        "targets": args.targets,
        "lookback_days": args.lookback_days,
        "status": "pending",
        "steps": [
            {"agent": s, "status": "pending", "artifact": None, "note": None}
            for s in STEPS
        ],
        "notes": [],
    }
    write_json(d / "run_manifest.json", manifest)
    emit({"run_id": run_id, "run_dir": str(d)})


if __name__ == "__main__":
    main()
