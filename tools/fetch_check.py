#!/usr/bin/env python3
"""逐块体检：十一个数据块，一块一块试，告诉你哪块能取、哪块不能、为什么。

# 和别的工具的分工

    doctor            环境对不对（依赖、配置、代理、预算、仓库）
    net_check         域名通不通（DNS / 直连 / IPv6 / UA）
    fetch_check  ←    **数据取不取得到**（这一个）
    review            真的跑一遍复盘

`review` 也能发现问题，但它是**流水线**：前面的块失败会影响后面，
而且失败时你拿到的是一个中断的 run，不是一张体检表。
这个工具反过来——每块独立试，一块失败不影响下一块，最后给一张全景。

# 它遵守所有的闸

限流、每日预算、熔断、本地仓库全部照常生效。所以：
  - 跑它会发出约 12–20 个请求，结尾会告诉你实际用量
  - 仓库里已有的日子不会重新取，所以第二次跑会明显更省
  - 有域名在冷却期时，相关块会直接报"冷却中"，一个请求都不发

# 用法

    python tools/fetch_check.py                  # 全部
    python tools/fetch_check.py --only breadth sectors
    python tools/fetch_check.py --as-of 2026-08-28
    python tools/fetch_check.py --json           # 给 agent 用
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

C_OK, C_NO, C_WARN, C_DIM, C_B, C_END = (
    "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[1m", "\033[0m")


def _c(s, color):
    return f"{color}{s}{C_END}" if sys.stdout.isatty() else str(s)


# 每块：名字 → (报告章节, 必需?, 说明)
BLOCKS = [
    ("calendar",       "全部",   True,  "交易日历——所有时间对齐都靠它，它挂了别的都别谈"),
    ("index_hist",     "①②",    True,  "四大指数日线：开收高低、涨跌幅、两市成交额"),
    ("index_spot",     "①",     True,  "指数当日快照——由 index_hist 派生，不额外发请求"),
    ("index_intraday", "②",     False, "指数分时→日内四段。东财只留最近几天，历史日期取不到属正常"),
    ("breadth",        "①",     True,  "涨跌家数"),
    ("limit_pool",     "①③",    True,  "涨停/炸板/跌停池→连板梯队与炸板率"),
    ("sectors",        "③",     True,  "板块行情排名"),
    ("sector_flow",    "③",     False, "板块主力资金流"),
    ("holdings",       "④",     True,  "持仓个股日线与快照（positions.yaml 为空时会跳过）"),
    ("news",           "⑥",     False, "财联社/东财快讯"),
    ("announcements",  "⑥",     False, "当日公告"),
    ("northbound",     "①",     False, "北向资金（披露规则多次调整，取不到属正常）"),
]


def _probe(name, as_of, days, codes):
    """跑一块，返回 (状态, 行数, 备注)。异常一律吃掉——体检不该自己崩。"""
    from scripts.fetch import breadth as f_br
    from scripts.fetch import market as f_mk
    from scripts.fetch import news as f_nw
    from scripts.fetch import sectors as f_sc
    from scripts.fetch import stocks as f_st

    prev = days[1] if len(days) > 1 else None
    if name == "index_hist":
        b, _ = f_mk.fetch_index_daily(as_of, trading_days=days)
    elif name == "index_intraday":
        b, _ = f_mk.fetch_index_intraday(as_of)
    elif name in ("breadth", "limit_pool"):
        b, pools = f_br.fetch_breadth(as_of, prev)
        if name == "limit_pool":
            n = sum(len(v) for v in pools.values())
            return b.status, n, f"{len(pools)} 个池 / {n} 行"
    elif name == "sectors":
        b, _ = f_sc.fetch_sectors()
    elif name == "sector_flow":
        b = f_sc.fetch_sector_flow()
    elif name == "holdings":
        if not codes:
            return "skipped", 0, "positions.yaml 里没有持仓"
        b, _ = f_st.fetch_holdings_quotes(codes, as_of, trading_days=days)
        src = (b.provenance.params or {}).get("spot_provider")
        store = b.provenance.from_store or []
        return b.status, b.rows or 0, f"快照源={src or '无'}，{len(store)}/{len(codes)} 只历史走仓库"
    elif name == "news":
        b = f_nw.fetch_news(as_of)
    elif name == "announcements":
        b = f_nw.fetch_announcements(as_of)
    elif name == "northbound":
        b = f_st.fetch_northbound()
    else:
        return "unknown", 0, ""
    note = ""
    if getattr(b.provenance, "from_store", None):
        note = f"{len(b.provenance.from_store)} 项走仓库（未联网）"
    if b.provenance.fallback_from:
        note = (note + " / " if note else "") + f"降级自 {b.provenance.fallback_from}"
    return b.status, b.rows or 0, note


def main() -> int:
    ap = argparse.ArgumentParser(description="逐块检查数据能不能取到")
    ap.add_argument("--as-of", default=None, help="检查哪一天（默认最近交易日）")
    ap.add_argument("--only", nargs="*", help="只查这几块")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    from scripts.ak_client import budget_state, cooling_hosts, explain
    from scripts.fetch import calendar as f_cal

    spent0 = budget_state()["total"]
    cooling = cooling_hosts()
    if cooling and not args.json:
        print(_c("⚠ 有域名正在冷却，相关块会直接失败且不发请求：", C_WARN))
        for h, m in cooling.items():
            print(f"    {h}  还剩 {m:.0f} 分钟")
        print()

    # 日历单独先跑：它决定 as_of，也决定别的块能不能用仓库
    as_of = args.as_of
    results, days = [], []
    t0 = time.time()
    try:
        cal, days = f_cal.fetch_calendar(as_of or time.strftime("%Y-%m-%d"))
        as_of = as_of or cal.inline["last_trading_day"]
        results.append({"block": "calendar", "status": cal.status,
                        "rows": cal.rows, "note": f"最近交易日 {as_of}"
                        + ("" if cal.inline["is_trading_day"] else "（今天不是交易日）"),
                        "secs": round(time.time() - t0, 1)})
    except Exception as e:
        results.append({"block": "calendar", "status": "failed",
                        "rows": 0, "note": explain(e)[:200],
                        "secs": round(time.time() - t0, 1)})

    codes = []
    try:
        import yaml
        pos = REPO_ROOT / "config" / "positions.yaml"
        if pos.is_file():
            data = yaml.safe_load(pos.read_text(encoding="utf-8")) or {}
            codes = [str(h["code"]) for h in (data.get("holdings") or []) if h.get("code")]
    except Exception:
        pass

    wanted = args.only or [n for n, *_ in BLOCKS]
    for name, chap, required, desc in BLOCKS:
        if name == "calendar" or name not in wanted:
            continue
        if not days:
            results.append({"block": name, "status": "skipped", "rows": 0,
                            "note": "日历没取到，无法继续", "secs": 0})
            continue
        if name == "index_spot":
            # 派生块：直接沿用 index_hist 的结果，绝不为了体检多发一次请求
            src = next((r for r in results if r["block"] == "index_hist"), None)
            results.append({"block": name, "status": src["status"] if src else "skipped",
                            "rows": src["rows"] if src else 0,
                            "note": "派生自 index_hist", "secs": 0})
            continue
        t = time.time()
        try:
            st, rows, note = _probe(name, as_of, days, codes)
        except Exception as e:
            st, rows, note = "failed", 0, explain(e)[:200]
        results.append({"block": name, "status": st, "rows": rows,
                        "note": note, "secs": round(time.time() - t, 1)})

    spent = budget_state()["total"] - spent0
    meta = {name: (chap, req, desc) for name, chap, req, desc in BLOCKS}
    if args.json:
        print(json.dumps({"as_of": as_of, "requests_used": spent,
                          "results": results}, ensure_ascii=False, indent=2))
    else:
        print(_c(f"数据体检 · {as_of}", C_B))
        print(_c(f"  {'数据块':<16}{'章节':<6}{'状态':<10}{'行数':>7}{'耗时':>7}  备注", C_DIM))
        for r in results:
            chap, required, _ = meta.get(r["block"], ("", False, ""))
            mark = {"ok": _c("✓ ok", C_OK), "degraded": _c("! 降级", C_WARN),
                    "missing": _c("! 缺失", C_WARN), "skipped": _c("- 跳过", C_DIM),
                    }.get(r["status"], _c("✗ " + r["status"], C_NO))
            print(f"  {r['block']:<16}{chap:<6}{mark:<18}{r['rows']:>7}"
                  f"{r['secs']:>6}s  {r['note'][:60]}")
        bad = [r for r in results
               if r["status"] in ("failed", "missing")
               and meta.get(r["block"], ("", False, ""))[1]]
        print()
        print(_c(f"  本次用掉 {spent} 个请求（今日累计 {budget_state()['total']}，无上限）",
                 C_DIM))
        print()
        if bad:
            print(_c(f"✗ {len(bad)} 个**必需**数据块拿不到：" +
                     "、".join(r["block"] for r in bad), C_NO))
            print(_c("  必需块缺失会让对应章节整章 blocked。先看备注里的原因，", C_DIM))
            print(_c("  再按 docs/05-常见失败模式.md 排查。不要靠反复重跑解决。", C_DIM))
            return 1
        soft = [r for r in results if r["status"] in ("failed", "missing", "degraded")]
        if soft:
            print(_c(f"! 必需块都正常；{len(soft)} 个可选/降级块见上表。", C_WARN))
            print(_c("  这种情况可以照常跑复盘——缺的部分会标 blocked 并在报告顶部声明。", C_DIM))
            return 0
        print(_c("✓ 全部数据块都能取到，可以跑 python tools/astock.py review", C_OK))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
