"""持仓历史流水。让"行为自检"从主观印象变成可判定的事实。

## 为什么需要它

`config/positions.yaml` 只记录**此刻**的持仓。但章节④的七条行为自检里，
有三条本质上是"**和过去比**"：

- 亏损补仓 —— 需要知道加仓那天是不是已经浮亏
- 卖飞后追回 —— 需要知道这只票曾经被清掉过
- 短线失败后临时改成长线 —— 需要知道 thesis 昨天写的是什么

只有一份当前快照的话，这三条只能靠人回忆，而**人恰恰会在这三件事上骗自己**。
所以每次持仓变化或每次复盘，都往这里追加一条快照。

## 格式

`memory/positions_history.jsonl`，一行一条 JSON，只增不改：

    {"ts":"2026-08-30T15:40:00+08:00","source":"run","as_of":"2026-08-30",
     "code":"600519.SH","cost":12.8,"shares":2000,"price":14.62,"pnl_pct":14.2,
     "thesis":"...","stop_level":11.5,"module":"打板"}

只增不改是刻意的：**改过的历史就不是历史了。**
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
HISTORY = REPO_ROOT / "memory" / "positions_history.jsonl"
TRACKED = ("cost", "shares", "price", "pnl_pct", "thesis", "stop_level", "module", "sector")


def append_snapshot(records: list[dict], source: str, as_of: str | None = None) -> int:
    """追加一批持仓快照。source: import（改了持仓）/ run（跑了一次复盘）。"""
    if not records:
        return 0
    ts = datetime.now().astimezone().isoformat(timespec="seconds")
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY.open("a", encoding="utf-8") as f:
        for r in records:
            row: dict[str, Any] = {"ts": ts, "source": source, "as_of": as_of,
                                   "code": r.get("code")}
            row.update({k: r.get(k) for k in TRACKED if r.get(k) is not None})
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return len(records)


def load_history() -> list[dict]:
    if not HISTORY.is_file():
        return []
    out = []
    for line in HISTORY.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue          # 坏行跳过，不要让一条脏数据毁掉整个复盘
    return out


def _last_differing(past: list[dict], field: str, current) -> dict | None:
    """在窗口内往回找**第一条与当前值不同**的记录，那就是"变化发生前"的状态。

    为什么不能只跟上一条比：导入持仓时会写一条快照，跑复盘时又写一条，
    只跟上一条比等于跟自己比，变化会被自己抹掉。
    """
    for h in reversed(past):
        v = h.get(field)
        if v is None:
            continue
        if isinstance(v, (int, float)) and isinstance(current, (int, float)):
            if abs(float(v) - float(current)) > 1e-9:
                return h
        elif v != current:
            return h
    return None


def behavior_signals(current: list[dict], history: list[dict] | None = None,
                     lookback: int = 20) -> list[dict]:
    """把历史与当前持仓比对，产出**事实层面**的行为信号。

    只出"发生了什么"，不出"你错了"——定性是 position-advisor 的活。
    同样是加仓，主升期加在强势票上和浮亏时摊成本，是两件完全不同的事，
    代码分不出来，人和模型能。

    `lookback`：每只票只看最近 N 条记录。变化超出窗口就自然淡出，
    否则一次改动会被报到天荒地老。
    """
    history = load_history() if history is None else history
    by_code: dict[str, list[dict]] = {}
    for h in history:
        by_code.setdefault(h.get("code"), []).append(h)

    signals = []
    for pos in current:
        code = pos.get("code")
        past = (by_code.get(code) or [])[-lookback:]
        if not past:
            continue

        def when(h: dict) -> str:
            return h.get("as_of") or (h.get("ts") or "")[:10]

        # ① 加仓：数量变多。附上"加仓前"那一刻的浮亏状态
        prev = _last_differing(past, "shares", pos.get("shares"))
        if prev and pos.get("shares", 0) > (prev.get("shares") or 0):
            signals.append({
                "type": "加仓", "code": code, "changed_since": when(prev),
                "detail": f"数量 {prev['shares']} → {pos['shares']}",
                "was_losing": (prev.get("pnl_pct") is not None and prev["pnl_pct"] < 0),
                "prev_pnl_pct": prev.get("pnl_pct"),
                "hint": "若加仓前已浮亏，对应行为自检第 3 条「亏损补仓」",
            })

        # ② 清仓后又买回
        if any(h.get("shares") == 0 for h in past) and pos.get("shares", 0) > 0:
            sold = [h for h in past if h.get("shares") == 0]
            signals.append({
                "type": "清仓后买回", "code": code, "changed_since": when(sold[-1]),
                "detail": f"曾清仓，现持有 {pos.get('shares')} 股",
                "sold_around": sold[-1].get("price"), "now_price": pos.get("price"),
                "hint": "对应行为自检第 4 条「卖飞后追回」",
            })

        # ③ 买入逻辑被改写
        prev = _last_differing(past, "thesis", pos.get("thesis"))
        if prev and pos.get("thesis"):
            signals.append({
                "type": "买入逻辑被改写", "code": code, "changed_since": when(prev),
                "detail": f"原：{str(prev['thesis'])[:40]}　→　现：{str(pos['thesis'])[:40]}",
                "was_losing": (prev.get("pnl_pct") is not None and prev["pnl_pct"] < 0),
                "hint": "若改写发生在浮亏之后，对应行为自检第 7 条「短线失败后改成长线」",
            })

        # ④ 失效位下移 —— 最典型的自我欺骗，止损位一挪，风险控制就名存实亡
        prev = _last_differing(past, "stop_level", pos.get("stop_level"))
        if prev and pos.get("stop_level") and float(pos["stop_level"]) < float(prev["stop_level"]):
            signals.append({
                "type": "失效位下移", "code": code, "changed_since": when(prev),
                "detail": f"失效位 {prev['stop_level']} → {pos['stop_level']}",
                "hint": "失效位应当在买入时定好。往下挪等于取消了止损",
            })

        # ⑤ 交易模块被改
        prev = _last_differing(past, "module", pos.get("module"))
        if prev and pos.get("module"):
            signals.append({
                "type": "交易模块被改", "code": code, "changed_since": when(prev),
                "detail": f"{prev['module']} → {pos['module']}",
                "hint": "打板改成中线，风险敞口的性质就变了",
            })
    return signals
