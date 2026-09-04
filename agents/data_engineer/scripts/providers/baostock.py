"""Baostock-backed index daily bars."""
from __future__ import annotations

import contextlib
import io


PREFIX = {"000001": "sh", "399001": "sz", "399006": "sz", "000688": "sh"}
FIELDS = "date,open,high,low,close,preclose,volume,amount,pctChg"


def index_daily(code: str, start_date: str, end_date: str):
    """Return one index's unadjusted daily bars in the pipeline column contract."""
    import baostock as bs
    import pandas as pd

    symbol = f"{PREFIX[code]}.{code}"
    with contextlib.redirect_stdout(io.StringIO()):
        login = bs.login()
    if login.error_code != "0":
        raise RuntimeError(f"baostock login failed: {login.error_code} {login.error_msg}")
    try:
        result = bs.query_history_k_data_plus(
            symbol,
            FIELDS,
            start_date=start_date,
            end_date=end_date,
            frequency="d",
            adjustflag="3",
        )
        if result.error_code != "0":
            raise RuntimeError(
                f"baostock query failed for {symbol}: {result.error_code} {result.error_msg}"
            )
        rows = []
        while result.next():
            rows.append(result.get_row_data())
    finally:
        with contextlib.redirect_stdout(io.StringIO()):
            bs.logout()

    frame = pd.DataFrame(rows, columns=result.fields)
    if frame.empty:
        raise RuntimeError(f"baostock returned no daily bars for {symbol}")
    for column in ("open", "high", "low", "close", "preclose", "volume", "amount", "pctChg"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["日期"] = pd.to_datetime(frame["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    frame["振幅"] = ((frame["high"] - frame["low"]) / frame["preclose"] * 100).round(2)
    frame = frame.rename(columns={
        "open": "开盘", "close": "收盘", "high": "最高", "low": "最低",
        "volume": "成交量", "amount": "成交额", "pctChg": "涨跌幅",
    })
    return frame[["日期", "开盘", "收盘", "最高", "最低", "成交量", "成交额", "振幅", "涨跌幅"]]
