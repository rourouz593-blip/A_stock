"""AKShare 行情适配器测试；所有上游响应均为 mock，不访问网络。"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.contracts import FetchRequest  # noqa: E402
from scripts.fetch import market_data  # noqa: E402


def _valid_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "日期": "2026-08-27",
                "股票代码": "600552",
                "开盘": 17.66,
                "收盘": 18.09,
                "最高": 18.35,
                "最低": 17.40,
                "成交量": 531223,
                "成交额": 954069311.0,
                "振幅": 5.44,
                "涨跌幅": 3.67,
                "涨跌额": 0.64,
                "换手率": 5.62,
            }
        ]
    )


class _FakeAK:
    def __init__(self, frame: pd.DataFrame) -> None:
        self.frame = frame
        self.calls: list[dict] = []

    def stock_zh_a_hist(self, **kwargs):
        self.calls.append(kwargs)
        return self.frame.copy()


class _FallbackAK(_FakeAK):
    def stock_zh_a_hist_tx(self, **kwargs):
        return pd.DataFrame()


def test_fetch_ohlcv_normalizes_fields_and_records_provenance(monkeypatch) -> None:
    fake = _FakeAK(_valid_frame())
    monkeypatch.setattr(market_data, "_load_akshare", lambda: fake)

    block = market_data.fetch_ohlcv(
        FetchRequest(
            codes=["600552.SH"],
            start="2026-08-27",
            end="2026-08-28",
            extra={"timeout": 7},
        ),
        freq="daily",
        adjust="none",
    )

    assert block.status == "ok"
    assert block.rows == 1
    assert block.coverage == {"start": "2026-08-27", "end": "2026-08-27"}
    assert block.inline[0]["code"] == "600552.SH"
    assert block.inline[0]["amount_cny"] == 954069311.0
    assert block.provenance.source == "AKShare.stock_zh_a_hist (Eastmoney)"
    assert block.provenance.params["adjust"] == "none"
    assert fake.calls == [
        {
            "symbol": "600552",
            "period": "daily",
            "start_date": "20260827",
            "end_date": "20260828",
            "adjust": "",
            "timeout": 7.0,
        }
    ]


def test_fetch_ohlcv_empty_response_is_missing(monkeypatch) -> None:
    monkeypatch.setattr(market_data, "_load_akshare", lambda: _FallbackAK(pd.DataFrame()))

    block = market_data.fetch_ohlcv(
        FetchRequest(codes=["600552.SH"], start="2026-08-27", end="2026-08-28"),
        adjust="none",
    )

    assert block.status == "missing"
    assert block.rows == 0
    assert block.inline == []
    assert block.flags[0].level == "error"
    assert "空数据" in block.flags[0].message


def test_fetch_ohlcv_missing_columns_is_missing(monkeypatch) -> None:
    incomplete = _valid_frame().drop(columns=["成交额"])
    monkeypatch.setattr(market_data, "_load_akshare", lambda: _FallbackAK(incomplete))

    block = market_data.fetch_ohlcv(
        FetchRequest(codes=["600552.SH"], start="2026-08-27", end="2026-08-28"),
        adjust="none",
    )

    assert block.status == "missing"
    assert "缺列" in block.flags[0].message
    assert "成交额" in block.flags[0].message


def test_fetch_ohlcv_partial_failure_is_degraded(monkeypatch) -> None:
    class PartialAK(_FallbackAK):
        def stock_zh_a_hist(self, **kwargs):
            return _valid_frame() if kwargs["symbol"] == "600552" else pd.DataFrame()

    monkeypatch.setattr(market_data, "_load_akshare", lambda: PartialAK(_valid_frame()))

    block = market_data.fetch_ohlcv(
        FetchRequest(
            codes=["600552.SH", "600667.SH"],
            start="2026-08-27",
            end="2026-08-28",
        ),
        adjust="none",
    )

    assert block.status == "degraded"
    assert block.rows == 1
    assert "600667.SH" in block.flags[0].message


def test_fetch_ohlcv_uses_tencent_fallback_and_unifies_units(monkeypatch) -> None:
    class TencentAK(_FakeAK):
        def stock_zh_a_hist(self, **kwargs):
            raise ConnectionError("eastmoney unavailable")

        def stock_zh_a_hist_tx(self, **kwargs):
            return pd.DataFrame(
                [
                    {
                        "date": "2026-08-28",
                        "open": 18.07,
                        "close": 17.88,
                        "high": 18.58,
                        "low": 17.83,
                        "volume": 49433300.0,
                        "turnover": 0.0523,
                        "amount": 898414824.0,
                    }
                ]
            )

    monkeypatch.setattr(market_data, "_load_akshare", lambda: TencentAK(_valid_frame()))

    block = market_data.fetch_ohlcv(
        FetchRequest(codes=["600552.SH"], start="2026-08-27", end="2026-08-28"),
        adjust="none",
    )

    assert block.status == "degraded"
    assert block.inline[0]["volume_lots"] == 494333
    assert block.inline[0]["turnover_rate_pct"] == 5.23
    assert block.provenance.source == "AKShare.stock_zh_a_hist_tx (Tencent)"
    assert block.provenance.fallback_from == "AKShare.stock_zh_a_hist (Eastmoney)"
    assert block.provenance.params["source_by_code"] == {"600552.SH": "Tencent"}
