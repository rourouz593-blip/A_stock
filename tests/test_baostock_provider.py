from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from agents.data_engineer.scripts.providers import baostock


class Result:
    error_code = "0"
    error_msg = "success"
    fields = baostock.FIELDS.split(",")

    def __init__(self):
        self.rows = iter([
            ["2026-09-03", "100", "102", "99", "101", "100", "10", "1000", "1"],
        ])
        self.row = None

    def next(self):
        self.row = next(self.rows, None)
        return self.row is not None

    def get_row_data(self):
        return self.row


def test_index_daily_normalizes_baostock_response(monkeypatch) -> None:
    seen = {}
    fake = SimpleNamespace(
        login=lambda: SimpleNamespace(error_code="0", error_msg="success"),
        logout=lambda: None,
        query_history_k_data_plus=lambda symbol, fields, **kwargs:
            (seen.update(symbol=symbol, fields=fields, **kwargs), Result())[1],
    )
    monkeypatch.setitem(sys.modules, "baostock", fake)
    frame = baostock.index_daily("000001", "2026-09-01", "2026-09-03")
    assert seen["symbol"] == "sh.000001"
    assert seen["frequency"] == "d" and seen["adjustflag"] == "3"
    assert frame.iloc[0]["成交额"] == pytest.approx(1000)
    assert frame.iloc[0]["振幅"] == pytest.approx(3.0)
