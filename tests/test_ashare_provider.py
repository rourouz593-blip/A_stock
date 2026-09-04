from __future__ import annotations

import pandas as pd
import pytest

from agents.data_engineer.scripts.providers import ashare


def test_index_daily_normalizes_sina_and_computes_changes(monkeypatch) -> None:
    payload = [
        {"day": "2026-09-02", "open": "100", "close": "101", "high": "102",
         "low": "99", "volume": "10"},
        {"day": "2026-09-03", "open": "101", "close": "102", "high": "103",
         "low": "100", "volume": "20"},
    ]
    monkeypatch.setattr(ashare, "_json", lambda *args: payload)
    frame = ashare.index_daily("000688", "2026-09-02", "2026-09-03")
    assert frame["日期"].tolist() == ["2026-09-02", "2026-09-03"]
    assert frame.iloc[-1]["涨跌幅"] == pytest.approx(0.99)
    assert pd.isna(frame.iloc[-1]["成交额"])


def test_index_daily_falls_back_to_tencent(monkeypatch) -> None:
    monkeypatch.setattr(ashare, "_sina_daily",
                        lambda *args: (_ for _ in ()).throw(RuntimeError("Sina down")))
    monkeypatch.setattr(ashare, "_json", lambda *args: {"data": {"sh000688": {"day": [
        ["2026-09-02", "100", "101", "102", "99", "10"],
        ["2026-09-03", "101", "102", "103", "100", "20"],
    ]}}})
    frame = ashare.index_daily("000688", "2026-09-02", "2026-09-03")
    assert len(frame) == 2
    assert frame.iloc[-1]["成交量"] == 2000


def test_index_intraday_filters_date_and_keeps_unknown_amount(monkeypatch) -> None:
    payload = {"data": {"sh000688": {"m1": [
        ["202609031500", "100", "101", "102", "99", "10", {}, "0.1"],
        ["202609040930", "101", "102", "103", "100", "20", {}, "0.2"],
    ]}}}
    monkeypatch.setattr(ashare, "_json", lambda *args: payload)
    frame = ashare.index_intraday("000688", "2026-09-04")
    assert frame["时间"].tolist() == ["2026-09-04 09:30:00"]
    assert frame.iloc[0]["收盘"] == 102
    assert frame.iloc[0]["成交量"] == 2000
    assert pd.isna(frame.iloc[0]["成交额"])


def test_stock_daily_requires_qfq_and_enriches_latest_quote(monkeypatch) -> None:
    quote = [""] * 39
    quote[30], quote[37], quote[38] = "20260903150000", "12345.6", "2.5"
    payload = {"data": {"sh603005": {
        "qfqday": [
            ["2026-09-02", "100", "101", "102", "99", "10"],
            ["2026-09-03", "101", "102", "103", "100", "20"],
        ],
        "qt": {"sh603005": quote},
    }}}
    monkeypatch.setattr(ashare, "_json", lambda *args: payload)
    frame = ashare.stock_daily("603005", "2026-09-02", "2026-09-03")
    assert frame.iloc[-1]["成交量"] == 20, "个股成交量沿用原 qfq 口径，不乘 100"
    assert frame.iloc[-1]["成交额"] == pytest.approx(12345.6 * 1e4)
    assert frame.iloc[-1]["换手率"] == pytest.approx(2.5)


def test_stock_daily_rejects_unadjusted_fallback(monkeypatch) -> None:
    payload = {"data": {"sz002804": {"day": [
        ["2026-09-03", "10", "11", "12", "9", "20"],
    ]}}}
    monkeypatch.setattr(ashare, "_json", lambda *args: payload)
    with pytest.raises(RuntimeError, match="no qfq"):
        ashare.stock_daily("002804", "2026-09-02", "2026-09-03")
