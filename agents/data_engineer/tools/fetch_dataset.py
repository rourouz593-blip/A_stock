#!/usr/bin/env python3
"""取当日全部数据并写出 dataset.json。data-engineer 的唯一动作。

用法:
    python tools/fetch_dataset.py --run-id 2026-08-28_close --as-of 2026-08-28
    python tools/fetch_dataset.py --run-id ... --as-of ... --no-cache

这是同一 Agent 内 `scripts/build_dataset.py` 的薄封装。
"""
from __future__ import annotations

import argparse
import subprocess
import sys

from core.cli import REPO_ROOT, emit, fail


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-id", required=True)
    p.add_argument("--as-of", required=True)
    p.add_argument("--mode", default="close", choices=["close", "premarket", "positions", "weekly"])
    p.add_argument("--no-cache", action="store_true")
    p.add_argument("--no-positions", action="store_true")
    args = p.parse_args()

    cmd = [sys.executable, "-m", "agents.data_engineer.scripts.build_dataset",
           "--run-id", args.run_id, "--as-of", args.as_of, "--mode", args.mode]
    if args.no_cache:
        cmd.append("--no-cache")
    if args.no_positions:
        cmd.append("--no-positions")

    r = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
    sys.stderr.write(r.stdout)
    if r.returncode != 0:
        fail("FETCH_FAILED", "取数失败", stderr=r.stderr[-2000:], stdout=r.stdout[-2000:])

    emit({
        "ok": True,
        "artifact": f"workspace/runs/{args.run_id}/dataset.json",
        "detail_csv_dir": f"data/{args.run_id}/",
        "next": "python tools/validate_artifact.py --run-id %s --artifact dataset" % args.run_id,
    })


if __name__ == "__main__":
    main()
