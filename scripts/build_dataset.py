#!/usr/bin/env python3
"""数据流水线主入口：一条命令把当天所有原始数据取回来，产出 dataset.json。

用法（从仓库根目录执行）:
    python -m scripts.build_dataset --run-id 2026-08-28_close --as-of 2026-08-28
    python -m scripts.build_dataset --run-id ... --as-of ... --no-cache   # 强制重取

设计要点：
  1. 这一步**不做任何判断**，只把事实取回来并如实标注质量问题
  2. 任何一块取不到 → status=missing + flag，不影响其他块，也绝不填假数据
  3. 明细落 CSV（data/<run_id>/），dataset.json 只放摘要与路径——
     否则 dataset.json 会大到塞不进模型上下文
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts import ak_client  # noqa: E402
from scripts.clean import derive  # noqa: E402
from scripts.contracts import DataBlock, Provenance, QualityFlag  # noqa: E402
from scripts.fetch import breadth as f_breadth  # noqa: E402
from scripts.fetch import calendar as f_cal  # noqa: E402
from scripts.fetch import market as f_market  # noqa: E402
from scripts.fetch import news as f_news  # noqa: E402
from scripts.fetch import sectors as f_sectors  # noqa: E402
from scripts.fetch import stocks as f_stocks  # noqa: E402
from scripts.store import repository as store  # noqa: E402


def build(run_id: str, as_of: str, mode: str = "close", with_positions: bool = True) -> dict:
    blocks: dict[str, DataBlock] = {}
    tables: dict = {}
    flags: list[QualityFlag] = []

    def log(msg: str) -> None:
        print(f"[build_dataset] {msg}", flush=True)

    # ① 交易日历 —— 必需，失败就整体停下
    log("交易日历 …")
    cal_block, past_days = f_cal.fetch_calendar(as_of)
    blocks["calendar"] = cal_block
    prev_day = cal_block.inline.get("prev_trading_day")

    # ② 指数日线与快照
    log("指数日线 …")
    idx_block, idx_df = f_market.fetch_index_daily(as_of)
    idx_block.path = store.save_table(idx_df, run_id, "index_hist")
    blocks["index_hist"] = idx_block
    blocks["index_spot"] = DataBlock(
        status=idx_block.status,
        rows=len(idx_block.inline or []),
        inline=idx_block.inline,
        provenance=idx_block.provenance,
    )

    # ③ 指数分时（拆四段）
    log("指数分时 …")
    intra_block, intra_df = f_market.fetch_index_intraday(as_of)
    if intra_df is not None:
        intra_block.path = store.save_table(intra_df, run_id, "index_intraday")
    blocks["index_intraday"] = intra_block

    # ④ 市场宽度与涨停生态
    log("涨跌家数 / 涨停池 …")
    br_block, pools = f_breadth.fetch_breadth(as_of, prev_day)
    for k, df in pools.items():
        store.save_table(df, run_id, f"pool_{k}")
    br_block.path = f"data/{run_id}/pool_*.csv"
    blocks["breadth"] = br_block
    blocks["limit_pool"] = DataBlock(
        status=br_block.status,
        rows=sum(len(v) for v in pools.values()),
        path=br_block.path,
        provenance=br_block.provenance,
    )

    # ⑤ 板块
    log("板块行情 …")
    sec_block, sec_frames = f_sectors.fetch_sectors()
    for k, df in sec_frames.items():
        store.save_table(df, run_id, f"sector_{k}")
    sec_block.path = f"data/{run_id}/sector_*.csv"
    blocks["sectors"] = sec_block
    blocks["sector_flow"] = f_sectors.fetch_sector_flow()

    # ⑥ 持仓个股
    holdings_codes: list[str] = []
    if with_positions:
        try:
            from scripts.positions import load_positions

            pos = load_positions()
            holdings_codes = [p["code"] for p in pos["positions"]]
        except Exception as e:
            flags.append(QualityFlag("holdings", "warning", f"持仓读取失败，章节四将为空: {e}"))
    log(f"持仓个股 {holdings_codes} …")
    hold_block, hold_frames = f_stocks.fetch_holdings_quotes(holdings_codes, as_of)
    for code, df in hold_frames.items():
        store.save_table(df, run_id, f"holding_{code.replace('.', '_')}")
    blocks["holdings"] = hold_block

    # ⑦ 新闻与公告
    log("新闻 / 公告 …")
    blocks["news"] = f_news.fetch_news(as_of)
    blocks["announcements"] = f_news.fetch_announcements(as_of)

    # ⑧ 北向（可选）
    blocks["northbound"] = f_stocks.fetch_northbound()

    # ── 组装 ────────────────────────────────────────────────────
    dataset = {
        "run_id": run_id,
        "as_of": as_of,
        "mode": mode,
        "generated_at": ak_client.now_iso(),
        "adjust_mode": "qfq",
        "data_source": "akshare",
        "blocks": {k: v.to_dict() for k, v in blocks.items()},
        "derived": {},
        "quality_flags": [],
    }

    snap = blocks["index_spot"].inline or []
    dataset["derived"]["two_market_amount"] = derive.two_market_amount(snap)

    for b in blocks.values():
        flags.extend(b.flags)
    flags.extend(derive.sanity_check(dataset))
    dataset["quality_flags"] = [
        {"block": f.block, "level": f.level, "message": f.message, "affected_range": f.affected_range}
        for f in flags
    ]
    return dataset


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-id", required=True)
    p.add_argument("--as-of", required=True, help="YYYY-MM-DD")
    p.add_argument("--mode", default="close", choices=["close", "premarket", "positions", "weekly"])
    p.add_argument("--no-cache", action="store_true", help="忽略本地缓存，强制重新取数")
    p.add_argument("--no-positions", action="store_true")
    args = p.parse_args()

    if args.no_cache:
        os.environ["ASTOCK_NO_CACHE"] = "1"
        import shutil

        cache = ak_client.CACHE_DIR
        if cache.is_dir():
            shutil.rmtree(cache)

    dataset = build(args.run_id, args.as_of, args.mode, with_positions=not args.no_positions)
    out = REPO_ROOT / "workspace" / "runs" / args.run_id / "dataset.json"
    store.write_json(out, dataset)

    errs = [f for f in dataset["quality_flags"] if f["level"] == "error"]
    warns = [f for f in dataset["quality_flags"] if f["level"] == "warning"]
    print(f"\n✅ 已写出 {out.relative_to(REPO_ROOT)}")
    print(f"   数据块 {len(dataset['blocks'])} 个 | error {len(errs)} | warning {len(warns)}")
    for f in errs + warns:
        print(f"   [{f['level']}] {f['block']}: {f['message']}")


if __name__ == "__main__":
    main()
