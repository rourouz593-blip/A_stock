#!/usr/bin/env python3
"""把从持仓截图里读出来的数据合并进 config/positions.yaml。

## 怎么用（coding agent 的标准流程）

1. 学生上传券商 App 的持仓截图
2. **你（有视觉能力的 agent）看图**，按 `skills/positions-import/SKILL.md` 抽出字段
3. 把抽出的 JSON 喂给本工具**预览**：

       python tools/import_positions.py --json '{"positions":[...]}'

4. 工具会做算术自检 + 展示 diff。确认无误后加 `--apply` 落盘
5. 然后 `python tools/astock.py review --mode positions`

## 为什么不让工具自己去读图

因为**看图是模型的能力，校验是代码的职责**。
模型可能把 1,200 股看成 1200 股（对）或 12,00 股（错），
所以本工具不信任任何一个读出来的数字，而是用两条恒等式反过来验：

    shares × price  ≈ market_value
    (price − cost) × shares ≈ pnl

截图里这四个数是券商自己算好的，**互相能对上才说明没读错**。
对不上就打回去重看，绝不带着错数字往下跑——
成本价读错一位，章节⑦的单笔风险和 0.5% 判断就全错了。

## 人写的字段不会被截图覆盖

`thesis`（买入逻辑）、`module`（交易模块）、`sector`、`stop_level`（失效位）
截图里没有，而它们恰恰是章节④最重要的输入。
本工具按 `code` 匹配，**保留旧文件里的这些字段**，只更新成本与数量。
新出现的标的会被明确列出来，提示学生补写买入逻辑。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

from _common import REPO_ROOT, emit, fail

POSITIONS = REPO_ROOT / "config" / "positions.yaml"
EXAMPLE = REPO_ROOT / "config" / "positions.example.yaml"
HUMAN_FIELDS = ("thesis", "module", "sector", "stop_level", "buy_date")
CODE_RE = re.compile(r"^\d{6}$")


def suffixed(code: str) -> str:
    code = str(code).strip().upper()
    if "." in code:
        return code
    if not CODE_RE.match(code):
        fail("BAD_CODE", f"代码格式不对: {code}", expected="六位数字，如 600519")
    if code.startswith(("60", "68", "9", "5")):
        return f"{code}.SH"
    if code.startswith(("00", "30", "20", "1")):
        return f"{code}.SZ"
    if code.startswith(("8", "4")):
        return f"{code}.BJ"
    return f"{code}.SZ"


def _num(v, field: str, code: str) -> float:
    """把 '1,200' / '12.80元' 这类带装饰的数字转成 float。"""
    if v is None:
        fail("MISSING_FIELD", f"{code} 缺字段 {field}")
    try:
        return float(re.sub(r"[,，\s元股%]", "", str(v)))
    except ValueError:
        fail("BAD_NUMBER", f"{code} 的 {field} 不是数字: {v!r}")


def check_arithmetic(p: dict) -> list[str]:
    """用券商自己算好的市值与盈亏，反验读出来的成本与数量。

    这是整个流程里最重要的一道闸——OCR 错一位，这两条恒等式立刻不成立。
    """
    code = p["code"]
    issues: list[str] = []
    shares, cost = p["shares"], p["cost"]
    price, mv, pnl = p.get("price"), p.get("market_value"), p.get("pnl")

    if price and mv:
        calc = shares * price
        if abs(calc - mv) > max(1.0, abs(mv) * 0.01):
            issues.append(
                f"{code}: 数量×现价 = {shares}×{price} = {calc:,.2f}，"
                f"但截图市值是 {mv:,.2f}（差 {calc - mv:,.2f}）"
                f" → 多半是数量或现价读错了")
    if price and pnl is not None:
        calc = (price - cost) * shares
        if abs(calc - pnl) > max(1.0, abs(pnl) * 0.02):
            issues.append(
                f"{code}: (现价−成本)×数量 = ({price}−{cost})×{shares} = {calc:,.2f}，"
                f"但截图盈亏是 {pnl:,.2f}（差 {calc - pnl:,.2f}）"
                f" → 多半是成本价读错了（注意区分「摊薄成本」与「持仓成本」）")
    if not price or (mv is None and pnl is None):
        issues.append(
            f"{code}: 截图里没读到现价/市值/盈亏，**无法做算术自检**。"
            f"请回去补读这几个数，否则成本与数量没有任何东西能验证它们")
    return issues


def load_yaml(p: Path) -> dict:
    import yaml

    if not p.is_file():
        return {"version": 1, "positions": []}
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {"version": 1, "positions": []}


def normalize(raw: dict) -> list[dict]:
    out = []
    for i, item in enumerate(raw.get("positions") or [], 1):
        code = suffixed(item.get("code") or fail("MISSING_CODE", f"第 {i} 条没有 code"))
        rec = {
            "code": code,
            "name": (item.get("name") or "").strip() or None,
            "cost": round(_num(item.get("cost"), "cost", code), 4),
            "shares": int(_num(item.get("shares"), "shares", code)),
        }
        for k in ("price", "market_value", "pnl"):
            if item.get(k) is not None:
                rec[k] = round(_num(item.get(k), k, code), 4)
        if rec["shares"] <= 0 or rec["cost"] <= 0:
            fail("BAD_VALUE", f"{code} 的 cost/shares 必须为正数")
        out.append(rec)
    if not out:
        fail("EMPTY", "没有解析出任何持仓", hint="截图是不是空仓，或者金额被隐藏了？")
    return out


def merge(new: list[dict], old_doc: dict) -> tuple[list[dict], dict]:
    """按 code 合并：截图管数字，旧文件管人写的字段。

    匹配时**以六位数字为准**，而不是带后缀的全码：
    截图里通常只有六位，后缀是本工具推断出来的，可能与旧文件里写的不一致
    （比如推成 .SH 但旧文件是 .SZ）。一旦不匹配，thesis 就会被当成新标的丢掉——
    那是最不能丢的字段。所以：**旧文件里已有的后缀优先于推断**。
    """
    old = {p["code"]: p for p in (old_doc.get("positions") or [])}
    by_digits = {c.split(".")[0]: c for c in old}
    merged, added, changed, removed = [], [], [], []

    for n in new:
        code = n["code"]
        digits = code.split(".")[0]
        if code not in old and digits in by_digits:
            code = by_digits[digits]          # 沿用旧文件里的后缀
            n["code"] = code
        prev = old.get(code)
        rec = {"code": code, "name": n["name"] or (prev or {}).get("name"),
               "cost": n["cost"], "shares": n["shares"]}
        if prev:
            for f in HUMAN_FIELDS:                # ← 人写的字段原样保留
                if prev.get(f) is not None:
                    rec[f] = prev[f]
            diffs = []
            if abs(float(prev.get("cost", 0)) - n["cost"]) > 1e-6:
                diffs.append(f"成本 {prev.get('cost')} → {n['cost']}")
            if int(prev.get("shares", 0)) != n["shares"]:
                diffs.append(f"数量 {prev.get('shares')} → {n['shares']}")
            if diffs:
                changed.append((code, diffs))
        else:
            rec.setdefault("buy_date", date.today().isoformat())
            rec.setdefault("module", None)
            rec.setdefault("sector", None)
            rec.setdefault("thesis", None)
            rec.setdefault("stop_level", None)
            added.append(code)
        merged.append(rec)

    removed = [c for c in old if c not in {n["code"] for n in new}]
    return merged, {"added": added, "changed": changed, "removed": removed}


def dump_yaml(positions: list[dict]) -> str:
    """手写序列化而不是 yaml.dump——为了保住注释与字段顺序，让文件仍然可读可手改。"""
    lines = [
        "# 我的持仓。由 tools/import_positions.py 从截图合并生成，也可以直接手改。",
        "#",
        "# 截图只能提供 code / name / cost / shares 四个字段。",
        "# thesis（买入逻辑）、module（交易模块）、sector（题材）、stop_level（失效位）",
        "# 必须由你自己写——章节④要回答的第一个问题就是「买入逻辑是否仍成立」，",
        "# 没写下来，第二天你只会临时编一个理由说服自己继续拿着。",
        "#",
        "# 账户总资产不写在这里，写在 .env 的 ASTOCK_ACCOUNT_EQUITY。",
        "version: 1",
        "",
        "positions:",
    ]
    for p in positions:
        lines.append(f'  - code: "{p["code"]}"')
        if p.get("name"):
            lines.append(f'    name: "{p["name"]}"')
        lines.append(f'    cost: {p["cost"]:g}')
        lines.append(f'    shares: {p["shares"]}')
        for f, comment in (("buy_date", ""), ("module", "  # 打板 / 低吸 / 趋势 / 套利 / 中线"),
                           ("sector", "  # 你认为它属于哪个题材（章节⑦按这个聚合同题材风险）"),
                           ("thesis", "  # 买入逻辑，越具体越好"),
                           ("stop_level", "  # 失效位：破了就承认判断错了")):
            v = p.get(f)
            if v is None:
                lines.append(f'    {f}: ~{comment or "  # ← 待填"}')
            elif isinstance(v, (int, float)):
                lines.append(f"    {f}: {v:g}")
            else:
                lines.append(f'    {f}: "{v}"')
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--json", help="从截图读出来的 JSON 字符串")
    g.add_argument("--json-file", help="同上，但从文件读")
    g.add_argument("--stdin", action="store_true", help="同上，但从标准输入读")
    ap.add_argument("--apply", action="store_true",
                    help="真正写入 config/positions.yaml（默认只预览）")
    ap.add_argument("--allow-unverified", action="store_true",
                    help="跳过算术自检。**只在券商 App 确实不显示市值/盈亏时才用**")
    args = ap.parse_args()

    raw_text = (args.json if args.json
                else sys.stdin.read() if args.stdin
                else Path(args.json_file).read_text(encoding="utf-8"))
    try:
        raw = json.loads(raw_text)
    except json.JSONDecodeError as e:
        fail("BAD_JSON", f"输入不是合法 JSON: {e}")

    new = normalize(raw)

    # ── 算术自检 ────────────────────────────────────────────────
    issues = [msg for p in new for msg in check_arithmetic(p)]
    if issues and not args.allow_unverified:
        print("✗ 算术自检没通过，说明截图里的数字读错了：\n", file=sys.stderr)
        for m in issues:
            print(f"  · {m}", file=sys.stderr)
        print("\n请重新看图核对这几个数字后再来一次。", file=sys.stderr)
        print("（确认券商 App 真的不显示市值/盈亏，才用 --allow-unverified 跳过）",
              file=sys.stderr)
        sys.exit(1)

    old_doc = load_yaml(POSITIONS)
    merged, delta = merge(new, old_doc)
    content = dump_yaml(merged)

    need_thesis = [p["code"] for p in merged if not p.get("thesis")]
    equity = raw.get("account_equity")

    if not args.apply:
        print("── 预览（还没写入）" + "─" * 40)
        print(content)
        print("── 变化 " + "─" * 50)
        for c in delta["added"]:
            print(f"  + 新增 {c}")
        for c, d in delta["changed"]:
            print(f"  ~ 更新 {c}: {'; '.join(d)}")
        for c in delta["removed"]:
            print(f"  - 移除 {c}（截图里没有了——已清仓？）")
        if not any(delta.values()):
            print("  （与现有 positions.yaml 一致，无变化）")
        if need_thesis:
            print(f"\n  ⚠ 这几只还没有买入逻辑：{'、'.join(need_thesis)}")
            print("    章节④的第一个问题就是「买入逻辑是否仍成立」，请补上再跑复盘。")
        if equity:
            print(f"\n  账户总资产 {float(equity):,.0f} 元 → 请写进 .env："
                  f"\n    ASTOCK_ACCOUNT_EQUITY={float(equity):g}")
        print("\n确认无误后加 --apply 落盘。")
        return

    if POSITIONS.is_file():
        bak = POSITIONS.with_suffix(".yaml.bak")
        bak.write_text(POSITIONS.read_text(encoding="utf-8"), encoding="utf-8")
    POSITIONS.parent.mkdir(parents=True, exist_ok=True)
    POSITIONS.write_text(content, encoding="utf-8")

    emit({
        "ok": True,
        "written": "config/positions.yaml",
        "backup": "config/positions.yaml.bak" if (POSITIONS.with_suffix(".yaml.bak")).is_file() else None,
        "count": len(merged),
        "added": delta["added"],
        "changed": [c for c, _ in delta["changed"]],
        "removed": delta["removed"],
        "need_thesis": need_thesis,
        "account_equity_hint": (f"ASTOCK_ACCOUNT_EQUITY={float(equity):g}" if equity else None),
        "next": "python tools/astock.py review --mode positions",
    })


if __name__ == "__main__":
    main()
