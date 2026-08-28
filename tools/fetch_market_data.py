#!/usr/bin/env python3
"""通过 AKShare 拉取 A 股历史行情并写入本次 run。

示例:
    python tools/fetch_market_data.py --run-id 2026-08-28_akshare-demo \
      --params '{"codes":["600552.SH"],"start":"2026-08-20",\
                 "end":"2026-08-28","freq":"daily","adjust":"none"}'
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _common import emit, fail, run_dir, write_json
from scripts.contracts import FetchRequest
from scripts.fetch.market_data import fetch_ohlcv


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-id", required=True)
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument("--params", help="JSON 字符串，见 tool_manifest.yaml 的 input 定义")
    source.add_argument("--params-file", help="UTF-8 JSON 文件；Windows/教学演示推荐")
    args = p.parse_args()

    try:
        raw_params = (
            Path(args.params_file).read_text(encoding="utf-8")
            if args.params_file
            else args.params
        )
        params = json.loads(raw_params)
    except OSError as exc:
        fail("BAD_PARAMS_FILE", f"无法读取 --params-file: {exc}")
    except json.JSONDecodeError as exc:
        fail("BAD_PARAMS", f"参数不是合法 JSON: {exc}")
    if not isinstance(params, dict):
        fail("BAD_PARAMS", "--params 必须是 JSON 对象")

    required = ["codes", "start", "end", "freq", "adjust"]
    missing = [name for name in required if name not in params]
    if missing:
        fail("BAD_PARAMS", f"缺少参数: {missing}")

    try:
        req = FetchRequest(
            codes=params["codes"],
            start=params["start"],
            end=params["end"],
            extra={"timeout": params.get("timeout", 15)},
        )
        block = fetch_ohlcv(req, freq=params["freq"], adjust=params["adjust"])
    except (TypeError, ValueError, RuntimeError) as exc:
        fail("FETCH_FAILED", str(exc), source="AKShare.stock_zh_a_hist")

    if block.status == "missing":
        fail(
            "DATA_MISSING",
            "所有标的均未取得行情数据",
            quality_flags=[asdict(flag) for flag in block.flags],
        )

    current_run_dir = run_dir(args.run_id)
    destination = current_run_dir / "data" / "ohlcv.json"
    write_json(
        destination,
        {
            "version": 1,
            "block": "ohlcv",
            "status": block.status,
            "coverage": block.coverage,
            "provenance": asdict(block.provenance),
            "quality_flags": [asdict(flag) for flag in block.flags],
            "records": block.inline,
        },
    )
    block.inline = None
    block.path = destination.relative_to(current_run_dir).as_posix()
    payload = asdict(block)
    payload["quality_flags"] = payload.pop("flags")
    emit(payload)


if __name__ == "__main__":
    main()
