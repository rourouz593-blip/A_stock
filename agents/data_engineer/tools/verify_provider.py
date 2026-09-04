#!/usr/bin/env python3
"""跨源对账：同一天、同一只票，两个源说的一样吗？

# 为什么必须有这一步

换源最大的成本不是写代码，是**口径对不齐**——而且对不齐时没人会报错，
只是报告里的数字安静地变成了另一个意思。

按位置解析的行情接口尤其危险：字段错一位，
"成交额" 可能读成 "换手率基点"，差三个数量级；
"总市值" 可能读成 "流通市值"，总股本≠流通股本时差好几倍。

所以新 provider 进主链之前，必须拿它和现有源在**同一天同一只票**上对一遍。
对不上就别用——宁可多发几个请求，也不要在报告里放一个错的数。

# 用法

    python tools/verify_provider.py                     # 默认对四大指数 + 几只样本股
    python tools/verify_provider.py 600519 000858       # 指定标的
    python tools/verify_provider.py --dataset spot      # 指定数据集

退出码非 0 = 有对不上的字段，不要把新源设为主源。
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

from core.paths import REPO_ROOT
sys.path.insert(0, str(REPO_ROOT))

from agents.data_engineer.scripts import providers  # noqa: E402

# 字段 → 允许的相对误差。不同源的小数位、四舍五入、快照时刻都会有细微差别，
# 但**数量级绝不能差**——差三个数量级就是字段读错了，不是精度问题。
TOLERANCE = {
    "price": 0.005,          # 快照时刻可能差几秒
    "last_close": 0.0,       # 昨收是定值，必须完全一致
    "pct_chg": 0.02,
    "amount": 0.05,          # 成交额口径差异容忍大一点，但不能差量级
    "turnover_rate": 0.05,
    "limit_up": 0.0,         # 涨跌停价是算出来的定值
    "limit_down": 0.0,
}
DEFAULT_CODES = ["000001", "399001", "399006", "000688", "600519", "000858"]
DAILY_TOLERANCE = {"开盘": 0.001, "收盘": 0.001, "最高": 0.001,
                   "最低": 0.001, "成交量": 0.05}


def _cmp(a, b, tol: float) -> tuple[bool, str]:
    if a is None or b is None:
        return True, "（一方无此字段，跳过）"
    try:
        a, b = float(a), float(b)
    except (TypeError, ValueError):
        return a == b, ""
    if a == b:
        return True, ""
    base = max(abs(a), abs(b), 1e-9)
    rel = abs(a - b) / base
    if rel > 10:      # 差一个数量级以上，几乎一定是字段读错了
        return False, f"差 {rel:.0f} 倍 —— 多半是字段位置错了，不是精度"
    return rel <= tol, f"相对差 {rel:.2%}（容忍 {tol:.2%}）"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="跨源对账")
    ap.add_argument("codes", nargs="*", default=None)
    ap.add_argument("--dataset", default="spot")
    ap.add_argument("--providers", help="逗号分隔；用于对账尚未进入同一生产链的源")
    ap.add_argument("--as-of", default=date.today().isoformat())
    args = ap.parse_args()
    codes = args.codes or DEFAULT_CODES

    names = ([p.strip() for p in args.providers.split(",") if p.strip()]
             if args.providers else providers.chain(args.dataset))
    provs = []
    for name in names:
        module = providers._provider(name)
        call = getattr(module, args.dataset, None) if module else None
        if call:
            provs.append((name, call))
    if len(provs) < 2:
        print(f"✗ {args.dataset} 只有 {len(provs)} 个可用 provider，没法对账")
        return 2

    print(f"数据集 {args.dataset}，对账源 {names}")
    print(f"标的 {', '.join(codes)}\n")

    results = {}
    for name, fn in provs:
        try:
            if args.dataset == "index_daily":
                start = (date.fromisoformat(args.as_of) - timedelta(days=14)).isoformat()
                results[name] = {}
                for code in codes:
                    try:
                        frame = fn(code, start, args.as_of)
                        row = frame[frame["日期"] == args.as_of]
                        if not row.empty:
                            results[name][code] = row.iloc[-1].to_dict()
                    except Exception:
                        pass
            else:
                results[name] = fn(codes)
            print(f"  ✓ {name:<12} 拿到 {len(results[name])} 只")
        except Exception as e:
            print(f"  ✗ {name:<12} 失败：{str(e)[:100]}")
    if len(results) < 2:
        print("\n✗ 能取到数的源不足两个，无法对账。")
        return 2

    names = list(results)
    a_name, b_name = names[0], names[1]
    a, b = results[a_name], results[b_name]
    print(f"\n对账：{a_name} ←→ {b_name}\n")

    bad = 0
    for code in codes:
        qa, qb = a.get(code), b.get(code)
        if not qa or not qb:
            print(f"  {code}  一方没有这只票（{a_name}:{bool(qa)} {b_name}:{bool(qb)}）")
            continue
        rows = []
        tolerance = DAILY_TOLERANCE if args.dataset == "index_daily" else TOLERANCE
        for field, tol in tolerance.items():
            ok, note = _cmp(qa.get(field), qb.get(field), tol)
            if not ok:
                bad += 1
                rows.append(f"      ✗ {field:<14} {qa.get(field)} vs {qb.get(field)}  {note}")
        head = f"  {code} {qa.get('name') or qb.get('name') or ''}"
        print(head + ("  ✓ 一致" if not rows else ""))
        for r in rows:
            print(r)

    print()
    if bad:
        print(f"✗ {bad} 个字段对不上。**先别把新源设为主源**——")
        print("  差一个数量级通常是字段位置读错了，检查 data_engineer/scripts/providers/<源>.py")
        print("  的 FIELDS 映射，再跑一次这个脚本。")
        return 1
    print("✓ 全部一致。可以按 config/datasources.yaml 的顺序放心用。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
