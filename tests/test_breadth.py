"""涨停生态计算测试：炸板率与连板晋级率。

这两个数是情绪阶段判断的核心依据，必须由明细算出且可复现。
所有 akshare 调用都用 mock，不访问网络。
"""
from __future__ import annotations

import pandas as pd
import pytest

from agents.data_engineer.scripts.fetch import breadth


def _pool(codes, boards=None):
    df = pd.DataFrame({"代码": codes, "名称": [f"票{c}" for c in codes]})
    if boards:
        df["连板数"] = boards
        df["所属行业"] = ["示例"] * len(codes)
        df["封板资金"] = [1e8] * len(codes)
        df["首次封板时间"] = ["093000"] * len(codes)
        df["炸板次数"] = [0] * len(codes)
    return df


@pytest.fixture
def fake_calls(monkeypatch):
    data = {
        "stock_market_activity_legu": pd.DataFrame(
            {"item": ["上涨", "下跌", "平盘", "涨停", "跌停", "停牌"],
             "value": [3104, 1892, 121, 68, 9, 14]}),
        "stock_zt_pool_em": _pool(["001", "002", "003", "004"], [1, 1, 2, 3]),
        "stock_zt_pool_zbgc_em": _pool(["005", "006"]),
        "stock_zt_pool_dtgc_em": _pool(["007"]),
        "stock_zt_pool_previous_em": _pool(["001", "002", "008", "009"]),
    }

    def fake_try_call(name, params=None, cache=True):
        return (data[name].copy(), None) if name in data else (None, "not mocked")

    monkeypatch.setattr(breadth, "try_call", fake_try_call)
    return data


def test_broken_board_rate(fake_calls):
    """炸板率 = 炸板 / (涨停 + 炸板) = 2 / (4 + 2) = 33.33%"""
    block, _ = breadth.fetch_breadth("2026-08-28", "2026-08-27")
    assert block.inline["broken_board_rate"] == 33.33


def test_promotion_rate(fake_calls):
    """晋级率 = 昨日涨停中今日仍涨停 / 昨日涨停 = 2 / 4 = 50%"""
    block, _ = breadth.fetch_breadth("2026-08-28", "2026-08-27")
    assert block.inline["promotion_rate"] == 50.0


def test_ladder_and_highest_board(fake_calls):
    block, _ = breadth.fetch_breadth("2026-08-28", "2026-08-27")
    assert block.inline["ladder"] == {"1板": 2, "2板": 1, "3板": 1}
    assert block.inline["highest_board"] == 3


def test_missing_pool_is_flagged_not_faked(monkeypatch):
    """涨停池取不到时，炸板率必须是 None + flag，绝不能编一个数。"""
    monkeypatch.setattr(breadth, "try_call", lambda name, params=None, cache=True: (None, "boom"))
    block, pools = breadth.fetch_breadth("2026-08-28", "2026-08-27")
    assert block.inline["broken_board_rate"] is None
    assert block.inline["promotion_rate"] is None
    assert any(f.level == "warning" for f in block.flags)
    assert pools == {}
