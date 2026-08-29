"""派生指标测试。这些是全仓库最该有测试的地方——
因为它们是"唯一答案"型的计算，错了整份报告都会跟着错。
"""
from __future__ import annotations

from scripts.clean import derive


def _snap(sh_amount, sz_amount, sh_chg=10.0, sz_chg=10.0):
    return [
        {"code": "000001", "name": "上证指数", "amount": sh_amount, "amount_chg_pct": sh_chg},
        {"code": "399001", "name": "深证成指", "amount": sz_amount, "amount_chg_pct": sz_chg},
        # 创业板与科创50 的成交额已包含在上面两个市场里，绝不能再加一遍
        {"code": "399006", "name": "创业板指", "amount": 3.0e11, "amount_chg_pct": 5.0},
        {"code": "000688", "name": "科创50", "amount": 5.8e10, "amount_chg_pct": 5.0},
    ]


def test_two_market_amount_does_not_double_count():
    """两市成交额 = 上证 + 深成，不含创业板与科创板。"""
    out = derive.two_market_amount(_snap(5.0e11, 6.0e11))
    assert out["total"] == 1.1e12, "创业板/科创50 被重复计入了"
    assert out["total_yi"] == 11000.0


def test_two_market_amount_computes_change():
    """较昨日增减必须由涨跌幅反推，而不是拍脑袋。"""
    out = derive.two_market_amount(_snap(5.5e11, 5.5e11, sh_chg=10.0, sz_chg=10.0))
    # 今日 1.1 万亿，昨日 = 1.1e12 / 1.1 = 1.0e12
    assert round(out["prev_total_yi"]) == 10000
    assert round(out["chg_pct"]) == 10


def test_two_market_amount_missing_index_is_honest():
    """缺指数时返回 None 并说明，不许猜一个数出来。"""
    out = derive.two_market_amount([{"code": "000001", "amount": 1e11}])
    assert out["total"] is None
    assert "缺" in out["note"]


def test_relative_strength():
    assert derive.relative_strength(5.10, 0.74) == 4.36
    assert derive.relative_strength(-3.75, 0.74) == -4.49


def test_position_vs_key_levels():
    out = derive.position_vs_key_levels(
        {"close": 14.62, "ma5": 13.42, "ma10": 12.88, "ma20": 12.10,
         "high_20d": 14.71, "low_20d": 11.20}
    )
    assert out["vs_ma5"] == 8.94
    assert out["drawdown_from_20d_high"] == -0.61


def test_sanity_check_flags_non_trading_day():
    ds = {"blocks": {"calendar": {"inline": {"as_of": "2026-08-29", "is_trading_day": False}},
                     "breadth": {"inline": {"broken_board_rate": 30.0, "promotion_rate": 40.0}}}}
    flags = derive.sanity_check(ds)
    assert any(f.level == "error" and f.block == "calendar" for f in flags), \
        "非交易日必须报 error，否则会出一份没有数据支撑的复盘"
