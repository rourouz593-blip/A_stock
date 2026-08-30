"""持仓历史与行为信号测试。

行为自检里最有价值的三条（亏损补仓、卖飞追回、短线改长线）本质上是"和过去比"，
而人恰恰会在这三件事上骗自己。所以证据必须来自只增不改的流水，不能靠回忆。
"""
from __future__ import annotations

import json

from scripts.history import behavior_signals


def _h(code="600519.SH", **kw):
    base = {"code": code, "ts": "2026-08-28T15:40:00+08:00", "as_of": "2026-08-28",
            "source": "run", "cost": 12.8, "shares": 1000, "price": 12.5, "pnl_pct": -2.3}
    base.update(kw)
    return base


def test_adding_to_a_losing_position_is_flagged():
    sig = behavior_signals([{"code": "600519.SH", "shares": 2000, "cost": 12.0}],
                           history=[_h(shares=1000, pnl_pct=-2.3)])
    add = [s for s in sig if s["type"] == "加仓"]
    assert add and add[0]["was_losing"] is True
    assert add[0]["prev_pnl_pct"] == -2.3


def test_adding_to_a_winning_position_is_flagged_but_not_as_losing():
    """加仓本身不是错——主升期加强势票是对的。代码只陈述事实，不定性。"""
    sig = behavior_signals([{"code": "600519.SH", "shares": 2000}],
                           history=[_h(shares=1000, pnl_pct=8.0)])
    add = [s for s in sig if s["type"] == "加仓"]
    assert add and add[0]["was_losing"] is False


def test_comparison_survives_a_duplicate_snapshot():
    """导入持仓写一条、跑复盘又写一条——只跟上一条比等于跟自己比，变化会被抹掉。

    这是实测踩到的坑：必须往回找**第一条与当前值不同**的记录。
    """
    hist = [_h(shares=1000, pnl_pct=-2.3),
            _h(shares=2000, ts="2026-08-30T10:00:00+08:00", as_of="2026-08-30")]
    sig = behavior_signals([{"code": "600519.SH", "shares": 2000}], history=hist)
    add = [s for s in sig if s["type"] == "加仓"]
    assert add, "重复快照把加仓信号吃掉了"
    assert add[0]["detail"] == "数量 1000 → 2000"


def test_thesis_rewrite_is_flagged():
    sig = behavior_signals(
        [{"code": "600519.SH", "shares": 1000, "thesis": "公司基本面扎实，长期持有"}],
        history=[_h(thesis="题材启动第二天打板做龙头", pnl_pct=-8.0)])
    rw = [s for s in sig if s["type"] == "买入逻辑被改写"]
    assert rw and rw[0]["was_losing"] is True, "浮亏后改写逻辑是第 7 条自检的核心证据"


def test_stop_level_moved_down_is_flagged():
    sig = behavior_signals([{"code": "600519.SH", "shares": 1000, "stop_level": 10.0}],
                           history=[_h(stop_level=11.5)])
    assert any(s["type"] == "失效位下移" for s in sig)


def test_stop_level_moved_up_is_not_flagged():
    """上移失效位是保护利润，是对的，不该报警。"""
    sig = behavior_signals([{"code": "600519.SH", "shares": 1000, "stop_level": 13.0}],
                           history=[_h(stop_level=11.5)])
    assert not any(s["type"] == "失效位下移" for s in sig)


def test_sold_then_bought_back_is_flagged():
    sig = behavior_signals([{"code": "600519.SH", "shares": 1000, "price": 15.0}],
                           history=[_h(shares=1000), _h(shares=0, price=13.0)])
    back = [s for s in sig if s["type"] == "清仓后买回"]
    assert back and back[0]["sold_around"] == 13.0


def test_no_history_means_no_signals():
    """第一次跑没有历史，不该凭空造出信号。"""
    assert behavior_signals([{"code": "600519.SH", "shares": 1000}], history=[]) == []


def test_lookback_window_lets_old_changes_fade():
    """一次改动不该被报到天荒地老。"""
    old = [_h(shares=1000)] + [_h(shares=2000, as_of=f"2026-09-{d:02d}") for d in range(1, 25)]
    sig = behavior_signals([{"code": "600519.SH", "shares": 2000}], history=old, lookback=5)
    assert not any(s["type"] == "加仓" for s in sig)


def test_append_and_load_roundtrip(tmp_path, monkeypatch):
    import scripts.history as H

    monkeypatch.setattr(H, "HISTORY", tmp_path / "h.jsonl")
    n = H.append_snapshot([{"code": "600519.SH", "cost": 12.8, "shares": 100,
                            "thesis": "理由"}], source="import", as_of="2026-08-30")
    assert n == 1
    rows = H.load_history()
    assert rows[0]["code"] == "600519.SH" and rows[0]["source"] == "import"


def test_corrupt_line_does_not_break_loading(tmp_path, monkeypatch):
    """一条脏数据不该毁掉整个复盘。"""
    import scripts.history as H

    f = tmp_path / "h.jsonl"
    f.write_text(json.dumps({"code": "A", "shares": 1}) + "\n{坏行}\n"
                 + json.dumps({"code": "B", "shares": 2}) + "\n", encoding="utf-8")
    monkeypatch.setattr(H, "HISTORY", f)
    assert [r["code"] for r in H.load_history()] == ["A", "B"]
